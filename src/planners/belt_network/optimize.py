"""One-shot routing optimization: scoring rules and link group order variants."""

from __future__ import annotations

import logging
import random
from collections import defaultdict
from dataclasses import dataclass, field

from core.constants import (
    FACTORIO_EAST,
    FACTORIO_NORTH,
    FACTORIO_SOUTH,
    FACTORIO_WEST,
)
from planners.belt_network.link_graph import (
    PRIORITY_BASE,
    PRIORITY_OUTPUT,
    PRIORITY_STAGE,
    BeltLink,
    sort_links,
)

logger = logging.getLogger(__name__)

# Scoring weights (higher composite score is better).
BELT_COST = 1000
SPLITTER_WHEN_NEEDED_BONUS = 120
SPLITTER_MISSING_PENALTY = 200
SPLITTER_UNNECESSARY_PENALTY = 60
UG_SENSIBLE_PAIR_BONUS = 35
UG_WASTE_PAIR_PENALTY = 50
MIN_UG_SPAN_FOR_BONUS = 2


FIXED_VARIANT_COUNT = 4


@dataclass
class OptimizationSearchStatus:
    """One step of continuous optimization search."""

    iteration: int
    stale_iterations: int
    continue_search: bool
    improved: bool
    belts: int
    splitters: int
    underground_pairs: int
    composite_score: float
    viable: bool
    message: str


@dataclass
class OptimizationResult:
    """Outcome of a single optimization pass."""

    improved: bool
    belts_before: int
    belts_after: int
    score_before: float
    score_after: float
    variant_used: int
    viable: bool
    message: str
    splitters_before: int = 0
    splitters_after: int = 0
    underground_pairs_before: int = 0
    underground_pairs_after: int = 0


@dataclass
class RoutingQualityMetrics:
    """Breakdown used to compare two routed layouts."""

    viable: bool
    belt_count: int
    splitter_count: int
    underground_pairs: int
    fanout_groups_expected: int = 0
    fanout_groups_satisfied: int = 0
    underground_sensible: int = 0
    composite_score: float = 0.0
    details: list[str] = field(default_factory=list)


def count_transport_belts(entities: list) -> int:
    return sum(1 for e in entities if e.get("name") == "transport-belt")


def count_splitters(entities: list) -> int:
    return sum(1 for e in entities if "splitter" in e.get("name", ""))


def count_underground_pairs(entities: list) -> int:
    return sum(
        1
        for e in entities
        if e.get("name") == "underground-belt" and e.get("type") == "input"
    )


def _entity_tile(entity: dict) -> tuple[int, int]:
    pos = entity.get("position") or {}
    return int(round(pos.get("x", 0))), int(round(pos.get("y", 0)))


