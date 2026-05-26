"""Tests for belt/inserter/machine flow graph validation."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.constants import FACTORIO_EAST, FACTORIO_WEST, direction_for_inserter
from core.flow_connectivity import (
    build_flow_adjacency,
    build_tile_map,
    flow_reachable,
    validate_blueprint_flow,
)
from core.grid_env import Grid
from planners.machine_io import place_machine_io_block
from planners.production_planner import RateNode
from planners.stage_connector import connect_stages, stage_lanes_from_machines


class TestFlowConnectivity(unittest.TestCase):
    def test_machine_io_chain_reachable(self):
        grid = Grid(width=80, height=80)
        entities = []
        mx, my, w, h = 20, 20, 3, 3
        entity_number = place_machine_io_block(
            grid, entities, 1, mx, my, w, h, flow_direction=FACTORIO_EAST
        )
        self.assertGreater(entity_number, 1)

        tile_map = build_tile_map(entities)
        footprints = [("iron-plate", {(mx + dx, my + dy) for dx in range(w) for dy in range(h)})]
        adj = build_flow_adjacency(tile_map, entities, footprints)

        lane_y = my + h // 2
        input_belt = (mx - 3, lane_y)
        output_belt = (mx + w + 2, lane_y)
        input_drop = (mx, lane_y)

        self.assertTrue(flow_reachable({input_belt}, {input_drop}, adj))
        self.assertTrue(flow_reachable({(mx + w - 1, lane_y)}, {output_belt}, adj))

    def test_broken_inserter_direction_fails_validation(self):
        grid = Grid(width=80, height=80)
        entities = []
        mx, my, w, h = 20, 20, 3, 3
        place_machine_io_block(grid, entities, 1, mx, my, w, h, flow_direction=FACTORIO_EAST)

        for ent in entities:
            if ent.get("name") == "inserter":
                # East-flow blocks use WEST (pickup from belt); EAST is backwards.
                ent["direction"] = FACTORIO_EAST

        stage_machines = {"iron-plate": [(mx, my, w, h)]}
        nodes = {
            "iron-plate": RateNode(
                item="iron-plate",
                required_rate=10,
                recipe={},
                machine_count=1,
                dependencies=["iron-ore"],
            )
        }
        result = validate_blueprint_flow(entities, stage_machines, nodes)
        self.assertFalse(result.ok)
        self.assertTrue(
            any("pickup" in e.lower() or "fed" in e.lower() for e in result.errors),
            result.errors,
        )

    def test_stage_to_stage_flow_after_connect(self):
        grid = Grid(width=200, height=200)
        entities = []
        stage_machines = {
            "iron-plate": [(10, 10, 3, 3)],
            "iron-gear-wheel": [(40, 10, 3, 3)],
        }
        for machines in stage_machines.values():
            for mx, my, w, h in machines:
                grid.occupy(mx, my, "machine", [w, h])
                place_machine_io_block(
                    grid, entities, len(entities) + 1, mx, my, w, h, flow_direction=FACTORIO_EAST
                )

        nodes = {
            "iron-gear-wheel": RateNode(
                item="iron-gear-wheel",
                required_rate=10,
                recipe={},
                machine_count=1,
                dependencies=["iron-plate"],
            )
        }
        connect_stages(grid, entities, len(entities) + 1, stage_machines, nodes)

        result = validate_blueprint_flow(entities, stage_machines, nodes)
        self.assertTrue(result.ok, result.errors)

    def test_inserter_direction_matches_drop(self):
        inserter = (9, 13)
        drop = (10, 13)
        self.assertEqual(
            direction_for_inserter(inserter, drop),
            FACTORIO_WEST,
        )


if __name__ == "__main__":
    unittest.main()
