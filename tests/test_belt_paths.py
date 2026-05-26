"""Tests for belt path placement and corner directions."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.constants import (
    FACTORIO_EAST,
    FACTORIO_SOUTHEAST,
    FACTORIO_SOUTH,
    belt_direction_at_path_index,
)
from core.grid_env import Grid
from planners.stage_connector import connect_lane_to_lane, place_belt_path


class TestBeltPaths(unittest.TestCase):
    def test_corner_tile_uses_curve_direction(self):
        path = [(0, 0), (1, 0), (1, 1)]
        self.assertEqual(belt_direction_at_path_index(path, 0), FACTORIO_EAST)
        self.assertEqual(belt_direction_at_path_index(path, 1), FACTORIO_SOUTHEAST)
        self.assertEqual(belt_direction_at_path_index(path, 2), FACTORIO_SOUTH)

    def test_l_path_places_all_tiles(self):
        grid = Grid(width=30, height=30)
        entities = []
        path = [(10, 10), (11, 10), (12, 10), (12, 11), (12, 12)]
        place_belt_path(grid, entities, 1, path)
        belts = {
            (int(e["position"]["x"]), int(e["position"]["y"]))
            for e in entities
            if e.get("name") == "transport-belt"
        }
        for tile in path:
            self.assertIn(tile, belts, f"missing belt at {tile}")

    def test_connect_lane_includes_endpoints(self):
        grid = Grid(width=80, height=80)
        entities = []
        entities.append({
            "entity_number": 0,
            "name": "transport-belt",
            "position": {"x": 20, "y": 10},
            "direction": FACTORIO_EAST,
        })
        entities.append({
            "entity_number": 0,
            "name": "transport-belt",
            "position": {"x": 50, "y": 10},
            "direction": FACTORIO_EAST,
        })
        grid.occupy(20, 10, "transport-belt", [1, 1])
        grid.occupy(50, 10, "transport-belt", [1, 1])
        connect_lane_to_lane(
            grid,
            entities,
            1,
            producer_output=(20, 10),
            consumer_input=(50, 10),
        )
        belt_tiles = {
            (int(e["position"]["x"]), int(e["position"]["y"]))
            for e in entities
            if e.get("name") == "transport-belt"
        }
        for x in range(20, 51):
            self.assertIn((x, 10), belt_tiles, f"gap at ({x}, 10)")


if __name__ == "__main__":
    unittest.main()
