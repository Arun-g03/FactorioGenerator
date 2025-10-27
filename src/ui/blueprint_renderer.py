import pygame
import logging
from sprite_loader import SpriteLoader
from sprite_mapper import SpriteMapper
from screen_manager import ScreenManager
from toolbar import Toolbar
from recipe_panel import RecipePanel
from core.constants import PYGAME_WINDOW_WIDTH, PYGAME_WINDOW_HEIGHT, PYGAME_TILE_SIZE

class BlueprintRenderer:
    """
    Renders Factorio blueprints using pygame with actual game sprites.
    """
    
    def __init__(self, tile_size=64):
        self.screen_manager = ScreenManager()
        self.tile_size = tile_size
        self.sprite_loader = SpriteLoader()
        self.sprite_mapper = SpriteMapper()
        self.screen = None
        self.width = PYGAME_WINDOW_WIDTH
        self.height = PYGAME_WINDOW_HEIGHT
        self.logger = logging.getLogger(__name__)
        
        # Camera state
        self.camera_x = 0
        self.camera_y = 0
        self.zoom = 1.0
        self.dragging = False
        self.last_mouse_pos = (0, 0)
        
        # Input/output tracking
        self.input_positions = set()  # Set of (x, y) tuples for input positions
        self.output_positions = set()  # Set of (x, y) tuples for output positions
        
        # Pause menu state
        self.paused = False
        self.pause_selected_button = 0
        
        # Toolbar
        self.toolbar = None
        self.blueprint_string = None
        
        # Recipe panel
        self.recipe_panel = None
        self.show_recipe_panel = False
    
    def calculate_bounds(self, entities):
        """Calculate the bounding box for all entities."""
        if not entities:
            return (0, 0, 1, 1)
        
        min_x = min(entity['position']['x'] for entity in entities)
        max_x = max(entity['position']['x'] for entity in entities)
        min_y = min(entity['position']['y'] for entity in entities)
        max_y = max(entity['position']['y'] for entity in entities)
        
        return (min_x, min_y, max_x - min_x, max_y - min_y)
    
    def initialize_screen(self, entities):
        """Initialize the pygame screen based on blueprint bounds."""
        min_x, min_y, width, height = self.calculate_bounds(entities)
        
        # Get screen from manager
        self.screen = self.screen_manager.get_screen()
        self.screen_manager.set_caption("Factorio Blueprint Visualizer")
        
        # Center camera on blueprint
        padding = 5
        self.camera_x = -min_x * self.tile_size + padding * self.tile_size
        self.camera_y = -min_y * self.tile_size + padding * self.tile_size
        
        screen_width = PYGAME_WINDOW_WIDTH
        screen_height = PYGAME_WINDOW_HEIGHT
        self.logger.info(f"Initialized screen: {screen_width}x{screen_height}")
    
    def world_to_screen(self, world_x, world_y):
        """Convert world coordinates to screen coordinates."""
        screen_x = world_x * self.tile_size * self.zoom + self.camera_x
        screen_y = world_y * self.tile_size * self.zoom + self.camera_y
        return int(screen_x), int(screen_y)
    
    def render_entity(self, entity, show_grid=True):
        """Render a single entity."""
        # Handle both Entity objects and dictionaries
        if hasattr(entity, 'to_dict'):
            entity = entity.to_dict()
        
        # Get entity properties
        entity_name = entity.get('name', 'unknown')
        position = entity.get('position', {})
        direction = entity.get('direction')
        
        # Convert position - handle both dict and tuple formats
        if isinstance(position, dict):
            world_x = position.get('x', 0)
            world_y = position.get('y', 0)
        elif isinstance(position, (tuple, list)):
            world_x = position[0]
            world_y = position[1]
        else:
            world_x = 0
            world_y = 0
        
        screen_x, screen_y = self.world_to_screen(world_x, world_y)
        
        # Get sprite
        sprite_name = self.sprite_mapper.get_sprite_name(entity_name, direction)
        sprite = self.sprite_loader.get_sprite(sprite_name)
        
        # If sprite not found, draw a colored rectangle as fallback
        if sprite is None:
            # Try to find a similar sprite
            fallback_sprite = self._find_fallback_sprite(entity_name)
            if fallback_sprite:
                sprite = fallback_sprite
            else:
                # Draw a colored rectangle
                color = self._get_color_for_entity(entity_name)
                scaled_size = int(self.tile_size * self.zoom)
                pygame.draw.rect(self.screen, color, 
                               (screen_x, screen_y, scaled_size, scaled_size))
                self.logger.debug(f"No sprite for {sprite_name}, using fallback")
                return
        
        # Scale and draw sprite
        if self.zoom != 1.0:
            sprite_width = int(sprite.get_width() * self.zoom)
            sprite_height = int(sprite.get_height() * self.zoom)
            sprite = pygame.transform.scale(sprite, (sprite_width, sprite_height))
        
        self.screen.blit(sprite, (screen_x, screen_y))
    
    def _find_fallback_sprite(self, entity_name):
        """Try to find a fallback sprite for an entity."""
        # Try base name without suffixes
        base_parts = entity_name.split('-')
        if len(base_parts) > 1:
            # Try different variations
            for i in range(len(base_parts), 0, -1):
                partial_name = '-'.join(base_parts[:i])
                sprite = self.sprite_loader.get_sprite(partial_name)
                if sprite:
                    return sprite
        return None
    
    def _get_color_for_entity(self, entity_name):
        """Get a color for an entity type as fallback."""
        if 'belt' in entity_name:
            return (200, 100, 50)  # Orange
        elif 'inserter' in entity_name:
            return (50, 200, 50)  # Green
        elif 'pipe' in entity_name:
            return (200, 50, 50)  # Red
        elif 'machine' in entity_name or 'furnace' in entity_name:
            return (100, 100, 200)  # Blue
        elif 'pole' in entity_name:
            return (150, 150, 150)  # Gray
        else:
            return (128, 128, 128)  # Gray
    
    def render_grid(self):
        """Render a grid overlay."""
        if self.zoom < 0.5:  # Don't show grid when zoomed out too much
            return
        
        width, height = self.screen.get_size()
        
        # Calculate grid spacing
        grid_spacing = int(self.tile_size * self.zoom)
        
        color = (50, 50, 50)
        
        # Draw vertical lines
        start_x = self.camera_x % grid_spacing
        for x in range(start_x, width, grid_spacing):
            pygame.draw.line(self.screen, color, (x, 0), (x, height), 1)
        
        # Draw horizontal lines
        start_y = self.camera_y % grid_spacing
        for y in range(start_y, height, grid_spacing):
            pygame.draw.line(self.screen, color, (0, y), (width, y), 1)
    
    def handle_events(self):
        """Handle pygame events.
        
        Returns:
            "menu" if returning to main menu
            False if quitting
            True to continue
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "menu"  # Return to menu instead of quitting
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    mouse_pos = pygame.mouse.get_pos()
                    
                    # Handle pause menu clicks
                    if self.paused:
                        # Check if clicking on pause menu buttons
                        button_width = 400
                        button_height = 60
                        button_y_start = 250
                        button_spacing = 20
                        
                        for i in range(2):
                            button_y = button_y_start + i * (button_height + button_spacing)
                            button_rect = pygame.Rect((self.width - button_width) // 2, button_y,
                                                    button_width, button_height)
                            if button_rect.collidepoint(mouse_pos):
                                if i == 0:  # Resume
                                    self.paused = False
                                elif i == 1:  # Return to menu
                                    return "menu"
                        continue  # Don't process camera controls
                    
                    # Check if clicking on recipe panel
                    if self.show_recipe_panel and self.recipe_panel:
                        panel_action = self.recipe_panel.handle_click(mouse_pos)
                        if panel_action:
                            return self._handle_recipe_panel_action(panel_action)
                        # Also handle key input for recipe panel
                        self.recipe_panel.handle_key(event)
                        continue
                    
                    # Check if clicking on toolbar
                    if self.toolbar:
                        toolbar_action = self.toolbar.handle_click(mouse_pos)
                        if toolbar_action:
                            return toolbar_action
                    
                    self.dragging = True
                    self.last_mouse_pos = mouse_pos
                elif event.button == 4:  # Scroll up
                    if not self.paused:  # Only zoom when not paused
                        self.zoom *= 1.1
                        self.zoom = min(self.zoom, 3.0)
                elif event.button == 5:  # Scroll down
                    if not self.paused:  # Only zoom when not paused
                        self.zoom /= 1.1
                        self.zoom = max(self.zoom, 0.1)
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self.dragging = False
            elif event.type == pygame.MOUSEMOTION:
                if self.dragging and not self.paused:  # Only drag camera when not paused
                    dx, dy = pygame.mouse.get_pos()
                    self.camera_x += dx - self.last_mouse_pos[0]
                    self.camera_y += dy - self.last_mouse_pos[1]
                    self.last_mouse_pos = (dx, dy)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:  # Pause/unpause
                    self.paused = not self.paused
                elif event.key == pygame.K_s:  # Save screenshot
                    self.save_screenshot()
                elif event.key == pygame.K_r:  # Reset camera
                    self._reset_camera()
                elif event.key == pygame.K_UP:  # Navigate pause menu
                    if self.paused:
                        self.pause_selected_button = (self.pause_selected_button - 1) % 2
                elif event.key == pygame.K_DOWN:  # Navigate pause menu
                    if self.paused:
                        self.pause_selected_button = (self.pause_selected_button + 1) % 2
                elif event.key == pygame.K_RETURN:  # Select in pause menu
                    if self.paused:
                        if self.pause_selected_button == 0:  # Resume
                            self.paused = False
                        elif self.pause_selected_button == 1:  # Return to menu
                            return "menu"
                elif event.key == pygame.K_ESCAPE:  # Close recipe panel
                    if self.show_recipe_panel:
                        self.show_recipe_panel = False
                        return True
            
            # Handle key input for recipe panel
            if self.show_recipe_panel and self.recipe_panel:
                panel_result = self.recipe_panel.handle_key(event)
                if panel_result:
                    return self._handle_recipe_panel_action(panel_result)
        
        return True
    
    def _handle_recipe_panel_action(self, action):
        """Handle actions from the recipe panel."""
        if action == "close":
            self.show_recipe_panel = False
            return True
        elif action == "generate":
            # Close the panel and return to trigger generation
            self.show_recipe_panel = False
            return "generate"
        elif action.startswith("remove_"):
            index = int(action.split("_")[1])
            self.recipe_panel.remove_recipe(index)
            return True
        elif action in ("add", "add_from_suggestion"):
            if self.recipe_panel.typing_item_name:
                count = int(self.recipe_panel.typing_count) if self.recipe_panel.typing_count and self.recipe_panel.typing_count.isdigit() else 1
                self.recipe_panel.add_recipe(self.recipe_panel.typing_item_name, count)
                self.recipe_panel.typing_item_name = ""
                self.recipe_panel.typing_count = ""
                self.recipe_panel.suggestions = []
                self.recipe_panel.active_input_field = "item_name"
            return True
        elif action == "recipe_added":
            # Recipe was added, update if needed
            return True
    
    def _reset_camera(self):
        """Reset camera position and zoom."""
        self.camera_x = 0
        self.camera_y = 0
        self.zoom = 1.0
    
    def save_screenshot(self):
        """Save a screenshot of the current view."""
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"blueprint_{timestamp}.png"
        pygame.image.save(self.screen, filename)
        self.logger.info(f"Screenshot saved as {filename}")
    
    def identify_inputs_outputs(self, entities):
        """
        Identify input and output positions by analyzing entity types and positions.
        
        Args:
            entities: List of entity dictionaries
        """
        # Find resource input belts (typically at the start)
        for entity in entities:
            entity_name = entity.get('name', '')
            pos = entity.get('position', {})
            
            if isinstance(pos, dict):
                x, y = pos.get('x', 0), pos.get('y', 0)
            else:
                x, y = pos[0] if len(pos) > 0 else 0, pos[1] if len(pos) > 1 else 0
            
            # Input indicators: resource belts, initial materials
            if 'resource' in entity_name or 'iron-ore' in entity_name or 'copper-ore' in entity_name:
                self.input_positions.add((x, y))
            
            # Output indicators: assembly machine outputs, finished products
            if 'assembling-machine' in entity_name or 'furnace' in entity_name:
                # Assume output is slightly offset from the machine
                # (This is a heuristic, actual output position depends on machine direction)
                self.output_positions.add((x, y))
        
        self.logger.info(f"Identified {len(self.input_positions)} input positions and {len(self.output_positions)} output positions")
    
    def render_position_markers(self):
        """Render colored markers for input (green) and output (red) positions."""
        marker_radius = int(8 * self.zoom)
        
        # Render input markers (green)
        for x, y in self.input_positions:
            screen_x, screen_y = self.world_to_screen(x, y)
            pygame.draw.circle(self.screen, (0, 255, 0), (screen_x, screen_y), marker_radius)
            pygame.draw.circle(self.screen, (255, 255, 255), (screen_x, screen_y), marker_radius, 2)
        
        # Render output markers (red)
        for x, y in self.output_positions:
            screen_x, screen_y = self.world_to_screen(x, y)
            pygame.draw.circle(self.screen, (255, 0, 0), (screen_x, screen_y), marker_radius)
            pygame.draw.circle(self.screen, (255, 255, 255), (screen_x, screen_y), marker_radius, 2)
    
    def render(self, blueprint, blueprint_string=None):
        """
        Render a blueprint.
        
        Args:
            blueprint: Blueprint dictionary with entities list
            blueprint_string: Encoded blueprint string for copying
        
        Returns:
            String indicating exit reason ("menu" if returned to menu)
        """
        entities = blueprint.get('blueprint', {}).get('entities', [])
        
        if not entities:
            self.logger.warning("No entities to render")
            return None
        
        # Store blueprint string for copying
        self.blueprint_string = blueprint_string
        
        # Initialize toolbar
        if self.toolbar is None:
            self.toolbar = Toolbar(self.width, self.height, self.height)
        
        # Initialize recipe panel
        if self.recipe_panel is None:
            self.recipe_panel = RecipePanel()
        
        # Identify input/output positions
        self.identify_inputs_outputs(entities)
        
        # Initialize screen if not already done
        if self.screen is None:
            self.initialize_screen(entities)
        
        self.logger.info(f"Rendering {len(entities)} entities")
        
        running = True
        result = None
        show_recipe_menu = False
        
        while running:
            action = self.handle_events()
            
            # Handle toolbar actions
            if action == "recipes":
                if not self.recipe_panel:
                    self.recipe_panel = RecipePanel()
                self.show_recipe_panel = True
            elif action == "generate":
                # Trigger blueprint generation with recipes
                return "generate_blueprint"
            elif action == "copy":
                if self.blueprint_string:
                    self.toolbar.copy_to_clipboard(self.blueprint_string)
                    self.logger.info("Blueprint copied to clipboard!")
                else:
                    self.logger.warning("No blueprint string to copy")
            elif action == "pause":
                self.paused = not self.paused
            elif action == "menu":
                return "menu"
            
            # If handle_events returns a string, we should exit
            if action in ("menu", "exit"):
                break
            
            # Clear screen
            self.screen.fill((30, 30, 40))  # Dark background
            
            # Draw recipe panel if shown (draws background)
            if self.show_recipe_panel and self.recipe_panel:
                self.recipe_panel.draw(self.screen)
            else:
                # Only draw blueprint if recipe panel is not shown
                # Render grid
                self.render_grid()
                
                # Render entities
                for entity in entities:
                    self.render_entity(entity)
                
                # Render position markers
                self.render_position_markers()
                
                # Draw UI info (only if not paused)
                if not self.paused:
                    self._draw_ui_info(len(entities))
                
                # Draw toolbar
                if self.toolbar:
                    self.toolbar.draw(self.screen)
            
            # Draw pause menu if paused
            if self.paused:
                self._draw_pause_menu()
        
            self.screen_manager.flip()
            self.screen_manager.tick(60)
        
        return result if result else action
    
    def _draw_ui_info(self, entity_count):
        """Draw UI information overlay."""
        font = pygame.font.Font(None, 24)
        
        # Create info text
        legend = "Green=Input, Red=Output | "
        info_text = f"{legend}Entities: {entity_count} | Zoom: {self.zoom:.2f}x"
        controls = "Controls: Scroll=Zoom, Drag=Pan, S=Save, R=Reset, ESC=Pause"
        
        # Draw semi-transparent background for text
        text_surface = font.render(info_text, True, (255, 255, 255))
        controls_surface = font.render(controls, True, (200, 200, 200))
        
        text_rect = text_surface.get_rect()
        
        # Draw background rectangle for first line
        pygame.draw.rect(self.screen, (0, 0, 0, 200), 
                       (0, 0, text_rect.width + 10, text_rect.height + 10))
        pygame.draw.rect(self.screen, (0, 0, 0, 200), 
                       (0, text_rect.height + 5, controls_surface.get_width() + 10, text_rect.height + 10))
        
        # Draw text
        self.screen.blit(text_surface, (5, 5))
        self.screen.blit(controls_surface, (5, text_rect.height + 10))
    
    def _draw_pause_menu(self):
        """Draw the pause menu overlay."""
        # Draw semi-transparent overlay
        overlay = pygame.Surface((self.width, self.height))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))
        
        # Draw pause menu
        menu_font = pygame.font.Font(None, 72)
        button_font = pygame.font.Font(None, 48)
        button_font_small = pygame.font.Font(None, 32)
        
        # Title
        title_text = "PAUSED"
        title_surface = menu_font.render(title_text, True, (255, 200, 50))
        title_rect = title_surface.get_rect(center=(self.width // 2, 150))
        self.screen.blit(title_surface, title_rect)
        
        # Buttons
        buttons = [
            {"text": "Resume", "key": "resume"},
            {"text": "Return to Menu", "key": "menu"}
        ]
        
        button_width = 400
        button_height = 60
        button_y_start = 250
        button_spacing = 20
        
        for i, button in enumerate(buttons):
            button_y = button_y_start + i * (button_height + button_spacing)
            button_rect = pygame.Rect((self.width - button_width) // 2, button_y, 
                                     button_width, button_height)
            
            # Button color
            color = (100, 140, 200) if i == self.pause_selected_button else (60, 90, 150)
            
            # Draw button
            pygame.draw.rect(self.screen, color, button_rect, border_radius=10)
            pygame.draw.rect(self.screen, (255, 255, 255), button_rect, width=2, border_radius=10)
            
            # Button text
            text_surface = button_font.render(button["text"], True, (255, 255, 255))
            text_rect = text_surface.get_rect(center=button_rect.center)
            self.screen.blit(text_surface, text_rect)
        
        # Instructions
        instructions = [
            "↑↓: Navigate | Enter: Select | ESC: Resume"
        ]
        for i, instruction in enumerate(instructions):
            inst_surface = button_font_small.render(instruction, True, (200, 200, 200))
            inst_rect = inst_surface.get_rect(center=(self.width // 2, 400))
            self.screen.blit(inst_surface, inst_rect)
    
    def cleanup(self):
        """Clean up pygame resources."""
        # Don't quit pygame here, let the screen manager handle it
        pass

