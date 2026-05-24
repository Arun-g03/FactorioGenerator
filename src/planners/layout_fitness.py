"""Shared fitness scoring for machine layouts (rule-based and genetic).

Scoring is two-tier:
  1. Viability — end-to-end production must work (dominates total score).
  2. Efficiency — footprint / belt estimate (only applied when viable).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.constants import BASE_MATERIALS
from planners.stage_connector import (
    BASE_BUS_LENGTH,
    BASE_BUS_X_START,
    BASE_BUS_Y,
    stage_lanes_from_machines,
)

PREFERRED_STAGE_Y = 15
BELTS_PER_MACHINE = 6

# Reference raw penalties per machine for 0–100 efficiency normalization
REF_FOOTPRINT_PER_MACHINE = 45.0
REF_BELT_TILES_PER_MACHINE = 35.0
REF_LAYOUT_PER_MACHINE = 8.0

EFFICIENCY_WEIGHTS = {
    "footprint": 0.45,
    "belts": 0.40,
    "layout": 0.15,
}


@dataclass
class LayoutFitnessBreakdown:
    """Normalized fitness on 0–100 (higher is better)."""

    total: float = 0.0
    is_viable: bool = False
    blockers: list[str] = field(default_factory=list)
    viability_score: float = 0.0
    efficiency_score: float = 0.0
    footprint_score: float = 0.0
    belt_score: float = 0.0
    layout_score: float = 0.0
    raw_efficiency_penalty: float = 0.0
    estimated_belt_tiles: int = 0
    machine_count: int = 0
    # Legacy aliases (kept for logs)
    viability_total: float = 0.0
    efficiency_total: float = 0.0

    overlap_penalty: float = 0.0
    capacity_penalty: float = 0.0
    inserter_penalty: float = 0.0
    connection_penalty: float = 0.0
    footprint_penalty: float = 0.0
    estimated_belts_penalty: float = 0.0
    outlier_penalty: float = 0.0
    stage_cluster_penalty: float = 0.0
    bus_alignment_penalty: float = 0.0
    flow_order_bonus: float = 0.0
    belt_distance_penalty: float = 0.0
    compactness_penalty: float = 0.0
    grid_conflict_penalty: float = 0.0
    details: list[str] = field(default_factory=list)

    def _finalize_total(self, machine_count: int):
        self.machine_count = max(machine_count, 0)
        self.flow_order_bonus = self.connection_penalty
        self.belt_distance_penalty = self.estimated_belts_penalty
        self.compactness_penalty = self.footprint_penalty

        self.raw_efficiency_penalty = (
            self.footprint_penalty
            + self.estimated_belts_penalty
            + self.outlier_penalty
            + self.stage_cluster_penalty
            + self.bus_alignment_penalty
        )

        if self.blockers:
            self.is_viable = False
            self.viability_score = 0.0
            self.efficiency_score = 0.0
            self.footprint_score = 0.0
            self.belt_score = 0.0
            self.layout_score = 0.0
            self.total = 0.0
        else:
            self.is_viable = True
            self.viability_score = 100.0
            scores = _normalized_efficiency_scores(self, self.machine_count)
            self.footprint_score = scores["footprint"]
            self.belt_score = scores["belts"]
            self.layout_score = scores["layout"]
            self.efficiency_score = scores["combined"]
            self.total = self.efficiency_score

        self.viability_total = self.viability_score
        self.efficiency_total = self.efficiency_score

    def ui_summary_lines(self, *, genetic_generations: int | None = None) -> list[str]:
        """Short lines for the workspace overlay."""
        status = "VIABLE" if self.is_viable else "BROKEN"
        lines = [
            f"Production: {status}  |  Score: {self.total:.0f}/100",
            f"  Viability {self.viability_score:.0f}/100  "
            f"Efficiency {self.efficiency_score:.0f}/100",
        ]
        if genetic_generations is not None:
            lines.append(f"Genetic generations: {genetic_generations}")

        if not self.is_viable:
            lines.append(f"  Blockers ({len(self.blockers)}):")
            for blocker in self.blockers[:3]:
                lines.append(f"    - {blocker}")
            if len(self.blockers) > 3:
                lines.append(f"    - …and {len(self.blockers) - 3} more")
        else:
            lines.append(
                f"  Footprint {self.footprint_score:.0f}/100  "
                f"Belts {self.belt_score:.0f}/100  "
                f"Layout {self.layout_score:.0f}/100"
            )
            if self.machine_count:
                lines.append(f"  ({self.machine_count} machines, normalized)")
        return lines


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def _ratio_to_score(raw: float, reference: float) -> float:
    """Map raw penalty magnitude to 0–100 (100 = best)."""
    if reference <= 0:
        return 100.0
    return _clamp_score(100.0 * (1.0 - min(raw / reference, 1.0)))


def _normalized_efficiency_scores(
    breakdown: LayoutFitnessBreakdown, machine_count: int
) -> dict[str, float]:
    """Per-machine normalized efficiency sub-scores."""
    if machine_count <= 0:
        return {"footprint": 0.0, "belts": 0.0, "layout": 0.0, "combined": 0.0}

    footprint_raw = abs(breakdown.footprint_penalty)
    belt_raw = float(breakdown.estimated_belt_tiles)
    layout_raw = abs(
        breakdown.outlier_penalty
        + breakdown.stage_cluster_penalty
        + breakdown.bus_alignment_penalty
    )

    footprint = _ratio_to_score(
        footprint_raw, machine_count * REF_FOOTPRINT_PER_MACHINE
    )
    belts = _ratio_to_score(belt_raw, machine_count * REF_BELT_TILES_PER_MACHINE)
    layout = _ratio_to_score(layout_raw, machine_count * REF_LAYOUT_PER_MACHINE)

    combined = (
        EFFICIENCY_WEIGHTS["footprint"] * footprint
        + EFFICIENCY_WEIGHTS["belts"] * belts
        + EFFICIENCY_WEIGHTS["layout"] * layout
    )
    return {
        "footprint": footprint,
        "belts": belts,
        "layout": layout,
        "combined": _clamp_score(combined),
    }


def positions_from_stage_machines(stage_machines: dict[str, list]) -> list[tuple[int, int, str]]:
    positions = []
    for item in sorted(stage_machines.keys()):
        for mx, my, _w, _h in sorted(stage_machines[item], key=lambda m: (m[0], m[1])):
            positions.append((mx, my, item))
    return positions


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _manhattan_path_length(start: tuple[int, int], end: tuple[int, int]) -> int:
    if start == end:
        return 0
    return _manhattan(start, end)


def _machine_cells(x: int, y: int, w: int, h: int) -> set[tuple[int, int]]:
    return {(x + dx, y + dy) for dx in range(w) for dy in range(h)}


def _machine_io_tiles(mx: int, my: int, w: int, h: int) -> set[tuple[int, int]]:
    lane_y = my + h // 2
    tiles = set()
    for i in range(3):
        tiles.add((mx - 4 + i, lane_y))
    for i in range(3):
        tiles.add((mx + w + 1 + i, lane_y))
    tiles.add((mx - 1, lane_y))
    tiles.add((mx + w, lane_y))
    return tiles


def _machine_center(mx: int, my: int, w: int, h: int) -> tuple[float, float]:
    return mx + w / 2, my + h / 2


def _add_blocker(breakdown: LayoutFitnessBreakdown, message: str):
    if message not in breakdown.blockers:
        breakdown.blockers.append(message)
        breakdown.details.append(message)


def evaluate_stage_layout(
    stage_machines: dict[str, list],
    nodes: dict,
    grid=None,
    *,
    preferred_stage_y: int = PREFERRED_STAGE_Y,
    expected_counts: dict[str, int] | None = None,
) -> LayoutFitnessBreakdown:
    """
    Score a layout: viability first, efficiency second.

    A compact layout that breaks mid-chain is always scored as non-viable.
    """
    breakdown = LayoutFitnessBreakdown()
    if not stage_machines and not nodes:
        breakdown.blockers.append("no machines placed")
        breakdown._finalize_total(0)
        return breakdown

    stage_lanes: dict = {}
    machine_footprints: list[tuple[str, set[tuple[int, int]]]] = []
    all_machine_cells: set[tuple[int, int]] = set()
    io_tiles_by_machine: list[set[tuple[int, int]]] = []

    for item, machines in stage_machines.items():
        lanes = stage_lanes_from_machines(machines)
        if lanes:
            stage_lanes[item] = lanes
        for mx, my, w, h in machines:
            mx, my, w, h = int(mx), int(my), int(w), int(h)
            cells = _machine_cells(mx, my, w, h)
            machine_footprints.append((item, cells))
            io_tiles_by_machine.append(_machine_io_tiles(mx, my, w, h))
            all_machine_cells |= cells

    counts = expected_counts or {
        item: node.machine_count for item, node in nodes.items()
    }

    # ----- TIER 1: VIABILITY (production must work end-to-end) -----

    seen: dict[tuple[int, int], str] = {}
    for item, cells in machine_footprints:
        for cell in cells:
            if cell in seen:
                breakdown.overlap_penalty -= 1
                _add_blocker(
                    breakdown,
                    f"machines overlap: {item} on {seen[cell]}",
                )
            else:
                seen[cell] = item

    for item, required in counts.items():
        if required <= 0:
            continue
        placed = len(stage_machines.get(item, []))
        if placed < required:
            _add_blocker(
                breakdown,
                f"not enough {item}: {placed}/{required} machines",
            )
        elif placed > required:
            breakdown.capacity_penalty -= (placed - required) * 5

    for item, required in counts.items():
        if required <= 0:
            continue
        if item not in stage_lanes:
            _add_blocker(breakdown, f"production stage missing: {item}")

    for idx, io_tiles in enumerate(io_tiles_by_machine):
        blocked = io_tiles & all_machine_cells
        if blocked:
            breakdown.inserter_penalty -= len(blocked)
            _add_blocker(
                breakdown,
                "inserter/belt tile blocked by a machine body",
            )
            break

    for idx, io_tiles in enumerate(io_tiles_by_machine):
        for jdx in range(idx + 1, len(io_tiles_by_machine)):
            shared = io_tiles & io_tiles_by_machine[jdx]
            if shared:
                breakdown.inserter_penalty -= len(shared)
                _add_blocker(
                    breakdown,
                    "machine I/O lanes collide (inserters cannot be placed)",
                )
                break

    estimated_belts = sum(len(m) for m in stage_machines.values()) * BELTS_PER_MACHINE
    base_material_feeds: dict[str, list] = {}

    for item, node in nodes.items():
        if item not in stage_lanes:
            continue

        consumer = stage_lanes[item]
        consumer_in = consumer["input_start"]
        ingredient_index = 0

        for dep in node.dependencies:
            if dep in BASE_MATERIALS:
                base_material_feeds.setdefault(dep, []).append(consumer_in)
                continue

            if dep not in stage_lanes:
                _add_blocker(breakdown, f"broken chain: no {dep} for {item}")
                continue

            producer = stage_lanes[dep]
            producer_out = producer["output_end"]
            target_in = (consumer_in[0], consumer_in[1] + ingredient_index * 2)

            if producer_out[0] >= target_in[0]:
                _add_blocker(
                    breakdown,
                    f"backward belt route: {dep} cannot feed {item} (east flow)",
                )

            route_start = (producer_out[0] + 1, producer_out[1])
            route_end = (target_in[0] - 1, target_in[1])
            estimated_belts += max(_manhattan_path_length(route_start, route_end), 0)
            if ingredient_index > 0:
                estimated_belts += _manhattan_path_length(
                    (target_in[0] - 1, target_in[1]),
                    (consumer_in[0] - 1, consumer_in[1]),
                )
            ingredient_index += 1

    for resource, input_points in base_material_feeds.items():
        estimated_belts += BASE_BUS_LENGTH
        for input_start in input_points:
            in_x, in_y = input_start
            drop_x = max(BASE_BUS_X_START, in_x - 5)
            estimated_belts += _manhattan_path_length(
                (drop_x, BASE_BUS_Y), (in_x - 1, in_y)
            )

    if grid is not None:
        for _item, cells in machine_footprints:
            for cell in cells:
                occupant = grid.occupied.get(cell)
                if occupant and not _is_machine_entity(occupant):
                    breakdown.grid_conflict_penalty -= 1
                    _add_blocker(breakdown, f"machine blocked by {occupant}")

    # ----- TIER 2: EFFICIENCY (only affects score when viable) -----

    breakdown.estimated_belt_tiles = estimated_belts
    breakdown.estimated_belts_penalty -= estimated_belts * 0.35

    all_x: list[int] = []
    all_y: list[int] = []
    centers: list[tuple[float, float]] = []
    for machines in stage_machines.values():
        for mx, my, w, h in machines:
            mx, my, w, h = int(mx), int(my), int(w), int(h)
            all_x.extend([mx, mx + w - 1])
            all_y.extend([my, my + h - 1])
            centers.append(_machine_center(mx, my, w, h))

    if all_x and all_y:
        width = max(all_x) - min(all_x) + 1
        height = max(all_y) - min(all_y) + 1
        breakdown.footprint_penalty -= width * height * 0.04
        breakdown.footprint_penalty -= (width + height) * 0.5

    if centers:
        factory_cx = sum(c[0] for c in centers) / len(centers)
        factory_cy = sum(c[1] for c in centers) / len(centers)
        for cx, cy in centers:
            dist = abs(cx - factory_cx) + abs(cy - factory_cy)
            if dist > 25:
                breakdown.outlier_penalty -= (dist - 25) * 1.0

    for _item, machines in stage_machines.items():
        if len(machines) < 2:
            continue
        cx = sum(m[0] + m[2] / 2 for m in machines) / len(machines)
        cy = sum(m[1] + m[3] / 2 for m in machines) / len(machines)
        spread = sum(
            abs(m[0] + m[2] / 2 - cx) + abs(m[1] + m[3] / 2 - cy) for m in machines
        )
        breakdown.stage_cluster_penalty -= spread * 0.15

    for item, node in nodes.items():
        if item not in stage_machines:
            continue
        needs_bus = any(dep in BASE_MATERIALS for dep in node.dependencies)
        if not needs_bus:
            continue
        avg_y = sum(m[1] for m in stage_machines[item]) / len(stage_machines[item])
        breakdown.bus_alignment_penalty -= abs(avg_y - preferred_stage_y) * 0.5

    machine_count = sum(len(machines) for machines in stage_machines.values())
    breakdown._finalize_total(machine_count)
    return breakdown


def _is_machine_entity(name: str) -> bool:
    if not name:
        return False
    return (
        "assembling-machine" in name
        or "furnace" in name
        or "miner" in name
        or "refinery" in name
    )


def evaluate_machine_positions(
    positions: list[tuple],
    machine_slots: list[tuple[str, dict]],
    nodes: dict,
    grid=None,
) -> LayoutFitnessBreakdown:
    """Score a genetic individual: list of (x, y, item) aligned with machine_slots."""
    stage_machines: dict[str, list] = {}
    expected_counts = {item: node.machine_count for item, node in nodes.items()}

    for idx, pos in enumerate(positions):
        if idx >= len(machine_slots) or pos is None or len(pos) < 3:
            continue
        x, y, item = int(pos[0]), int(pos[1]), pos[2]
        _, recipe = machine_slots[idx]
        w, h = recipe.get("machine_size", [3, 3])
        stage_machines.setdefault(item, []).append((x, y, w, h))

    if len(positions) < len(machine_slots):
        breakdown = evaluate_stage_layout(
            stage_machines, nodes, grid=None, expected_counts=expected_counts
        )
        missing = len(machine_slots) - len(
            [p for p in positions if p is not None and len(p) >= 3]
        )
        if missing > 0:
            _add_blocker(breakdown, f"{missing} machine slot(s) empty in layout")
            breakdown._finalize_total(len(stage_machines))
        return breakdown

    return evaluate_stage_layout(
        stage_machines,
        nodes,
        grid=None,
        expected_counts=expected_counts,
    )
