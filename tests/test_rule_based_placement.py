"""Tests for network-first rule-based layout."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from planners.production_planner import RateNode
from planners.rule_based_placement import (
    NetworkLayoutCursor,
    compute_stage_depths,
    estimate_connection_cost,
    network_origin_for_stage,
    select_best_rule_candidate,
    RuleLayoutCandidate,
)
from planners.layout_fitness import LayoutFitnessBreakdown
from planners.stage_connector import stage_lanes_from_machines


class TestRuleBasedPlacement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SRC / "data" / "recipes.json", encoding="utf-8") as f:
            cls.recipes = json.load(f)

    def _nodes(self, items):
        nodes = {}
        for item in items:
            recipe = self.recipes["recipes"].get(item)
            if not recipe:
                continue
            nodes[item] = RateNode(
                item=item,
                required_rate=10,
                recipe=recipe,
                machine_count=1,
                dependencies=list(recipe.get("ingredients", {}).keys()),
            )
        return nodes

    def test_consumer_placed_near_producer_any_cardinal(self):
        nodes = self._nodes(["iron-plate", "iron-gear-wheel"])
        cursor = NetworkLayoutCursor()
        stage_lanes = {}

        plate_node = nodes["iron-plate"]
        px, py, _ = network_origin_for_stage(plate_node, nodes, stage_lanes, cursor)
        stage_lanes["iron-plate"] = stage_lanes_from_machines([(px, py, 2, 2)])

        gear_node = nodes["iron-gear-wheel"]
        gx, gy, _ = network_origin_for_stage(gear_node, nodes, stage_lanes, cursor)
        self.assertGreater(abs(gx - px) + abs(gy - py), 0)
        self.assertLess(abs(gx - px) + abs(gy - py), 40)

    def test_connection_cost_lower_when_aligned(self):
        nodes = self._nodes(["iron-plate", "iron-gear-wheel", "electronic-circuit"])
        cursor = NetworkLayoutCursor()
        stage_lanes = {}

        for item in ["iron-plate", "iron-gear-wheel", "electronic-circuit"]:
            node = nodes[item]
            x, y, flow = network_origin_for_stage(node, nodes, stage_lanes, cursor)
            w, h = node.recipe.get("machine_size", [3, 3])
            machines = [(x, y, w, h)]
            lanes = stage_lanes_from_machines(machines, flow)
            if lanes:
                stage_lanes[item] = lanes

        cost = estimate_connection_cost(stage_lanes, nodes)
        self.assertGreater(cost, 0)
        depths = compute_stage_depths(nodes)
        self.assertLess(depths["iron-plate"], depths["electronic-circuit"])

    def test_select_prefers_viable_candidate(self):
        viable = RuleLayoutCandidate(
            stage_y=0,
            fitness=LayoutFitnessBreakdown(total=60.0, is_viable=True),
            entities=[],
            entity_number=1,
            production_stages=[],
            stage_machines={},
            grid_occupied={},
        )
        broken = RuleLayoutCandidate(
            stage_y=0,
            fitness=LayoutFitnessBreakdown(
                total=90.0, is_viable=False, blockers=["overlap"]
            ),
            entities=[],
            entity_number=1,
            production_stages=[],
            stage_machines={},
            grid_occupied={},
        )
        best = select_best_rule_candidate([broken, viable])
        self.assertIs(best, viable)


if __name__ == "__main__":
    unittest.main()
