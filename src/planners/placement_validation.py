"""
Compare rule-based vs genetic placement on the same production targets.

Used for regression checks and tuning — genetic should not be required to
beat rule-based, but both should produce viable layouts for standard targets.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.constants import GenerationMode, PlacementStrategy
from core.grid_env import Grid
from core.pathfinding import Pathfinder
from core.belt_router import BeltRouter
from planners.production_planner import ProductionPlanner


@dataclass
class PlacementComparison:
    """Fitness summary for one placement strategy run."""

    strategy: PlacementStrategy
    entity_count: int
    is_viable: bool
    total_score: float
    viability_score: float
    efficiency_score: float
    blockers: list[str]
    genetic_generations: int = 0
    genetic_converged: bool = False


def _run_planner(
    targets: dict[str, float],
    recipes_data: dict,
    mode: GenerationMode,
    strategy: PlacementStrategy,
    *,
    genetic_generations_cap: int | None = None,
) -> PlacementComparison:
    grid = Grid()
    pathfinder = Pathfinder(grid)
    belt_router = BeltRouter(grid, pathfinder)
    planner = ProductionPlanner(
        grid, pathfinder, belt_router, recipes_data, mode
    )

    entities: list = []
    entity_number = 1

    if strategy == PlacementStrategy.GENETIC:
        if genetic_generations_cap is not None:
            from planners import genetic_placement as gp

            original_max = gp.MAX_GENERATIONS
            gp.MAX_GENERATIONS = genetic_generations_cap
            try:
                entities, entity_number = planner.generate_genetic(
                    targets, entities, entity_number
                )
            finally:
                gp.MAX_GENERATIONS = original_max
        else:
            entities, entity_number = planner.generate_genetic(
                targets, entities, entity_number
            )
    else:
        entities, entity_number = planner.generate(targets, entities, entity_number)

    bd = planner.layout_fitness
    return PlacementComparison(
        strategy=strategy,
        entity_count=len(entities),
        is_viable=bd.is_viable if bd else False,
        total_score=bd.total if bd else 0.0,
        viability_score=bd.viability_score if bd else 0.0,
        efficiency_score=bd.efficiency_score if bd else 0.0,
        blockers=list(bd.blockers) if bd else ["no fitness breakdown"],
        genetic_generations=planner.genetic_generations,
        genetic_converged=planner.genetic_converged,
    )


def compare_placement_strategies(
    targets: dict[str, float],
    recipes_data: dict,
    mode: GenerationMode = GenerationMode.FULL_CHAIN,
    *,
    genetic_generations_cap: int = 80,
) -> dict[str, PlacementComparison]:
    """
    Run rule-based and genetic placement on the same targets.

    Returns a dict keyed by strategy value ('rule_based', 'genetic').
    """
    rule = _run_planner(
        targets, recipes_data, mode, PlacementStrategy.RULE_BASED
    )
    genetic = _run_planner(
        targets,
        recipes_data,
        mode,
        PlacementStrategy.GENETIC,
        genetic_generations_cap=genetic_generations_cap,
    )
    return {
        PlacementStrategy.RULE_BASED.value: rule,
        PlacementStrategy.GENETIC.value: genetic,
    }
