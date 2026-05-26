"""
Toolbar component for the blueprint renderer.
Provides controls for targets, generate, placement mode, copy, and pause.
"""
import pygame
import logging

try:
    import pyperclip
except ImportError:
    pyperclip = None


class Toolbar:
    """Bottom toolbar for blueprint renderer."""

    def __init__(self, width, height, y_position, mode: str = "generate"):
        self.width = width
        self.toolbar_height = 80
        self.y_position = y_position - self.toolbar_height
        self.mode = mode  # "generate" | "assisted"
        self.logger = logging.getLogger(__name__)

        self.bg_color = (30, 30, 40)
        self.border_color = (100, 100, 120)
        self.button_color = (60, 90, 150)
        self.button_hover_color = (80, 120, 200)
        self.button_text_color = (255, 255, 255)
        self.generate_color = (50, 130, 50)
        self.generate_hover_color = (60, 150, 60)
        self.placement_genetic_color = (120, 80, 140)
        self.placement_genetic_hover_color = (150, 100, 170)

        self.button_font = pygame.font.Font(None, 24)
        self.has_clipboard = pyperclip is not None
        if not self.has_clipboard:
            self.logger.warning("pyperclip not available. Copy button will be disabled.")

        self.placement_strategy = None

    def resize(self, width: int, height: int) -> None:
        """Re-anchor the toolbar when the window is resized."""
        self.width = width
        self.y_position = height - self.toolbar_height

    def draw(self, screen):
        toolbar_rect = pygame.Rect(0, self.y_position, self.width, self.toolbar_height)
        pygame.draw.rect(screen, self.bg_color, toolbar_rect)
        pygame.draw.line(
            screen, self.border_color, (0, self.y_position), (self.width, self.y_position), 2
        )

        button_y = self.y_position + 15
        button_height = 50
        button_spacing = 10
        x = 12
        button_widths = {
            "targets": 110,
            "generate": 92,
            "placement": 118,
            "options": 92,
            "center": 88,
            "copy": 100,
            "pause": 88,
        }

        from core.constants import PlacementStrategy

        placement_label = "Rules"
        if self.placement_strategy == PlacementStrategy.GENETIC:
            placement_label = "Genetic"

        if self.mode == "assisted":
            button_defs = [
                ("route", "Route all", button_widths["generate"], self.generate_color),
                ("center", "Center", button_widths["center"], (70, 110, 130)),
                ("copy", "Copy BP", button_widths["copy"], self.button_color),
                ("pause", "Pause", button_widths["pause"], self.button_color),
            ]
        else:
            button_defs = [
                ("targets", "Targets", button_widths["targets"], self.button_color),
                ("generate", "Generate", button_widths["generate"], self.generate_color),
                (
                    "placement",
                    f"Place: {placement_label}",
                    button_widths["placement"],
                    self.placement_genetic_color
                    if self.placement_strategy == PlacementStrategy.GENETIC
                    else (70, 85, 100),
                ),
                ("options", "Options", button_widths["options"], (85, 95, 115)),
                ("center", "Center", button_widths["center"], (70, 110, 130)),
                ("copy", "Copy BP", button_widths["copy"], self.button_color),
                ("pause", "Pause", button_widths["pause"], self.button_color),
            ]

        mouse_pos = pygame.mouse.get_pos()
        self.buttons = {}

        for name, label, width, base_color in button_defs:
            if name == "copy" and not self.has_clipboard:
                continue
            rect = pygame.Rect(x, button_y, width, button_height)
            self.buttons[name] = rect
            x += width + button_spacing

            is_hovered = rect.collidepoint(mouse_pos)
            if name in ("generate", "route"):
                color = self.generate_hover_color if is_hovered else base_color
            elif name == "placement":
                color = (
                    self.placement_genetic_hover_color
                    if is_hovered
                    and self.placement_strategy == PlacementStrategy.GENETIC
                    else self.placement_genetic_color
                    if self.placement_strategy == PlacementStrategy.GENETIC
                    else (90, 105, 120) if is_hovered else base_color
                )
            else:
                color = self.button_hover_color if is_hovered else base_color

            pygame.draw.rect(screen, color, rect, border_radius=5)
            pygame.draw.rect(screen, (255, 255, 255), rect, width=2, border_radius=5)
            text_surface = self.button_font.render(label, True, self.button_text_color)
            screen.blit(text_surface, text_surface.get_rect(center=rect.center))

    def handle_click(self, mouse_pos):
        for button_name, button_rect in self.buttons.items():
            if button_rect.collidepoint(mouse_pos):
                return button_name
        return None

    def copy_to_clipboard(self, text):
        if not self.has_clipboard:
            self.logger.error("Clipboard not available")
            return False
        try:
            pyperclip.copy(text)
            self.logger.info("Copied to clipboard")
            return True
        except Exception as e:
            self.logger.error("Failed to copy to clipboard: %s", e)
            return False
