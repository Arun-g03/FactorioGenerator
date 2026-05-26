"""Blueprint generation pipeline: placement → encode → visualization."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from core.grid_env import Grid
from core.pathfinding import Pathfinder
from core.belt_router import BeltRouter
from core.blueprintEncoder import encode_blueprint
from core.blueprint_manager import BlueprintManager
from core.constants import GenerationMode, PlacementStrategy
from planners.layout_fitness import LayoutFitnessBreakdown


class GenerationStage:
    """Named steps from targets to on-screen blueprint."""

    CONFIGURE = "configure_targets"
    INIT = "init_components"
    PLACE = "place_entities"
    ENCODE = "encode_blueprint"
    VISUALIZE = "visualize"


@dataclass
class BlueprintGenerationResult:
    """Output of the placement + encode stages, consumed by the renderer."""

    blueprint: dict
    blueprint_string: str
    production_stages: list = field(default_factory=list)
    entity_count: int = 0
    rate_summary: list = field(default_factory=list)
    placement_strategy: PlacementStrategy = PlacementStrategy.RULE_BASED
    layout_fitness: LayoutFitnessBreakdown | None = None
    genetic_generations: int = 0
    genetic_converged: bool = False

    @classmethod
    def from_blueprint(
        cls,
        blueprint: dict,
        blueprint_string: str,
        production_stages: list | None = None,
        rate_summary: list | None = None,
    ):
        entities = blueprint.get("blueprint", {}).get("entities", [])
        return cls(
            blueprint=blueprint,
            blueprint_string=blueprint_string,
            production_stages=production_stages or [],
            entity_count=len(entities),
            rate_summary=rate_summary or [],
        )


def run_generation_pipeline(
    custom_recipes,
    recipes_data,
    generation_mode: GenerationMode = GenerationMode.ASSEMBLER_ONLY,
    placement_strategy: PlacementStrategy = PlacementStrategy.RULE_BASED,
    progress_callback=None,
) -> BlueprintGenerationResult:
    """Stages: init → place entities → encode blueprint string."""
    logging.info("[%s] Initializing components...", GenerationStage.INIT)

    if custom_recipes:
        from core import constants as constants_module
        constants_module.PRODUCTION_TARGETS = custom_recipes
        logging.info("Production targets: %s", custom_recipes)

    logging.info("Generation mode: %s", generation_mode.value)
    logging.info("Placement strategy: %s", placement_strategy.value)

    grid = Grid()
    pathfinder = Pathfinder(grid)
    belt_router = BeltRouter(grid, pathfinder)
    blueprint_manager = BlueprintManager(
        grid,
        pathfinder,
        belt_router,
        recipes_data,
        generation_mode,
        placement_strategy,
    )

    logging.info("[%s] Placing entities and production stages...", GenerationStage.PLACE)
    (
        blueprint,
        production_stages,
        rate_summary,
        layout_fitness,
        genetic_generations,
        genetic_converged,
    ) = blueprint_manager.generate_blueprint(progress_callback=progress_callback)

    logging.info("[%s] Encoding blueprint string...", GenerationStage.ENCODE)
    blueprint_string = encode_blueprint(blueprint, recipes_data)
    logging.info("Blueprint string length: %s characters", len(blueprint_string))

    result = BlueprintGenerationResult.from_blueprint(
        blueprint, blueprint_string, production_stages, rate_summary
    )
    result.placement_strategy = placement_strategy
    result.layout_fitness = layout_fitness
    result.genetic_generations = genetic_generations
    result.genetic_converged = genetic_converged
    return result
