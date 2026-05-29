"""Sprite name mapping for directional entities."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.constants import FACTORIO_EAST, FACTORIO_NORTH
from ui.sprite_mapper import SpriteMapper


class TestSpriteMapper(unittest.TestCase):
    def setUp(self):
        self.mapper = SpriteMapper()

    def test_splitter_uses_direction_suffix(self):
        self.assertEqual(
            self.mapper.get_sprite_name("splitter", FACTORIO_EAST),
            "splitter-east",
        )
        self.assertEqual(
            self.mapper.get_sprite_name("splitter", FACTORIO_NORTH),
            "splitter-north",
        )

    def test_splitter_default_suffix_when_direction_missing(self):
        self.assertEqual(self.mapper.get_sprite_name("splitter", None), "splitter-east")


if __name__ == "__main__":
    unittest.main()
