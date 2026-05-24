"""Rate-driven blueprint placement with Factorio game rules."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from core.constants import (
    BASE_MATERIALS,
    GenerationMode,
    TRANSPORT_BELT_THROUGHPUT_PER_MIN,
)
from planners.machine_placer.calculations import ProductionCalculator
from planners.machine_placer.positioning import PositionFinder
from planners.layout_fitness import evaluate_stage_layout
from planners.machine_io import place_machine_io_block


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
        self._stage_spacing = 18
        self._next_stage_x = 10
        self._stage_y = 15
        self.layout_fitness = None
        self.genetic_generations = 0
        self.genetic_converged = False

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

        for item in self.nodes:
            visit(item)
        return order

    def _allocate_stage_position(self, item, machine_w, machine_h, machine_count):
        """Allocate origin for a stage (row of machines along X)."""
        total_width = machine_count * (machine_w + 6) + 6
        x_start = self._next_stage_x
        y_start = self._stage_y
        self._next_stage_x += total_width + self._stage_spacing
        self.production_stages.append({
            "id": len(self.production_stages) + 1,
            "type": item,
            "position": (x_start, y_start),
            "recipe": self.nodes[item].recipe,
            "entities": [],
        })
        return x_start, y_start

    def place_node(self, entities, entity_number, node: RateNode) -> int:
        """Place machines and I/O for one rate node."""
        if not node.recipe:
            return entity_number

        self._refresh_machine_counts()
        machine_name = node.recipe.get("machine", "assembling-machine-1")
        w, h = node.recipe.get("machine_size", [3, 3])
        x_start, y_start = self._allocate_stage_position(
            node.item, w, h, node.machine_count
        )

        for i in range(node.machine_count):
            mx = x_start + i * (w + 6)
            my = y_start
            if self.grid.is_occupied(mx, my, w, h):
                alt = self.position_finder.find_next_available_position_with_spacing(w, h)
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
            if machine_name.startswith("assembling-machine") or "furnace" in machine_name:
                entity["recipe"] = node.item
            entities.append(entity)
            self.grid.occupy(mx, my, machine_name, [w, h])
            entity_number += 1

            self.stage_machines.setdefault(node.item, []).append((mx, my, w, h))

            entity_number = place_machine_io_block(
                self.grid, entities, entity_number, mx, my, w, h, flow_east=True
            )

        return entity_number

    def _connect_production_stages(self, entities, entity_number):
        """Route belts between stages and from base-material buses."""
        from planners.stage_connector import connect_base_materials, connect_stages

        entity_number = connect_stages(
            self.grid, entities, entity_number, self.stage_machines, self.nodes
        )
        entity_number = connect_base_materials(
            self.grid, entities, entity_number, self.stage_machines, self.nodes
        )
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

    def _reset_placement_state(self, stage_y: int):
        self._stage_y = stage_y
        self._next_stage_x = 10
        self.production_stages.clear()
        self.stage_machines.clear()

    def _place_all_nodes(self, entities: list, entity_number: int) -> int:
        for node in self.topological_order():
            entity_number = self.place_node(entities, entity_number, node)
        return entity_number

    def generate(
        self, targets: dict[str, float], entities: list, entity_number: int
    ) -> tuple[list, int]:
        """Rule-based placement; picks the best stage row among fitness candidates."""
        self.build_rate_graph(targets)
        self._refresh_machine_counts()

        grid_backup = dict(self.grid.occupied)
        candidate_rows = (12, 15, 18, 22)
        best_score = float("-inf")
        best_pack = None

        for stage_y in candidate_rows:
            self.grid.occupied = dict(grid_backup)
            self._reset_placement_state(stage_y)
            trial_entities: list = []
            trial_num = self._place_all_nodes(trial_entities, entity_number)
            score = evaluate_stage_layout(
                self.stage_machines, self.nodes, self.grid
            ).total
            if score > best_score:
                best_score = score
                best_pack = (
                    trial_entities,
                    trial_num,
                    list(self.production_stages),
                    {k: list(v) for k, v in self.stage_machines.items()},
                    stage_y,
                    dict(self.grid.occupied),
                )

        if best_pack:
            trial_entities, trial_num, stages, machines, stage_y, grid_state = best_pack
            entities.clear()
            entities.extend(trial_entities)
            entity_number = trial_num
            self.production_stages = stages
            self.stage_machines = machines
            self._stage_y = stage_y
            self.grid.occupied = grid_state
            self.logger.info(
                "Rule-based layout chose stage_y=%s (score=%.0f/100)",
                stage_y,
                best_score,
            )
        else:
            self.grid.occupied = dict(grid_backup)

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
