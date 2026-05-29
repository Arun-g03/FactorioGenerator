"""Tests for splitter footprint and belt connection geometry."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.constants import FACTORIO_EAST, FACTORIO_NORTH
from core.splitter_geometry import (
    anchor_for_feed,
    splitter_flow_edges,
    splitter_footprint_size,
    splitter_layout,
)


class TestSplitterGeometry(unittest.TestCase):
    def test_east_footprint_is_2x1(self):
        self.assertEqual(splitter_footprint_size(FACTORIO_EAST), (2, 1))
        layout = splitter_layout((10, 20), FACTORIO_EAST)
        self.assertEqual(layout.footprint, frozenset({(10, 20), (11, 20)}))
        self.assertEqual(layout.input_belt, (9, 20))
        self.assertEqual(
            layout.output_belts, frozenset({(12, 19), (12, 21)})
        )

    def test_north_footprint_is_1x2(self):
        self.assertEqual(splitter_footprint_size(FACTORIO_NORTH), (1, 2))
        layout = splitter_layout((5, 5), FACTORIO_NORTH)
        self.assertEqual(layout.footprint, frozenset({(5, 5), (5, 6)}))

    def test_flow_edges_use_perpendicular_outputs(self):
        edges = splitter_flow_edges((10, 20), FACTORIO_EAST)
        dsts = {dst for _src, dst in edges}
        self.assertIn((12, 19), dsts)
        self.assertIn((12, 21), dsts)
        self.assertNotIn((12, 20), dsts)

    def test_anchor_for_feed_matches_placement(self):
        feed = (12, 20)
        anchor = anchor_for_feed(feed, FACTORIO_EAST)
        self.assertEqual(anchor, (13, 20))
        layout = splitter_layout(anchor, FACTORIO_EAST)
        self.assertEqual(layout.input_belt, feed)


if __name__ == "__main__":
    unittest.main()
