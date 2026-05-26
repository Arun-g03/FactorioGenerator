"""Rate-driven blueprint placement with Factorio game rules."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from core.constants import (
    BASE_MATERIALS,
    GenerationMode,
    TRANSPORT_BELT_THROUGHPUT_PER_MIN,
    machine_io_stride,
)
from planners.machine_placer.calculations import (
    ProductionCalculator,
    entity_accepts_recipe_field,
    machine_entity_for_recipe,
)
from planners.machine_placer.positioning import PositionFinder
from planners.layout_fitness import evaluate_stage_layout
from planners.machine_io import machine_row_step, place_machine_io_block
from planners.rule_based_placement import (
    NetworkLayoutCursor,
    compute_stage_depths,
    evaluate_rule_machine_layout,
    network_origin_for_stage,
)
from planners.stage_connector import stage_lanes_from_machines


@dataclass
class RateNode:
    item: str
    required_rate: float
    recipe: dict | None
    machine_count: int = 1
    dependencies: list = field(default_factory=list)
    is_user_target: bool = False


@dataclass
class RateSummaryLine:
    item: str
    requested: float
    achieved: float
    machine_count: int
    warning: str | None = None


class ProductionPlanner:
    """Builds rate graph and places entities for a blueprint."""

    def __init__(self, grid, pathfinder, belt_router, recipes_data, mode: GenerationMode):
        self.grid = grid
        self.pathfinder = pathfinder
        self.belt_router = belt_router
        self.recipes_data = recipes_data
        self.mode = mode
        self.calculator = ProductionCalculator(recipes_data)
        self.position_finder = PositionFinder(grid)
        self.logger = logging.getLogger(__name__)
        self.nodes: dict[str, RateNode] = {}
        self.rate_summary: list[RateSummaryLine] = []
        self.production_stages: list = []
        self.stage_machines: dict[str, list] = {}
        self._network_cursor: NetworkLayoutCursor | None = None
        self._stage_lanes: dict = {}
        self._stage_flow_direction: dict[str, int] = {}
        self.layout_fitness = None
        self.genetic_generations = 0
        self.genetic_converged = False
        self.blueprint_input_starts: dict[str, tuple[int, int]] = {}
        self.blueprint_start: tuple[int, int] | None = None  # first chest, if any

    def build_rate_graph(self, targets: dict[str, float]):
        """Populate self.nodes from user targets and mode."""
        self.nodes.clear()
        self.stage_machines.clear()
        demands: dict[str, float] = {}
        user_targets = set(targets.keys())

        def accumulate(item, rate):
            if item in BASE_MATERIALS:
                return
            demands[item] = demands.get(item, 0) + rate
            if self.mode == GenerationMode.FULL_CHAIN:
                recipe = self._recipe(item)
                if recipe:
                    for ing, amount in recipe.get("ingredients", {}).items():
                        accumulate(ing, rate * amount)

        if self.mode == GenerationMode.ASSEMBLER_ONLY:
            for item, rate in targets.items():
                demands[item] = rate
        else:
            for item, rate in targets.items():
                accumulate(item, rate)

        for item, rate in demands.items():
            recipe = self._recipe(item)
            if not recipe:
                self.logger.warning("No recipe for %s", item)
                continue
            self.nodes[item] = RateNode(
                item=item,
                required_rate=rate,
                recipe=recipe,
                machine_count=self.calculator.machines_needed(recipe, rate),
                dependencies=list(recipe.get("ingredients", {}).keys()),
                is_user_target=item in user_targets,
            )

    def _recipe(self, item):
        return self.recipes_data.get("recipes", {}).get(item)

    def _refresh_machine_counts(self):
        for node in self.nodes.values():
            if node.recipe:
                node.machine_count = self.calculator.machines_needed(
                    node.recipe, node.required_rate
                )

    def topological_order(self) -> list[RateNode]:
        """Ingredients before products (rough topological sort)."""
        order = []
        visited = set()

        def visit(item):
            if item in visited or item not in self.nodes:
                return
            visited.add(item)
            for dep in self.nodes[item].dependencies:
                if dep in self.nodes:
                    visit(dep)
            order.append(self.nodes[item])

        for item in sorted(self.nodes.keys()):
            visit(item)
        return order

    def _record_stage(self, item, x_start, y_start):
        self.production_stages.append({
            "id": len(self.production_stages) + 1,
            "type": item,
            "position": (x_start, y_start),
            "recipe": self.nodes[item].recipe,
            "entities": [],
        })

    def place_node(self, entities, entity_number, node: RateNode) -> int:
        """Place machines and I/O for one rate node."""
        if not node.recipe:
            return entity_number

        self._refresh_machine_counts()
        machine_name = machine_entity_for_recipe(node.item, node.recipe)
        w, h = node.recipe.get("machine_size", [3, 3])
        cursor = self._network_cursor or NetworkLayoutCursor()
        x_start, y_start, flow_dir = network_origin_for_stage(
            node, self.nodes, self._stage_lanes, cursor
        )
        self._stage_flow_direction[node.item] = flow_dir
        self._record_stage(node.item, x_start, y_start)

        for i in range(node.machine_count):
            dx, dy = machine_row_step(flow_dir, machine_io_stride(w), i)
            mx = x_start + dx
            my = y_start + dy
            if self.grid.is_occupied(mx, my, w, h):
                alt = self.position_finder.find_placement_near(mx, my, w, h)
                if alt[0] is not None:
                    mx, my = alt
                else:
                    self.logger.warning("No space for %s machine %s", node.item, i)
                    continue

            entity = {
                "entity_number": entity_number,
                "name": machine_name,
                "position": {"x": mx, "y": my},
            }
            if entity_accepts_recipe_field(machine_name):
                entity["recipe"] = node.item
            entities.append(entity)
            self.grid.occupy(mx, my, machine_name, [w, h])
            entity_number += 1

            self.stage_machines.setdefault(node.item, []).append((mx, my, w, h))

            entity_number = place_machine_io_block(
                self.grid,
                entities,
                entity_number,
                mx,
                my,
                w,
                h,
                flow_direction=flow_dir,
            )

        lanes = stage_lanes_from_machines(
            self.stage_machines.get(node.item, []), flow_dir
        )
        if lanes:
            self._stage_lanes[node.item] = lanes

        return entity_number

    def _connect_production_stages(self, entities, entity_number):
        """Route belts between stages and from base-material buses."""
        from planners.stage_connector import connect_base_materials, connect_stages

        self.blueprint_input_starts = {}
        self.blueprint_start = None
        entity_number = connect_stages(
            self.grid, entities, entity_number, self.stage_machines, self.nodes
        )
        entity_number, self.blueprint_input_starts = connect_base_materials(
            self.grid, entities, entity_number, self.stage_machines, self.nodes
        )
        if self.blueprint_input_starts:
            self.blueprint_start = next(iter(self.blueprint_input_starts.values()))
        return entity_number

    def build_rate_summary(self, targets: dict[str, float]):
        """Compute achieved vs requested for user targets."""
        self.rate_summary.clear()
        for item, requested in targets.items():
            node = self.nodes.get(item)
            if not node or not node.recipe:
                self.rate_summary.append(
                    RateSummaryLine(item, requested, 0.0, 0, "No recipe")
                )
                continue
            achieved = self.calculator.achieved_rate(node.recipe, node.machine_count)
            warning = None
            if achieved < requested * 0.99:
                warning = "Under target"
            elif achieved > requested * 1.5:
                warning = "Over target"
            if node.required_rate > TRANSPORT_BELT_THROUGHPUT_PER_MIN:
                belt_warn = "Exceeds yellow belt throughput"
                warning = f"{warning}; {belt_warn}" if warning else belt_warn
            self.rate_summary.append(
                RateSummaryLine(item, requested, achieved, node.machine_count, warning)
            )

    def _reset_placement_state(self):
        self._network_cursor = NetworkLayoutCursor()
        self._stage_lanes = {}
        self._stage_flow_direction = {}
        self.production_stages.clear()
        self.stage_machines.clear()

    def _place_all_nodes(self, entities: list, entity_number: int) -> int:
        for node in self.topological_order():
            entity_number = self.place_node(entities, entity_number, node)
        return entity_number

    def generate(
        self, targets: dict[str, float], entities: list, entity_number: int
    ) -> tuple[list, int]:
        """Rule-based network placement: stages anchor on their recipe dependencies."""
        self.build_rate_graph(targets)
        self._refresh_machine_counts()
        depths = compute_stage_depths(self.nodes)

        self._reset_placement_state()
        entity_number = self._place_all_nodes(entities, entity_number)

        fitness = evaluate_rule_machine_layout(
            self.stage_machines, self.nodes, grid=self.grid
        )
        self.layout_fitness = fitness
        self.logger.info(
            "Rule-based network: stages=%s max_depth=%s viable=%s score=%.0f/100",
            len(self.stage_machines),
            max(depths.values()) if depths else 0,
            fitness.is_viable,
            fitness.total,
        )
        if fitness.blockers:
            for msg in fitness.blockers[:3]:
                self.logger.warning("  layout: %s", msg)

        entity_number = self._connect_production_stages(entities, entity_number)
        self._score_layout()
        self.build_rate_summary(targets)
        return entities, entity_number

    def _score_layout(self):
        """Evaluate layout quality (machines + estimated I/O; ignores placed belt tiles)."""
        expected = {item: node.machine_count for item, node in self.nodes.items()}
        self.layout_fitness = evaluate_stage_layout(
            self.stage_machines,
            self.nodes,
            grid=None,
            expected_counts=expected,
        )
        bd = self.layout_fitness
        self.logger.info(
            "Layout %s score=%.0f/100 (viability=%.0f, efficiency=%.0f, blockers=%s)",
            "VIABLE" if bd.is_viable else "BROKEN",
            bd.total,
            bd.viability_score,
            bd.efficiency_score,
            len(bd.blockers),
        )

    def generate_genetic(
        self,
        targets: dict[str, float],
        entities: list,
        entity_number: int,
        progress_callback=None,
    ) -> tuple[list, int]:
        """Placement pass using genetic algorithm for machine positions."""
        from planners.genetic_placement import (
            collect_machine_slots,
            place_machines_from_genetic_layout,
            run_genetic_layout,
        )

        self.build_rate_graph(targets)
        self._refresh_machine_counts()
        self.production_stages.clear()
        self.stage_machines.clear()
        self.genetic_generations = 0
        self.genetic_converged = False

        machine_slots = collect_machine_slots(self)
        if machine_slots:
            self.logger.info(
                "Genetic placement for %s machines...", len(machine_slots)
            )
            result = run_genetic_layout(
                self.grid,
                machine_slots,
                self.nodes,
                progress_callback=progress_callback,
            )
            self.genetic_generations = result.generations
            self.genetic_converged = result.converged
            self.layout_fitness = result.fitness_breakdown
            entity_number = place_machines_from_genetic_layout(
                self, entities, entity_number, machine_slots, result.machines
            )

        entity_number = self._connect_production_stages(entities, entity_number)
        self._score_layout()
        self.build_rate_summary(targets)
        return entities, entity_number
