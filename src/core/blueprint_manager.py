import logging

from core.constants import GenerationMode, PlacementStrategy, PRODUCTION_TARGETS
from planners.production_planner import ProductionPlanner


class BlueprintManager:
    """Places entities and builds a Factorio blueprint dict."""

    def __init__(
        self,
        grid,
        pathfinder,
        belt_router,
        recipes_data,
        generation_mode: GenerationMode = GenerationMode.ASSEMBLER_ONLY,
        placement_strategy: PlacementStrategy = PlacementStrategy.RULE_BASED,
    ):
        self.grid = grid
        self.pathfinder = pathfinder
        self.belt_router = belt_router
        self.recipes_data = recipes_data
        self.generation_mode = generation_mode
        self.placement_strategy = placement_strategy
        self.planner = None
        self.rate_summary = []

    def generate_blueprint(self, progress_callback=None):
        from core import constants as constants_module

        targets = constants_module.PRODUCTION_TARGETS
        logging.info(
            "Generating blueprint for %s (mode=%s, placement=%s)...",
            targets,
            self.generation_mode.value,
            self.placement_strategy.value,
        )

        entities = []
        entity_number = 1

        self.planner = ProductionPlanner(
            self.grid,
            self.pathfinder,
            self.belt_router,
            self.recipes_data,
            self.generation_mode,
        )
        if self.placement_strategy == PlacementStrategy.GENETIC:
            entities, entity_number = self.planner.generate_genetic(
                targets, entities, entity_number, progress_callback=progress_callback
            )
        else:
            entities, entity_number = self.planner.generate(
                targets, entities, entity_number
            )
        self.rate_summary = self.planner.rate_summary
        production_stages = list(self.planner.production_stages)
        layout_fitness = self.planner.layout_fitness
        genetic_generations = getattr(self.planner, "genetic_generations", 0)
        genetic_converged = getattr(self.planner, "genetic_converged", False)

        blueprint = self.create_blueprint(entities)
        return (
            blueprint,
            production_stages,
            self.rate_summary,
            layout_fitness,
            genetic_generations,
            genetic_converged,
        )

    def create_blueprint(self, entities):
        return {
            "blueprint": {
                "icons": [{"signal": {"name": "stone-furnace"}, "index": 1}],
                "entities": entities,
                "item": "blueprint",
                "version": 281479276889473,
            }
        }
