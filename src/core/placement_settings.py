"""Configurable placement parameters for rule-based and genetic strategies."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class RuleBasedPlacementSettings:
    """Tunables for dependency-network rule placement."""

    connection_gap: int = 2
    network_seed_x: int = 12
    network_seed_y: int = 14
    row_stride_y: int = 14

    def clamp(self) -> RuleBasedPlacementSettings:
        return RuleBasedPlacementSettings(
            connection_gap=max(1, min(12, int(self.connection_gap))),
            network_seed_x=max(0, min(120, int(self.network_seed_x))),
            network_seed_y=max(0, min(120, int(self.network_seed_y))),
            row_stride_y=max(6, min(48, int(self.row_stride_y))),
        )


@dataclass
class GeneticPlacementSettings:
    """Tunables for genetic machine layout evolution."""

    population_size: int = 64
    min_generations: int = 20
    max_generations: int = 2500
    stale_generations_limit: int = 120
    mutation_rate: float = 0.85
    placement_x_min: int = 5
    placement_x_max: int = 160
    placement_y_min: int = 4
    placement_y_max: int = 90

    def clamp(self) -> GeneticPlacementSettings:
        x_min = max(0, min(200, int(self.placement_x_min)))
        x_max = max(x_min + 20, min(300, int(self.placement_x_max)))
        y_min = max(0, min(200, int(self.placement_y_min)))
        y_max = max(y_min + 10, min(300, int(self.placement_y_max)))
        return GeneticPlacementSettings(
            population_size=max(8, min(256, int(self.population_size))),
            min_generations=max(1, min(500, int(self.min_generations))),
            max_generations=max(10, min(10000, int(self.max_generations))),
            stale_generations_limit=max(5, min(1000, int(self.stale_generations_limit))),
            mutation_rate=max(0.05, min(1.0, float(self.mutation_rate))),
            placement_x_min=x_min,
            placement_x_max=x_max,
            placement_y_min=y_min,
            placement_y_max=y_max,
        )


@dataclass
class PlacementSettingsBundle:
    rule_based: RuleBasedPlacementSettings
    genetic: GeneticPlacementSettings

    @classmethod
    def defaults(cls) -> PlacementSettingsBundle:
        return cls(
            rule_based=RuleBasedPlacementSettings(),
            genetic=GeneticPlacementSettings(),
        )


def _merge_dataclass(cls, data: dict[str, Any] | None):
    if not data:
        return cls()
    valid = {f.name for f in fields(cls)}
    kwargs = {k: v for k, v in data.items() if k in valid}
    return cls(**kwargs).clamp()


def bundle_from_config(config: dict | None) -> PlacementSettingsBundle:
    """Load placement settings from a config dict (e.g. config.json section)."""
    raw = (config or {}).get("placement_settings") or {}
    return PlacementSettingsBundle(
        rule_based=_merge_dataclass(
            RuleBasedPlacementSettings, raw.get("rule_based")
        ),
        genetic=_merge_dataclass(GeneticPlacementSettings, raw.get("genetic")),
    )


def bundle_to_config_dict(bundle: PlacementSettingsBundle) -> dict:
    return {
        "placement_settings": {
            "rule_based": asdict(bundle.rule_based.clamp()),
            "genetic": asdict(bundle.genetic.clamp()),
        }
    }


@contextmanager
def apply_genetic_settings(settings: GeneticPlacementSettings):
    """Temporarily override genetic_placement module constants."""
    import planners.genetic_placement as gp

    settings = settings.clamp()
    saved = {
        "DEFAULT_POPULATION_SIZE": gp.DEFAULT_POPULATION_SIZE,
        "MIN_GENERATIONS": gp.MIN_GENERATIONS,
        "MAX_GENERATIONS": gp.MAX_GENERATIONS,
        "STALE_GENERATIONS_LIMIT": gp.STALE_GENERATIONS_LIMIT,
        "MUTATION_RATE": gp.MUTATION_RATE,
        "PLACEMENT_X_MIN": gp.PLACEMENT_X_MIN,
        "PLACEMENT_X_MAX": gp.PLACEMENT_X_MAX,
        "PLACEMENT_Y_MIN": gp.PLACEMENT_Y_MIN,
        "PLACEMENT_Y_MAX": gp.PLACEMENT_Y_MAX,
    }
    gp.DEFAULT_POPULATION_SIZE = settings.population_size
    gp.MIN_GENERATIONS = settings.min_generations
    gp.MAX_GENERATIONS = settings.max_generations
    gp.STALE_GENERATIONS_LIMIT = settings.stale_generations_limit
    gp.MUTATION_RATE = settings.mutation_rate
    gp.PLACEMENT_X_MIN = settings.placement_x_min
    gp.PLACEMENT_X_MAX = settings.placement_x_max
    gp.PLACEMENT_Y_MIN = settings.placement_y_min
    gp.PLACEMENT_Y_MAX = settings.placement_y_max
    try:
        yield
    finally:
        for key, value in saved.items():
            setattr(gp, key, value)
