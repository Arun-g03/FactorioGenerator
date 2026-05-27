import logging
from pathlib import Path

import pygame

from core.constants import CARDINAL_NAMES

class SpriteLoader:
    """
    Loads and caches sprites directly from Factorio game installation.
    Handles belt sprite sheets, inserter platform strips, and underground belts.
    """

    # Belt sheets: row count and column count (sprite size is auto-detected from PNG)
    BELT_SHEET_LAYOUT = {
        "transport-belt": (20, 16),
        "fast-transport-belt": (20, 16),
        "express-transport-belt": (20, 16),
    }

    # Entity animation sheets: (cell_width, cell_height, line_length); frame 0 = icon
    ENTITY_SPRITE_SHEET_LAYOUT = {
        "assembling-machine-1": (214, 226, 8),
        "assembling-machine-2": (214, 218, 8),
        "assembling-machine-3": (214, 237, 8),
    }

    BELT_DIRECTION_ROWS = {
        "east": 0,
        "west": 1,
        "north": 2,
        "south": 3,
        "east-to-north": 4,
        "north-to-east": 5,
        "west-to-north": 6,
        "north-to-west": 7,
        "south-to-east": 8,
        "east-to-south": 9,
        "south-to-west": 10,
        "west-to-south": 11,
    }

    def __init__(self, factorio_graphics_path=None):
        if factorio_graphics_path is None:
            from core.constants import FACTORIO_BASE_GRAPHICS_PATH
            factorio_graphics_path = FACTORIO_BASE_GRAPHICS_PATH

        self.factorio_path = Path(factorio_graphics_path)
        self.sprites = {}
        self.logger = logging.getLogger(__name__)

        if not self.factorio_path.exists():
            self.logger.error(f"Factorio graphics path not found: {self.factorio_path}")
            self.logger.error("Set FACTORIO_INSTALL_PATH in core/constants.py")
        else:
            self.logger.info(f"Loading sprites from: {self.factorio_path}")
            self._load_all_sprites()

    def _load_image(self, path):
        """Load a PNG; use alpha when a display is available."""
        image = pygame.image.load(str(path))
        try:
            return image.convert_alpha()
        except pygame.error:
            return image

    def _apply_transparency(self, sprite):
        if sprite.get_flags() & pygame.SRCALPHA:
            return sprite
        sprite.set_colorkey((0, 0, 0))
        return sprite

    def _extract_sprite_from_sheet(self, sheet_surface, row, col, cell_width, cell_height):
        x = col * cell_width
        y = row * cell_height
        sprite = pygame.Surface((cell_width, cell_height), pygame.SRCALPHA)
        sprite.blit(sheet_surface, (0, 0), (x, y, cell_width, cell_height))
        return self._apply_transparency(sprite)

    def _extract_sheet_frame(self, sheet_surface, frame_index, cell_width, cell_height, line_length):
        """Extract one frame from a Factorio animation sprite sheet."""
        col = frame_index % line_length
        row = frame_index // line_length
        return self._extract_sprite_from_sheet(
            sheet_surface, row, col, cell_width, cell_height
        )

    def _detect_sheet_sprite_size(self, sheet, rows, cols):
        width, height = sheet.get_size()
        return width // cols, height // rows  # cell_width, cell_height

    def _load_belt_sheet(self, entity_name, sheet_path):
        try:
            from core.constants import BELT_ENTITIES
            if entity_name not in BELT_ENTITIES:
                return

            sheet = self._load_image(sheet_path)
            rows, cols = self.BELT_SHEET_LAYOUT[entity_name]
            cell_width, cell_height = self._detect_sheet_sprite_size(sheet, rows, cols)

            for direction, row_idx in self.BELT_DIRECTION_ROWS.items():
                sprite = self._extract_sprite_from_sheet(
                    sheet, row_idx, 0, cell_width, cell_height
                )
                self.sprites[f"{entity_name}-{direction}"] = sprite

            self.logger.info(
                f"Loaded belt sheet {entity_name}: {cell_width}x{cell_height}px sprites, "
                f"{len(self.BELT_DIRECTION_ROWS)} directions"
            )
        except Exception as e:
            self.logger.error(f"Failed to load belt sprite sheet {entity_name}: {e}")

    def _load_inserter_sprites(self, entity_name, entity_path):
        platform_file = entity_path / f"{entity_name}-platform.png"
        if not platform_file.exists():
            self.logger.warning(f"No platform sprite for {entity_name}")
            return False

        try:
            sheet = self._load_image(platform_file)
            width, height = sheet.get_size()
            frame_count = len(CARDINAL_NAMES)

            if width >= height * frame_count:
                frame_width = width // frame_count
                for index, direction in enumerate(CARDINAL_NAMES):
                    frame = pygame.Surface((frame_width, height), pygame.SRCALPHA)
                    frame.blit(sheet, (0, 0), (index * frame_width, 0, frame_width, height))
                    self.sprites[f"{entity_name}-platform-{direction}"] = self._apply_transparency(frame)
                default = f"{entity_name}-platform-east"
                self.sprites[f"{entity_name}-platform"] = self.sprites[default]
            else:
                self.sprites[f"{entity_name}-platform"] = self._apply_transparency(sheet)

            self.logger.info(f"Loaded inserter sprites for {entity_name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to load inserter sprites for {entity_name}: {e}")
            return False

    def _load_underground_belt(self, entity_name, entity_path):
        structure_file = entity_path / f"{entity_name}-structure.png"
        if not structure_file.exists():
            return False

        try:
            sheet = self._load_image(structure_file)
            width, height = sheet.get_size()
            # Structure PNGs are sprite sheets (e.g. 768x768); use one tile for display
            cell_size = 128 if width >= 128 and height >= 128 else min(width, height)
            if width > cell_size or height > cell_size:
                sprite = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
                sprite.blit(sheet, (0, 0), (0, 0, cell_size, cell_size))
                sprite = self._apply_transparency(sprite)
            else:
                sprite = self._apply_transparency(sheet)
            self.sprites[f"{entity_name}-structure"] = sprite
            self.logger.info(f"Loaded underground belt structure for {entity_name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to load underground belt {entity_name}: {e}")
            return False

    def _load_entity_sprite(self, entity_name, entity_path):
        png_files = list(entity_path.glob("*.png"))
        if not png_files:
            self.logger.warning(f"No PNG files found for {entity_name}")
            return False

        main_sprite = None
        for sprite_file in png_files:
            if sprite_file.stem == entity_name:
                main_sprite = sprite_file
                break

        if main_sprite is None:
            for sprite_file in png_files:
                sprite_stem = sprite_file.stem
                is_variant = (
                    sprite_stem.startswith(entity_name)
                    and len(sprite_stem) > len(entity_name)
                    and sprite_stem[len(entity_name)] == "-"
                )
                if is_variant:
                    continue
                if sprite_stem.startswith(entity_name):
                    main_sprite = sprite_file
                    break

        if main_sprite is None:
            main_sprite = png_files[0]

        try:
            sheet = self._load_image(main_sprite)
            layout = self.ENTITY_SPRITE_SHEET_LAYOUT.get(entity_name)
            if layout:
                cell_width, cell_height, line_length = layout
                sprite = self._extract_sheet_frame(
                    sheet, 0, cell_width, cell_height, line_length
                )
                self.logger.info(
                    f"Loaded {entity_name} sprite sheet frame 0: "
                    f"{cell_width}x{cell_height}px"
                )
            else:
                sprite = self._apply_transparency(sheet)
            self.sprites[entity_name] = sprite
            return True
        except Exception as e:
            self.logger.error(f"Failed to load sprite for {entity_name}: {e}")
            return False

    def _is_special_entity(self, entity_name):
        from core.constants import BELT_ENTITIES, INSERTER_ENTITIES, UNDERGROUND_BELT_ENTITIES

        if entity_name in BELT_ENTITIES or entity_name in UNDERGROUND_BELT_ENTITIES:
            return True
        if entity_name in INSERTER_ENTITIES or entity_name.endswith("-inserter"):
            return True
        return False

    def _load_all_sprites(self):
        if not self.factorio_path.exists():
            return

        from core.constants import BELT_ENTITIES, INSERTER_ENTITIES, UNDERGROUND_BELT_ENTITIES

        for belt_type in BELT_ENTITIES:
            belt_folder = self.factorio_path / belt_type
            if not belt_folder.exists():
                continue
            sheet_files = sorted(belt_folder.glob(f"{belt_type}.png"))
            if not sheet_files:
                sheet_files = sorted(belt_folder.glob("*belt*.png"))
            if sheet_files:
                self._load_belt_sheet(belt_type, sheet_files[0])

        for entity_name in INSERTER_ENTITIES:
            entity_path = self.factorio_path / entity_name
            if entity_path.is_dir():
                self._load_inserter_sprites(entity_name, entity_path)

        for entity_name in UNDERGROUND_BELT_ENTITIES:
            entity_path = self.factorio_path / entity_name
            if entity_path.is_dir():
                self._load_underground_belt(entity_name, entity_path)

        for entity_folder in self.factorio_path.iterdir():
            if not entity_folder.is_dir():
                continue
            entity_name = entity_folder.name
            if self._is_special_entity(entity_name):
                continue
            self._load_entity_sprite(entity_name, entity_folder)

        belt_count = sum(1 for k in self.sprites if "belt" in k)
        inserter_count = sum(1 for k in self.sprites if "inserter" in k)
        self.logger.info(
            f"Loaded {len(self.sprites)} sprites "
            f"({belt_count} belt, {inserter_count} inserter)"
        )

    def get_sprite(self, sprite_name):
        return self.sprites.get(sprite_name)

    def has_sprite(self, sprite_name):
        return sprite_name in self.sprites

    def get_sprite_count(self):
        return len(self.sprites)

    def list_sprites(self):
        return list(self.sprites.keys())
