"""Rate-driven blueprint placement with Factorio game rules."""

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
        self._stage_spacing = 18
        self._next_stage_x = 10
        self._stage_y = 15

    def build_rate_graph(self, targets: dict[str, float]):
        """Populate self.nodes from user targets and mode."""
        self.nodes.clear()
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

            entity_number = place_machine_io_block(
                self.grid, entities, entity_number, mx, my, w, h, flow_east=True
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

    def generate(
        self, targets: dict[str, float], entities: list, entity_number: int
    ) -> tuple[list, int]:
        """Full placement pass (deterministic rule-based layout)."""
        self.build_rate_graph(targets)
        self._refresh_machine_counts()

        for node in self.topological_order():
            entity_number = self.place_node(entities, entity_number, node)

        self.build_rate_summary(targets)
        return entities, entity_number

    def generate_genetic(
        self, targets: dict[str, float], entities: list, entity_number: int
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

        machine_slots = collect_machine_slots(self)
        if machine_slots:
            self.logger.info(
                "Genetic placement for %s machines...", len(machine_slots)
            )
            positions = run_genetic_layout(self.grid, machine_slots)
            entity_number = place_machines_from_genetic_layout(
                self, entities, entity_number, machine_slots, positions
            )

        self.build_rate_summary(targets)
        return entities, entity_number
