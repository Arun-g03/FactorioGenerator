import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.blueprintEncoder import _entity_footprint


class TestEntityFootprint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        recipes_path = ROOT / "src" / "data" / "recipes.json"
        with open(recipes_path, encoding="utf-8") as f:
            cls.recipes_data = json.load(f)

        buildings_path = ROOT / "src" / "data" / "buildngs.json"
        with open(buildings_path, encoding="utf-8") as f:
            cls.buildings = json.load(f)["buildings"]

    def test_stone_furnace_defaults_to_2x2(self):
        entity = {"name": "stone-furnace", "position": {"x": 0, "y": 0}}
        self.assertEqual(_entity_footprint(entity, self.recipes_data), (2, 2))

    def test_entity_size_field_overrides_lookup(self):
        entity = {
            "name": "stone-furnace",
            "position": {"x": 0, "y": 0},
            "size": [3, 3],
        }
        self.assertEqual(_entity_footprint(entity, self.recipes_data), (3, 3))

    def test_buildings_json_sizes_match_footprint_for_machines(self):
        for name, info in self.buildings.items():
            if info.get("type") not in ("smelting", "assembly", "chemical", "nuclear"):
                continue
            entity = {"name": name, "position": {"x": 0, "y": 0}, "size": info["size"]}
            self.assertEqual(
                tuple(info["size"]),
                _entity_footprint(entity, self.recipes_data),
                msg=name,
            )


if __name__ == "__main__":
    unittest.main()
