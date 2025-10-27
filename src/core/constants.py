
PRODUCTION_TARGETS = {
   "iron-plate": 20  # Produce 60 gear wheels per minute
}

BASE_MATERIALS = {"iron-ore", "copper-ore", "coal", "water", "crude-oil", "stone"}

DIRECTIONS = {
    "north": None,  # No direction needed for North (upward)
    "east": 4,      # Right-facing
    "south": 8,     # Downward-facing
    "west": 12       # Left-facing
}

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

