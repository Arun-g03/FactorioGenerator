"""Configurable options for Assisted Build workspace."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class AssistedBuildSettings:
    """Tunables for manual placement and belt routing in Assisted Build."""

    auto_route_on_change: bool = True
    show_machine_labels: bool = True
    palette_width: int = 220
    incremental_reroute: bool = False
    optimization_stale_limit: int = 20
    optimization_max_iterations: int = 0

    def clamp(self) -> AssistedBuildSettings:
        return AssistedBuildSettings(
            auto_route_on_change=bool(self.auto_route_on_change),
            show_machine_labels=bool(self.show_machine_labels),
            palette_width=max(160, min(420, int(self.palette_width))),
            incremental_reroute=bool(self.incremental_reroute),
            optimization_stale_limit=max(3, min(500, int(self.optimization_stale_limit))),
            optimization_max_iterations=max(0, min(10_000, int(self.optimization_max_iterations))),
        )


def settings_from_config(config: dict | None) -> AssistedBuildSettings:
    """Load assisted settings from a config dict (e.g. config.json section)."""
    raw = (config or {}).get("assisted_build_settings") or {}
    valid = {f.name for f in fields(AssistedBuildSettings)}
    kwargs = {k: v for k, v in raw.items() if k in valid}
    return AssistedBuildSettings(**kwargs).clamp()


def settings_to_config_dict(settings: AssistedBuildSettings) -> dict:
    return {"assisted_build_settings": asdict(settings.clamp())}
