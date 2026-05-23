import logging


class BlueprintManager:
    """Places entities and builds a Factorio blueprint dict."""

    def __init__(self, grid, pathfinder, belt_router, inserter_placer, machine_placer):
        self.grid = grid
        self.pathfinder = pathfinder
        self.belt_router = belt_router
        self.inserter_placer = inserter_placer
        self.machine_placer = machine_placer

    def generate_blueprint(self):
        from core.constants import PRODUCTION_TARGETS

        logging.info("Generating blueprint for production targets...")

        entities = []
        entity_number = 1

        entity_number = self.machine_placer.place_base_resource_belt(
            entities, entity_number, "iron-ore"
        )

        for target_item, target_rate in PRODUCTION_TARGETS.items():
            logging.info(
                "Placing production line for %s at %s/min", target_item, target_rate
            )
            entity_number = self.machine_placer.build_connected_production_line(
                entities, entity_number, target_item, target_rate
            )

        self.machine_placer.production_map.visualize_map()
        production_stages = list(self.machine_placer.production_map.production_stages)

        blueprint = self.create_blueprint(entities)
        return blueprint, production_stages

    def create_blueprint(self, entities):
        return {
            "blueprint": {
                "icons": [{"signal": {"name": "stone-furnace"}, "index": 1}],
                "entities": entities,
                "item": "blueprint",
                "version": 281479276889473,
            }
        }
