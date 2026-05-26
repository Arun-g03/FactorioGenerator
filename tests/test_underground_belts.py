"""Tests for underground belt placement constraints."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.constants import FACTORIO_EAST, FACTORIO_WEST
from core.grid_env import Grid
from planners.stage_connector import _place_underground_pair, place_belt_path


class TestUndergroundBelts(unittest.TestCase):
    def test_places_valid_eastbound_pair(self):
        grid = Grid(width=50, height=50)
        entities = []
        entity_number = _place_underground_pair(
            grid,
            entities,
            1,
            (10, 10),
            (15, 10),  # 4 underground tiles between endpoints
            FACTORIO_EAST,
            name="underground-belt",
        )

        self.assertEqual(entity_number, 3)
        self.assertEqual(len(entities), 2)
        self.assertEqual(entities[0]["type"], "input")
        self.assertEqual(entities[1]["type"], "output")
        self.assertEqual(entities[0]["direction"], FACTORIO_EAST)
        self.assertEqual(entities[1]["direction"], FACTORIO_EAST)

    def test_rejects_misaligned_or_wrong_direction_pair(self):
        grid = Grid(width=50, height=50)
        entities = []

        # Not straight line.
        entity_number = _place_underground_pair(
            grid,
            entities,
            1,
            (10, 10),
            (14, 11),
            FACTORIO_EAST,
            name="underground-belt",
        )
        self.assertEqual(entity_number, 1)
        self.assertEqual(entities, [])

        # Straight, but direction does not match endpoint vector.
        entity_number = _place_underground_pair(
            grid,
            entities,
            1,
            (10, 10),
            (15, 10),
            FACTORIO_WEST,
            name="underground-belt",
        )
        self.assertEqual(entity_number, 1)
        self.assertEqual(entities, [])

    def test_place_belt_path_uses_underground_for_blocked_straight_run(self):
        grid = Grid(width=50, height=50)
        entities = []

        # Occupy the middle of a straight eastbound path.
        grid.occupy(11, 10, "blocker", [1, 1])
        grid.occupy(12, 10, "blocker", [1, 1])
        grid.occupy(13, 10, "blocker", [1, 1])
        grid.occupy(14, 10, "blocker", [1, 1])

        path = [(10, 10), (11, 10), (12, 10), (13, 10), (14, 10), (15, 10), (16, 10)]
        next_num = place_belt_path(grid, entities, 1, path)

        self.assertGreaterEqual(next_num, 4)
        names = [e["name"] for e in entities]
        self.assertIn("underground-belt", names)

        underground = [e for e in entities if e["name"] == "underground-belt"]
        self.assertEqual(len(underground), 2)
        self.assertEqual(underground[0]["type"], "input")
        self.assertEqual(underground[1]["type"], "output")
        self.assertEqual(underground[0]["direction"], FACTORIO_EAST)
        self.assertEqual(underground[1]["direction"], FACTORIO_EAST)

    def test_rejects_oversized_underground_span(self):
        grid = Grid(width=50, height=50)
        entities = []
        entity_number = _place_underground_pair(
            grid,
            entities,
            1,
            (10, 10),
            (17, 10),  # 6 underground tiles; too long for yellow underground belts.
            FACTORIO_EAST,
            name="underground-belt",
        )

        self.assertEqual(entity_number, 1)
        self.assertEqual(entities, [])


if __name__ == "__main__":
    unittest.main()
