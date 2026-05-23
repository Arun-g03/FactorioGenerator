"""Blueprint generation pipeline: placement → encode → visualization."""

import logging
from dataclasses import dataclass, field

from core.grid_env import Grid
from core.pathfinding import Pathfinder
from core.belt_router import BeltRouter
from core.inserter_placer import InserterPlacer
from core.blueprintEncoder import encode_blueprint
from core.blueprint_manager import BlueprintManager
from planners.machine_placer import MachinePlacer


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

    @classmethod
    def from_blueprint(
        cls, blueprint: dict, blueprint_string: str, production_stages: list | None = None
    ):
        entities = blueprint.get("blueprint", {}).get("entities", [])
        return cls(
            blueprint=blueprint,
            blueprint_string=blueprint_string,
            production_stages=production_stages or [],
            entity_count=len(entities),
        )


def run_generation_pipeline(custom_recipes, recipes_data) -> BlueprintGenerationResult:
    """Stages: init → place entities → encode blueprint string."""
    logging.info("[%s] Initializing components...", GenerationStage.INIT)

    if custom_recipes:
        from core import constants as constants_module
        constants_module.PRODUCTION_TARGETS = custom_recipes
        logging.info("Production targets: %s", custom_recipes)

    grid = Grid()
    pathfinder = Pathfinder(grid)
    belt_router = BeltRouter(grid, pathfinder)
    inserter_placer = InserterPlacer(grid)
    machine_placer = MachinePlacer(
        grid, belt_router, inserter_placer, pathfinder, recipes_data
    )
    blueprint_manager = BlueprintManager(
        grid, pathfinder, belt_router, inserter_placer, machine_placer
    )

    logging.info("[%s] Placing entities and production stages...", GenerationStage.PLACE)
    blueprint, production_stages = blueprint_manager.generate_blueprint()

    logging.info("[%s] Encoding blueprint string...", GenerationStage.ENCODE)
    blueprint_string = encode_blueprint(blueprint)
    logging.info("Blueprint string length: %s characters", len(blueprint_string))

    return BlueprintGenerationResult.from_blueprint(
        blueprint, blueprint_string, production_stages
    )
