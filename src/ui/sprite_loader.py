import os
import pygame
import logging
from pathlib import Path

class SpriteLoader:
    """
    Loads and caches sprites directly from Factorio game installation.
    Handles both individual sprite files and sprite sheets that need to be split.
    """
    
    # Sprite sheets that need to be split (entity_name: (grid_rows, grid_cols, sprite_size))
    SPRITE_SHEETS = {
        "transport-belt": (20, 16, 64),  # 20 rows, 16 cols, 64x64 pixels per sprite
        "fast-transport-belt": (20, 16, 64),
        "express-transport-belt": (20, 16, 64),
    }
    
    def __init__(self, factorio_graphics_path=None):
        """
        Initialize sprite loader.
        
        Args:
            factorio_graphics_path: Path to Factorio graphics/entity directory
                                   If None, tries to load from constants
        """
        if factorio_graphics_path is None:
            from core.constants import FACTORIO_BASE_GRAPHICS_PATH
            factorio_graphics_path = FACTORIO_BASE_GRAPHICS_PATH
        
        self.factorio_path = Path(factorio_graphics_path)
        self.sprites = {}
        self.logger = logging.getLogger(__name__)
        
        if not self.factorio_path.exists():
            self.logger.error(f"Factorio graphics path not found: {self.factorio_path}")
            self.logger.error("Please set FACTORIO_BASE_GRAPHICS_PATH in core/constants.py")
        else:
            self.logger.info(f"Loading sprites from: {self.factorio_path}")
            self._load_all_sprites()
    
    def _extract_sprite_from_sheet(self, sheet_surface, row, col, rows, cols, sprite_size):
        """Extract a single sprite from a sprite sheet."""
        x = col * sprite_size
        y = row * sprite_size
        sprite = pygame.Surface((sprite_size, sprite_size))
        sprite.blit(sheet_surface, (0, 0), (x, y, sprite_size, sprite_size))
        sprite.set_colorkey((0, 0, 0))  # Black is transparent
        return sprite
    
    def _load_belt_sheet(self, entity_name, sheet_path):
        """Load and split belt sprite sheets."""
        try:
            sheet = pygame.image.load(sheet_path)
            rows, cols, sprite_size = self.SPRITE_SHEETS[entity_name]
            
            # Map of directions for belt sprites (row indices 0-11 in first column)
            # First 4 are straight directions, next 8 are corners
            direction_map = {
                'east': 0,   # Right
                'west': 1,   # Left
                'north': 2,  # Up
                'south': 3,  # Down
                'east-to-north': 4,
                'north-to-east': 5,
                'west-to-north': 6,
                'north-to-west': 7,
                'south-to-east': 8,
                'east-to-south': 9,
                'south-to-west': 10,
                'west-to-south': 11,
            }
            
            # Extract sprites from first column (col=0)
            for direction, row_idx in direction_map.items():
                sprite = self._extract_sprite_from_sheet(sheet, row_idx, 0, rows, cols, sprite_size)
                key = f"{entity_name}-{direction}"
                self.sprites[key] = sprite
                self.logger.debug(f"Extracted sprite: {key}")
            
            self.logger.info(f"Loaded belt sprite sheet: {entity_name} with {len(direction_map)} variations")
            
        except Exception as e:
            self.logger.error(f"Failed to load belt sprite sheet {entity_name}: {e}")
    
    def _load_entity_sprite(self, entity_name, entity_path):
        """Load a sprite from an entity's folder."""
        # Look for PNG files in the entity folder
        png_files = list(entity_path.glob("*.png"))
        
        if not png_files:
            self.logger.warning(f"No PNG files found for {entity_name}")
            return False
        
        # Try to find a main sprite file
        # Priority: exact match, then first file that starts with entity_name but isn't a variant
        main_sprite = None
        
        # First, try exact match
        for sprite_file in png_files:
            if sprite_file.stem == entity_name:
                main_sprite = sprite_file
                self.logger.debug(f"Found exact match for {entity_name}: {sprite_file.name}")
                break
        
        # If no exact match, look for files starting with entity_name but not being variants
        # (e.g., stone-furnace.png but not stone-furnace-fire.png)
        if main_sprite is None:
            for sprite_file in png_files:
                sprite_stem = sprite_file.stem
                
                # Check if this is a variant (has entity_name followed by a dash and more characters)
                is_variant = (sprite_stem.startswith(entity_name) and 
                             len(sprite_stem) > len(entity_name) and
                             sprite_stem[len(entity_name)] == "-")
                
                if is_variant:
                    # This is a variant (e.g., stone-furnace-fire), skip it
                    continue
                
                if sprite_stem.startswith(entity_name):
                    main_sprite = sprite_file
                    self.logger.debug(f"Found match for {entity_name}: {sprite_file.name}")
                    break
        
        # If still no match, use the first PNG file
        if main_sprite is None:
            main_sprite = png_files[0]
            self.logger.debug(f"Using first available sprite for {entity_name}: {main_sprite.name}")
        
        try:
            sprite = pygame.image.load(main_sprite)
            self.sprites[entity_name] = sprite
            self.logger.debug(f"Loaded sprite: {entity_name} from {main_sprite.name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to load sprite for {entity_name}: {e}")
            return False
    
    def _load_all_sprites(self):
        """Load all sprites from the Factorio installation."""
        if not self.factorio_path.exists():
            return
        
        # Load belt sprites (which are sprite sheets)
        for belt_type in self.SPRITE_SHEETS.keys():
            belt_folder = self.factorio_path / belt_type
            if belt_folder.exists():
                # Look for the sheet file
                sheet_files = list(belt_folder.glob("*belt*.png"))
                if sheet_files:
                    self._load_belt_sheet(belt_type, sheet_files[0])
        
        # Load other entity sprites
        # Walk through all entity folders
        if self.factorio_path.exists():
            for entity_folder in self.factorio_path.iterdir():
                if entity_folder.is_dir():
                    entity_name = entity_folder.name
                    # Skip belts (already handled)
                    if entity_name not in self.SPRITE_SHEETS:
                        self._load_entity_sprite(entity_name, entity_folder)
        
        self.logger.info(f"Loaded {len(self.sprites)} sprites")
    
    def get_sprite(self, sprite_name):
        """
        Get a sprite by name.
        
        Args:
            sprite_name: Name of the sprite (without .png extension)
        
        Returns:
            pygame.Surface if found, None otherwise
        """
        return self.sprites.get(sprite_name)
    
    def has_sprite(self, sprite_name):
        """Check if a sprite exists."""
        return sprite_name in self.sprites
    
    def get_sprite_count(self):
        """Get the total number of loaded sprites."""
        return len(self.sprites)
    
    def list_sprites(self):
        """List all available sprite names."""
        return list(self.sprites.keys())
