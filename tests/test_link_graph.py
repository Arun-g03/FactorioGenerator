"""Tests for belt network link graph construction."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from planners.assisted_routing import (
    rate_nodes_from_machines,
    stage_machines_from_placed,
)
from planners.belt_network.link_graph import build_link_graph, sort_links
from planners.assisted_routing import AssistedBuildState, PlacedMachine
from core.grid_env import Grid


def _load_recipes():
    with open(ROOT / "src" / "data" / "recipes.json", encoding="utf-8") as f:
        return json.load(f)


class TestLinkGraph(unittest.TestCase):
    def test_stage_and_base_links_ordered(self):
        recipes = _load_recipes()
        state = AssistedBuildState(grid=Grid(width=120, height=120), recipes_data=recipes)
        cell = state.place_input_cell(10, 20)
        state.assign_input_resources_bulk([cell.id], "iron-ore")
        f1 = state.place_machine("stone-furnace", 50, 20, (2, 2))
        f2 = state.place_machine("stone-furnace", 50, 40, (2, 2))
        state.assign_recipes_bulk([f1.id, f2.id], "iron-plate")
        a = state.place_machine("assembling-machine-1", 80, 20, (3, 3))
        state.assign_recipes_bulk([a.id], "iron-gear-wheel")

        nodes = rate_nodes_from_machines(state.machines, recipes)
        stage_machines = stage_machines_from_placed(state.machines)
        input_sources = {cell.input_resource: [cell.position]}
        links = sort_links(
            build_link_graph(
                stage_machines,
                nodes,
                input_sources=input_sources,
                output_sinks=None,
            )
        )
        kinds = [link.kind for link in links]
        self.assertIn("base_feed", kinds)
        self.assertIn("stage", kinds)
        base_links = [link for link in links if link.kind == "base_feed"]
        self.assertGreaterEqual(len(base_links), 2)
        self.assertTrue(all(link.group_key.startswith("base:iron-ore:") for link in base_links))
        stage_links = [link for link in links if link.kind == "stage"]
        self.assertGreaterEqual(len(stage_links), 1)
        priorities = [link.priority for link in links]
        self.assertEqual(priorities, sorted(priorities))

    def test_fanout_group_key_shared(self):
        recipes = _load_recipes()
        state = AssistedBuildState(grid=Grid(width=120, height=120), recipes_data=recipes)
        cell = state.place_input_cell(10, 20)
        state.assign_input_resources_bulk([cell.id], "iron-ore")
        f1 = state.place_machine("stone-furnace", 50, 20, (2, 2))
        f2 = state.place_machine("stone-furnace", 50, 40, (2, 2))
        state.assign_recipes_bulk([f1.id, f2.id], "iron-plate")

        nodes = rate_nodes_from_machines(state.machines, recipes)
        stage_machines = stage_machines_from_placed(state.machines)
        links = build_link_graph(
            stage_machines,
            nodes,
            input_sources={"iron-ore": [cell.position]},
        )
        base = [link for link in links if link.kind == "base_feed"]
        group_keys = {link.group_key for link in base}
        self.assertEqual(len(group_keys), 1)
        self.assertEqual(len(base), 2)


if __name__ == "__main__":
    unittest.main()
