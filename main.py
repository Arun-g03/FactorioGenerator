import json
import logging
from grid_env import Grid
from pathfinding import Pathfinder
from belt_router import BeltRouter
from inserter_placer import InserterPlacer
from machine_placer import MachinePlacer
from blueprintEncoder import encode_blueprint

# Load JSON data
with open('recipes.json', 'r') as recipes_file:
    recipes_data = json.load(recipes_file)

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Initialize components
    grid = Grid()  # Initialize Grid first
    pathfinder = Pathfinder(grid)  # Initialize Pathfinder using the grid
    belt_router = BeltRouter(grid, pathfinder)  # Initialize BeltRouter using grid and pathfinder
    inserter_placer = InserterPlacer(grid)  # Initialize InserterPlacer using the grid
    machine_placer = MachinePlacer(grid, belt_router, inserter_placer, pathfinder, recipes_data)  # Initialize MachinePlacer
    blueprint_manager = BlueprintManager(grid, pathfinder, belt_router, inserter_placer, machine_placer)  # Initialize BlueprintManager

    # Generate the blueprint using the generational algorithm
    blueprint = blueprint_manager.generate_blueprint()
    blueprint_string = encode_blueprint(blueprint)

    logging.info(f"Generated Blueprint String:\n {blueprint_string}")









class BlueprintManager:
    def __init__(self, grid, pathfinder, belt_router, inserter_placer, machine_placer):
        self.grid = grid
        self.pathfinder = pathfinder
        self.belt_router = belt_router
        self.inserter_placer = inserter_placer
        self.machine_placer = machine_placer

    def generate_blueprint(self):
        from constants import PRODUCTION_TARGETS, BASE_MATERIALS

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

        # Visualize the production line map
        self.machine_placer.production_map.visualize_map()

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


