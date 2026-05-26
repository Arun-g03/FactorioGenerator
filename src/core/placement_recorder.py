"""Record placement steps for replay / debugging UI."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field


@dataclass
class PlacementStep:
    """One frame in a placement replay."""

    index: int
    kind: str
    title: str
    detail: list[str] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    highlights: list[tuple[int, int]] = field(default_factory=list)


class PlacementRecorder:
    """Append-only log of placement reasoning and cumulative entity snapshots."""

    def __init__(self):
        self.steps: list[PlacementStep] = []
        self.targets: dict[str, float] = {}
        self.mode_label: str = ""
        self.strategy_label: str = ""

    def set_run_context(
        self,
        targets: dict[str, float],
        mode_label: str,
        strategy_label: str,
    ) -> None:
        self.targets = dict(targets)
        self.mode_label = mode_label
        self.strategy_label = strategy_label

    def record(
        self,
        kind: str,
        title: str,
        detail: list[str] | None,
        entities: list[dict],
        *,
        highlights: list[tuple[int, int]] | None = None,
    ) -> None:
        self.steps.append(
            PlacementStep(
                index=len(self.steps),
                kind=kind,
                title=title,
                detail=list(detail or []),
                entities=copy.deepcopy(entities),
                highlights=list(highlights or []),
            )
        )

    def step_count(self) -> int:
        return len(self.steps)

    def get_step(self, index: int) -> PlacementStep | None:
        if 0 <= index < len(self.steps):
            return self.steps[index]
        return None
