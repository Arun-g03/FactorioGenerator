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

# Factorio blueprint / map-exchange directions (0–7, 45° steps).
# See https://wiki.factorio.com/Types/Direction
DIRECTIONS = {
    "north": 0,
    "northeast": 1,
    "east": 2,
    "southeast": 3,
    "south": 4,
    "southwest": 5,
    "west": 6,
    "northwest": 7,
}

FACTORIO_NORTH = 0
FACTORIO_NORTHEAST = 1
FACTORIO_EAST = 2
FACTORIO_SOUTHEAST = 3
FACTORIO_SOUTH = 4
FACTORIO_SOUTHWEST = 5
FACTORIO_WEST = 6
FACTORIO_NORTHWEST = 7


# Inserters only use cardinals (0, 2, 4, 6) in blueprints.
INSERTER_DIRECTIONS = (
    FACTORIO_NORTH,
    FACTORIO_EAST,
    FACTORIO_SOUTH,
    FACTORIO_WEST,
)

# Factorio blueprint inserter direction is rotated 90° CW vs pick-up→drop facing.
INSERTER_BLUEPRINT_ROTATION_OFFSET = 2


def direction_for_flow(from_pos, to_pos):
    """Factorio entity direction for belt flow from one tile toward another."""
    fx, fy = from_pos
    tx, ty = to_pos
    dx = tx - fx
    dy = ty - fy
    if dx == 0 and dy == 0:
        return FACTORIO_EAST
    if abs(dx) >= abs(dy):
        if dx > 0:
            return FACTORIO_EAST
        if dx < 0:
            return FACTORIO_WEST
    if dy > 0:
        return FACTORIO_SOUTH
    if dy < 0:
        return FACTORIO_NORTH
    return FACTORIO_EAST


def direction_for_inserter(pickup_pos, drop_pos):
    """
    Blueprint direction for an inserter (cardinals only).

    The inserter faces drop_pos and picks from the opposite side of pickup_pos.
    Stored values include INSERTER_BLUEPRINT_ROTATION_OFFSET so pasted blueprints
    match in-game arm orientation.
    """
    facing = direction_for_flow(pickup_pos, drop_pos)
    return (facing + INSERTER_BLUEPRINT_ROTATION_OFFSET) % 8


def inserter_direction_for_display(blueprint_direction):
    """Map stored inserter direction to pick-up→drop facing for UI arrows."""
    if blueprint_direction is None:
        return FACTORIO_EAST
    return (int(blueprint_direction) - INSERTER_BLUEPRINT_ROTATION_OFFSET) % 8

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

