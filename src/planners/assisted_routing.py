"""Routing for Assisted Build: user-placed machines with per-machine recipes."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from core.constants import BASE_MATERIALS, FACTORIO_EAST
from planners.machine_io import (
    ingredient_lane_index,
    machine_io_lanes,
    place_machine_io_block,
    recipe_input_lane_count,
    recipe_ingredient_order,
)
from planners.machine_placer.calculations import (
    entity_accepts_recipe_field,
    machine_entity_for_recipe,
)
from planners.production_planner import RateNode
from planners.stage_connector import (
    BASE_BUS_LENGTH,
    BASE_BUS_X_START,
    BASE_BUS_Y,
    connect_lane_to_lane,
    _dedupe_connection_requests,
    _manhattan_path,
    _needs_splitter_fanout,
    _place_belt,
    _place_splitter,
    place_belt_path,
    stage_lanes_from_machines,
)

INPUT_CELL_ENTITY = "wooden-chest"

logger = logging.getLogger(__name__)


def _is_machine_entity(name: str) -> bool:
    if not name:
        return False
    if "furnace" in name or "assembling-machine" in name:
        return True
    return name in ("chemical-plant", "oil-refinery", "centrifuge")


@dataclass
class PlacedMachine:
    """User-placed machine awaiting or after recipe assignment."""

    id: str
    entity_name: str
    position: tuple[int, int]
    size: tuple[int, int]
    recipe_item: str | None = None
    lanes: dict | None = None
    is_input_cell: bool = False
    input_resource: str | None = None


@dataclass
class AssistedBuildState:
    """Grid, entities, and placed machines for an assisted build session."""

    grid: object
    entities: list = field(default_factory=list)
    machines: list[PlacedMachine] = field(default_factory=list)
    entity_number: int = 1
    recipes_data: dict = field(default_factory=dict)

    def _recipe(self, item: str) -> dict | None:
        return self.recipes_data.get("recipes", {}).get(item)

    def _machine_at(self, machine_id: str) -> PlacedMachine | None:
        for m in self.machines:
            if m.id == machine_id:
                return m
        return None

    def _next_entity_number(self) -> int:
        n = self.entity_number
        self.entity_number = n + 1
        return n

    def place_machine(
        self, entity_name: str, x: int, y: int, size: tuple[int, int]
    ) -> PlacedMachine | None:
        w, h = size
        if self.grid.is_occupied(x, y, w, h):
            logger.warning("Cannot place %s at (%s, %s): occupied", entity_name, x, y)
            return None
        machine = PlacedMachine(
            id=str(uuid.uuid4()),
            entity_name=entity_name,
            position=(x, y),
            size=(w, h),
        )
        entity = {
            "entity_number": self._next_entity_number(),
            "name": entity_name,
            "position": {"x": x, "y": y},
        }
        self.entities.append(entity)
        self.grid.occupy(x, y, entity_name, [w, h])
        self.machines.append(machine)
        return machine

    def place_input_cell(self, x: int, y: int) -> PlacedMachine | None:
        """Place a user-positioned raw-resource input chest (1x1)."""
        machine = self.place_machine(INPUT_CELL_ENTITY, x, y, (1, 1))
        if machine:
            machine.is_input_cell = True
        return machine

    def remove_machine(self, machine_id: str) -> bool:
        return self.remove_machines([machine_id]) > 0

    def remove_machines(self, machine_ids: list[str]) -> int:
        """Remove multiple machines and re-route once."""
        ids = set(machine_ids)
        if not ids:
            return 0
        before = len(self.machines)
        self.machines = [m for m in self.machines if m.id not in ids]
        removed = before - len(self.machines)
        if removed:
            self.full_reroute()
        return removed

    def machines_in_tile_rect(
        self, x0: int, y0: int, x1: int, y1: int
    ) -> list[PlacedMachine]:
        """Machines whose footprint overlaps the inclusive tile rectangle."""
        min_x, max_x = min(x0, x1), max(x0, x1)
        min_y, max_y = min(y0, y1), max(y0, y1)
        found: list[PlacedMachine] = []
        for m in self.machines:
            mx, my = m.position
            w, h = m.size
            if mx + w - 1 >= min_x and mx <= max_x and my + h - 1 >= min_y and my <= max_y:
                found.append(m)
        return found

    def machine_at_tile(self, x: int, y: int) -> PlacedMachine | None:
        for m in self.machines:
            mx, my = m.position
            w, h = m.size
            if mx <= x < mx + w and my <= y < my + h:
                return m
        return None

    def _recipe_valid_for_machine(self, machine: PlacedMachine, recipe_item: str) -> bool:
        recipe = self._recipe(recipe_item)
        if not recipe:
            return False
        expected = machine_entity_for_recipe(recipe_item, recipe)
        if expected == machine.entity_name or recipe.get("machine") == machine.entity_name:
            return True
        if machine.entity_name.startswith("assembling-machine") and (
            recipe.get("machine", "").startswith("assembling-machine")
        ):
            return True
        if "furnace" in machine.entity_name and "furnace" in (recipe.get("machine") or ""):
            return True
        return False

    def assign_recipe(self, machine_id: str, recipe_item: str) -> bool:
        return self.assign_recipes_bulk([machine_id], recipe_item) > 0

    def assign_recipes_bulk(self, machine_ids: list[str], recipe_item: str) -> int:
        """Assign one recipe to many machines, then re-route once."""
        recipe = self._recipe(recipe_item)
        if not recipe:
            logger.warning("Unknown recipe item: %s", recipe_item)
            return 0
        applied = 0
        for mid in machine_ids:
            machine = self._machine_at(mid)
            if not machine or not self._recipe_valid_for_machine(machine, recipe_item):
                continue
            machine.recipe_item = recipe_item
            entity = self._find_machine_entity(machine)
            if entity and entity_accepts_recipe_field(machine.entity_name):
                entity["recipe"] = recipe_item
            applied += 1
        if applied:
            self.full_reroute()
        return applied

    def assign_input_resources_bulk(self, machine_ids: list[str], resource: str) -> int:
        if resource not in BASE_MATERIALS:
            logger.warning("Not a base material: %s", resource)
            return 0
        applied = 0
        for mid in machine_ids:
            machine = self._machine_at(mid)
            if not machine or not machine.is_input_cell:
                continue
            machine.input_resource = resource
            machine.recipe_item = resource
            applied += 1
        if applied:
            self.full_reroute()
        return applied

    def _find_machine_entity(self, machine: PlacedMachine) -> dict | None:
        mx, my = machine.position
        for ent in self.entities:
            if ent.get("name") != machine.entity_name:
                continue
            pos = ent.get("position") or {}
            if int(round(pos.get("x", 0))) == mx and int(round(pos.get("y", 0))) == my:
                return ent
        return None

    def _rebuild_machine_entities(self) -> None:
        """Reset grid and rebuild entity list from placed machines and input cells."""
        self.entities = []
        self.grid.reset()
        self.entity_number = 1
        for m in self.machines:
            mx, my = m.position
            w, h = m.size
            entity = {
                "entity_number": self._next_entity_number(),
                "name": m.entity_name,
                "position": {"x": mx, "y": my},
            }
            self.entities.append(entity)
            self.grid.occupy(mx, my, m.entity_name, [w, h])
            m.lanes = None

    def full_reroute(self) -> None:
        """Clear routing artifacts and rebuild I/O + belts for all assigned recipes."""
        self._rebuild_machine_entities()
        for machine in self.machines:
            if machine.is_input_cell or not machine.recipe_item:
                continue
            self._place_machine_io(machine)
        route_connections(self)
        self._connect_base_buses()

    def _place_machine_io(self, machine: PlacedMachine) -> None:
        recipe = self._recipe(machine.recipe_item)
        mx, my = machine.position
        w, h = machine.size
        lane_count = recipe_input_lane_count(recipe)
        self.entity_number = place_machine_io_block(
            self.grid,
            self.entities,
            self.entity_number,
            mx,
            my,
            w,
            h,
            flow_direction=FACTORIO_EAST,
            recipe=recipe,
            input_lane_count=lane_count,
        )
        machine.lanes = machine_io_lanes(
            mx, my, w, h, FACTORIO_EAST, input_lane_count=lane_count
        )

    def _connect_base_buses(self) -> None:
        nodes = _build_rate_nodes(self.machines, self.recipes_data)
        stage_machines = _build_stage_machines(self.machines)
        if not nodes or not stage_machines:
            return
        input_cells = _input_cells_by_resource(self.machines)
        self.entity_number = connect_assisted_base_materials(
            self.grid,
            self.entities,
            self.entity_number,
            stage_machines,
            nodes,
            input_cells,
        )

    def encode_blueprint_string(self) -> str | None:
        if not self.entities:
            return None
        from core.blueprintEncoder import encode_blueprint

        blueprint = {
            "blueprint": {
                "icons": [{"signal": {"name": "iron-plate", "type": "item"}, "index": 1}],
                "entities": self.entities,
                "item": "blueprint",
                "version": 562949958402048,
            }
        }
        return encode_blueprint(blueprint, self.recipes_data)


def _input_cells_by_resource(
    machines: list[PlacedMachine],
) -> dict[str, list[tuple[int, int]]]:
    cells: dict[str, list[tuple[int, int]]] = {}
    for m in machines:
        if m.is_input_cell and m.input_resource:
            cells.setdefault(m.input_resource, []).append(m.position)
    return cells


def connect_assisted_base_materials(
    grid,
    entities,
    entity_number,
    stage_machines,
    nodes,
    input_cells: dict[str, list[tuple[int, int]]],
):
    """
    Route base materials from user-placed input chests, or fixed bus if none placed.
    """
    base_demands: dict[str, list[tuple[int, int]]] = {}
    for item, node in nodes.items():
        if item not in stage_machines:
            continue
        lanes = stage_lanes_from_machines(
            stage_machines[item], recipe=getattr(node, "recipe", None)
        )
        if not lanes:
            continue
        input_starts = lanes.get("input_starts", [lanes["input_start"]])
        consumer_recipe = getattr(node, "recipe", None) or {}
        for dep in node.dependencies:
            if dep in BASE_MATERIALS:
                lane_idx = ingredient_lane_index(consumer_recipe, dep)
                anchor = input_starts[min(lane_idx, len(input_starts) - 1)]
                base_demands.setdefault(dep, []).append(anchor)

    if not base_demands:
        return entity_number

    auto_bus_index = 0
    for resource in sorted(base_demands.keys()):
        input_points = base_demands[resource]
        sources = input_cells.get(resource, [])

        if sources:
            chest_x, bus_y = sources[0]
            bus_x_start = chest_x + 1
        else:
            bus_y = BASE_BUS_Y + auto_bus_index * 2
            chest_x = BASE_BUS_X_START
            bus_x_start = BASE_BUS_X_START + 1
            entity_number = _place_storage_chest_assisted(
                grid, entities, entity_number, chest_x, bus_y
            )
            auto_bus_index += 1

        for belt_x in range(bus_x_start, bus_x_start + BASE_BUS_LENGTH):
            entity_number = _place_belt(
                grid, entities, entity_number, belt_x, bus_y, FACTORIO_EAST
            )

        for input_start in input_points:
            in_x, in_y = input_start
            drop_x = max(bus_x_start, in_x - 5)
            path = _manhattan_path((drop_x, bus_y), (in_x - 1, in_y))
            entity_number = place_belt_path(grid, entities, entity_number, path)
            logger.info(
                "Routed %s from (%s, %s) to %s",
                resource,
                chest_x,
                bus_y,
                input_start,
            )

    return entity_number


def _place_storage_chest_assisted(grid, entities, entity_number, x, y):
    from planners.stage_connector import _place_storage_chest

    return _place_storage_chest(grid, entities, entity_number, x, y)


def recipes_for_entity(entity_name: str, recipes_data: dict) -> list[str]:
    """Craftable items valid for a placed building type."""
    recipes = recipes_data.get("recipes", {})
    items: list[str] = []
    for item, recipe in recipes.items():
        if recipe.get("type") == "raw":
            continue
        if not recipe.get("ingredients") and "crafting_time" not in recipe:
            continue
        machine = recipe.get("machine")
        if machine == entity_name:
            items.append(item)
        elif entity_name.startswith("assembling-machine") and machine:
            if machine.startswith("assembling-machine"):
                items.append(item)
        elif "furnace" in entity_name and machine and "furnace" in machine:
            items.append(item)
        elif entity_name == "chemical-plant" and machine == "chemical-plant":
            items.append(item)
        elif entity_name == "oil-refinery" and machine == "oil-refinery":
            items.append(item)
    return sorted(set(items))


def _build_rate_nodes(machines: list[PlacedMachine], recipes_data: dict) -> dict[str, RateNode]:
    nodes: dict[str, RateNode] = {}
    recipes = recipes_data.get("recipes", {})
    for m in machines:
        if m.is_input_cell or not m.recipe_item:
            continue
        recipe = recipes.get(m.recipe_item)
        if not recipe:
            continue
        deps = list(recipe.get("ingredients", {}).keys())
        nodes[m.recipe_item] = RateNode(
            item=m.recipe_item,
            required_rate=0.0,
            recipe=recipe,
            dependencies=deps,
        )
    return nodes


def _build_stage_machines(
    machines: list[PlacedMachine],
) -> dict[str, list[tuple[int, int, int, int]]]:
    stage: dict[str, list[tuple[int, int, int, int]]] = {}
    for m in machines:
        if m.is_input_cell or not m.recipe_item:
            continue
        mx, my = m.position
        w, h = m.size
        stage.setdefault(m.recipe_item, []).append((mx, my, w, h))
    return stage


def route_connections(state: AssistedBuildState) -> None:
    """Connect producer outputs to consumer inputs for all routed machines."""
    requests_by_producer: dict[tuple[int, int], list[dict]] = {}

    for consumer in state.machines:
        if consumer.is_input_cell or not consumer.recipe_item or not consumer.lanes:
            continue
        consumer_recipe = state._recipe(consumer.recipe_item)
        if not consumer_recipe:
            continue
        input_connects = consumer.lanes.get(
            "input_connects",
            [consumer.lanes["input_start"]],
        )

        for dep in recipe_ingredient_order(consumer_recipe):
            if dep in BASE_MATERIALS:
                continue
            producers = [
                p
                for p in state.machines
                if not p.is_input_cell and p.recipe_item == dep and p.lanes
            ]
            if not producers:
                continue
            producer = producers[0]
            lane_idx = ingredient_lane_index(consumer_recipe, dep)
            consumer_input = input_connects[min(lane_idx, len(input_connects) - 1)]
            producer_output = producer.lanes.get(
                "output_start", producer.lanes["output_end"]
            )
            requests_by_producer.setdefault(producer_output, []).append(
                {
                    "consumer_input_start": consumer_input,
                    "target_y": consumer_input[1],
                    "lane_offset": 0,
                    "consumer_item": consumer.recipe_item,
                    "dep": dep,
                }
            )

    for producer_output, requests in requests_by_producer.items():
        requests = _dedupe_connection_requests(requests)
        out_x, out_y = producer_output

        if not _needs_splitter_fanout(requests):
            for req in requests:
                state.entity_number = connect_lane_to_lane(
                    state.grid,
                    state.entities,
                    state.entity_number,
                    producer_output,
                    req["consumer_input_start"],
                    lane_offset=req["lane_offset"],
                )
            continue

        splitter_x = out_x + 1
        splitter_y = out_y
        before = state.entity_number
        state.entity_number = _place_splitter(
            state.grid,
            state.entities,
            state.entity_number,
            splitter_x,
            splitter_y,
            direction=FACTORIO_EAST,
            name="splitter",
        )

        if state.entity_number == before:
            for req in requests:
                state.entity_number = connect_lane_to_lane(
                    state.grid,
                    state.entities,
                    state.entity_number,
                    producer_output,
                    req["consumer_input_start"],
                    lane_offset=req["lane_offset"],
                )
            continue

        splitter_exit_x = splitter_x + 2
        for req in requests:
            in_x, in_y = req["consumer_input_start"]
            target_y = req["target_y"]
            path = _manhattan_path((splitter_exit_x, target_y), (in_x - 1, target_y))
            state.entity_number = place_belt_path(
                state.grid, state.entities, state.entity_number, path
            )
            if req["lane_offset"] != 0:
                merge_path = _manhattan_path((in_x - 1, target_y), (in_x - 1, in_y))
                state.entity_number = place_belt_path(
                    state.grid, state.entities, state.entity_number, merge_path
                )
