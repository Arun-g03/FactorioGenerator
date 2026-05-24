from enum import Enum

# Production targets and planner logic use items per minute ("min") or per second ("sec").
PRODUCTION_RATE_UNIT = "min"


class GenerationMode(Enum):
    """How far upstream to build when generating a blueprint."""

    ASSEMBLER_ONLY = "assembler_only"
    FULL_CHAIN = "full_chain"


class PlacementStrategy(Enum):
    """How machine positions are chosen on the grid."""

    RULE_BASED = "rule_based"
    GENETIC = "genetic"


# Yellow transport belt: 15 items/s
TRANSPORT_BELT_THROUGHPUT_PER_MIN = 15 * 60

PRODUCTION_TARGETS = {
   "inserter": 20  # items per minute
}


def production_rate_suffix():
    """Display suffix for the active production rate unit (e.g. '/min')."""
    return f"/{PRODUCTION_RATE_UNIT}"

BASE_MATERIALS = {"iron-ore", "copper-ore", "coal", "water", "crude-oil", "stone"}

DIRECTIONS = {
    "north": 0,
    "east": 4,
    "south": 8,
    "west": 12,
}

FACTORIO_NORTH = 0
FACTORIO_EAST = 4
FACTORIO_SOUTH = 8
FACTORIO_WEST = 12


def direction_for_flow(from_pos, to_pos):
    """Factorio entity direction for belt/inserter flow from one tile toward another."""
    fx, fy = from_pos
    tx, ty = to_pos
    if tx > fx:
        return FACTORIO_EAST
    if tx < fx:
        return FACTORIO_WEST
    if ty > fy:
        return FACTORIO_SOUTH
    if ty < fy:
        return FACTORIO_NORTH
    return FACTORIO_EAST

# Pygame visualization settings
PYGAME_WINDOW_WIDTH = 1280
PYGAME_WINDOW_HEIGHT = 720
PYGAME_TILE_SIZE = 64  # Size of each tile in pixels

# Factorio installation path (base directory)
# Users should provide the root Factorio installation directory
# The tool will automatically append: data/base/graphics/entity
# Windows Steam default:
FACTORIO_INSTALL_PATH = r"C:\Program Files (x86)\Steam\steamapps\common\Factorio"
# Alternative paths:
# Windows GOG: C:\GOG Games\Factorio
# Linux Steam: ~/.steam/steam/steamapps/common/Factorio
# Mac: ~/Library/Application Support/Steam/steamapps/common/Factorio

def get_factorio_graphics_path(base_path):
    """Get the full graphics path from the base Factorio installation path."""
    from pathlib import Path
    return str(Path(base_path) / "data" / "base" / "graphics" / "entity")

# Default full graphics path (for backward compatibility)
FACTORIO_BASE_GRAPHICS_PATH = get_factorio_graphics_path(FACTORIO_INSTALL_PATH)

# Entity folders under graphics/entity with dedicated sprite loading logic
BELT_ENTITIES = ("transport-belt", "fast-transport-belt", "express-transport-belt")
UNDERGROUND_BELT_ENTITIES = ("underground-belt", "fast-underground-belt", "express-underground-belt")
INSERTER_ENTITIES = (
    "inserter",
    "fast-inserter",
    "long-handed-inserter",
    "burner-inserter",
    "bulk-inserter",
)

