"""
Rule-based factory layout as a production network.

Placement follows recipe dependencies (edges), not a fixed left-to-right strip:
  - Each consumer is placed adjacent to its upstream outputs (any cardinal).
  - Belt I/O on each machine matches the connection direction.
  - The grid is unbounded; search expands from the ideal anchor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.constants import (
    BASE_MATERIALS,
    FACTORIO_EAST,
    FACTORIO_NORTH,
    FACTORIO_SOUTH,
    FACTORIO_WEST,
    machine_io_stride,
)
from planners.layout_fitness import LayoutFitnessBreakdown, evaluate_stage_layout
from planners.machine_io import machine_io_lanes
from planners.stage_connector import stage_lanes_from_machines

CONNECTION_GAP = 2
NETWORK_SEED_X = 12
NETWORK_SEED_Y = 14

CARDINAL_FLOW_ORDER = (
    FACTORIO_EAST,
    FACTORIO_SOUTH,
    FACTORIO_WEST,
    FACTORIO_NORTH,
)


@dataclass
class NetworkLayoutCursor:
    """Places root stages (no upstream producers in the graph) on open ground."""

    next_x: int = NETWORK_SEED_X
    next_y: int = NETWORK_SEED_Y
    row_stride_y: int = 14
    used_lane_ys: set[int] = field(default_factory=set)

    def _reserve_lane_y(self, lane_y: int) -> int:
        while lane_y in self.used_lane_ys:
            lane_y += 2
        self.used_lane_ys.add(lane_y)
        return lane_y

    def allocate_root_origin(self, recipe: dict, machine_count: int) -> tuple[int, int]:
        w, h = recipe.get("machine_size", [3, 3])
        lane_y = self._reserve_lane_y(self.next_y + h // 2)
        y = max(0, lane_y - h // 2)
        x = self.next_x
        span = machine_count * machine_io_stride(w) + 8
        self.next_x += span
        return x, y

    def next_row(self):
        self.next_x = NETWORK_SEED_X
        self.next_y += self.row_stride_y


@dataclass
class RuleLayoutCandidate:
    """Legacy wrapper for tests comparing layout trials."""

    stage_y: int
    fitness: LayoutFitnessBreakdown
    entities: list
    entity_number: int
    production_stages: list
    stage_machines: dict[str, list]
    grid_occupied: dict


def compute_stage_depths(nodes) -> dict[str, int]:
    """Dependency depth in the rate graph (for logging / diagnostics)."""
    depths: dict[str, int] = {}

    def depth(item: str) -> int:
        if item in depths:
            return depths[item]
        node = nodes.get(item)
        if not node:
            depths[item] = 0
            return 0
        upstream = [
            d
            for d in node.dependencies
            if d in nodes and d not in BASE_MATERIALS
        ]
        if not upstream:
            depths[item] = 0
        else:
            depths[item] = 1 + max(depth(d) for d in upstream)
        return depths[item]

    for item in sorted(nodes.keys()):
        depth(item)
    return depths


def _upstream_items(node, nodes) -> list[str]:
    return [
        d
        for d in node.dependencies
        if d in nodes and d not in BASE_MATERIALS
    ]


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _machine_origin_for_feed(
    out_x: int,
    out_y: int,
    flow_direction: int,
    width: int,
    height: int,
    clearance: int,
) -> tuple[int, int]:
    """Place machine origin so its input lane sits ``clearance`` tiles from producer output."""
    if flow_direction == FACTORIO_EAST:
        return out_x + clearance, max(0, out_y - height // 2)
    if flow_direction == FACTORIO_WEST:
        return out_x - clearance - width, max(0, out_y - height // 2)
    if flow_direction == FACTORIO_SOUTH:
        return max(0, out_x - width // 2), out_y + clearance
    if flow_direction == FACTORIO_NORTH:
        return max(0, out_x - width // 2), out_y - clearance - height
    return out_x + clearance, max(0, out_y - height // 2)


def network_origin_for_stage(
    node,
    nodes,
    stage_lanes: dict,
    cursor: NetworkLayoutCursor,
) -> tuple[int, int, int]:
    """
    Top-left tile and belt flow direction for the first machine in a stage.

    Picks the cardinal that minimizes belt run length from upstream outputs.
    """
    recipe = node.recipe
    w, h = recipe.get("machine_size", [3, 3])
    upstream = _upstream_items(node, nodes)

    if not upstream:
        x, y = cursor.allocate_root_origin(recipe, node.machine_count)
        return x, y, FACTORIO_EAST

    outputs = []
    for dep in upstream:
        lanes = stage_lanes.get(dep)
        if lanes:
            outputs.append(lanes["output_end"])

    if not outputs:
        x, y = cursor.allocate_root_origin(recipe, node.machine_count)
        return x, y, FACTORIO_EAST

    centroid = (
        round(sum(p[0] for p in outputs) / len(outputs)),
        round(sum(p[1] for p in outputs) / len(outputs)),
    )
    max_stride = max(
        machine_io_stride(nodes[d].recipe.get("machine_size", [3, 3])[0])
        for d in upstream
        if d in nodes
    )
    clearance = max_stride + CONNECTION_GAP

    best = None
    for direction in CARDINAL_FLOW_ORDER:
        mx, my = _machine_origin_for_feed(
            centroid[0], centroid[1], direction, w, h, clearance
        )
        input_start, _ = machine_io_lanes(mx, my, w, h, direction)
        dist = _manhattan(centroid, input_start)
        if best is None or dist < best[0]:
            best = (dist, mx, my, direction)

    _, mx, my, direction = best
    return mx, my, direction


def estimate_connection_cost(stage_lanes: dict, nodes) -> int:
    """Manhattan belt-tile estimate for all producer→consumer edges (lower is better)."""
    total = 0
    for item, node in nodes.items():
        if item not in stage_lanes:
            continue
        consumer_in = stage_lanes[item]["input_start"]
        offset = 0
        for dep in node.dependencies:
            if dep in BASE_MATERIALS or dep not in stage_lanes:
                continue
            producer_out = stage_lanes[dep]["output_end"]
            target = (consumer_in[0], consumer_in[1] + offset * 2)
            start = (producer_out[0] + 1, producer_out[1])
            end = (target[0] - 1, target[1])
            total += _manhattan(start, end)
            offset += 1
    return total


def evaluate_rule_machine_layout(
    stage_machines: dict[str, list],
    nodes,
    *,
    grid=None,
) -> LayoutFitnessBreakdown:
    """Score layout: viability first, then connection distance (network quality)."""
    stage_lanes = {}
    for item, machines in stage_machines.items():
        lanes = stage_lanes_from_machines(machines)
        if lanes:
            stage_lanes[item] = lanes

    breakdown = evaluate_stage_layout(
        stage_machines,
        nodes,
        grid=grid,
        preferred_stage_y=None,
        expected_counts={item: node.machine_count for item, node in nodes.items()},
    )

    if breakdown.is_viable and stage_lanes:
        conn = estimate_connection_cost(stage_lanes, nodes)
        edge_count = max(
            sum(
                1
                for item, node in nodes.items()
                for dep in node.dependencies
                if dep not in BASE_MATERIALS and dep in stage_lanes and item in stage_lanes
            ),
            1,
        )
        avg = conn / edge_count
        breakdown.connection_penalty = -avg * 0.5
        breakdown.details.append(f"network avg connection distance: {avg:.1f} tiles/edge")
        breakdown._finalize_total(breakdown.machine_count)

    return breakdown


def _candidate_sort_key(candidate: RuleLayoutCandidate) -> tuple:
    bd = candidate.fitness
    viable_rank = 0 if bd.is_viable else 1
    return (viable_rank, -bd.total, len(bd.blockers))


def select_best_rule_candidate(
    candidates: list[RuleLayoutCandidate],
) -> RuleLayoutCandidate | None:
    if not candidates:
        return None
    return min(candidates, key=_candidate_sort_key)
