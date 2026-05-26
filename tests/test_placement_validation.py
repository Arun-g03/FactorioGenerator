"""Rule vs genetic placement comparison (validation harness)."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.constants import GenerationMode
from planners.placement_validation import compare_placement_strategies


class TestPlacementValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SRC / "data" / "recipes.json", encoding="utf-8") as f:
            cls.recipes = json.load(f)

    def test_rule_based_viable_for_inserter_chain(self):
        from core.constants import PlacementStrategy
        from planners.placement_validation import _run_planner

        rule = _run_planner(
            {"inserter": 20},
            self.recipes,
            GenerationMode.FULL_CHAIN,
            PlacementStrategy.RULE_BASED,
        )
        self.assertTrue(rule.is_viable, rule.blockers)
        self.assertGreater(rule.entity_count, 0)

    def test_compare_rule_and_genetic_both_run(self):
        results = compare_placement_strategies(
            {"iron-gear-wheel": 30},
            self.recipes,
            GenerationMode.FULL_CHAIN,
            genetic_generations_cap=25,
        )
        self.assertIn("rule_based", results)
        self.assertIn("genetic", results)
        self.assertTrue(results["rule_based"].is_viable, results["rule_based"].blockers)


if __name__ == "__main__":
    unittest.main()
