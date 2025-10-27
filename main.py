import json
import logging
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))
import pygame
from core.grid_env import Grid
from core.pathfinding import Pathfinder
from core.belt_router import BeltRouter
from core.inserter_placer import InserterPlacer
from planners.machine_placer import MachinePlacer
from core.blueprintEncoder import encode_blueprint

# Import UI components
sys.path.insert(0, str(Path(__file__).parent / "src" / "ui"))
from blueprint_renderer import BlueprintRenderer

# Load config and update constants if necessary
def load_config():
    """Load configuration from config.json."""
    config_file = Path(__file__).parent / "config.json"
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            # Update the constants module
            import core.constants as constants_module
            
            # Handle both old and new config format
            if "factorio_install_path" in config:
                # New format: base path
                constants_module.FACTORIO_INSTALL_PATH = config["factorio_install_path"]
                constants_module.FACTORIO_BASE_GRAPHICS_PATH = constants_module.get_factorio_graphics_path(config["factorio_install_path"])
            elif "factorio_graphics_path" in config:
                # Old format: full graphics path (backward compatibility)
                constants_module.FACTORIO_BASE_GRAPHICS_PATH = config["factorio_graphics_path"]
        except Exception as e:
            logging.warning(f"Failed to load config: {e}")

# Load JSON data
with open('src/data/recipes.json', 'r') as recipes_file:
    recipes_data = json.load(recipes_file)

def show_menu():
    """Show the main menu and return user's choice."""
    from main_menu import MainMenu
    menu = MainMenu()
    return menu.run()

def generate_blueprint_with_recipes(custom_recipes):
    """Generate and visualize a blueprint with custom recipes.
    
    Args:
        custom_recipes: Dictionary of {item_name: count} production targets
    
    Returns:
        Result from renderer (usually None or "menu")
    """
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    logging.info("Initializing components...")
    
    # Update constants with custom recipes if provided
    if custom_recipes:
        import core.constants as constants_module
        constants_module.PRODUCTION_TARGETS = custom_recipes
        logging.info(f"Using custom recipes: {custom_recipes}")
    
    # Initialize components
    grid = Grid()  # Initialize Grid first
    pathfinder = Pathfinder(grid)  # Initialize Pathfinder using the grid
    belt_router = BeltRouter(grid, pathfinder)  # Initialize BeltRouter using grid and pathfinder
    inserter_placer = InserterPlacer(grid)  # Initialize InserterPlacer using the grid
    machine_placer = MachinePlacer(grid, belt_router, inserter_placer, pathfinder, recipes_data)  # Initialize MachinePlacer
    blueprint_manager = BlueprintManager(grid, pathfinder, belt_router, inserter_placer, machine_placer)  # Initialize BlueprintManager

    # Generate the blueprint using the generational algorithm
    logging.info("Generating blueprint...")
    blueprint = blueprint_manager.generate_blueprint()
    blueprint_string = encode_blueprint(blueprint)

    logging.info(f"Generated Blueprint String:\n {blueprint_string}")
    
    # Visualize the blueprint using pygame
    logging.info("Starting pygame visualization...")
    from core.constants import PYGAME_TILE_SIZE
    renderer = BlueprintRenderer(tile_size=PYGAME_TILE_SIZE)
    result = renderer.render(blueprint, blueprint_string)
    return result

def show_settings():
    """Show the settings menu."""
    sys.path.insert(0, str(Path(__file__).parent / "src" / "ui" / "UI"))
    from settings_menu import SettingsMenu
    settings = SettingsMenu()
    result = settings.run()
    return result

def main():
    """Main entry point."""
    # Load config first
    load_config()
    
    try:
        while True:
            # Show menu and get user choice
            choice = show_menu()
            
            if choice == "generate":
                # Show recipe panel instead of generating immediately
                from recipe_panel import RecipePanel
                from screen_manager import ScreenManager
                
                screen_manager = ScreenManager()
                recipe_panel = RecipePanel()
                screen = screen_manager.get_screen()
                
                show_panel = True
                while show_panel:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            show_panel = False
                            break
                        elif event.type == pygame.MOUSEBUTTONDOWN:
                            if event.button == 1:
                                mouse_pos = pygame.mouse.get_pos()
                                panel_action = recipe_panel.handle_click(mouse_pos)
                                if panel_action == "generate":
                                    # Get recipes and generate blueprint
                                    recipes = recipe_panel.get_recipes()
                                    result = generate_blueprint_with_recipes(recipes)
                                    if result != "menu":
                                        show_panel = False
                                    break
                                elif panel_action == "close":
                                    show_panel = False
                                    break
                        elif event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_ESCAPE:
                                show_panel = False
                                break
                            else:
                                recipe_panel.handle_key(event)
                    
                    screen.fill((30, 30, 40))
                    recipe_panel.draw(screen)
                    screen_manager.flip()
                    screen_manager.tick(60)
            elif choice == "settings":
                result = show_settings()
                if result == "back":
                    continue  # Return to main menu
                elif result == "exit":
                    break
            elif choice == "exit":
                logging.info("Exiting...")
                break
    finally:
        # Clean up pygame only on exit
        sys.path.insert(0, str(Path(__file__).parent / "src" / "ui" / "UI"))
        from screen_manager import ScreenManager
        ScreenManager().cleanup()









class BlueprintManager:
    def __init__(self, grid, pathfinder, belt_router, inserter_placer, machine_placer):
        self.grid = grid
        self.pathfinder = pathfinder
        self.belt_router = belt_router
        self.inserter_placer = inserter_placer
        self.machine_placer = machine_placer

    def generate_blueprint(self):
        from core.constants import PRODUCTION_TARGETS, BASE_MATERIALS

        # Create a connected production line system
        logging.info("Generating blueprint for production targets...")
        
        entities = []
        entity_number = 1
        
        # Place base resource belt at the top
        entity_number = self.machine_placer.place_base_resource_belt(entities, entity_number, "iron-ore")
        
        # Place production lines using the new ProductionLineMap system
        for target_item, target_rate in PRODUCTION_TARGETS.items():
            logging.info(f"Placing production line for {target_item} at {target_rate}/min")
            entity_number = self.machine_placer.build_connected_production_line(
                entities, entity_number, target_item, target_rate
            )

        # Create a blueprint
        blueprint = self.create_blueprint(entities)
        return blueprint


    def create_blueprint(self, entities):
        """
        Create a Factorio-compatible blueprint from the entities.
        """
        blueprint = {
            "blueprint": {
                "icons": [{"signal": {"name": "stone-furnace"}, "index": 1}],
                "entities": entities,
                "item": "blueprint",
                "version": 281479276889473
            }
        }
        return blueprint


if __name__ == "__main__":
    main()


