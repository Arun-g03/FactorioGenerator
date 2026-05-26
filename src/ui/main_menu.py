"""
Main menu for the Factorio Blueprint Generator.
Provides a GUI to launch the generator and configure settings.
"""
import pygame
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.constants import PYGAME_WINDOW_WIDTH, PYGAME_WINDOW_HEIGHT, FACTORIO_BASE_GRAPHICS_PATH
from screen_manager import ScreenManager

class MainMenu:
    """Main menu for the blueprint generator."""
    
    def __init__(self):
        self.screen_manager = ScreenManager()
        self.width = PYGAME_WINDOW_WIDTH
        self.height = PYGAME_WINDOW_HEIGHT
        self.screen = self.screen_manager.get_screen()
        self.screen_manager.set_caption("Factorio Blueprint Generator")
        
        self.logger = logging.getLogger(__name__)
        
        # Colors
        self.bg_color = (40, 40, 50)
        self.title_color = (255, 200, 50)
        self.text_color = (255, 255, 255)
        self.button_color = (60, 90, 150)
        self.button_hover_color = (80, 120, 200)
        self.button_text_color = (255, 255, 255)
        
        # Fonts
        self.title_font = pygame.font.Font(None, 72)
        self.subtitle_font = pygame.font.Font(None, 36)
        self.button_font = pygame.font.Font(None, 48)
        self.info_font = pygame.font.Font(None, 24)
        
        # Menu state
        self.selected_button = 0
        self.buttons = []
        
        # Factorio path status
        self.factorio_path_ok = self._check_factorio_path()
        
    def _check_factorio_path(self):
        """Check if Factorio graphics path exists."""
        factorio_path = Path(FACTORIO_BASE_GRAPHICS_PATH)
        return factorio_path.exists() and factorio_path.is_dir()
    
    def setup_menu(self):
        """Set up menu buttons."""
        self.buttons = [
            {"text": "Start", "action": "generate", "y": 180},
            {"text": "Placement Replay", "action": "replay", "y": 250},
            {"text": "Settings", "action": "settings", "y": 320},
            {"text": "Exit", "action": "exit", "y": 390},
        ]
    
    def get_button_rect(self, button_info):
        """Get the rectangle for a button."""
        text_surface = self.button_font.render(button_info["text"], True, self.button_text_color)
        text_width, text_height = text_surface.get_size()
        
        padding = 20
        width = text_width + padding * 2
        height = text_height + padding
        
        x = (self.width - width) // 2
        
        return pygame.Rect(x, button_info["y"] - height // 2, width, height)
    
    def is_button_hovered(self, button_index, mouse_pos):
        """Check if a button is hovered."""
        button_rect = self.get_button_rect(self.buttons[button_index])
        return button_rect.collidepoint(mouse_pos)
    
    def draw(self, selected_index):
        """Draw the menu."""
        self.screen.fill(self.bg_color)
        
        # Draw title
        title_text = "Factorio Blueprint Generator"
        title_surface = self.title_font.render(title_text, True, self.title_color)
        title_rect = title_surface.get_rect(center=(self.width // 2, 80))
        self.screen.blit(title_surface, title_rect)
        
        # Draw subtitle
        subtitle_text = "Automated Factory Generation"
        subtitle_surface = self.subtitle_font.render(subtitle_text, True, self.text_color)
        subtitle_rect = subtitle_surface.get_rect(center=(self.width // 2, 130))
        self.screen.blit(subtitle_surface, subtitle_rect)
        
        # Draw status info
        status_text = "Factorio Graphics Path: "
        status_color = (100, 255, 100) if self.factorio_path_ok else (255, 100, 100)
        status_info = "✓ Found" if self.factorio_path_ok else "✗ Not Found"
        
        status_surface = self.info_font.render(status_text + status_info, True, status_color)
        self.screen.blit(status_surface, (20, self.height - 60))
        
        path_surface = self.info_font.render(FACTORIO_BASE_GRAPHICS_PATH, True, (150, 150, 150))
        self.screen.blit(path_surface, (20, self.height - 35))
        
        # Draw buttons
        for i, button_info in enumerate(self.buttons):
            button_rect = self.get_button_rect(button_info)
            
            # Determine if button is hovered or selected
            is_hovered = (i == selected_index)
            color = self.button_hover_color if is_hovered else self.button_color
            
            # Draw button background
            pygame.draw.rect(self.screen, color, button_rect, border_radius=10)
            pygame.draw.rect(self.screen, (255, 255, 255), button_rect, width=2, border_radius=10)
            
            # Draw button text
            text_surface = self.button_font.render(button_info["text"], True, self.button_text_color)
            text_rect = text_surface.get_rect(center=button_rect.center)
            self.screen.blit(text_surface, text_rect)
        
        # Draw instructions
        instructions = [
            "↑↓ or Mouse: Navigate | Enter: Select | Esc: Exit"
        ]
        for i, instruction in enumerate(instructions):
            inst_surface = self.info_font.render(instruction, True, (150, 150, 150))
            self.screen.blit(inst_surface, (20, self.height - 120 + i * 25))
    
    def handle_events(self):
        """Handle menu events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "exit"
            if self.screen_manager.handle_resize_event(event):
                self.width, self.height = self.screen_manager.get_size()
                self.screen = self.screen_manager.get_screen()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    self.selected_button = (self.selected_button - 1) % len(self.buttons)
                elif event.key == pygame.K_DOWN:
                    self.selected_button = (self.selected_button + 1) % len(self.buttons)
                elif event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                    return self.buttons[self.selected_button]["action"]
                elif event.key == pygame.K_ESCAPE:
                    return "exit"
            
            elif event.type == pygame.MOUSEMOTION:
                mouse_pos = pygame.mouse.get_pos()
                for i in range(len(self.buttons)):
                    if self.is_button_hovered(i, mouse_pos):
                        self.selected_button = i
                        break
            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    mouse_pos = pygame.mouse.get_pos()
                    for i in range(len(self.buttons)):
                        if self.is_button_hovered(i, mouse_pos):
                            return self.buttons[i]["action"]
        
        return None
    
    def run(self):
        """Run the main menu."""
        self.setup_menu()
        self.width, self.height = self.screen_manager.get_size()

        if not self.factorio_path_ok:
            self.logger.warning("Factorio graphics path not found. Visualization may not work.")
        
        running = True
        result = None
        
        while running and result is None:
            # Handle events
            result = self.handle_events()
            
            # Draw menu
            self.draw(self.selected_button)
            
            self.screen_manager.flip()
            self.screen_manager.tick(60)
        
        return result

