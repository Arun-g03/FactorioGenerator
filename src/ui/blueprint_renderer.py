import math
import pygame
import logging
from sprite_loader import SpriteLoader
from sprite_mapper import SpriteMapper
from screen_manager import ScreenManager
from toolbar import Toolbar
from recipe_panel import RecipePanel
from placement_options_modal import PlacementOptionsModal
from core.constants import (
    PYGAME_WINDOW_WIDTH,
    PYGAME_WINDOW_HEIGHT,
    PYGAME_TILE_SIZE,
    PlacementStrategy,
    inserter_direction_for_display,
)

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
        
        # Recipe panel (modal over workspace)
        self.recipe_panel = None
        self.show_recipe_panel = False
        self.production_stages = []
        self.rate_summary = []
        self.entities = []
        self._recipes_data = None
        self._generation_mode = None
        self.placement_strategy = PlacementStrategy.RULE_BASED
        self.layout_fitness = None
        self.genetic_generations = 0
        self.genetic_converged = False
        self._genetic_progress = None

        self.placement_options_modal = None
        self.show_placement_options = False
        self.placement_settings = None

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
        self.screen = self.screen_manager.get_screen()
        self.screen_manager.set_caption("Factorio Blueprint Visualizer")
        self._center_camera_on_blueprint(entities)
        self.logger.info(
            "Initialized screen: %sx%s",
            PYGAME_WINDOW_WIDTH,
            PYGAME_WINDOW_HEIGHT,
        )

    def _on_window_resize(self, width: int, height: int) -> None:
        """Update layout for a new window size."""
        self.width = width
        self.height = height
        if self.toolbar:
            self.toolbar.resize(width, height)
        if self.recipe_panel:
            self.recipe_panel.set_window_size(width, height)
        if self.placement_options_modal:
            self.placement_options_modal.set_window_size(width, height)

    def _viewport_center(self):
        """Pixel center of the drawable canvas (area above the toolbar)."""
        canvas_bottom = self.toolbar.y_position if self.toolbar else self.height
        return self.width // 2, canvas_bottom // 2

    def _center_camera_on_blueprint(self, entities=None):
        """Pan the camera so the blueprint bounding box is centered in the workspace."""
        entities = entities if entities is not None else self.entities
        if not entities:
            self.logger.warning("No blueprint to center on.")
            return False

        min_x, min_y, width, height = self.calculate_bounds(entities)
        world_cx = min_x + width / 2
        world_cy = min_y + height / 2
        screen_cx, screen_cy = self._viewport_center()
        scale = self.tile_size * self.zoom
        self.camera_x = screen_cx - world_cx * scale
        self.camera_y = screen_cy - world_cy * scale
        self.logger.info(
            "Centered camera on blueprint at (%.1f, %.1f)",
            world_cx,
            world_cy,
        )
        return True
    
    def world_to_screen(self, world_x, world_y):
        """Convert world coordinates to screen coordinates."""
        screen_x = world_x * self.tile_size * self.zoom + self.camera_x
        screen_y = world_y * self.tile_size * self.zoom + self.camera_y
        return int(screen_x), int(screen_y)

    def screen_to_world(self, screen_x, screen_y):
        """Convert screen coordinates to world coordinates."""
        scale = self.tile_size * self.zoom
        if scale <= 0:
            return 0.0, 0.0
        return (
            (screen_x - self.camera_x) / scale,
            (screen_y - self.camera_y) / scale,
        )

    def _zoom_at_screen(self, screen_x, screen_y, factor):
        """Zoom while keeping the world point under the cursor fixed on screen."""
        world_x, world_y = self.screen_to_world(screen_x, screen_y)
        new_zoom = max(0.1, min(3.0, self.zoom * factor))
        if abs(new_zoom - self.zoom) < 1e-9:
            return
        scale = self.tile_size * new_zoom
        self.camera_x = screen_x - world_x * scale
        self.camera_y = screen_y - world_y * scale
        self.zoom = new_zoom
    
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
        
        tile_screen_x, tile_screen_y = self.world_to_screen(world_x, world_y)
        
        # Get sprite (inserters use base platform; direction shown via arrow overlay)
        is_inserter = "inserter" in entity_name
        sprite_direction = None if is_inserter else direction
        sprite_name = self.sprite_mapper.get_sprite_name(entity_name, sprite_direction)
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
                               (tile_screen_x, tile_screen_y, scaled_size, scaled_size))
                self.logger.debug(f"No sprite for {sprite_name}, using fallback")
                if is_inserter:
                    self._draw_inserter_direction_arrow(
                        tile_screen_x,
                        tile_screen_y,
                        inserter_direction_for_display(direction),
                    )
                return
        
        sprite = self._scale_sprite_to_tile(sprite)
        blit_x, blit_y = self._center_sprite_on_tile(sprite, tile_screen_x, tile_screen_y)
        self.screen.blit(sprite, (blit_x, blit_y))

        if is_inserter:
            self._draw_inserter_direction_arrow(
                tile_screen_x,
                tile_screen_y,
                inserter_direction_for_display(direction),
            )

    def _scale_sprite_to_tile(self, sprite):
        """Scale a sprite to fit within one tile."""
        tile = max(1, int(self.tile_size * self.zoom))
        sw, sh = sprite.get_width(), sprite.get_height()
        if sw <= 0 or sh <= 0:
            return sprite
        scale = min(tile / sw, tile / sh)
        if abs(scale - 1.0) < 0.01:
            return sprite
        return pygame.transform.smoothscale(
            sprite, (max(1, int(sw * scale)), max(1, int(sh * scale)))
        )

    def _center_sprite_on_tile(self, sprite, screen_x, screen_y):
        """Offset blit position so the sprite is centered on its tile."""
        tile = int(self.tile_size * self.zoom)
        offset_x = (tile - sprite.get_width()) // 2
        offset_y = (tile - sprite.get_height()) // 2
        return screen_x + offset_x, screen_y + offset_y

    def _direction_to_arrow_vector(self, direction):
        """Map Factorio blueprint direction to a screen-space unit vector."""
        from core.constants import direction_arrow_vector

        return direction_arrow_vector(direction)

    def _draw_inserter_direction_arrow(self, tile_screen_x, tile_screen_y, direction):
        """Draw a direction arrow over an inserter tile."""
        dx, dy = self._direction_to_arrow_vector(direction)
        tile = max(4, int(self.tile_size * self.zoom))
        cx = tile_screen_x + tile // 2
        cy = tile_screen_y + tile // 2

        shaft_len = max(8, tile // 3)
        tip_x = cx + dx * shaft_len
        tip_y = cy + dy * shaft_len

        arrow_color = (255, 255, 255)
        outline_color = (30, 30, 30)
        line_width = max(2, int(2 * self.zoom))

        pygame.draw.line(
            self.screen, outline_color, (cx, cy), (tip_x, tip_y), line_width + 2
        )
        pygame.draw.line(
            self.screen, arrow_color, (cx, cy), (tip_x, tip_y), line_width
        )

        head_len = max(5, tile // 5)
        angle = math.atan2(dy, dx)
        head_spread = math.pi / 7
        left = (
            tip_x - head_len * math.cos(angle - head_spread),
            tip_y - head_len * math.sin(angle - head_spread),
        )
        right = (
            tip_x - head_len * math.cos(angle + head_spread),
            tip_y - head_len * math.sin(angle + head_spread),
        )
        head_points = [(tip_x, tip_y), left, right]
        pygame.draw.polygon(self.screen, outline_color, head_points)
        pygame.draw.polygon(self.screen, arrow_color, head_points)
    
    def _find_fallback_sprite(self, entity_name):
        """Try to find a fallback sprite for an entity."""
        candidates = [entity_name]
        if "inserter" in entity_name:
            candidates.extend([
                f"{entity_name}-platform-east",
                f"{entity_name}-platform",
            ])
        if "belt" in entity_name:
            candidates.extend([
                f"{entity_name}-east",
                "transport-belt-east",
            ])

        for name in candidates:
            sprite = self.sprite_loader.get_sprite(name)
            if sprite:
                return sprite

        base_parts = entity_name.split('-')
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
        
        # Draw vertical lines (camera is float from panning; range needs ints)
        start_x = int(self.camera_x) % grid_spacing
        for x in range(start_x, width, grid_spacing):
            pygame.draw.line(self.screen, color, (x, 0), (x, height), 1)
        
        # Draw horizontal lines
        start_y = int(self.camera_y) % grid_spacing
        for y in range(start_y, height, grid_spacing):
            pygame.draw.line(self.screen, color, (0, y), (width, y), 1)
    
    def handle_events(self):
        """Handle pygame events.
        
        Returns:
            "menu" if returning to main menu
            "exit" on window close
            "targets", "copy", "pause" for toolbar actions
            True to continue
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "exit"
            if self.screen_manager.handle_resize_event(event):
                w, h = self.screen_manager.get_size()
                self._on_window_resize(w, h)
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
                    
                    if self.show_placement_options and self.placement_options_modal:
                        opt_action = self.placement_options_modal.handle_click(mouse_pos)
                        if opt_action:
                            self._handle_placement_options_action(opt_action)
                        continue

                    # Targets modal captures clicks
                    if self.show_recipe_panel and self.recipe_panel:
                        panel_action = self.recipe_panel.handle_click(mouse_pos)
                        if panel_action:
                            self._handle_recipe_panel_action(panel_action)
                        continue
                    
                    if not self._workspace_interactive():
                        continue

                    # Check if clicking on toolbar
                    if self.toolbar:
                        toolbar_action = self.toolbar.handle_click(mouse_pos)
                        if toolbar_action:
                            return toolbar_action
                    
                    self.dragging = True
                    self.last_mouse_pos = mouse_pos
                elif event.button in (4, 5):  # Scroll wheel
                    if self._workspace_interactive():
                        mx, my = event.pos
                        factor = 1.1 if event.button == 4 else 1.0 / 1.1
                        self._zoom_at_screen(mx, my, factor)
            elif event.type == pygame.MOUSEWHEEL:
                if self._workspace_interactive():
                    mx, my = pygame.mouse.get_pos()
                    factor = 1.1 if event.y > 0 else 1.0 / 1.1
                    self._zoom_at_screen(mx, my, factor)
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self.dragging = False
            elif event.type == pygame.MOUSEMOTION:
                if self.dragging and self._workspace_interactive():
                    dx, dy = pygame.mouse.get_pos()
                    self.camera_x += dx - self.last_mouse_pos[0]
                    self.camera_y += dy - self.last_mouse_pos[1]
                    self.last_mouse_pos = (dx, dy)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.show_placement_options:
                        self.show_placement_options = False
                        continue
                    if self.show_recipe_panel:
                        self.show_recipe_panel = False
                        continue
                    if self.paused:
                        self.paused = False
                    else:
                        self.paused = True
                elif event.key == pygame.K_o and not self.paused:
                    return "options"
                elif event.key == pygame.K_o and not self.paused:
                    return "options"
                elif event.key == pygame.K_t and not self.paused:
                    return "targets"
                elif event.key == pygame.K_g and not self.paused:
                    return "generate"
                elif event.key == pygame.K_s and self._workspace_interactive():
                    self.save_screenshot()
                elif event.key == pygame.K_r and self._workspace_interactive():
                    self._reset_camera()
                elif event.key == pygame.K_c and self._workspace_interactive():
                    self._center_camera_on_blueprint()
                elif event.key == pygame.K_UP:
                    if self.paused:
                        self.pause_selected_button = (self.pause_selected_button - 1) % 2
                elif event.key == pygame.K_DOWN:
                    if self.paused:
                        self.pause_selected_button = (self.pause_selected_button + 1) % 2
                elif event.key == pygame.K_RETURN:
                    if self.paused:
                        if self.pause_selected_button == 0:
                            self.paused = False
                        elif self.pause_selected_button == 1:
                            return "menu"
            
            if self.show_placement_options and self.placement_options_modal and event.type == pygame.KEYDOWN:
                opt_result = self.placement_options_modal.handle_key(event)
                if opt_result:
                    self._handle_placement_options_action(opt_result)

            if self.show_recipe_panel and self.recipe_panel and event.type == pygame.KEYDOWN:
                panel_result = self.recipe_panel.handle_key(event)
                if panel_result:
                    self._handle_recipe_panel_action(panel_result)

        return True
    
    def _handle_recipe_panel_action(self, action):
        """Handle actions from the targets modal."""
        result = self.recipe_panel.process_action(action)
        if result == "close":
            self.show_recipe_panel = False
            return
        if result == "generate":
            if self._generate_from_targets(self.recipe_panel.get_generation_config()):
                self.show_recipe_panel = False
        return
    
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
    
    def _workspace_interactive(self):
        """True when the user can pan/zoom the blueprint canvas."""
        return (
            not self.paused
            and not self.show_recipe_panel
            and not self.show_placement_options
        )

    def load_blueprint(self, gen_result):
        """Load generated blueprint data into the workspace."""
        from core.pipeline import BlueprintGenerationResult

        if isinstance(gen_result, BlueprintGenerationResult):
            self.entities = gen_result.blueprint.get("blueprint", {}).get("entities", [])
            self.blueprint_string = gen_result.blueprint_string
            self.production_stages = gen_result.production_stages
            self.rate_summary = gen_result.rate_summary
            self.placement_strategy = gen_result.placement_strategy
            self.layout_fitness = gen_result.layout_fitness
            self.genetic_generations = gen_result.genetic_generations
            self.genetic_converged = gen_result.genetic_converged
        else:
            blueprint = gen_result
            self.entities = blueprint.get("blueprint", {}).get("entities", [])
            self.production_stages = []

        self.input_positions.clear()
        self.output_positions.clear()
        self.identify_inputs_outputs(self.entities)
        if self.entities:
            self.initialize_screen(self.entities)

    def _get_generation_config(self):
        """Current targets, chain mode, and placement strategy."""
        from core.constants import GenerationMode

        if self.recipe_panel is None:
            self.recipe_panel = RecipePanel()
        config = self.recipe_panel.get_generation_config()
        config["placement"] = self.placement_strategy
        if config.get("mode") is None:
            config["mode"] = self._generation_mode or GenerationMode.ASSEMBLER_ONLY
        return config

    def _toggle_placement_strategy(self):
        if self.placement_strategy == PlacementStrategy.RULE_BASED:
            self.placement_strategy = PlacementStrategy.GENETIC
            self.logger.info("Placement strategy: genetic")
        else:
            self.placement_strategy = PlacementStrategy.RULE_BASED
            self.logger.info("Placement strategy: rule-based")
        if self.placement_options_modal:
            self.placement_options_modal.set_strategy(self.placement_strategy)

    def _generate_from_targets(self, config=None):
        """Run the generation pipeline and update the workspace."""
        from core.constants import GenerationMode
        from core.pipeline import GenerationStage, run_generation_pipeline

        if config is None:
            config = self._get_generation_config()
        elif isinstance(config, dict) and "placement" not in config:
            config = {**config, "placement": self.placement_strategy}

        if isinstance(config, dict):
            targets = config.get("targets", {})
            mode = config.get("mode", GenerationMode.ASSEMBLER_ONLY)
            placement = config.get("placement", self.placement_strategy)
        else:
            targets = config
            mode = self._generation_mode or GenerationMode.ASSEMBLER_ONLY
            placement = self.placement_strategy

        if not targets:
            self.logger.warning("No production targets set.")
            return False

        self._generation_mode = mode
        self.placement_strategy = placement

        progress_callback = None
        if placement == PlacementStrategy.GENETIC:
            progress_callback = self._on_genetic_progress

        self._genetic_progress = None
        if self.placement_settings is None:
            self._load_placement_settings()
        gen_result = run_generation_pipeline(
            targets,
            self._recipes_data,
            mode,
            placement,
            progress_callback=progress_callback,
            placement_settings=self.placement_settings,
        )
        self._genetic_progress = None
        self.load_blueprint(gen_result)
        self.logger.info(
            "[%s] %s entities, %s stage(s), placement=%s",
            GenerationStage.VISUALIZE,
            gen_result.entity_count,
            len(gen_result.production_stages),
            placement.value,
        )
        return True

    def _genetic_stale_limit(self):
        if self.placement_settings:
            return self.placement_settings.genetic.stale_generations_limit
        from planners.genetic_placement import STALE_GENERATIONS_LIMIT
        return STALE_GENERATIONS_LIMIT

    def _on_genetic_progress(self, generation, fitness, stale_generations, done):
        """Pump UI while genetic placement runs (called each generation)."""
        self._genetic_progress = {
            "generation": generation,
            "fitness": fitness,
            "stale": stale_generations,
            "done": done,
        }
        pygame.event.pump()
        self._draw_workspace()
        self._draw_genetic_progress_overlay()
        if self.toolbar:
            self.toolbar.draw(self.screen)
        self.screen_manager.flip()

    def _draw_genetic_progress_overlay(self):
        """Semi-transparent status while genetic optimization is running."""
        if not self._genetic_progress:
            return

        overlay = pygame.Surface((self.width, self.height))
        overlay.set_alpha(140)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        p = self._genetic_progress
        title_font = pygame.font.Font(None, 42)
        detail_font = pygame.font.Font(None, 28)

        if p["done"]:
            title = "Genetic placement complete"
        else:
            title = "Genetic placement — searching for best layout"

        title_surf = title_font.render(title, True, (255, 220, 100))
        title_rect = title_surf.get_rect(center=(self.width // 2, self.height // 2 - 50))
        self.screen.blit(title_surf, title_rect)

        lines = [
            f"Generation: {p['generation']}",
            f"Best fitness: {p['fitness']:.1f}",
            f"Stale generations: {p['stale']} / {self._genetic_stale_limit()}",
        ]
        if not p["done"]:
            lines.append("Runs until fitness stops improving…")

        y = title_rect.bottom + 16
        for line in lines:
            surf = detail_font.render(line, True, (220, 220, 230))
            rect = surf.get_rect(center=(self.width // 2, y))
            self.screen.blit(surf, rect)
            y += 32

    def _load_placement_settings(self):
        from core.app_config import load_config, load_placement_settings

        self.placement_settings = load_placement_settings(load_config())

    def _open_placement_options_modal(self):
        """Show placement options for the current strategy (Rules or Genetic)."""
        from core.placement_settings import PlacementSettingsBundle

        if self.placement_settings is None:
            self._load_placement_settings()
        if self.placement_options_modal is None:
            self.placement_options_modal = PlacementOptionsModal(
                self.placement_strategy,
                self.placement_settings,
            )
        else:
            self.placement_options_modal.set_strategy(self.placement_strategy)
            self.placement_options_modal.bundle = self.placement_settings
        self.placement_options_modal.set_window_size(self.width, self.height)
        self.show_placement_options = True
        self.show_recipe_panel = False

    def _handle_placement_options_action(self, action: str):
        from core.app_config import save_placement_settings
        from core.placement_settings import PlacementSettingsBundle

        if action == "save" and self.placement_options_modal:
            self.placement_settings = PlacementSettingsBundle(
                rule_based=self.placement_options_modal.bundle.rule_based.clamp(),
                genetic=self.placement_options_modal.bundle.genetic.clamp(),
            )
            save_placement_settings(self.placement_settings)
            self.logger.info("Placement settings saved")
        else:
            self._load_placement_settings()
        self.show_placement_options = False

    def _open_targets_modal(self):
        """Show the production-targets modal."""
        if self.recipe_panel is None:
            self.recipe_panel = RecipePanel()
        self.show_recipe_panel = True
        self.show_placement_options = False

    def run_workspace(self, recipes_data, initial_targets=None, open_targets_modal=False):
        """Main workspace loop: canvas + toolbar, targets in a modal overlay.

        Returns:
            "menu" when returning to the main menu, "exit" on quit.
        """
        self._recipes_data = recipes_data
        self.screen = self.screen_manager.get_screen()
        self.screen_manager.set_caption("Factorio Blueprint Workspace")
        w, h = self.screen_manager.get_size()
        self._on_window_resize(w, h)

        if self.toolbar is None:
            self.toolbar = Toolbar(self.width, self.height, self.height)
        else:
            self.toolbar.resize(self.width, self.height)
        if self.recipe_panel is None:
            self.recipe_panel = RecipePanel()
        else:
            self.recipe_panel.set_window_size(self.width, self.height)
        if initial_targets:
            self.recipe_panel.load_targets(initial_targets)

        self.entities = []
        self.blueprint_string = None
        self.production_stages = []
        self.rate_summary = []
        self.show_recipe_panel = open_targets_modal
        self.show_placement_options = False
        self.paused = False
        self._reset_camera()
        self._load_placement_settings()
        self.toolbar.placement_strategy = self.placement_strategy

        while True:
            action = self.handle_events()

            if action == "menu":
                return "menu"
            if action == "exit":
                return "exit"
            if action == "targets":
                self._open_targets_modal()
            elif action == "options":
                self._open_placement_options_modal()
            elif action == "generate":
                if not self._generate_from_targets():
                    self._open_targets_modal()
            elif action == "placement":
                self._toggle_placement_strategy()
                self.toolbar.placement_strategy = self.placement_strategy
            elif action == "copy":
                if self.blueprint_string:
                    self.toolbar.copy_to_clipboard(self.blueprint_string)
                else:
                    self.logger.warning("No blueprint to copy yet.")
            elif action == "pause":
                self.paused = not self.paused
            elif action == "center":
                self._center_camera_on_blueprint()

            self._draw_workspace()
            if self.show_placement_options and self.placement_options_modal:
                self.placement_options_modal.draw(self.screen)
            elif self.show_recipe_panel and self.recipe_panel:
                self.recipe_panel.draw(self.screen)
            if self.paused:
                self._draw_pause_menu()

            self.screen_manager.flip()
            self.screen_manager.tick(60)

    def _draw_workspace(self):
        """Draw the blueprint canvas, toolbar, and empty-state hint."""
        self.screen.fill((30, 30, 40))

        self.render_grid()
        for entity in self.entities:
            self.render_entity(entity)

        if self.entities:
            self.render_position_markers()
            self.render_production_stages()
            if not self.paused:
                self._draw_ui_info(len(self.entities))
        elif not self.paused and not self.show_recipe_panel:
            self._draw_empty_hint()

        if self.toolbar:
            self.toolbar.placement_strategy = self.placement_strategy
            self.toolbar.draw(self.screen)

    def _draw_empty_hint(self):
        """Hint shown on an empty workspace before the first generation."""
        font = pygame.font.Font(None, 36)
        hint = font.render(
            "Set targets, then Generate (toolbar or G)",
            True,
            (160, 160, 170),
        )
        sub = pygame.font.Font(None, 24).render(
            "Place: Rules/Genetic  |  O=options  |  T=targets  |  C=center  |  Scroll zoom, drag pan",
            True,
            (120, 120, 130),
        )
        hint_rect = hint.get_rect(center=(self.width // 2, self.height // 2 - 20))
        sub_rect = sub.get_rect(center=(self.width // 2, self.height // 2 + 20))
        self.screen.blit(hint, hint_rect)
        self.screen.blit(sub, sub_rect)

    def render_production_stages(self):
        """Label each production stage from the generation pipeline."""
        if not self.production_stages:
            return

        font = pygame.font.Font(None, 22)
        for index, stage in enumerate(self.production_stages, start=1):
            position = stage.get("position")
            if not position or len(position) < 2:
                continue
            x, y = position[0], position[1]
            screen_x, screen_y = self.world_to_screen(x, y)
            tile = int(self.tile_size * self.zoom)
            label_y = screen_y - max(14, int(14 * self.zoom))

            item = stage.get("type", "unknown")
            display_name = item.replace("-", " ").title()
            label = font.render(f"S{index}: {display_name}", True, (200, 220, 255))
            outline = font.render(f"S{index}: {display_name}", True, (20, 20, 30))
            label_x = screen_x + (tile - label.get_width()) // 2
            self.screen.blit(outline, (label_x + 1, label_y + 1))
            self.screen.blit(label, (label_x, label_y))

    def _draw_ui_info(self, entity_count):
        """Draw UI information overlay."""
        font = pygame.font.Font(None, 24)
        small = pygame.font.Font(None, 20)
        
        legend = "Green=Input, Red=Output | "
        stage_count = len(self.production_stages)
        info_text = (
            f"{legend}Entities: {entity_count} | Stages: {stage_count} | "
            f"Zoom: {self.zoom:.2f}x"
        )
        placement_label = (
            "Genetic" if self.placement_strategy == PlacementStrategy.GENETIC else "Rules"
        )
        controls = (
            f"G=Generate | Place:{placement_label} | T=Targets | "
            "Center=recenter | Scroll=Zoom | Drag=Pan | ESC=Pause"
        )

        lines = [info_text, controls]
        if self.layout_fitness is not None:
            gen_gens = (
                self.genetic_generations
                if self.placement_strategy == PlacementStrategy.GENETIC
                else None
            )
            lines.extend(self.layout_fitness.ui_summary_lines(genetic_generations=gen_gens))
            if self.placement_strategy == PlacementStrategy.GENETIC:
                status = "converged" if self.genetic_converged else "max generations"
                lines.append(f"  Genetic run: {status}")
        for line in self.rate_summary[:4]:
            name = line.item.replace("-", " ")
            text = (
                f"{name}: {line.requested:.0f} req, {line.achieved:.1f} achieved "
                f"({line.machine_count} machines)"
            )
            if line.warning:
                text += f" [{line.warning}]"
            lines.append(text)

        y = 5
        max_w = 0
        surfaces = []
        for i, text in enumerate(lines):
            surf = (font if i < 2 else small).render(text, True, (255, 255, 220) if i >= 2 and "[" in text else (255, 255, 255) if i < 2 else (200, 200, 200))
            surfaces.append(surf)
            max_w = max(max_w, surf.get_width())

        total_h = sum(s.get_height() + 4 for s in surfaces)
        pygame.draw.rect(self.screen, (0, 0, 0), (0, 0, max_w + 12, total_h + 8))
        for surf in surfaces:
            self.screen.blit(surf, (6, y))
            y += surf.get_height() + 4
    
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

