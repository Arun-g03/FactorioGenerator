"""Parallel genetic fitness evaluation."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.constants import GenerationMode
from core.grid_env import Grid
from core.pathfinding import Pathfinder
from core.belt_router import BeltRouter
from core.placement_settings import GeneticPlacementSettings, apply_genetic_settings
from planners import genetic_placement as gp
from planners.genetic_placement import (
    _build_layout_walkforward,
    _evaluate_population,
    _initialize_population,
    _prefix_viable_through,
    collect_machine_slots,
)
from planners.layout_fitness import evaluate_machine_positions, evaluate_placed_subset
import random
from planners.production_planner import ProductionPlanner


class TestGeneticParallel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SRC / "data" / "recipes.json", encoding="utf-8") as f:
            cls.recipes = json.load(f)

    def _planner_with_slots(self):
        grid = Grid()
        pathfinder = Pathfinder(grid)
        belt_router = BeltRouter(grid, pathfinder)
        planner = ProductionPlanner(
            grid, pathfinder, belt_router, self.recipes, GenerationMode.FULL_CHAIN
        )
        planner.build_rate_graph({"iron-gear-wheel": 30})
        planner._refresh_machine_counts()
        machine_slots = collect_machine_slots(planner)
        return planner, machine_slots

    def test_parallel_matches_serial_scores(self):
        planner, machine_slots = self._planner_with_slots()
        population = _initialize_population(
            12, machine_slots, planner.nodes, planner.grid
        )

        serial = _evaluate_population(
            [gp.copy.deepcopy(layout) for layout in population],
            planner.grid,
            machine_slots,
            planner.nodes,
            worker_count=1,
        )
        parallel = _evaluate_population(
            [gp.copy.deepcopy(layout) for layout in population],
            planner.grid,
            machine_slots,
            planner.nodes,
            worker_count=4,
        )

        serial_scores = sorted(fitness for _layout, fitness in serial)
        parallel_scores = sorted(fitness for _layout, fitness in parallel)
        self.assertEqual(serial_scores, parallel_scores)

    def test_walkforward_prefixes_stay_viable(self):
        planner, machine_slots = self._planner_with_slots()
        layout = _build_layout_walkforward(
            machine_slots, planner.nodes, planner.grid, random, jitter=False
        )
        for idx in range(len(layout["machines"])):
            self.assertTrue(
                _prefix_viable_through(
                    layout, machine_slots, planner.nodes, planner.grid, idx
                ),
                f"prefix through slot {idx} should be viable",
            )

    def test_full_layout_scored_after_walkforward(self):
        planner, machine_slots = self._planner_with_slots()
        layout = _build_layout_walkforward(
            machine_slots, planner.nodes, planner.grid, random, jitter=False
        )
        full = evaluate_machine_positions(
            layout["machines"], machine_slots, planner.nodes, planner.grid
        )
        self.assertFalse(
            full.blockers,
            f"walk-forward layout should be globally viable: {full.blockers}",
        )

    def test_walkforward_respects_slot_order(self):
        planner, machine_slots = self._planner_with_slots()
        layout = _build_layout_walkforward(
            machine_slots, planner.nodes, planner.grid, random, jitter=False
        )
        self.assertEqual(len(layout["machines"]), len(machine_slots))
        for idx, (x, y, item) in enumerate(layout["machines"]):
            self.assertEqual(item, machine_slots[idx][0])

    def test_apply_genetic_settings_sets_worker_count(self):
        settings = GeneticPlacementSettings(worker_count=6)
        with apply_genetic_settings(settings):
            self.assertEqual(gp.GA_WORKER_COUNT, 6)
        self.assertNotEqual(gp.GA_WORKER_COUNT, 6)


if __name__ == "__main__":
    unittest.main()
