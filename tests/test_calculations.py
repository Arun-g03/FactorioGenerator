"""Tests for production rate calculations."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from planners.machine_placer.calculations import ProductionCalculator


class TestProductionCalculator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        recipes_path = SRC / "data" / "recipes.json"
        with open(recipes_path, encoding="utf-8") as f:
            cls.recipes_data = json.load(f)
        cls.calc = ProductionCalculator(cls.recipes_data)

    def test_furnace_iron_plate_rate(self):
        recipe = self.recipes_data["recipes"]["iron-plate"]
        rate = self.calc.get_items_per_minute(recipe)
        self.assertAlmostEqual(rate, 60.0 / 3.2, places=2)
        self.assertEqual(self.calc.machines_needed(recipe, 20), 2)

    def test_assembler_gear_rate(self):
        recipe = self.recipes_data["recipes"]["iron-gear-wheel"]
        rate = self.calc.get_items_per_minute(recipe)
        self.assertAlmostEqual(rate, 30.0, places=1)
        self.assertEqual(self.calc.machines_needed(recipe, 30), 1)


if __name__ == "__main__":
    unittest.main()
