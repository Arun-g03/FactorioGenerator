"""
Toolbar component for the blueprint renderer.
Provides controls for recipes, copying blueprint string, and pause menu.
"""
import pygame
import logging
import pyperclip

class Toolbar:
    """Bottom toolbar for blueprint renderer."""
    
    def __init__(self, width, height, y_position):
        self.width = width
        self.toolbar_height = 80
        self.y_position = y_position - self.toolbar_height
        self.logger = logging.getLogger(__name__)
        
        # Colors
        self.bg_color = (30, 30, 40)
        self.border_color = (100, 100, 120)
        self.button_color = (60, 90, 150)
        self.button_hover_color = (80, 120, 200)
        self.button_text_color = (255, 255, 255)
        
        # Fonts
        self.button_font = pygame.font.Font(None, 28)
        
        # Try to initialize pyperclip for clipboard operations
        try:
            import pyperclip
            self.has_clipboard = True
        except ImportError:
            self.has_clipboard = False
            self.logger.warning("pyperclip not available. Copy button will be disabled.")
    
    def draw(self, screen):
        """Draw the toolbar."""
        # Draw toolbar background
        toolbar_rect = pygame.Rect(0, self.y_position, self.width, self.toolbar_height)
        pygame.draw.rect(screen, self.bg_color, toolbar_rect)
        pygame.draw.line(screen, self.border_color, (0, self.y_position), (self.width, self.y_position), 2)
        
        # Draw buttons
        button_x = 20
        button_y = self.y_position + 15
        button_width = 150
        button_height = 50
        button_spacing = 20
        
        # Buttons
        self.buttons = {
            "recipes": pygame.Rect(button_x, button_y, button_width, button_height),
            "copy": pygame.Rect(button_x + button_width + button_spacing, button_y, button_width, button_height),
            "pause": pygame.Rect(button_x + (button_width + button_spacing) * 2, button_y, button_width, button_height),
        }
        
        button_texts = {
            "recipes": "Set Recipes",
            "copy": "Copy Blueprint",
            "pause": "Pause Menu",
        }
        
        # Get mouse position for hover effects
        mouse_pos = pygame.mouse.get_pos()
        
        for button_name, button_rect in self.buttons.items():
            # Skip copy button if clipboard not available
            if button_name == "copy" and not self.has_clipboard:
                continue
            
            # Determine if hovered
            is_hovered = button_rect.collidepoint(mouse_pos)
            color = self.button_hover_color if is_hovered else self.button_color
            
            # Draw button
            pygame.draw.rect(screen, color, button_rect, border_radius=5)
            pygame.draw.rect(screen, (255, 255, 255), button_rect, width=2, border_radius=5)
            
            # Button text
            text = button_texts.get(button_name, button_name)
            text_surface = self.button_font.render(text, True, self.button_text_color)
            text_rect = text_surface.get_rect(center=button_rect.center)
            screen.blit(text_surface, text_rect)
    
    def handle_click(self, mouse_pos):
        """Handle click on toolbar.
        
        Returns:
            String indicating action: "recipes", "copy", "pause", or None
        """
        for button_name, button_rect in self.buttons.items():
            if button_rect.collidepoint(mouse_pos):
                return button_name
        return None
    
    def copy_to_clipboard(self, text):
        """Copy text to clipboard."""
        if not self.has_clipboard:
            self.logger.error("Clipboard not available")
            return False
        
        try:
            pyperclip.copy(text)
            self.logger.info("Copied to clipboard")
            return True
        except Exception as e:
            self.logger.error(f"Failed to copy to clipboard: {e}")
            return False

