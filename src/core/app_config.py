"""Load and save user settings in config.json (repo root)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from core.constants import PYGAME_WINDOW_HEIGHT, PYGAME_WINDOW_WIDTH

logger = logging.getLogger(__name__)

# Repo root: src/core/app_config.py -> parents[2]
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"

MIN_WINDOW_WIDTH = 960
MIN_WINDOW_HEIGHT = 540


def load_config() -> dict:
    """Read config.json; returns empty dict if missing or invalid."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("Failed to load config: %s", e)
        return {}


def save_config(config: dict) -> None:
    """Write config.json, merging with existing keys."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    current = load_config()
    current.update(config)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=4)


def get_window_size(config: dict | None = None) -> tuple[int, int]:
    """Window size from config, or defaults from constants."""
    cfg = config if config is not None else load_config()
    width = cfg.get("window_width", PYGAME_WINDOW_WIDTH)
    height = cfg.get("window_height", PYGAME_WINDOW_HEIGHT)
    try:
        w, h = int(width), int(height)
    except (TypeError, ValueError):
        w, h = PYGAME_WINDOW_WIDTH, PYGAME_WINDOW_HEIGHT
    return max(MIN_WINDOW_WIDTH, w), max(MIN_WINDOW_HEIGHT, h)


def save_window_size(width: int, height: int) -> None:
    """Persist the current window dimensions."""
    save_config({"window_width": int(width), "window_height": int(height)})


def load_placement_settings(config: dict | None = None):
    """Placement tunables from config (rule-based + genetic)."""
    from core.placement_settings import bundle_from_config

    return bundle_from_config(config if config is not None else load_config())


def save_placement_settings(bundle) -> None:
    """Persist placement_settings section in config.json."""
    from core.placement_settings import bundle_to_config_dict

    save_config(bundle_to_config_dict(bundle))


def load_assisted_settings(config: dict | None = None):
    """Assisted Build tunables from config."""
    from core.assisted_settings import settings_from_config

    return settings_from_config(config if config is not None else load_config())


def save_assisted_settings(settings) -> None:
    """Persist assisted_build_settings section in config.json."""
    from core.assisted_settings import settings_to_config_dict

    save_config(settings_to_config_dict(settings))


def apply_factorio_paths(config: dict | None = None) -> None:
    """Apply Factorio install/graphics paths from config to constants."""
    from core import constants as constants_module

    cfg = config if config is not None else load_config()
    if "factorio_install_path" in cfg:
        constants_module.FACTORIO_INSTALL_PATH = cfg["factorio_install_path"]
        constants_module.FACTORIO_BASE_GRAPHICS_PATH = constants_module.get_factorio_graphics_path(
            cfg["factorio_install_path"]
        )
    elif "factorio_graphics_path" in cfg:
        constants_module.FACTORIO_BASE_GRAPHICS_PATH = cfg["factorio_graphics_path"]
