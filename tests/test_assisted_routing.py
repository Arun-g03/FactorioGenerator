"""Tests for assisted build routing."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.grid_env import Grid
from planners.assisted_routing import AssistedBuildState


def _load_recipes():
    with open(ROOT / "src" / "data" / "recipes.json", encoding="utf-8") as f:
        return json.load(f)


class TestAssistedRouting(unittest.TestCase):
    def setUp(self):
        self.recipes_data = _load_recipes()

    def _state(self) -> AssistedBuildState:
        return AssistedBuildState(grid=Grid(width=120, height=120), recipes_data=self.recipes_data)

    def test_place_machine_io_on_recipe_assign(self):
        state = self._state()
        furnace = state.place_machine("stone-furnace", 10, 10, (2, 2))
        self.assertIsNotNone(furnace)
        self.assertTrue(state.assign_recipe(furnace.id, "iron-plate"))
        self.assertIsNotNone(furnace.lanes)
        belts = [e for e in state.entities if e.get("name") == "transport-belt"]
        inserters = [e for e in state.entities if "inserter" in e.get("name", "")]
        self.assertEqual(len(belts), 0)
        self.assertGreater(len(inserters), 0)

    def test_connect_furnace_to_assembler(self):
        state = self._state()
        furnace = state.place_machine("stone-furnace", 5, 10, (2, 2))
        assembler = state.place_machine("assembling-machine-1", 40, 10, (3, 3))
        state.assign_recipe(furnace.id, "iron-plate")
        state.assign_recipe(assembler.id, "iron-gear-wheel")

        self.assertIsNotNone(furnace.lanes)
        self.assertIsNotNone(assembler.lanes)

        belt_tiles = {
            (int(e["position"]["x"]), int(e["position"]["y"]))
            for e in state.entities
            if e.get("name") == "transport-belt"
        }
        self.assertGreater(len(belt_tiles), 5)
        inserters = [e for e in state.entities if "inserter" in e.get("name", "")]
        self.assertGreaterEqual(len(inserters), 2)

    def test_full_reroute_after_recipe_change(self):
        state = self._state()
        machine = state.place_machine("assembling-machine-1", 20, 20, (3, 3))
        state.assign_recipe(machine.id, "iron-gear-wheel")
        count_after_first = len(state.entities)
        state.assign_recipe(machine.id, "iron-gear-wheel")
        self.assertEqual(count_after_first, len(state.entities))

    def test_machines_in_tile_rect_and_batch_remove(self):
        state = self._state()
        f = state.place_machine("stone-furnace", 5, 10, (2, 2))
        a = state.place_machine("assembling-machine-1", 40, 10, (3, 3))
        self.assertEqual(len(state.machines_in_tile_rect(5, 10, 6, 11)), 1)
        removed = state.remove_machines([f.id, a.id])
        self.assertEqual(removed, 2)
        self.assertEqual(len(state.machines), 0)

    def test_input_cell_routes_from_placed_chest(self):
        state = self._state()
        cell = state.place_input_cell(10, 20)
        state.assign_input_resources_bulk([cell.id], "iron-ore")
        furnace = state.place_machine("stone-furnace", 50, 20, (2, 2))
        state.assign_recipes_bulk([furnace.id], "iron-plate")
        belts = [
            e for e in state.entities if e.get("name") == "transport-belt"
        ]
        self.assertGreater(len(belts), 0)
        chest_belts = [
            (int(e["position"]["x"]), int(e["position"]["y"]))
            for e in belts
            if e["position"]["y"] == 20 and e["position"]["x"] >= 11
        ]
        self.assertGreater(len(chest_belts), 0)
        inserters = [e for e in state.entities if "inserter" in e.get("name", "")]
        self.assertGreater(len(inserters), 0)

    def test_one_input_splits_to_two_smelters(self):
        state = self._state()
        cell = state.place_input_cell(10, 20)
        state.assign_input_resources_bulk([cell.id], "iron-ore")
        f1 = state.place_machine("stone-furnace", 50, 20, (2, 2))
        f2 = state.place_machine("stone-furnace", 50, 40, (2, 2))
        state.assign_recipes_bulk([f1.id, f2.id], "iron-plate")

        belts = [e for e in state.entities if e.get("name") == "transport-belt"]
        belt_tiles = {(int(e["position"]["x"]), int(e["position"]["y"])) for e in belts}
        splitters = [e for e in state.entities if e.get("name") == "splitter"]

        self.assertGreater(len(splitters), 0)
        # Belts run on each furnace's input lane row (machine center y).
        self.assertTrue(any(x >= 15 and y == 21 for x, y in belt_tiles))
        self.assertTrue(any(x >= 15 and y == 41 for x, y in belt_tiles))

    def test_multiple_input_cells_feed_nearest_consumers(self):
        state = self._state()
        top = state.place_input_cell(10, 20)
        bottom = state.place_input_cell(10, 40)
        state.assign_input_resources_bulk([top.id, bottom.id], "iron-ore")

        f1 = state.place_machine("stone-furnace", 50, 20, (2, 2))
        f2 = state.place_machine("stone-furnace", 50, 40, (2, 2))
        state.assign_recipes_bulk([f1.id, f2.id], "iron-plate")

        belts = [e for e in state.entities if e.get("name") == "transport-belt"]
        belt_tiles = {(int(e["position"]["x"]), int(e["position"]["y"])) for e in belts}

        # Feed belts extend east from each input-cell row (chest y or furnace input lane).
        self.assertTrue(any(x >= 11 and y in (20, 21) for x, y in belt_tiles))
        self.assertTrue(any(x >= 11 and y in (40, 41) for x, y in belt_tiles))

    def test_assign_recipes_bulk(self):
        state = self._state()
        m1 = state.place_machine("stone-furnace", 5, 10, (2, 2))
        m2 = state.place_machine("stone-furnace", 15, 10, (2, 2))
        applied = state.assign_recipes_bulk([m1.id, m2.id], "iron-plate")
        self.assertEqual(applied, 2)
        self.assertEqual(m1.recipe_item, "iron-plate")
        self.assertEqual(m2.recipe_item, "iron-plate")

    def test_remove_machine_reroutes(self):
        state = self._state()
        f = state.place_machine("stone-furnace", 5, 10, (2, 2))
        a = state.place_machine("assembling-machine-1", 40, 10, (3, 3))
        state.assign_recipe(f.id, "iron-plate")
        state.assign_recipe(a.id, "iron-gear-wheel")
        belts_before = sum(1 for e in state.entities if e.get("name") == "transport-belt")
        state.remove_machine(a.id)
        belts_after = sum(1 for e in state.entities if e.get("name") == "transport-belt")
        self.assertLess(belts_after, belts_before)

    def test_output_cell_routes_to_placed_chest(self):
        state = self._state()
        furnace = state.place_machine("stone-furnace", 10, 20, (2, 2))
        state.assign_recipe(furnace.id, "iron-plate")
        cell = state.place_output_cell(55, 20)
        state.assign_output_products_bulk([cell.id], "iron-plate")
        belts = [
            e for e in state.entities if e.get("name") == "transport-belt"
        ]
        self.assertGreater(len(belts), 0)
        west_of_chest = [
            (int(e["position"]["x"]), int(e["position"]["y"]))
            for e in belts
            if e["position"]["y"] == 20 and e["position"]["x"] < 55
        ]
        self.assertGreater(len(west_of_chest), 0)

    def test_place_output_cell_sets_flag(self):
        state = self._state()
        cell = state.place_output_cell(30, 30)
        self.assertIsNotNone(cell)
        self.assertTrue(cell.is_output_cell)
        self.assertFalse(cell.is_input_cell)

    def test_output_cell_any_routes_latest_in_chain(self):
        state = self._state()
        furnace = state.place_machine("stone-furnace", 5, 10, (2, 2))
        assembler = state.place_machine("assembling-machine-1", 40, 10, (3, 3))
        state.assign_recipe(furnace.id, "iron-plate")
        state.assign_recipe(assembler.id, "iron-gear-wheel")
        cell = state.place_output_cell(70, 10)
        state.assign_output_products_bulk([cell.id], "any")
        self.assertEqual(cell.output_product, "any")
        belts = [e for e in state.entities if e.get("name") == "transport-belt"]
        self.assertGreater(len(belts), 0)
        west_of_chest = [
            (int(e["position"]["x"]), int(e["position"]["y"]))
            for e in belts
            if e["position"]["y"] == 10 and e["position"]["x"] < 70
        ]
        self.assertGreater(len(west_of_chest), 0)


if __name__ == "__main__":
    unittest.main()
