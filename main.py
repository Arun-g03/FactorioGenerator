"""Main entry point for the Factorio Blueprint Generator."""


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

def load_config():
    """Load configuration from config.json (paths + window size)."""
    from src.core.app_config import apply_factorio_paths, load_config as read_config

    apply_factorio_paths(read_config())

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
            elif choice == "assisted_build":
                logging.basicConfig(
                    level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s",
                )
                from src.ui.assisted_build import run_assisted_build_session

                result = run_assisted_build_session(recipes_data)
                if result == "exit":
                    break
            elif choice == "replay":
                logging.basicConfig(
                    level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s",
                )
                from src.core.constants import PRODUCTION_TARGETS
                from src.ui.placement_replay import run_placement_replay_session

                result = run_placement_replay_session(
                    recipes_data,
                    initial_targets=PRODUCTION_TARGETS,
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

