"""Tests for network router pathfinding and materialization."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.constants import FACTORIO_EAST
from core.grid_env import Grid
from planners.belt_network.link_graph import BeltLink
from planners.belt_network.occupancy import RoutingOccupancy
from planners.belt_network.pathfinder import BeltPathfinder, RouteConflict
from planners.belt_network.materialize import materialize_single_link
from planners.stage_connector import place_belt_path


class TestNetworkPathfinder(unittest.TestCase):
    def test_reuses_same_item_belt(self):
        grid = Grid(width=40, height=40)
        grid.occupy(10, 10, "transport-belt", [1, 1])
        grid.mark_resource_lane(10, 10, "iron-ore")
        occupancy = RoutingOccupancy(grid)
        pf = BeltPathfinder(occupancy)
        path = pf.shortest_path((8, 10), (12, 10), "iron-ore")
        self.assertIsNotNone(path)
        self.assertIn((10, 10), path)

    def test_blocks_other_item_belt(self):
        grid = Grid(width=40, height=40)
        grid.occupy(10, 10, "transport-belt", [1, 1])
        grid.mark_resource_lane(10, 10, "copper-ore")
        occupancy = RoutingOccupancy(grid)
        pf = BeltPathfinder(occupancy)
        path = pf.shortest_path((8, 10), (12, 10), "iron-ore")
        if path:
            self.assertNotIn((10, 10), path)

    def test_empty_only_manhattan_skips_hard_tile(self):
        grid = Grid(width=40, height=40)
        grid.occupy(11, 10, "stone-furnace", [2, 2])
        occupancy = RoutingOccupancy(grid)
        pf = BeltPathfinder(occupancy)
        path = pf._empty_only_manhattan((8, 10), (14, 10), "iron-plate")
        self.assertIsNone(path)


class TestMaterializeLink(unittest.TestCase):
    def test_materialize_places_belts(self):
        grid = Grid(width=60, height=60)
        entities = []
        occupancy = RoutingOccupancy(grid)
        link = BeltLink(
            link_id="t1",
            item="iron-plate",
            source=(5, 10),
            sink=(20, 10),
            kind="stage",
            group_key="stage:5,10",
            priority=200,
        )
        materialize_single_link(grid, entities, 1, occupancy, link)
        belts = [e for e in entities if e.get("name") == "transport-belt"]
        self.assertGreater(len(belts), 3)


if __name__ == "__main__":
    unittest.main()
