"""Tests for per-ingredient machine input lanes."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.constants import BELT_LANES_PER_TILE
from core.grid_env import Grid
from planners.machine_io import (
    ingredient_lane_index,
    place_machine_io_block,
    recipe_input_lane_count,
)
from planners.stage_connector import stage_lanes_from_machines


class TestMachineIoLanes(unittest.TestCase):
    def test_recipe_input_lane_count(self):
        recipe = {
            "ingredients": {"iron-plate": 1, "copper-cable": 3},
        }
        self.assertEqual(recipe_input_lane_count(recipe), 2)
        self.assertEqual(recipe_input_lane_count({"ingredients": {}}), 1)

    def test_two_ingredient_places_two_input_inserters(self):
        grid = Grid(width=40, height=40)
        entities = []
        recipe = {
            "ingredients": {"iron-plate": 1, "copper-cable": 3},
            "machine_size": [3, 3],
        }
        place_machine_io_block(
            grid,
            entities,
            1,
            10,
            10,
            3,
            3,
            recipe=recipe,
        )
        inserters = [e for e in entities if e.get("name") == "inserter"]
        self.assertEqual(len(inserters), 3)  # 2 input + 1 output

    def test_stage_lanes_per_ingredient(self):
        recipe = {
            "ingredients": {"iron-plate": 1, "copper-cable": 3},
            "machine_size": [3, 3],
        }
        machines = [(10, 10, 3, 3)]
        lanes = stage_lanes_from_machines(machines, recipe=recipe)
        self.assertEqual(len(lanes["input_starts"]), 2)
        self.assertNotEqual(lanes["input_starts"][0], lanes["input_starts"][1])
        self.assertEqual(len(lanes["input_connects"]), 2)
        self.assertEqual(lanes["input_connects"][0][0], lanes["input_starts"][0][0] - 1)

    def test_ingredient_lane_index_maps_deps(self):
        recipe = {"ingredients": {"iron-plate": 1, "copper-cable": 3}}
        self.assertEqual(ingredient_lane_index(recipe, "iron-plate"), 0)
        self.assertEqual(ingredient_lane_index(recipe, "copper-cable"), 1)

    def test_belt_lanes_per_tile_constant(self):
        self.assertEqual(BELT_LANES_PER_TILE, 2)


if __name__ == "__main__":
    unittest.main()
