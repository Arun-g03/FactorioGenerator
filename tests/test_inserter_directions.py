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
)


class TestInserterDirections(unittest.TestCase):
    def test_cardinal_blueprint_values(self):
        """Stored directions are always one of the four cardinals."""
        cases = [
            ((0, 0), (1, 0), FACTORIO_EAST),
            ((1, 0), (0, 0), FACTORIO_WEST),
            ((0, 0), (0, 1), FACTORIO_SOUTH),
            ((0, 1), (0, 0), FACTORIO_NORTH),
        ]
        for pickup, drop, facing in cases:
            stored = direction_for_inserter(pickup, drop)
            self.assertIn(stored, INSERTER_DIRECTIONS)
            self.assertEqual(inserter_direction_for_display(stored), facing)

    def test_east_flow_io_block_directions(self):
        """Input picks west of inserter; output drops east — both face east."""
        machine_x, machine_y, w, h = 10, 15, 3, 3
        lane_y = machine_y + h // 2
        input_pickup = (machine_x - 2, lane_y)
        machine_center = (machine_x + w // 2, machine_y + h // 2)
        output_drop = (machine_x + w + 1, lane_y)

        in_dir = direction_for_inserter(input_pickup, machine_center)
        out_dir = direction_for_inserter(machine_center, output_drop)

        self.assertEqual(inserter_direction_for_display(in_dir), FACTORIO_EAST)
        self.assertEqual(inserter_direction_for_display(out_dir), FACTORIO_EAST)
        self.assertEqual(in_dir, FACTORIO_SOUTH)
        self.assertEqual(out_dir, FACTORIO_SOUTH)

    def test_display_round_trip(self):
        for facing in INSERTER_DIRECTIONS:
            stored = (facing + 2) % 8
            self.assertEqual(inserter_direction_for_display(stored), facing)


if __name__ == "__main__":
    unittest.main()
