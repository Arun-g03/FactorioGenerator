"""Tests for assisted routing optimization pass and scoring rules."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.grid_env import Grid
from planners.assisted_routing import AssistedBuildState
from planners.belt_network.link_graph import PRIORITY_STAGE, BeltLink
from planners.belt_network.optimize import (
    BELT_COST,
    SPLITTER_MISSING_PENALTY,
    SPLITTER_WHEN_NEEDED_BONUS,
    evaluate_routing_quality,
    fanout_groups_from_links,
    group_order_for_variant,
)


def _load_recipes():
    with open(ROOT / "src" / "data" / "recipes.json", encoding="utf-8") as f:
        return json.load(f)


class TestOptimizationScoring(unittest.TestCase):
    def test_fanout_groups_detected(self):
        links = [
            BeltLink(
                link_id="a",
                item="iron-plate",
                source=(10, 20),
                sink=(48, 21),
                kind="base_feed",
                group_key="base:iron-ore:10,20",
                priority=100,
            ),
            BeltLink(
                link_id="b",
                item="iron-plate",
                source=(10, 20),
                sink=(48, 41),
                kind="base_feed",
                group_key="base:iron-ore:10,20",
                priority=100,
            ),
        ]
        expected = fanout_groups_from_links(links)
        self.assertEqual(len(expected), 1)
        self.assertEqual(expected["base:iron-ore:10,20"], (10, 20))

    def test_fewer_belts_lower_cost_component(self):
        links = []
        stage_machines = {}
        nodes = {}
        many = [{"name": "transport-belt", "position": {"x": i, "y": 10}} for i in range(20)]
        few = [{"name": "transport-belt", "position": {"x": i, "y": 10}} for i in range(8)]
        m_many = evaluate_routing_quality(many, links, stage_machines, nodes)
        m_few = evaluate_routing_quality(few, links, stage_machines, nodes)
        self.assertLess(m_few.belt_count, m_many.belt_count)
        self.assertGreater(
            -m_few.belt_count * BELT_COST, -m_many.belt_count * BELT_COST
        )

    def test_missing_splitter_penalized(self):
        links = [
            BeltLink(
                link_id="a",
                item="x",
                source=(10, 20),
                sink=(40, 21),
                kind="stage",
                group_key="g1",
                priority=PRIORITY_STAGE,
            ),
            BeltLink(
                link_id="b",
                item="x",
                source=(10, 20),
                sink=(40, 41),
                kind="stage",
                group_key="g1",
                priority=PRIORITY_STAGE,
            ),
        ]
        base_belts = 10
        entities_no_splitter = [
            {"name": "transport-belt", "position": {"x": i, "y": 20}}
            for i in range(base_belts)
        ]
        from core.constants import FACTORIO_EAST

        entities_with_splitter = entities_no_splitter + [
            {
                "name": "splitter",
                "position": {"x": 11, "y": 20},
                "direction": FACTORIO_EAST,
            }
        ]
        stage_machines = {}
        nodes = {}
        without = evaluate_routing_quality(
            entities_no_splitter, links, stage_machines, nodes
        )
        with_sp = evaluate_routing_quality(
            entities_with_splitter, links, stage_machines, nodes
        )
        self.assertEqual(without.fanout_groups_expected, 1)
        self.assertEqual(without.fanout_groups_satisfied, 0)
        self.assertEqual(with_sp.fanout_groups_satisfied, 1)
        # One extra splitter costs one belt equivalent at most; fan-out bonus should win.
        belt_delta = (with_sp.belt_count - without.belt_count) * BELT_COST
        self.assertGreaterEqual(
            SPLITTER_WHEN_NEEDED_BONUS - belt_delta,
            SPLITTER_MISSING_PENALTY // 2,
        )


class TestOptimizationPass(unittest.TestCase):
    def test_group_order_variants_differ(self):
        links = [
            BeltLink(
                link_id="a",
                item="iron-plate",
                source=(0, 0),
                sink=(1, 0),
                kind="stage",
                group_key="stage:1,0",
                priority=PRIORITY_STAGE,
            ),
            BeltLink(
                link_id="b",
                item="iron-plate",
                source=(0, 0),
                sink=(1, 1),
                kind="stage",
                group_key="stage:2,0",
                priority=PRIORITY_STAGE,
            ),
        ]
        o0 = group_order_for_variant(links, 0)
        o1 = group_order_for_variant(links, 1)
        self.assertEqual(len(o0), 2)
        self.assertEqual(o0[::-1], o1)

    def test_optimization_pass_runs_on_simple_layout(self):
        state = AssistedBuildState(
            grid=Grid(width=120, height=120), recipes_data=_load_recipes()
        )
        f = state.place_machine("stone-furnace", 5, 10, (2, 2))
        a = state.place_machine("assembling-machine-1", 40, 10, (3, 3))
        state.assign_recipe(f.id, "iron-plate")
        state.assign_recipe(a.id, "iron-gear-wheel")
        result = state.optimization_pass(max_variants=2)
        self.assertIsNotNone(result.message)
        self.assertGreater(result.belts_after, 0)

    def test_fanout_layout_prefers_splitter(self):
        state = AssistedBuildState(
            grid=Grid(width=120, height=120), recipes_data=_load_recipes()
        )
        cell = state.place_input_cell(10, 20)
        state.assign_input_resources_bulk([cell.id], "iron-ore")
        f1 = state.place_machine("stone-furnace", 50, 20, (2, 2))
        f2 = state.place_machine("stone-furnace", 50, 40, (2, 2))
        state.assign_recipes_bulk([f1.id, f2.id], "iron-plate")
        result = state.optimization_pass(max_variants=4)
        self.assertGreaterEqual(result.splitters_after, 1)


class TestOptimizationSearch(unittest.TestCase):
    def _simple_state(self) -> AssistedBuildState:
        state = AssistedBuildState(
            grid=Grid(width=120, height=120), recipes_data=_load_recipes()
        )
        f = state.place_machine("stone-furnace", 5, 10, (2, 2))
        a = state.place_machine("assembling-machine-1", 40, 10, (3, 3))
        state.assign_recipe(f.id, "iron-plate")
        state.assign_recipe(a.id, "iron-gear-wheel")
        return state

    def test_start_returns_false_without_recipes(self):
        state = AssistedBuildState(
            grid=Grid(width=120, height=120), recipes_data=_load_recipes()
        )
        state.place_machine("stone-furnace", 5, 10, (2, 2))
        self.assertFalse(state.start_optimization_search(stale_limit=3))

    def test_search_step_stops_at_stale_limit(self):
        state = self._simple_state()
        self.assertTrue(state.start_optimization_search(stale_limit=2, max_iterations=0))
        steps = 0
        while state.optimization_search_active and steps < 50:
            status = state.optimization_search_step()
            steps += 1
            if not status.continue_search:
                break
        self.assertFalse(state.optimization_search_active)
        self.assertLessEqual(steps, 50)
        self.assertIsNotNone(state.last_optimization)

    def test_stop_applies_best_and_clears_active(self):
        state = self._simple_state()
        self.assertTrue(state.start_optimization_search(stale_limit=100))
        state.optimization_search_step()
        state.stop_optimization_search()
        self.assertFalse(state.optimization_search_active)
        self.assertIsNotNone(state.last_optimization)

    def test_layout_edit_stops_search(self):
        state = self._simple_state()
        self.assertTrue(state.start_optimization_search(stale_limit=100))
        furnace = state.machines[0]
        state.assign_recipe(furnace.id, "iron-plate")
        self.assertFalse(state.optimization_search_active)


if __name__ == "__main__":
    unittest.main()
