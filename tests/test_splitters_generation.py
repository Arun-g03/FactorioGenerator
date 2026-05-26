"""Tests that splitters are placed only when routing requires fan-out."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.grid_env import Grid
from planners.stage_connector import (
    _dedupe_connection_requests,
    _needs_splitter_fanout,
    connect_stages,
)


class _Node:
    def __init__(self, dependencies):
        self.dependencies = dependencies


def _occupy_machines(grid, stage_machines):
    for machines in stage_machines.values():
        for mx, my, w, h in machines:
            grid.occupy(mx, my, "machine", [w, h])


class TestSplittersGeneration(unittest.TestCase):
    def test_needs_splitter_fanout_helpers(self):
        req_a = {
            "consumer_item": "gear",
            "consumer_input_start": (50, 10),
            "target_y": 10,
            "dep": "iron-plate",
        }
        req_b = {
            "consumer_item": "circuit",
            "consumer_input_start": (70, 10),
            "target_y": 10,
            "dep": "iron-plate",
        }
        dup = dict(req_a)

        self.assertFalse(_needs_splitter_fanout([req_a]))
        self.assertTrue(_needs_splitter_fanout([req_a, req_b]))
        self.assertFalse(_needs_splitter_fanout(_dedupe_connection_requests([req_a, dup])))

    def test_no_splitter_on_linear_chain(self):
        grid = Grid(width=200, height=200)
        entities = []
        stage_machines = {
            "iron-plate": [(10, 10, 3, 3)],
            "gear": [(40, 10, 3, 3)],
        }
        _occupy_machines(grid, stage_machines)
        nodes = {"gear": _Node(["iron-plate"])}

        connect_stages(grid, entities, 1, stage_machines, nodes)

        splitters = [e for e in entities if e.get("name") == "splitter"]
        self.assertEqual(splitters, [])

    def test_splitter_only_when_one_producer_feeds_multiple_stages(self):
        grid = Grid(width=200, height=200)
        entities = []
        stage_machines = {
            "iron-plate": [(10, 10, 3, 3)],
            "copper-plate": [(30, 10, 3, 3)],
            "gear": [(50, 10, 3, 3)],
            "circuit": [(70, 10, 3, 3)],
        }
        _occupy_machines(grid, stage_machines)
        nodes = {
            "gear": _Node(["iron-plate", "copper-plate"]),
            "circuit": _Node(["copper-plate", "iron-plate"]),
        }

        connect_stages(grid, entities, 1, stage_machines, nodes)

        splitters = [e for e in entities if e.get("name") == "splitter"]
        self.assertGreaterEqual(len(splitters), 1)

    def test_no_splitter_when_two_ingredients_one_consumer(self):
        """Two producers → one consumer uses separate lanes, not a splitter."""
        grid = Grid(width=200, height=200)
        entities = []
        stage_machines = {
            "iron-plate": [(10, 10, 3, 3)],
            "copper-plate": [(30, 10, 3, 3)],
            "gear": [(50, 10, 3, 3)],
        }
        _occupy_machines(grid, stage_machines)
        nodes = {"gear": _Node(["iron-plate", "copper-plate"])}

        connect_stages(grid, entities, 1, stage_machines, nodes)

        splitters = [e for e in entities if e.get("name") == "splitter"]
        self.assertEqual(splitters, [])


if __name__ == "__main__":
    unittest.main()
