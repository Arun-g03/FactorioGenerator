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
    def test_faces_pickup_tile(self):
        """Direction is the pickup side (opposite of drop along the axis)."""
        cases = [
            ((0, 0), (1, 0), FACTORIO_WEST),
            ((1, 0), (0, 0), FACTORIO_EAST),
            ((0, 0), (0, 1), FACTORIO_NORTH),
            ((0, 1), (0, 0), FACTORIO_SOUTH),
        ]
        drop_arrow = {
            FACTORIO_WEST: FACTORIO_EAST,
            FACTORIO_EAST: FACTORIO_WEST,
            FACTORIO_NORTH: FACTORIO_SOUTH,
            FACTORIO_SOUTH: FACTORIO_NORTH,
        }
        for inserter, drop, pickup in cases:
            stored = direction_for_inserter(inserter, drop)
            self.assertIn(stored, INSERTER_DIRECTIONS)
            self.assertEqual(stored, pickup)
            self.assertEqual(inserter_direction_for_display(stored), drop_arrow[pickup])

    def test_pickup_is_inserter_front(self):
        """Pickup tile is on the side encoded by blueprint direction."""
        inserter = (9, 13)
        drop = (10, 13)
        facing = direction_for_inserter(inserter, drop)
        self.assertEqual(facing, FACTORIO_WEST)
        self.assertEqual(inserter_pickup_tile(inserter, facing), (8, 13))

    def test_east_flow_io_block(self):
        """Belt west, machine/belt east — both inserters pick up from the west (dir 12)."""
        machine_x, machine_y, w, h = 10, 15, 3, 3
        lane_y = machine_y + h // 2
        input_inserter = (machine_x - 1, lane_y)
        output_inserter = (machine_x + w, lane_y)
        input_drop = (machine_x, lane_y)
        output_drop = (machine_x + w + 1, lane_y)
        belt_pickup = (machine_x - 2, lane_y)

        in_dir = direction_for_inserter(input_inserter, input_drop)
        out_dir = direction_for_inserter(output_inserter, output_drop)

        self.assertEqual(in_dir, FACTORIO_WEST)
        self.assertEqual(out_dir, FACTORIO_WEST)
        self.assertEqual(inserter_direction_for_display(in_dir), FACTORIO_EAST)
        self.assertEqual(inserter_direction_for_display(out_dir), FACTORIO_EAST)
        self.assertEqual(inserter_pickup_tile(input_inserter, in_dir), belt_pickup)
        self.assertEqual(
            inserter_pickup_tile(output_inserter, out_dir),
            (machine_x + w - 1, lane_y),
        )

    def test_ui_arrow_opposite_of_pickup(self):
        """Preview arrows point at drop side (opposite of exported pickup direction)."""
        pickup_to_arrow = {
            None: FACTORIO_SOUTH,
            FACTORIO_EAST: FACTORIO_WEST,
            FACTORIO_SOUTH: FACTORIO_NORTH,
            FACTORIO_WEST: FACTORIO_EAST,
        }
        for pickup, arrow in pickup_to_arrow.items():
            self.assertEqual(
                inserter_direction_for_display(pickup),
                arrow,
                f"pickup {pickup!r}",
            )


if __name__ == "__main__":
    unittest.main()
