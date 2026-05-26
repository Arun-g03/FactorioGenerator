"""Constants for the Factorio Blueprint Generator."""

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

# ---------------------------------------------------------------------------
# Factorio 2.0 directions (defines.direction — values doubled vs 1.1).
# Verified in-game: N=0 (omitted in JSON), E=4, S=8, W=12.
# See wiki Blueprint_string_format and 2.0 mod porting guide.
# ---------------------------------------------------------------------------
FACTORIO_BLUEPRINT_VERSION = 562949958402048

DIRECTIONS = {
    "north": 0,
    "northeast": 2,
    "east": 4,
    "southeast": 6,
    "south": 8,
    "southwest": 10,
    "west": 12,
    "northwest": 14,
}

# Named constants (same values as DIRECTIONS; use for readable imports).
FACTORIO_NORTH = DIRECTIONS["north"]
FACTORIO_NORTHEAST = DIRECTIONS["northeast"]
FACTORIO_EAST = DIRECTIONS["east"]
FACTORIO_SOUTHEAST = DIRECTIONS["southeast"]
FACTORIO_SOUTH = DIRECTIONS["south"]
FACTORIO_SOUTHWEST = DIRECTIONS["southwest"]
FACTORIO_WEST = DIRECTIONS["west"]
FACTORIO_NORTHWEST = DIRECTIONS["northwest"]

CARDINAL_NAMES = ("north", "east", "south", "west")

# Blueprint cardinals used by inserters and belt flow helpers.
CARDINAL_DIRECTIONS = tuple(DIRECTIONS[name] for name in CARDINAL_NAMES)
INSERTER_DIRECTIONS = CARDINAL_DIRECTIONS

# Grid offset from an entity tile to its front neighbor (inserter pickup / belt flow).
DIRECTION_FRONT_OFFSET = {
    FACTORIO_NORTH: (0, -1),
    FACTORIO_EAST: (1, 0),
    FACTORIO_SOUTH: (0, 1),
    FACTORIO_WEST: (-1, 0),
}

# Belt curve sprites (incoming flow -> outgoing flow at a 90° path vertex).
BELT_CORNER_DIRECTIONS = {
    (FACTORIO_EAST, FACTORIO_NORTH): FACTORIO_NORTHWEST,
    (FACTORIO_EAST, FACTORIO_SOUTH): FACTORIO_SOUTHEAST,
    (FACTORIO_WEST, FACTORIO_NORTH): FACTORIO_NORTHEAST,
    (FACTORIO_WEST, FACTORIO_SOUTH): FACTORIO_SOUTHWEST,
    (FACTORIO_NORTH, FACTORIO_EAST): FACTORIO_NORTHEAST,
    (FACTORIO_NORTH, FACTORIO_WEST): FACTORIO_NORTHWEST,
    (FACTORIO_SOUTH, FACTORIO_EAST): FACTORIO_SOUTHEAST,
    (FACTORIO_SOUTH, FACTORIO_WEST): FACTORIO_SOUTHWEST,
}

BELT_CORNER_SPRITE_SUFFIX = {
    (FACTORIO_EAST, FACTORIO_NORTH): "east-to-north",
    (FACTORIO_EAST, FACTORIO_SOUTH): "east-to-south",
    (FACTORIO_WEST, FACTORIO_NORTH): "west-to-north",
    (FACTORIO_WEST, FACTORIO_SOUTH): "west-to-south",
    (FACTORIO_NORTH, FACTORIO_EAST): "north-to-east",
    (FACTORIO_NORTH, FACTORIO_WEST): "north-to-west",
    (FACTORIO_SOUTH, FACTORIO_EAST): "south-to-east",
    (FACTORIO_SOUTH, FACTORIO_WEST): "south-to-west",
}

# Pygame sprite suffix for straight belts and inserter platforms.
CARDINAL_DIRECTION_SUFFIX = {
    None: "north",
    FACTORIO_NORTH: "north",
    FACTORIO_EAST: "east",
    FACTORIO_SOUTH: "south",
    FACTORIO_WEST: "west",
}

BELT_DIRECTION_SUFFIX = dict(CARDINAL_DIRECTION_SUFFIX)
for corner_key, blueprint_dir in BELT_CORNER_DIRECTIONS.items():
    BELT_DIRECTION_SUFFIX[blueprint_dir] = BELT_CORNER_SPRITE_SUFFIX[corner_key]

# Screen-space unit vectors for UI arrows (y increases downward on screen).
CARDINAL_ARROW_VECTOR = {
    "north": (0, -1),
    "east": (1, 0),
    "south": (0, 1),
    "west": (-1, 0),
}


def direction_sprite_suffix(direction):
    """Map a Factorio blueprint direction to a sprite suffix (straight or curve)."""
    if direction in BELT_DIRECTION_SUFFIX:
        return BELT_DIRECTION_SUFFIX[direction]
    return CARDINAL_DIRECTION_SUFFIX.get(direction, "east")


