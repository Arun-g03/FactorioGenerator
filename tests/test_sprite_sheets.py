"""Sprite sheet frame extraction for multi-frame entity graphics."""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.constants import FACTORIO_BASE_GRAPHICS_PATH


class TestAssemblingMachineSpriteSheets(unittest.TestCase):
  EXPECTED_FRAME_SIZES = {
      "assembling-machine-1": (214, 226),
      "assembling-machine-2": (214, 218),
      "assembling-machine-3": (214, 237),
  }

  @classmethod
  def setUpClass(cls):
      if not FACTORIO_BASE_GRAPHICS_PATH.exists():
          raise unittest.SkipTest("Factorio graphics path not available")

  def test_first_animation_frame_extracted(self):
      os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
      import pygame

      pygame.init()
      from ui.sprite_loader import SpriteLoader

      loader = SpriteLoader()
      for name, expected in self.EXPECTED_FRAME_SIZES.items():
          sprite = loader.get_sprite(name)
          self.assertIsNotNone(sprite, msg=name)
          actual = (sprite.get_width(), sprite.get_height())
          self.assertEqual(actual, expected, msg=name)


if __name__ == "__main__":
    unittest.main()
