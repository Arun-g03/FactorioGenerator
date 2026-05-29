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
    auto_route_on_change: bool = True
    incremental_reroute: bool = False
    network_router: object | None = None
    _pending_reroute_group_keys: set[str] | None = None
    last_optimization: object | None = None
    optimization_search_active: bool = False
    _search_links: list | None = field(default=None, repr=False)
    _search_nodes: dict | None = field(default=None, repr=False)
    _search_stage_machines: dict | None = field(default=None, repr=False)
    _search_iteration: int = 0
    _search_stale: int = 0
    _search_best_variant: int = 0
    _search_best_score: tuple = field(default=(-1, -1.0e18, 0, 0), repr=False)
    _search_stale_limit: int = 20
    _search_max_iterations: int = 0

    def _maybe_reroute(self, *, group_keys: set[str] | None = None) -> None:
        if self.optimization_search_active:
            self.stop_optimization_search()
        if not self.auto_route_on_change:
            return
        if self.incremental_reroute and group_keys and self.network_router is not None:
            self.partial_reroute(group_keys)
        else:
            self.full_reroute()

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
            self._maybe_reroute()
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
            for mid in machine_ids:
                machine = self._machine_at(mid)
                if machine and machine.recipe_item:
                    self._refresh_machine_lanes(machine)
            keys = self._group_keys_for_recipe_change(recipe_item)
            self._maybe_reroute(group_keys=keys if self.incremental_reroute else None)
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
            keys: set[str] = set()
            for mid in machine_ids:
                machine = self._machine_at(mid)
                if machine and machine.is_input_cell and machine.input_resource:
                    cx, cy = machine.position
                    keys.add(f"base:{machine.input_resource}:{cx},{cy}")
            self._maybe_reroute(group_keys=keys if self.incremental_reroute else None)
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
            keys: set[str] = set()
            for mid in machine_ids:
                machine = self._machine_at(mid)
                if machine and machine.is_output_cell and machine.output_product:
                    cx, cy = machine.position
                    keys.add(f"sink:{machine.output_product}:{cx},{cy}")
            self._maybe_reroute(group_keys=keys if self.incremental_reroute else None)
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
        self.network_router = None
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
            network_router=None,
        )
        from planners.stage_connector import route_placed_layout as _rpl

        self.network_router = getattr(_rpl, "_last_router", None)

    def _prepare_optimization_context(self):
        """Build link graph context for optimize / search. Returns tuple or None."""
        from planners.belt_network.link_graph import build_link_graph, sort_links

        nodes = rate_nodes_from_machines(self.machines, self.recipes_data)
        stage_machines = stage_machines_from_placed(self.machines)
        if not stage_machines:
            return None
        input_sources = input_sources_from_machines(self.machines)
        output_sinks = output_sinks_from_machines(self.machines)
        links = sort_links(
            build_link_graph(
                stage_machines,
                nodes,
                input_sources=input_sources or None,
                output_sinks=output_sinks or None,
            )
        )
        if not links:
            return None
        return links, nodes, stage_machines

    def _route_layout_variant(
        self,
        *,
        link_order_variant: int = 0,
        links=None,
        search_iteration: int | None = None,
    ) -> None:
        """Rebuild routing from machines using one link-group ordering variant."""
        from planners.belt_network.optimize import group_order_for_search

        self._rebuild_machine_entities()
        for machine in self.machines:
            if _is_io_cell(machine) or not machine.recipe_item:
                continue
            self._refresh_machine_lanes(machine)

        nodes = rate_nodes_from_machines(self.machines, self.recipes_data)
        stage_machines = stage_machines_from_placed(self.machines)
        if not nodes or not stage_machines:
            return

        if links is None:
            ctx = self._prepare_optimization_context()
            if ctx is None:
                return
            links, nodes, stage_machines = ctx

        group_order = None
        if search_iteration is not None:
            group_order = group_order_for_search(links, search_iteration)

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
            network_router=None,
            link_order_variant=link_order_variant,
            links=links,
            group_order=group_order,
        )
        from planners.stage_connector import route_placed_layout as _rpl

        self.network_router = getattr(_rpl, "_last_router", None)

    def start_optimization_search(
        self,
        *,
        stale_limit: int = 20,
        max_iterations: int = 0,
    ) -> bool:
        """
        Begin continuous optimization (caller runs optimization_search_step each frame).
        """
        ctx = self._prepare_optimization_context()
        if ctx is None:
            return False

        from planners.belt_network.optimize import layout_score

        links, nodes, stage_machines = ctx
        self._search_links = links
        self._search_nodes = nodes
        self._search_stage_machines = stage_machines
        self._search_stale_limit = max(1, int(stale_limit))
        self._search_max_iterations = max(0, int(max_iterations))
        self._search_iteration = 0
        self._search_stale = 0
        self._search_best_variant = 0
        self._route_layout_variant(search_iteration=0, links=links)
        self._search_best_score = layout_score(
            self.entities,
            stage_machines,
            nodes,
            links=links,
            grid=self.grid,
        )
        self.optimization_search_active = True
        logger.info(
            "Optimization search started (stale_limit=%s, max_iter=%s)",
            self._search_stale_limit,
            self._search_max_iterations,
        )
        return True

    def stop_optimization_search(self) -> None:
        """Stop search and apply the best layout found."""
        if not self.optimization_search_active:
            return
        from planners.belt_network.optimize import (
            OptimizationResult,
            count_splitters,
            count_transport_belts,
            count_underground_pairs,
            evaluate_routing_quality,
        )

        links = self._search_links
        nodes = self._search_nodes
        stage_machines = self._search_stage_machines
        if links and nodes and stage_machines:
            self._route_layout_variant(
                search_iteration=self._search_best_variant, links=links
            )
            metrics = evaluate_routing_quality(
                self.entities, links, stage_machines, nodes, grid=self.grid
            )
            self.last_optimization = OptimizationResult(
                improved=True,
                belts_before=0,
                belts_after=count_transport_belts(self.entities),
                score_before=0.0,
                score_after=metrics.composite_score,
                variant_used=self._search_best_variant,
                viable=metrics.viable,
                message=(
                    f"Search stopped at iter {self._search_iteration}: "
                    f"{metrics.belt_count} belts, "
                    f"{count_splitters(self.entities)} splitters, "
                    f"{count_underground_pairs(self.entities)} UG"
                ),
                splitters_after=count_splitters(self.entities),
                underground_pairs_after=count_underground_pairs(self.entities),
            )
        self.optimization_search_active = False
        self._search_links = None
        self._search_nodes = None
        self._search_stage_machines = None

    def optimization_search_step(self) -> object:
        """
        Run one search iteration. Call each frame while optimization_search_active.
        """
        from planners.belt_network.optimize import (
            OptimizationSearchStatus,
            count_splitters,
            count_transport_belts,
            count_underground_pairs,
            layout_score,
        )

        if not self.optimization_search_active:
            return OptimizationSearchStatus(
                iteration=0,
                stale_iterations=0,
                continue_search=False,
                improved=False,
                belts=0,
                splitters=0,
                underground_pairs=0,
                composite_score=0.0,
                viable=False,
                message="Search not active",
            )

        links = self._search_links or []
        nodes = self._search_nodes or {}
        stage_machines = self._search_stage_machines or {}

        self._search_iteration += 1
        trial = self._search_iteration
        self._route_layout_variant(search_iteration=trial, links=links)
        score = layout_score(
            self.entities, stage_machines, nodes, links=links, grid=self.grid
        )
        improved = score > self._search_best_score
        if improved:
            self._search_best_score = score
            self._search_best_variant = trial
            self._search_stale = 0
        else:
            self._search_stale += 1

        self._route_layout_variant(
            search_iteration=self._search_best_variant, links=links
        )

        belts = count_transport_belts(self.entities)
        splitters = count_splitters(self.entities)
        ug = count_underground_pairs(self.entities)
        viable = bool(score[0])
        composite = float(score[1])

        hit_stale = self._search_stale >= self._search_stale_limit
        hit_max = (
            self._search_max_iterations > 0
            and self._search_iteration >= self._search_max_iterations
        )
        continue_search = not hit_stale and not hit_max

        if hit_stale:
            reason = f"no improvement for {self._search_stale_limit} iters"
        elif hit_max:
            reason = f"reached {self._search_max_iterations} iterations"
        else:
            reason = "searching"

        message = (
            f"Opt search #{trial}: {belts} belts, {splitters} spl, {ug} UG "
            f"({'+' if improved else '='}) — {reason}"
        )
        status = OptimizationSearchStatus(
            iteration=trial,
            stale_iterations=self._search_stale,
            continue_search=continue_search,
            improved=improved,
            belts=belts,
            splitters=splitters,
            underground_pairs=ug,
            composite_score=composite,
            viable=viable,
            message=message,
        )
        if not continue_search:
            self.stop_optimization_search()
            status = OptimizationSearchStatus(
                iteration=status.iteration,
                stale_iterations=status.stale_iterations,
                continue_search=False,
                improved=status.improved,
                belts=status.belts,
                splitters=status.splitters,
                underground_pairs=status.underground_pairs,
                composite_score=status.composite_score,
                viable=status.viable,
                message=self.last_optimization.message
                if self.last_optimization
                else status.message,
            )
        return status

    def optimization_pass(self, max_variants: int = 4) -> object:
        """
        Try several belt group orderings; keep the best viable layout.

        Machines and cells stay fixed; only belts/inserters/splitters change.
        """
        from planners.belt_network.link_graph import build_link_graph, sort_links
        from planners.belt_network.optimize import (
            OptimizationResult,
            count_splitters,
            count_transport_belts,
            count_underground_pairs,
            evaluate_routing_quality,
            layout_score,
        )

        nodes = rate_nodes_from_machines(self.machines, self.recipes_data)
        stage_machines = stage_machines_from_placed(self.machines)
        if not stage_machines:
            result = OptimizationResult(
                improved=False,
                belts_before=0,
                belts_after=0,
                score_before=0.0,
                score_after=0.0,
                variant_used=0,
                viable=False,
                message="No machines with recipes to optimize",
            )
            self.last_optimization = result
            return result

        input_sources = input_sources_from_machines(self.machines)
        output_sinks = output_sinks_from_machines(self.machines)
        links = sort_links(
            build_link_graph(
                stage_machines,
                nodes,
                input_sources=input_sources or None,
                output_sinks=output_sinks or None,
            )
        )
        if not links:
            result = OptimizationResult(
                improved=False,
                belts_before=count_transport_belts(self.entities),
                belts_after=count_transport_belts(self.entities),
                score_before=0.0,
                score_after=0.0,
                variant_used=0,
                viable=False,
                message="No belt links to optimize",
            )
            self.last_optimization = result
            return result

        belts_before = count_transport_belts(self.entities)
        splitters_before = count_splitters(self.entities)
        ug_before = count_underground_pairs(self.entities)
        metrics_before = evaluate_routing_quality(
            self.entities, links, stage_machines, nodes, grid=self.grid
        )
        score_before = metrics_before.composite_score

        best_variant = 0
        best_score = (-1, -1.0e18, 0, 0)
        trials = max(1, min(max_variants, 4))

        for variant in range(trials):
            self._route_layout_variant(link_order_variant=variant, links=links)
            score = layout_score(
                self.entities,
                stage_machines,
                nodes,
                links=links,
                grid=self.grid,
            )
            if score > best_score:
                best_score = score
                best_variant = variant

        self._route_layout_variant(link_order_variant=best_variant, links=links)
        belts_after = count_transport_belts(self.entities)
        splitters_after = count_splitters(self.entities)
        ug_after = count_underground_pairs(self.entities)
        metrics_after = evaluate_routing_quality(
            self.entities, links, stage_machines, nodes, grid=self.grid
        )
        score_after = metrics_after.composite_score
        viable_a = metrics_after.viable
        improved = score_after > score_before or (
            viable_a and belts_after < belts_before
        )
        if improved:
            msg = (
                f"Optimized: {belts_before}→{belts_after} belts, "
                f"{splitters_after} splitters, {ug_after} UG pairs "
                f"(variant {best_variant})"
            )
        elif viable_a:
            msg = (
                f"No improvement — {belts_after} belts, "
                f"{splitters_after} splitters, {ug_after} UG pairs "
                f"(variant {best_variant})"
            )
        else:
            msg = "Layout still has connectivity issues after optimization"

        logger.info(msg)
        if metrics_after.details:
            logger.info("Optimize metrics: %s", ", ".join(metrics_after.details))
        result = OptimizationResult(
            improved=improved,
            belts_before=belts_before,
            belts_after=belts_after,
            score_before=score_before,
            score_after=score_after,
            variant_used=best_variant,
            viable=bool(viable_a),
            message=msg,
            splitters_before=splitters_before,
            splitters_after=splitters_after,
            underground_pairs_before=ug_before,
            underground_pairs_after=ug_after,
        )
        self.last_optimization = result
        return result

    def partial_reroute(self, group_keys: set[str]) -> None:
        """Re-route only belt groups touching changed machines (incremental mode)."""
        from planners.belt_network.link_graph import build_link_graph, sort_links
        from planners.belt_network.materialize import materialize_link_group
        from planners.belt_network.occupancy import RoutingOccupancy
        from planners.belt_network.router import BeltNetworkRouter

        router = self.network_router
        if not isinstance(router, BeltNetworkRouter) or not group_keys:
            self.full_reroute()
            return

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
        links = sort_links(
            build_link_graph(
                stage_machines,
                nodes,
                input_sources=input_sources or None,
                output_sinks=output_sinks or None,
            )
        )
        groups: dict[str, list] = {}
        for link in links:
            if link.group_key in group_keys:
                groups.setdefault(link.group_key, []).append(link)

        if not groups:
            self.full_reroute()
            return

        router.strip_groups(self.grid, self.entities, group_keys)
        occupancy = RoutingOccupancy(self.grid)
        for group_links in groups.values():
            self.entity_number = materialize_link_group(
                self.grid,
                self.entities,
                self.entity_number,
                occupancy,
                group_links,
            )

    def _group_keys_for_recipe_change(self, recipe_item: str | None) -> set[str]:
        """Best-effort group keys to rerun when a machine recipe changes."""
        keys: set[str] = set()
        if recipe_item:
            recipe = self._recipe(recipe_item)
            for dep in (recipe or {}).get("ingredients", {}):
                for m in self.machines:
                    if m.is_input_cell and m.input_resource == dep:
                        cx, cy = m.position
                        keys.add(f"base:{dep}:{cx},{cy}")
            for m in self.machines:
                if m.recipe_item == recipe_item and m.lanes:
                    out = m.lanes.get("output_start", m.lanes.get("output_end"))
                    if out:
                        keys.add(f"stage:{out[0]},{out[1]}")
        return keys

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
