"""Assisted Build session state: user-placed machines, shared layout routing."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from core.constants import BASE_MATERIALS, FACTORIO_EAST
from planners.machine_io import (
    machine_io_lanes,
    recipe_input_lane_count,
)
from planners.machine_placer.calculations import (
    entity_accepts_recipe_field,
    machine_entity_for_recipe,
)
from planners.production_planner import RateNode
from planners.stage_connector import OUTPUT_ANY_PRODUCT, route_placed_layout

INPUT_CELL_ENTITY = "wooden-chest"
OUTPUT_CELL_ENTITY = "wooden-chest"

logger = logging.getLogger(__name__)


def _is_io_cell(machine: PlacedMachine) -> bool:
    return machine.is_input_cell or machine.is_output_cell


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
    is_output_cell: bool = False
    output_product: str | None = None


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
            "size": [w, h],
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

    def place_output_cell(self, x: int, y: int) -> PlacedMachine | None:
        """Place a user-positioned product output chest (1x1)."""
        machine = self.place_machine(OUTPUT_CELL_ENTITY, x, y, (1, 1))
        if machine:
            machine.is_output_cell = True
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

    def assign_output_products_bulk(self, machine_ids: list[str], product: str) -> int:
        if product != OUTPUT_ANY_PRODUCT and not self._recipe(product):
            logger.warning("Unknown product item: %s", product)
            return 0
        applied = 0
        for mid in machine_ids:
            machine = self._machine_at(mid)
            if not machine or not machine.is_output_cell:
                continue
            machine.output_product = product
            machine.recipe_item = product
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
                "size": [w, h],
            }
            self.entities.append(entity)
            self.grid.occupy(mx, my, m.entity_name, [w, h])
            m.lanes = None

    def full_reroute(self) -> None:
        """Clear routing artifacts and rebuild belts for all assigned recipes."""
        self._rebuild_machine_entities()
        for machine in self.machines:
            if _is_io_cell(machine) or not machine.recipe_item:
                continue
            self._refresh_machine_lanes(machine)

        nodes = rate_nodes_from_machines(self.machines, self.recipes_data)
        stage_machines = stage_machines_from_placed(self.machines)
        if not nodes or not stage_machines:
            return

        input_sources = input_sources_from_machines(self.machines)
        output_sinks = output_sinks_from_machines(self.machines)
        self.entity_number, _ = route_placed_layout(
            self.grid,
            self.entities,
            self.entity_number,
            stage_machines,
            nodes,
            input_sources=input_sources or None,
            output_sinks=output_sinks or None,
        )

    def _refresh_machine_lanes(self, machine: PlacedMachine) -> None:
        recipe = self._recipe(machine.recipe_item)
        mx, my = machine.position
        w, h = machine.size
        lane_count = recipe_input_lane_count(recipe)
        # Assisted mode keeps placement clean: no auto I/O entities on machine place.
        # Routing uses these lane anchors to connect belts between machines/cells.
        machine.lanes = machine_io_lanes(
            mx, my, w, h, FACTORIO_EAST, input_lane_count=lane_count
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


def input_sources_from_machines(
    machines: list[PlacedMachine],
) -> dict[str, list[tuple[int, int]]]:
    """Map base material to user-placed input chest positions."""
    cells: dict[str, list[tuple[int, int]]] = {}
    for m in machines:
        if m.is_input_cell and m.input_resource:
            cells.setdefault(m.input_resource, []).append(m.position)
    return cells


def output_sinks_from_machines(
    machines: list[PlacedMachine],
) -> dict[str, list[tuple[int, int]]]:
    """Map product item to user-placed output chest positions."""
    cells: dict[str, list[tuple[int, int]]] = {}
    for m in machines:
        if m.is_output_cell and m.output_product:
            cells.setdefault(m.output_product, []).append(m.position)
    return cells


def products_for_output_picker(recipes_data: dict) -> list[str]:
    """Craftable products available for output cell assignment."""
    recipes = recipes_data.get("recipes", {})
    items: list[str] = []
    for item, recipe in recipes.items():
        if recipe.get("type") == "raw":
            continue
        if not recipe.get("ingredients") and "crafting_time" not in recipe:
            continue
        items.append(item)
    return [OUTPUT_ANY_PRODUCT] + sorted(items)


def rate_nodes_from_machines(
    machines: list[PlacedMachine], recipes_data: dict
) -> dict[str, RateNode]:
    """Build rate graph nodes from placed machines (shared routing input)."""
    nodes: dict[str, RateNode] = {}
    recipes = recipes_data.get("recipes", {})
    for m in machines:
        if _is_io_cell(m) or not m.recipe_item:
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


def stage_machines_from_placed(
    machines: list[PlacedMachine],
) -> dict[str, list[tuple[int, int, int, int]]]:
    """Build stage_machines map from placed machines (shared routing input)."""
    stage: dict[str, list[tuple[int, int, int, int]]] = {}
    for m in machines:
        if _is_io_cell(m) or not m.recipe_item:
            continue
        mx, my = m.position
        w, h = m.size
        stage.setdefault(m.recipe_item, []).append((mx, my, w, h))
    return stage


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
