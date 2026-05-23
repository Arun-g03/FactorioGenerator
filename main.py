import json
import logging
import sys
from pathlib import Path

# src/ modules use flat imports (e.g. `from core.entity import Entity`)
_src = Path(__file__).parent / "src"
_ui = _src / "ui"
for _path in (_ui, _src):
    _p = str(_path)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.ui.blueprint_renderer import BlueprintRenderer

# Load config and update constants if necessary
def load_config():
    """Load configuration from config.json."""
    config_file = Path(__file__).parent / "config.json"
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            # Update the constants module
            from src.core import constants as constants_module
            
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
    from src.ui.main_menu import MainMenu
    menu = MainMenu()
    return menu.run()

def show_settings():
    """Show the settings menu."""
    from src.ui.settings_menu import SettingsMenu
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
                logging.basicConfig(
                    level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s",
                )
                from src.core.constants import PRODUCTION_TARGETS, PYGAME_TILE_SIZE

                renderer = BlueprintRenderer(tile_size=PYGAME_TILE_SIZE)
                result = renderer.run_workspace(
                    recipes_data,
                    initial_targets=PRODUCTION_TARGETS,
                    open_targets_modal=True,
                )
                if result == "exit":
                    break
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
        from src.ui.screen_manager import ScreenManager
        ScreenManager().cleanup()
if __name__ == "__main__":
    main()