def _line_tiles(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    """Interior tiles on a straight segment (excluding endpoints)."""
    ax, ay = a
    bx, by = b
    tiles: list[tuple[int, int]] = []
    if ax == bx:
        step = 1 if by > ay else -1
        for y in range(ay + step, by, step):
            tiles.append((ax, y))
    elif ay == by:
        step = 1 if bx > ax else -1
        for x in range(ax + step, bx, step):
            tiles.append((x, ay))
    return tiles


def _is_routing_surface(name: str) -> bool:
    return "belt" in name and "underground" not in name


def fanout_groups_from_links(links: list[BeltLink]) -> dict[str, tuple[int, int]]:
    """
    group_key -> feed tile when that group should use a splitter fan-out.

    Requires two or more distinct consumer sinks from one shared source.
    """
    by_group: dict[str, list[BeltLink]] = defaultdict(list)
    for link in links:
        by_group[link.group_key].append(link)

    expected: dict[str, tuple[int, int]] = {}
    for group_key, group_links in by_group.items():
        sinks = {link.sink for link in group_links}
        if len(group_links) >= 2 and len(sinks) >= 2:
            expected[group_key] = group_links[0].source
    return expected


def _splitter_placed_for_feed(
    entities: list,
    feed: tuple[int, int],
    *,
    flow_direction: int = FACTORIO_EAST,
) -> bool:
    """True if a splitter with correct 2×1 footprint serves ``feed``."""
    from core.splitter_geometry import find_splitter_at

    return find_splitter_at(entities, feed, flow_direction=flow_direction) is not None


def _underground_pair_sensible(
    grid,
    entities: list,
    input_entity: dict,
) -> bool:
    """
    True when an underground span likely crosses a real obstacle.

    Counts occupied non-belt tiles under the span (machines, splitters, etc.).
    """
    in_pos = _entity_tile(input_entity)
    direction = input_entity.get("direction", FACTORIO_EAST)
    out_pos = None
    for entity in entities:
        if entity.get("name") != "underground-belt":
            continue
        if entity.get("type") != "output":
            continue
        if entity.get("direction") != direction:
            continue
        ox, oy = _entity_tile(entity)
        if direction == FACTORIO_EAST and ox > in_pos[0] and oy == in_pos[1]:
            out_pos = (ox, oy)
            break
        if direction == FACTORIO_WEST and ox < in_pos[0] and oy == in_pos[1]:
            out_pos = (ox, oy)
            break
        if direction == FACTORIO_SOUTH and oy > in_pos[1] and ox == in_pos[0]:
            out_pos = (ox, oy)
            break
        if direction == FACTORIO_NORTH and oy < in_pos[1] and ox == in_pos[0]:
            out_pos = (ox, oy)
            break
    if out_pos is None:
        return False

    span = abs(out_pos[0] - in_pos[0]) + abs(out_pos[1] - in_pos[1]) - 1
    if span < MIN_UG_SPAN_FOR_BONUS:
        return False

    blocked = 0
    for tile in _line_tiles(in_pos, out_pos):
        if not grid.is_occupied(*tile):
            continue
        name = grid.occupied.get(tile, "")
        if _is_routing_surface(name):
            continue
        blocked += 1
    return blocked > 0


def evaluate_routing_quality(
    entities: list,
    links: list[BeltLink],
    stage_machines: dict,
    nodes: dict,
    grid=None,
) -> RoutingQualityMetrics:
    """Score a layout for the optimization pass (higher composite_score is better)."""
    from planners.layout_fitness import evaluate_stage_layout

    breakdown = evaluate_stage_layout(
        stage_machines, nodes, entities=entities, grid=grid
    )
    metrics = RoutingQualityMetrics(
        viable=breakdown.is_viable,
        belt_count=count_transport_belts(entities),
        splitter_count=count_splitters(entities),
        underground_pairs=count_underground_pairs(entities),
    )

    expected_fanout = fanout_groups_from_links(links)
    metrics.fanout_groups_expected = len(expected_fanout)
    satisfied = 0
    for feed in expected_fanout.values():
        if _splitter_placed_for_feed(entities, feed):
            satisfied += 1
    metrics.fanout_groups_satisfied = satisfied

    if grid is not None:
        sensible = 0
        for entity in entities:
            if entity.get("name") != "underground-belt" or entity.get("type") != "input":
                continue
            if _underground_pair_sensible(grid, entities, entity):
                sensible += 1
        metrics.underground_sensible = sensible

    if not metrics.viable:
        metrics.composite_score = -1_000_000.0
        metrics.details.append("not viable")
        return metrics

    score = -metrics.belt_count * BELT_COST
    score += satisfied * SPLITTER_WHEN_NEEDED_BONUS
    missing = metrics.fanout_groups_expected - satisfied
    score -= missing * SPLITTER_MISSING_PENALTY

    extra_splitters = max(
        0, metrics.splitter_count - metrics.fanout_groups_expected
    )
    score -= extra_splitters * SPLITTER_UNNECESSARY_PENALTY

    score += metrics.underground_sensible * UG_SENSIBLE_PAIR_BONUS
    waste_pairs = max(0, metrics.underground_pairs - metrics.underground_sensible)
    score -= waste_pairs * UG_WASTE_PAIR_PENALTY

    metrics.composite_score = score
    metrics.details.extend(
        [
            f"belts={metrics.belt_count}",
            f"splitters={metrics.splitter_count} ({satisfied}/{metrics.fanout_groups_expected} fan-outs)",
            f"underground={metrics.underground_pairs} ({metrics.underground_sensible} sensible)",
            f"score={score:.0f}",
        ]
    )
    return metrics


def layout_score(
    entities: list,
    stage_machines: dict,
    nodes: dict,
    links: list[BeltLink] | None = None,
    grid=None,
) -> tuple[int, float, int, int]:
    """
    Sort key for comparing layouts (higher is better).

    Tuple: (viable, composite_score, -belt_count, splitter_count).
    """
    links = links or []
    metrics = evaluate_routing_quality(
        entities, links, stage_machines, nodes, grid=grid
    )
    return (
        1 if metrics.viable else 0,
        metrics.composite_score,
        -metrics.belt_count,
        metrics.splitter_count,
    )


def group_order_for_variant(links: list[BeltLink], variant: int) -> list[str]:
    """
    Produce a group_key materialization order for a link list.

    Variant 0: default (sorted link order).
    Variant 1: reverse stage groups (same priority band).
    Variant 2: reverse output-sink groups.
    Variant 3: stage groups before base (outputs still last).
    """
    sorted_links = sort_links(links)
    by_priority: dict[int, list[str]] = defaultdict(list)
    seen: set[str] = set()
    for link in sorted_links:
        if link.group_key not in seen:
            seen.add(link.group_key)
            by_priority[link.priority].append(link.group_key)

    def keys_for(priority: int, *, reverse: bool = False) -> list[str]:
        keys = list(by_priority.get(priority, []))
        if reverse:
            keys.reverse()
        return keys

    if variant == 1:
        return (
            keys_for(PRIORITY_BASE)
            + keys_for(PRIORITY_STAGE, reverse=True)
            + keys_for(PRIORITY_OUTPUT)
        )
    if variant == 2:
        return (
            keys_for(PRIORITY_BASE)
            + keys_for(PRIORITY_STAGE)
            + keys_for(PRIORITY_OUTPUT, reverse=True)
        )
    if variant == 3:
        return (
            keys_for(PRIORITY_STAGE)
            + keys_for(PRIORITY_BASE)
            + keys_for(PRIORITY_OUTPUT)
        )
    return list(dict.fromkeys(link.group_key for link in sorted_links))


def group_order_for_search(links: list[BeltLink], iteration: int) -> list[str]:
    """
    Ordering for continuous search: fixed strategies first, then pseudo-random shuffles.
    """
    if iteration < FIXED_VARIANT_COUNT:
        return group_order_for_variant(links, iteration)

    sorted_links = sort_links(links)
    by_priority: dict[int, list[str]] = defaultdict(list)
    seen: set[str] = set()
    for link in sorted_links:
        if link.group_key not in seen:
            seen.add(link.group_key)
            by_priority[link.priority].append(link.group_key)

    rng = random.Random(iteration * 1_049_629)
    ordered: list[str] = []
    for priority in sorted(by_priority.keys()):
        keys = list(by_priority[priority])
        rng.shuffle(keys)
        ordered.extend(keys)
    return ordered
