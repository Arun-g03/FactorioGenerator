"""
Screen manager for managing pygame display across different screens.
Keeps a single pygame instance throughout the application.
"""
import pygame
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.app_config import (
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    get_window_size,
    save_window_size,
)


class ScreenManager:
    """Manages a single pygame instance for the application."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ScreenManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            pygame.init()
            self.width, self.height = get_window_size()
            self.screen = None
            self.clock = pygame.time.Clock()
            self.logger = logging.getLogger(__name__)
            self._initialized = True

    def _clamp_size(self, width: int, height: int) -> tuple[int, int]:
        return max(MIN_WINDOW_WIDTH, int(width)), max(MIN_WINDOW_HEIGHT, int(height))

    def apply_resize(self, width: int, height: int) -> bool:
        """Resize the display surface. Returns True if dimensions changed."""
        width, height = self._clamp_size(width, height)
        if self.screen is not None and width == self.width and height == self.height:
            return False
        self.width = width
        self.height = height
        flags = pygame.RESIZABLE
        if self.screen is None:
            self.screen = pygame.display.set_mode((self.width, self.height), flags)
        else:
            self.screen = pygame.display.set_mode((self.width, self.height), flags)
        self.logger.debug("Window resized to %sx%s", self.width, self.height)
        save_window_size(self.width, self.height)
        return True

    def handle_resize_event(self, event) -> bool:
        """Apply a pygame.VIDEORESIZE event. Returns True if size changed."""
        if event.type != pygame.VIDEORESIZE:
            return False
        return self.apply_resize(event.w, event.h)

    def get_screen(self):
        """Get or create the resizable pygame screen."""
        if self.screen is None:
            self.apply_resize(self.width, self.height)
        return self.screen

    def get_size(self) -> tuple[int, int]:
        """Current window size (client area)."""
        if self.screen is not None:
            return self.screen.get_size()
        return self.width, self.height

    def set_caption(self, caption):
        """Set the window caption."""
        pygame.display.set_caption(caption)

    def tick(self, fps=60):
        """Tick the clock."""
        self.clock.tick(fps)

    def flip(self):
        """Flip the display."""
        pygame.display.flip()

    def persist_window_size(self) -> None:
        """Save current window size to config.json."""
        if self.screen is not None:
            self.width, self.height = self.get_size()
        save_window_size(self.width, self.height)

    def cleanup(self):
        """Clean up pygame (called on exit only)."""
        if self._initialized:
            self.persist_window_size()
            pygame.quit()
            self._initialized = False
            ScreenManager._instance = None
            ScreenManager._initialized = False
