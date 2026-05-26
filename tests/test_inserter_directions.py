"""Tests for inserter blueprint direction (cardinals only)."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.constants import (
    FACTORIO_EAST,
    FACTORIO_NORTH,
    FACTORIO_SOUTH,
    FACTORIO_WEST,
    INSERTER_DIRECTIONS,
    direction_for_inserter,
    inserter_direction_for_display,
    inserter_pickup_tile,
)


class TestInserterDirections(unittest.TestCase):
    def test_faces_drop_tile(self):
        """Direction is from inserter toward the front (drop) tile."""
        cases = [
            ((0, 0), (1, 0), FACTORIO_EAST),
            ((1, 0), (0, 0), FACTORIO_WEST),
            ((0, 0), (0, 1), FACTORIO_SOUTH),
            ((0, 1), (0, 0), FACTORIO_NORTH),
        ]
        for inserter, drop, facing in cases:
            stored = direction_for_inserter(inserter, drop)
            self.assertIn(stored, INSERTER_DIRECTIONS)
            self.assertEqual(stored, facing)
            self.assertEqual(inserter_direction_for_display(stored), facing)

    def test_pickup_is_behind_inserter(self):
        """Pickup tile is behind the inserter (opposite of facing)."""
        inserter = (9, 13)
        drop = (10, 13)
        facing = direction_for_inserter(inserter, drop)
        self.assertEqual(facing, FACTORIO_EAST)
        self.assertEqual(inserter_pickup_tile(inserter, facing), (8, 13))

    def test_east_flow_io_block(self):
        """Belt west, machine/belt east — both inserters face east (dir 4)."""
        machine_x, machine_y, w, h = 10, 15, 3, 3
        lane_y = machine_y + h // 2
        input_inserter = (machine_x - 1, lane_y)
        output_inserter = (machine_x + w, lane_y)
        input_drop = (machine_x, lane_y)
        output_drop = (machine_x + w + 1, lane_y)
        belt_pickup = (machine_x - 2, lane_y)

        in_dir = direction_for_inserter(input_inserter, input_drop)
        out_dir = direction_for_inserter(output_inserter, output_drop)

        self.assertEqual(in_dir, FACTORIO_EAST)
        self.assertEqual(out_dir, FACTORIO_EAST)
        self.assertEqual(inserter_pickup_tile(input_inserter, in_dir), belt_pickup)
        self.assertEqual(
            inserter_pickup_tile(output_inserter, out_dir),
            (machine_x + w - 1, lane_y),
        )

    def test_in_game_cardinal_reference(self):
        """Directions from a real Factorio 2.0 blueprint (4 inserters, N/E/S/W)."""
        reference = {
            None: FACTORIO_NORTH,
            4: FACTORIO_EAST,
            8: FACTORIO_SOUTH,
            12: FACTORIO_WEST,
        }
        for exported, expected in reference.items():
            self.assertEqual(
                inserter_direction_for_display(exported),
                expected,
                f"direction {exported!r}",
            )


if __name__ == "__main__":
    unittest.main()
