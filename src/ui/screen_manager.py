"""
Screen manager for managing pygame display across different screens.
Keeps a single pygame instance throughout the application.
"""
import pygame
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.constants import PYGAME_WINDOW_WIDTH, PYGAME_WINDOW_HEIGHT

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
            self.width = PYGAME_WINDOW_WIDTH
            self.height = PYGAME_WINDOW_HEIGHT
            self.screen = None
            self.clock = pygame.time.Clock()
            self.logger = logging.getLogger(__name__)
            self._initialized = True
    
    def get_screen(self):
        """Get or create the pygame screen."""
        if self.screen is None:
            self.screen = pygame.display.set_mode((self.width, self.height))
        return self.screen
    
    def set_caption(self, caption):
        """Set the window caption."""
        pygame.display.set_caption(caption)
    
    def tick(self, fps=60):
        """Tick the clock."""
        self.clock.tick(fps)
    
    def flip(self):
        """Flip the display."""
        pygame.display.flip()
    
    def cleanup(self):
        """Clean up pygame (called on exit only)."""
        if self._initialized:
            pygame.quit()
            self._initialized = False