def belt_direction_at_path_index(path: list[tuple[int, int]], index: int) -> int:
    """
    Blueprint direction for a belt on ``path[index]``.

    Straight segments use the segment cardinal; 90° vertices use a diagonal curve.
    """
    if len(path) < 2:
        return FACTORIO_EAST
    if index <= 0:
        return direction_for_flow(path[0], path[1])
    if index >= len(path) - 1:
        return direction_for_flow(path[-2], path[-1])
    in_dir = direction_for_flow(path[index - 1], path[index])
    out_dir = direction_for_flow(path[index], path[index + 1])
    if in_dir == out_dir:
        return out_dir
    return BELT_CORNER_DIRECTIONS.get((in_dir, out_dir), out_dir)


def direction_arrow_vector(direction):
    """Unit (dx, dy) for drawing an inserter flow arrow in the Pygame preview."""
    suffix = direction_sprite_suffix(direction)
    dx, dy = CARDINAL_ARROW_VECTOR[suffix]
    length = max((dx * dx + dy * dy) ** 0.5, 1.0)
    return dx / length, dy / length


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



def direction_for_inserter(inserter_pos, drop_pos):
    """
    Blueprint direction for an inserter (Factorio 2.0 cardinals).

    Unlike belts (flow direction), inserter direction is the pickup side: the
    tile the inserter pulls from. Drop is on the opposite side.
    """
    return direction_for_flow(drop_pos, inserter_pos)


def inserter_pickup_tile(inserter_pos, blueprint_direction):
    """Grid tile the inserter picks up from (its facing / front tile)."""
    ix, iy = inserter_pos
    dx, dy = DIRECTION_FRONT_OFFSET.get(blueprint_direction, DIRECTION_FRONT_OFFSET[FACTORIO_EAST])
    return ix + dx, iy + dy


def inserter_drop_tile(inserter_pos, blueprint_direction):
    """Grid tile where the inserter places items (opposite of pickup)."""
    ix, iy = inserter_pos
    dx, dy = DIRECTION_FRONT_OFFSET.get(blueprint_direction, DIRECTION_FRONT_OFFSET[FACTORIO_EAST])
    return ix - dx, iy - dy


_INSERTER_PICKUP_TO_DROP = {
    FACTORIO_NORTH: FACTORIO_SOUTH,
    FACTORIO_SOUTH: FACTORIO_NORTH,
    FACTORIO_EAST: FACTORIO_WEST,
    FACTORIO_WEST: FACTORIO_EAST,
}


def inserter_direction_for_display(blueprint_direction):
    """
    Direction for Pygame inserter arrows.

    Blueprint stores pickup side; the UI arrow points toward the drop side.
    """
    if blueprint_direction is None:
        return FACTORIO_SOUTH
    return _INSERTER_PICKUP_TO_DROP.get(int(blueprint_direction), int(blueprint_direction))


# Each transport-belt tile has two parallel item lanes (left/right of flow direction).
# Throughput modeling can treat 1 belt tile as 2 logical item lanes; routing still
# places one belt row per recipe ingredient for clarity.
BELT_LANES_PER_TILE = 2

# Spacing between parallel input lanes on one machine (tiles perpendicular to flow).
INGREDIENT_LANE_SPACING = 2

# Horizontal tiles per machine I/O block: 4 west + machine_w + 4 east (belts + inserters).
MACHINE_IO_WEST_TILES = 4
MACHINE_IO_EAST_TILES = 4


def machine_io_stride(machine_w: int) -> int:
    """Minimum horizontal gap between machine origin columns (no shared I/O tiles)."""
    return machine_w + MACHINE_IO_WEST_TILES + MACHINE_IO_EAST_TILES


# Pygame visualization settings
PYGAME_WINDOW_WIDTH = 1280
PYGAME_WINDOW_HEIGHT = 720
PYGAME_TILE_SIZE = 64  # Size of each tile in pixels

# Factorio installation path (base directory)
FACTORIO_INSTALL_PATH = r"C:\Program Files (x86)\Steam\steamapps\common\Factorio"



def get_factorio_graphics_path(base_path):
    """Get the full graphics path from the base Factorio installation path."""
    from pathlib import Path


    return str(Path(base_path) / "data" / "base" / "graphics" / "entity")



FACTORIO_BASE_GRAPHICS_PATH = get_factorio_graphics_path(FACTORIO_INSTALL_PATH)

# Entity folders under graphics/entity with dedicated sprite loading logic
BELT_ENTITIES = ("transport-belt", "fast-transport-belt", "express-transport-belt")
UNDERGROUND_BELT_ENTITIES = (
    "underground-belt",
    "fast-underground-belt",
    "express-underground-belt",
    "turbo-underground-belt",
)
UNDERGROUND_BELT_MAX_UNDERGROUND_TILES = {
    "underground-belt": 4,
    "fast-underground-belt": 6,
    "express-underground-belt": 8,
    "turbo-underground-belt": 10,
}
UNDERGROUND_BELT_ENTITIES = (
    "underground-belt",
    "fast-underground-belt",
    "express-underground-belt",
    "turbo-underground-belt",
)
UNDERGROUND_BELT_MAX_UNDERGROUND_TILES = {
    "underground-belt": 4,
    "fast-underground-belt": 6,
    "express-underground-belt": 8,
    "turbo-underground-belt": 10,
}
INSERTER_ENTITIES = (
    "inserter",
    "fast-inserter",
    "long-handed-inserter",
    "burner-inserter",
    "bulk-inserter",
)
