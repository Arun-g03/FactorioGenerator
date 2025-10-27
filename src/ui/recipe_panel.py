"""
Recipe panel for configuring production targets.
Allows users to add/remove recipes and set production rates.
"""
import pygame
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.constants import PYGAME_WINDOW_WIDTH, PYGAME_WINDOW_HEIGHT
import json

class RecipePanel:
    """Panel for managing recipe production targets."""
    
    def __init__(self):
        self.width = PYGAME_WINDOW_WIDTH
        self.height = PYGAME_WINDOW_HEIGHT
        self.logger = logging.getLogger(__name__)
        
        # Panel settings
        self.panel_width = 600
        self.panel_height = 500
        self.panel_x = (self.width - self.panel_width) // 2
        self.panel_y = (self.height - self.panel_height) // 2
        
        # Colors
        self.bg_color = (50, 50, 60)
        self.border_color = (100, 100, 120)
        self.item_bg_color = (60, 60, 70)
        self.item_text_color = (255, 255, 255)
        self.button_color = (60, 90, 150)
        self.button_hover_color = (80, 120, 200)
        self.remove_button_color = (150, 60, 60)
        self.remove_button_hover_color = (200, 80, 80)
        
        # Fonts
        self.title_font = pygame.font.Font(None, 48)
        self.item_font = pygame.font.Font(None, 32)
        self.button_font = pygame.font.Font(None, 28)
        self.input_font = pygame.font.Font(None, 28)
        
        # Recipe data: list of dicts with 'item' and 'count'
        self.recipes = []
        
        # UI state
        self.active_input_field = None
        self.typing_item_name = ""
        self.typing_count = ""
        
        # Autocomplete state
        self.suggestions = []
        self.max_suggestions = 5
        self.selected_suggestion = 0
        
        # Load available items from recipes.json
        self.available_items = self._load_available_items()
    
    def add_recipe(self, item_name, count=1):
        """Add a recipe to the list."""
        if item_name and item_name not in [r['item'] for r in self.recipes]:
            self.recipes.append({'item': item_name, 'count': count})
            self.logger.info(f"Added recipe: {item_name} x{count}")
    
    def remove_recipe(self, index):
        """Remove a recipe from the list."""
        if 0 <= index < len(self.recipes):
            removed = self.recipes.pop(index)
            self.logger.info(f"Removed recipe: {removed['item']}")
    
    def update_recipe_count(self, index, count):
        """Update the count for a recipe."""
        if 0 <= index < len(self.recipes):
            self.recipes[index]['count'] = max(1, int(count) if count.isdigit() else 1)
    
    def _load_available_items(self):
        """Load all available items from recipes.json, excluding ore recipes."""
        try:
            recipes_file = Path(__file__).parent.parent / "data" / "recipes.json"
            with open(recipes_file, 'r') as f:
                data = json.load(f)
                all_items = list(data.get('recipes', {}).keys())
                
                # Exclude ore recipes and raw materials
                excluded_items = ["iron-ore", "copper-ore", "coal", "stone", "uranium-ore", 
                                "water", "crude-oil"]
                return [item for item in all_items if item not in excluded_items]
        except Exception as e:
            self.logger.error(f"Failed to load recipes: {e}")
            return []
    
    def _format_item_name(self, item_name):
        """Convert kebab-case to Title Case.
        
        Args:
            item_name: Item name in kebab-case (e.g., "iron-gear-wheel")
        
        Returns:
            Formatted name (e.g., "Iron Gear Wheel")
        """
        return item_name.replace('-', ' ').title()
    
    def update_suggestions(self):
        """Update autocomplete suggestions based on typed text."""
        if not self.typing_item_name or not self.available_items:
            self.suggestions = []
            self.selected_suggestion = 0
            return
        
        typed_lower = self.typing_item_name.lower()
        # Filter items that start with or contain the typed text
        self.suggestions = [
            item for item in self.available_items 
            if item.lower().startswith(typed_lower) or typed_lower in item.lower()
        ][:self.max_suggestions]
        
        # Sort: exact matches first, then prefix matches, then substring matches
        def sort_key(item):
            item_lower = item.lower()
            typed = typed_lower
            if item_lower == typed:
                return (0, item_lower)
            elif item_lower.startswith(typed):
                return (1, item_lower)
            else:
                return (2, item_lower)
        
        self.suggestions.sort(key=sort_key)
        self.suggestions = self.suggestions[:self.max_suggestions]
        self.selected_suggestion = 0
    
    def get_recipes(self):
        """Get the current recipe list as a dictionary."""
        return {recipe['item']: recipe['count'] for recipe in self.recipes}
    
    def draw(self, screen):
        """Draw the recipe panel."""
        # Draw overlay
        overlay = pygame.Surface((self.width, self.height))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))
        
        # Draw panel background
        panel_rect = pygame.Rect(self.panel_x, self.panel_y, self.panel_width, self.panel_height)
        pygame.draw.rect(screen, self.bg_color, panel_rect, border_radius=10)
        pygame.draw.rect(screen, self.border_color, panel_rect, width=3, border_radius=10)
        
        # Draw title
        title_text = "Set Production Targets"
        title_surface = self.title_font.render(title_text, True, (255, 200, 50))
        title_rect = title_surface.get_rect(center=(self.panel_x + self.panel_width // 2, 
                                                      self.panel_y + 40))
        screen.blit(title_surface, title_rect)
        
        # Draw recipe list
        y_offset = self.panel_y + 100
        item_height = 45
        max_items = min(len(self.recipes), 7)  # Show up to 7 items
        
        mouse_pos = pygame.mouse.get_pos()
        
        for i in range(max_items):
            recipe = self.recipes[i]
            item_y = y_offset + i * item_height
            
            # Item background
            item_rect = pygame.Rect(self.panel_x + 20, item_y, 
                                   self.panel_width - 40, item_height)
            pygame.draw.rect(screen, self.item_bg_color, item_rect, border_radius=5)
            
            # Item name (formatted)
            item_name = recipe['item']
            formatted_name = self._format_item_name(item_name)
            name_surface = self.item_font.render(formatted_name, True, self.item_text_color)
            screen.blit(name_surface, (item_rect.x + 10, item_rect.y + 8))
            
            # Count input
            count_text = str(recipe['count'])
            count_surface = self.input_font.render(f"Count: {count_text}", True, self.item_text_color)
            screen.blit(count_surface, (item_rect.x + 250, item_rect.y + 8))
            
            # Remove button (X)
            remove_btn = pygame.Rect(item_rect.right - 40, item_rect.y + 5, 35, 35)
            is_hovered = remove_btn.collidepoint(mouse_pos)
            remove_color = self.remove_button_hover_color if is_hovered else self.remove_button_color
            pygame.draw.rect(screen, remove_color, remove_btn, border_radius=5)
            
            # X text
            x_text = self.button_font.render("X", True, (255, 255, 255))
            x_text_rect = x_text.get_rect(center=remove_btn.center)
            screen.blit(x_text, x_text_rect)
        
        # Add new recipe input and button
        add_y = self.panel_y + self.panel_height - 150
        
        # Input field for item name
        input_rect = pygame.Rect(self.panel_x + 20, add_y, 200, 40)
        pygame.draw.rect(screen, (30, 30, 40), input_rect, border_radius=5)
        pygame.draw.rect(screen, 
                        (255, 255, 255) if self.active_input_field == "item_name" else (100, 100, 100),
                        input_rect, width=2, border_radius=5)
        
        if self.active_input_field == "item_name":
            text_to_show = self.typing_item_name
            cursor = "_"
        else:
            text_to_show = "Enter item name..."
            cursor = ""
        
        input_surface = self.input_font.render(text_to_show + cursor, True, self.item_text_color)
        screen.blit(input_surface, (input_rect.x + 10, input_rect.y + 8))
        
        # Input field for count
        count_input_rect = pygame.Rect(self.panel_x + 230, add_y, 80, 40)
        pygame.draw.rect(screen, (30, 30, 40), count_input_rect, border_radius=5)
        pygame.draw.rect(screen,
                        (255, 255, 255) if self.active_input_field == "count" else (100, 100, 100),
                        count_input_rect, width=2, border_radius=5)
        
        if self.active_input_field == "count":
            text_to_show = self.typing_count
            cursor = "_"
        else:
            text_to_show = "1"
            cursor = ""
        
        count_surface = self.input_font.render(text_to_show + cursor, True, self.item_text_color)
        screen.blit(count_surface, (count_input_rect.x + 10, count_input_rect.y + 8))
        
        # Add button (+ button) - only show if there's content to add
        if self.typing_item_name:
            add_btn = pygame.Rect(count_input_rect.right + 10, add_y, 40, 40)
            is_hovered = add_btn.collidepoint(mouse_pos)
            add_color = self.button_hover_color if is_hovered else self.button_color
            pygame.draw.rect(screen, add_color, add_btn, border_radius=5)
            pygame.draw.rect(screen, (255, 255, 255), add_btn, width=2, border_radius=5)
            
            # Draw + icon
            plus_size = 20
            pygame.draw.line(screen, (255, 255, 255), 
                           (add_btn.centerx, add_btn.centery - plus_size//2),
                           (add_btn.centerx, add_btn.centery + plus_size//2), 3)
            pygame.draw.line(screen, (255, 255, 255),
                           (add_btn.centerx - plus_size//2, add_btn.centery),
                           (add_btn.centerx + plus_size//2, add_btn.centery), 3)
        
        # Generate button
        generate_btn = pygame.Rect(self.panel_x + self.panel_width - 240, add_y, 120, 40)
        is_hovered = generate_btn.collidepoint(mouse_pos)
        gen_color = (60, 150, 60) if is_hovered else (50, 130, 50)
        pygame.draw.rect(screen, gen_color, generate_btn, border_radius=5)
        
        gen_text = self.button_font.render("Generate", True, (255, 255, 255))
        gen_text_rect = gen_text.get_rect(center=generate_btn.center)
        screen.blit(gen_text, gen_text_rect)
        
        # Close button
        close_btn = pygame.Rect(self.panel_x + self.panel_width - 120, add_y, 100, 40)
        is_hovered = close_btn.collidepoint(mouse_pos)
        close_color = self.button_hover_color if is_hovered else self.button_color
        pygame.draw.rect(screen, close_color, close_btn, border_radius=5)
        
        close_text = self.button_font.render("Close", True, (255, 255, 255))
        close_text_rect = close_text.get_rect(center=close_btn.center)
        screen.blit(close_text, close_text_rect)
        
        # Draw autocomplete suggestions last (on top of everything)
        if self.active_input_field == "item_name" and self.suggestions:
            suggestion_y = add_y + 45
            suggestion_height = 30
            
            for i, suggestion in enumerate(self.suggestions):
                sugg_rect = pygame.Rect(self.panel_x + 20, suggestion_y + i * suggestion_height, 
                                      200, suggestion_height)
                
                # Highlight selected suggestion (fully opaque background)
                if i == self.selected_suggestion:
                    pygame.draw.rect(screen, (80, 120, 180), sugg_rect)  # Highlighted: brighter blue
                    pygame.draw.rect(screen, (255, 255, 255), sugg_rect, width=2)  # White border
                else:
                    pygame.draw.rect(screen, (50, 50, 60), sugg_rect)  # Normal: slightly lighter gray
                
                # Suggestion text (formatted)
                formatted_name = self._format_item_name(suggestion)
                sugg_surface = self.button_font.render(formatted_name, True, self.item_text_color)
                screen.blit(sugg_surface, (sugg_rect.x + 10, sugg_rect.y + 5))
        
        # Instructions
        instructions = [
            "Click on input fields to edit",
            "Press Enter to submit, Generate to create blueprint, ESC to close"
        ]
        for i, instruction in enumerate(instructions):
            inst_surface = self.button_font.render(instruction, True, (150, 150, 150))
            inst_rect = inst_surface.get_rect(center=(self.panel_x + self.panel_width // 2,
                                                       add_y + 60 + i * 25))
            screen.blit(inst_surface, inst_rect)
    
    def handle_click(self, mouse_pos):
        """Handle mouse clicks on the panel.
        
        Returns:
            String indicating action: "close", "add", "remove_X" (X is index), or None
        """
        y_offset = self.panel_y + 100
        item_height = 45
        
        # Check remove buttons
        for i in range(len(self.recipes)):
            item_y = y_offset + i * item_height
            item_rect = pygame.Rect(self.panel_x + 20, item_y, self.panel_width - 40, item_height)
            remove_btn = pygame.Rect(item_rect.right - 40, item_rect.y + 5, 35, 35)
            
            if remove_btn.collidepoint(mouse_pos):
                return f"remove_{i}"
        
        # Check input fields
        add_y = self.panel_y + self.panel_height - 150
        item_name_input = pygame.Rect(self.panel_x + 20, add_y, 200, 40)
        count_input = pygame.Rect(self.panel_x + 230, add_y, 80, 40)
        
        if item_name_input.collidepoint(mouse_pos):
            self.active_input_field = "item_name"
            self.update_suggestions()
            return None
        elif count_input.collidepoint(mouse_pos):
            self.active_input_field = "count"
            self.suggestions = []  # Clear suggestions
            return None
        
        # Check suggestion clicks
        if self.active_input_field == "item_name" and self.suggestions:
            suggestion_y = add_y + 45
            suggestion_height = 30
            for i, suggestion in enumerate(self.suggestions):
                sugg_rect = pygame.Rect(self.panel_x + 20, suggestion_y + i * suggestion_height, 
                                      200, suggestion_height)
                if sugg_rect.collidepoint(mouse_pos):
                    self.typing_item_name = suggestion
                    self.suggestions = []
                    self.active_input_field = None  # Clear field after selection
                    # Auto-fill count if empty
                    if not self.typing_count:
                        self.typing_count = "1"
                    return "add_from_suggestion"
        
        # Check add button (+ button)
        if self.typing_item_name and (self.typing_count.isdigit() or self.typing_count == ""):
            add_btn = pygame.Rect(count_input.right + 10, add_y, 40, 40)
            if add_btn.collidepoint(mouse_pos):
                return "add"
        
        # Check generate button
        generate_btn = pygame.Rect(self.panel_x + self.panel_width - 240, add_y, 120, 40)
        if generate_btn.collidepoint(mouse_pos):
            if len(self.recipes) > 0:
                return "generate"
        
        # Check close button
        close_btn = pygame.Rect(self.panel_x + self.panel_width - 120, add_y, 100, 40)
        if close_btn.collidepoint(mouse_pos):
            return "close"
        
        # Click outside inputs
        if not item_name_input.collidepoint(mouse_pos) and not count_input.collidepoint(mouse_pos):
            self.active_input_field = None
        
        return None
    
    def handle_key(self, event):
        """Handle keyboard input.
        
        Returns:
            String indicating action or None
        """
        if event.type == pygame.KEYDOWN:
            if self.active_input_field == "item_name" and self.suggestions:
                # Handle autocomplete navigation
                if event.key == pygame.K_UP:
                    self.selected_suggestion = (self.selected_suggestion - 1) % len(self.suggestions)
                    return None
                elif event.key == pygame.K_DOWN:
                    self.selected_suggestion = (self.selected_suggestion + 1) % len(self.suggestions)
                    return None
                elif event.key == pygame.K_TAB:
                    # Accept selected suggestion
                    if self.suggestions:
                        self.typing_item_name = self.suggestions[self.selected_suggestion]
                        self.suggestions = []
                        self.active_input_field = "count"
                    return None
            
            if self.active_input_field:
                if event.key == pygame.K_BACKSPACE:
                    if self.active_input_field == "item_name":
                        self.typing_item_name = self.typing_item_name[:-1]
                        self.update_suggestions()  # Update suggestions as user types
                    elif self.active_input_field == "count":
                        self.typing_count = self.typing_count[:-1]
                elif event.key == pygame.K_RETURN:
                    if self.active_input_field == "item_name":
                        if self.suggestions:
                            # Accept selected suggestion
                            self.typing_item_name = self.suggestions[self.selected_suggestion]
                            self.suggestions = []
                        self.active_input_field = "count"
                    elif self.active_input_field == "count":
                        # Add recipe and reset
                        if self.typing_item_name:
                            count = int(self.typing_count) if self.typing_count and self.typing_count.isdigit() else 1
                            self.add_recipe(self.typing_item_name, count)
                            self.typing_item_name = ""
                            self.typing_count = ""
                            self.active_input_field = "item_name"
                        return "recipe_added"
                elif event.unicode and event.unicode.isprintable():
                    if self.active_input_field == "item_name":
                        self.typing_item_name += event.unicode
                        self.update_suggestions()  # Update suggestions as user types
                    elif self.active_input_field == "count" and event.unicode.isdigit():
                        self.typing_count += event.unicode
        
        return None

