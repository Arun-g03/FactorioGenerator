"""Genetic algorithm layout for production machines (rate graph from ProductionPlanner)."""

from __future__ import annotations

import copy
import logging
import os
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from core.constants import BASE_MATERIALS, FACTORIO_EAST, machine_io_stride
from core.generationalAlgorithm import select_top_layouts
from planners.layout_fitness import (
    LayoutFitnessBreakdown,
    evaluate_machine_positions,
    evaluate_placed_subset,
)
from planners.machine_io import (
    ingredient_lane_index,
    machine_io_lanes,
    machine_row_step,
    place_machine_io_block,
)
from planners.machine_placer.calculations import (
    entity_accepts_recipe_field,
    machine_entity_for_recipe,
)
from planners.rule_based_placement import NetworkLayoutCursor, network_origin_for_stage
from planners.stage_connector import stage_lanes_from_machines

PLACEMENT_X_MIN = 5
"""Minimum x coordinate for genetic placement region (allows room for bus/inputs)"""

PLACEMENT_X_MAX = 160
"""Maximum x coordinate for genetic placement region (determines rightward build limit)"""

PLACEMENT_Y_MIN = 4
"""Minimum y coordinate for genetic placement region (typically avoids base row)"""

PLACEMENT_Y_MAX = 90
"""Maximum y coordinate for genetic placement region (vertical build limit)"""

DEFAULT_POPULATION_SIZE = 64
"""Number of layouts per generation in genetic algorithm"""

MIN_GENERATIONS = 20
"""Minimum number of generations to run before considering early stopping"""

MAX_GENERATIONS = 2500
"""Maximum allowable generations per placement run (absolute cap)"""

STALE_GENERATIONS_LIMIT = 120  
"""Number of generations to allow without fitness improvement before refresh or stop"""

FITNESS_IMPROVEMENT_EPS = 0.1
"""Required minimum improvement in layout fitness between stale generations to reset counter"""

MUTATION_RATE = 0.85
"""Per-child probability that at least one mutation operator is applied after crossover"""

MUTATIONS_PER_CHILD_MIN = 1
"""Minimum number of mutation operators to attempt per mutated child (may still skip some)"""

MUTATIONS_PER_CHILD_MAX = 4
"""Maximum number of mutation operators to attempt per mutated child"""

GA_WORKER_COUNT = 0
"""Parallel fitness evaluators; 0 = auto (cpu_count - 1), 1 = serial"""

WALKFORWARD_JITTER_SLOTS = 3
"""When jittering, pick randomly among the top N walk-forward candidates per slot"""

BACKTRACK_IMPROVE_ATTEMPTS = 2
"""Backtrack hill-climb tries on the best layout each generation"""

GeneticProgressCallback = Callable[[int, float, int, bool], None]


@dataclass
class GeneticRunResult:
    """Outcome of a genetic placement run."""

    machines: list
    fitness_breakdown: LayoutFitnessBreakdown
    generations: int
    converged: bool


def _machine_slots_from_nodes(nodes, topological_order):
    """Expand rate nodes into ordered (item, recipe) slots for each machine."""
    slots = []
    for node in topological_order:
        if not node.recipe:
            continue
        for _ in range(node.machine_count):
            slots.append((node.item, node.recipe))
    return slots


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _stage_machines_from_layout(machines, machine_slots, through_idx=None):
    """Build stage_machines dict from a layout prefix (topological slot order)."""
    stage: dict[str, list] = {}
    if through_idx is None:
        end = len(machines)
    else:
        end = min(through_idx + 1, len(machines))
    for idx in range(end):
        if idx >= len(machine_slots):
            break
        x, y, item = machines[idx]
        _, recipe = machine_slots[idx]
        w, h = recipe.get("machine_size", [3, 3])
        stage.setdefault(item, []).append((int(x), int(y), w, h))
    return stage


def _stage_lanes_map(stage_machines, nodes):
    lanes = {}
    for item, machines in stage_machines.items():
        node = nodes.get(item)
        recipe = getattr(node, "recipe", None) if node else None
        block = stage_lanes_from_machines(machines, recipe=recipe)
        if block:
            lanes[item] = block
    return lanes


def _local_slot_connection_score(slot_idx, x, y, layout, machine_slots, nodes):
    """Lower is better: per-edge belt distance using correct input lanes."""
    item, recipe = machine_slots[slot_idx]
    w, h = recipe.get("machine_size", [3, 3])
    node = nodes.get(item)
    if not node:
        return 0

    partial = _stage_machines_from_layout(
        layout.get("machines", []), machine_slots, slot_idx - 1
    )
    stage_lanes = _stage_lanes_map(partial, nodes)
    io = machine_io_lanes(x, y, w, h, FACTORIO_EAST)
    input_connects = io.get("input_connects", [io.get("input_start")])
    if not input_connects or input_connects[0] is None:
        return 10_000

    penalty = 0.0
    for dep in node.dependencies:
        if dep in BASE_MATERIALS:
            lane_idx = ingredient_lane_index(recipe, dep)
            target = input_connects[min(lane_idx, len(input_connects) - 1)]
            penalty += 12 + abs(target[1] - 15) * 0.4
        elif dep in stage_lanes:
            out = stage_lanes[dep].get("output_start", stage_lanes[dep]["output_end"])
            lane_idx = ingredient_lane_index(recipe, dep)
            target = input_connects[min(lane_idx, len(input_connects) - 1)]
            penalty += _manhattan((out[0] - 1, out[1]), target)
        else:
            penalty += 400
    return penalty


def _candidate_slot_score(slot_idx, x, y, layout, machine_slots, nodes, grid):
    """
    Combined local + partial-global score for walk-forward candidate ranking.

    Lower is better. Invalid I/O or broken partial chains receive a huge penalty.
    """
    item = machine_slots[slot_idx][0]
    trial = list(layout.get("machines", []))
    trial.append((int(x), int(y), item))
    stage_machines = _stage_machines_from_layout(trial, machine_slots, slot_idx)
    breakdown = evaluate_placed_subset(stage_machines, nodes, grid=grid)
    if breakdown.blockers:
        return 1_000_000.0 + len(breakdown.blockers) * 10_000.0

    local = _local_slot_connection_score(slot_idx, x, y, layout, machine_slots, nodes)
    global_hint = max(0.0, 100.0 - breakdown.total) * 1.5
    belt_hint = float(breakdown.estimated_belt_tiles) * 0.25
    return local + global_hint + belt_hint


def _prefix_viable_through(layout, machine_slots, nodes, grid, through_idx):
    """True when machines [0..through_idx] pass partial viability checks."""
    if through_idx < 0:
        return True
    machines = layout.get("machines", [])
    if len(machines) <= through_idx:
        return False
    stage_machines = _stage_machines_from_layout(machines, machine_slots, through_idx)
    return not evaluate_placed_subset(stage_machines, nodes, grid=grid).blockers


def _walkforward_candidates_for_slot(
    slot_idx, layout, machine_slots, nodes, grid, rng, *, jitter=False
):
    """Ordered candidate (x, y) positions for one slot, best connection score first."""
    item, recipe = machine_slots[slot_idx]
    w, h = recipe.get("machine_size", [3, 3])
    machines = layout.get("machines", [])
    used = set()
    for idx, (mx, my, _) in enumerate(machines):
        if idx >= len(machine_slots):
            break
        bw, bh = _machine_size_at_index(machine_slots, idx)
        used |= _cells_for_machine(int(mx), int(my), bw, bh)

    anchors: list[tuple[int, int]] = []
    if slot_idx > 0 and machine_slots[slot_idx - 1][0] == item and slot_idx - 1 < len(machines):
        px, py, _ = machines[slot_idx - 1]
        dx, dy = machine_row_step(FACTORIO_EAST, machine_io_stride(w), 1)
        anchors.append((int(px) + dx, int(py) + dy))
    else:
        partial = _stage_machines_from_layout(machines, machine_slots, slot_idx - 1)
        stage_lanes = _stage_lanes_map(partial, nodes)
        node = nodes.get(item)
        if node:
            cursor = NetworkLayoutCursor(
                next_x=PLACEMENT_X_MIN + (slot_idx % 6) * 14,
                next_y=PLACEMENT_Y_MIN + (slot_idx % 4) * 6,
            )
            ax, ay, _flow = network_origin_for_stage(
                node, nodes, stage_lanes, cursor
            )
            anchors.append((ax, ay))
        else:
            anchors.append((PLACEMENT_X_MIN, PLACEMENT_Y_MIN))

    offsets = [
        (0, 0),
        (2, 0),
        (4, 0),
        (6, 0),
        (0, 2),
        (0, -2),
        (-2, 0),
        (3, 1),
        (-3, -1),
    ]
    if jitter:
        offsets.extend((rng.randint(-5, 5), rng.randint(-3, 3)) for _ in range(8))

    scored: list[tuple[float, int, int]] = []
    seen_xy: set[tuple[int, int]] = set()
    for base_x, base_y in anchors:
        for ox, oy in offsets:
            x = max(PLACEMENT_X_MIN, min(PLACEMENT_X_MAX - w, base_x + ox))
            y = max(PLACEMENT_Y_MIN, min(PLACEMENT_Y_MAX - h, base_y + oy))
            if (x, y) in seen_xy:
                continue
            seen_xy.add((x, y))
            cells = _cells_for_machine(x, y, w, h)
            if cells & used:
                continue
            if grid is not None and any(grid.is_occupied(cx, cy) for cx, cy in cells):
                continue
            score = _candidate_slot_score(
                slot_idx, x, y, layout, machine_slots, nodes, grid
            )
            scored.append((score, x, y))

    scored.sort(key=lambda row: row[0])
    if jitter and len(scored) > 1:
        head = scored[: min(WALKFORWARD_JITTER_SLOTS, len(scored))]
        rng.shuffle(head)
        scored = head + scored[len(head) :]
    return [(x, y) for _score, x, y in scored]


def _walkforward_extend_from(
    layout, start_idx, machine_slots, nodes, grid, rng, *, jitter=False
):
    """Place slots [start_idx, end) in topological order (walk-forward)."""
    for slot_idx in range(start_idx, len(machine_slots)):
        item, recipe = machine_slots[slot_idx]
        candidates = _walkforward_candidates_for_slot(
            slot_idx, layout, machine_slots, nodes, grid, rng, jitter=jitter
        )
        placed = False
        for x, y in candidates:
            layout["machines"].append((x, y, item))
            if _prefix_viable_through(layout, machine_slots, nodes, grid, slot_idx):
                placed = True
                break
            layout["machines"].pop()

        if not placed:
            w, h = recipe.get("machine_size", [3, 3])
            used = set()
            for idx, (mx, my, _) in enumerate(layout.get("machines", [])):
                if idx >= len(machine_slots):
                    break
                bw, bh = _machine_size_at_index(machine_slots, idx)
                used |= _cells_for_machine(int(mx), int(my), bw, bh)
            for _ in range(40):
                pos = _random_open_position(used, w, h, grid)
                if pos is None:
                    break
                layout["machines"].append((pos[0], pos[1], item))
                if _prefix_viable_through(
                    layout, machine_slots, nodes, grid, slot_idx
                ):
                    placed = True
                    break
                layout["machines"].pop()
            if not placed:
                pos = (PLACEMENT_X_MIN + slot_idx * 8, PLACEMENT_Y_MIN)
                layout["machines"].append((pos[0], pos[1], item))

    layout["fitness"] = 0
    return layout


def _build_layout_walkforward(machine_slots, nodes, grid, rng, *, jitter=False):
    """Construct a full layout by walking the chain forward slot by slot."""
    layout = {"machines": [], "belts": [], "splitters": [], "fitness": 0}
    return _walkforward_extend_from(
        layout, 0, machine_slots, nodes, grid, rng, jitter=jitter
    )


def _first_invalid_slot(machines, machine_slots, grid):
    """Index of the first overlapping or out-of-bounds machine, or None."""
    for idx in range(len(machines)):
        if idx >= len(machine_slots):
            return idx
        item, recipe = machine_slots[idx]
        w, h = recipe.get("machine_size", [3, 3])
        mx, my = int(machines[idx][0]), int(machines[idx][1])
        cells = _cells_for_machine(mx, my, w, h)
        others = set()
        for jdx, (ox, oy, _) in enumerate(machines):
            if jdx == idx or jdx >= len(machine_slots):
                continue
            bw, bh = _machine_size_at_index(machine_slots, jdx)
            others |= _cells_for_machine(int(ox), int(oy), bw, bh)
        if cells & others:
            return idx
        if grid is not None and any(grid.is_occupied(cx, cy) for cx, cy in cells):
            return idx
    return None


def _initialize_population(population_size, machine_slots, nodes, grid):
    """Seed population with dependency-aware walk-forward layouts."""
    population = []
    for i in range(population_size):
        jitter = i >= population_size // 4
        population.append(
            _build_layout_walkforward(
                machine_slots, nodes, grid, random, jitter=jitter
            )
        )
    return population


def _evaluate_layout(layout, grid, machine_slots, nodes):
    """Higher fitness = better layout (shared scoring with rule-based)."""
    breakdown = evaluate_machine_positions(
        layout["machines"], machine_slots, nodes, grid
    )
    layout["fitness"] = breakdown.total
    layout["fitness_breakdown"] = breakdown
    return breakdown.total


def _resolve_worker_count(worker_count=None):
    """Map 0 to auto-detected parallelism; 1 keeps evaluation serial."""
    count = GA_WORKER_COUNT if worker_count is None else worker_count
    if count <= 0:
        cpus = os.cpu_count() or 1
        return max(1, cpus - 1)
    return count


def _evaluate_population(population, grid, machine_slots, nodes, worker_count=None):
    """Evaluate every layout in the population, optionally in parallel."""
    workers = _resolve_worker_count(worker_count)
    if workers <= 1 or len(population) <= 1:
        return [
            (layout, _evaluate_layout(layout, grid, machine_slots, nodes))
            for layout in population
        ]

    def _eval_one(layout):
        return layout, _evaluate_layout(layout, grid, machine_slots, nodes)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(_eval_one, population))


def _machine_size_at_index(machine_slots, index):
    _, recipe = machine_slots[index]
    w, h = recipe.get("machine_size", [3, 3])
    return w, h


def _cells_for_machine(x, y, w, h):
    return {(x + dx, y + dy) for dx in range(w) for dy in range(h)}


def _occupied_by_others(layout, skip_index, machine_slots):
    """Cells occupied by all machines except skip_index."""
    used = set()
    for idx, (mx, my, _item) in enumerate(layout["machines"]):
        if idx == skip_index or idx >= len(machine_slots):
            continue
        w, h = _machine_size_at_index(machine_slots, idx)
        used |= _cells_for_machine(int(mx), int(my), w, h)
    return used


def _random_open_position(used, w, h, grid, attempts=100):
    """Random top-left (x, y) where the w×h footprint is free."""
    for _ in range(attempts):
        x = random.randint(PLACEMENT_X_MIN, PLACEMENT_X_MAX - w)
        y = random.randint(PLACEMENT_Y_MIN, PLACEMENT_Y_MAX - h)
        cells = _cells_for_machine(x, y, w, h)
        if cells & used:
            continue
        if grid is not None and any(grid.is_occupied(cx, cy) for cx, cy in cells):
            continue
        return x, y
    return None


def _first_nonviable_prefix_slot(machines, machine_slots, nodes, grid):
    """First slot index where the prefix fails partial viability (or None)."""
    for idx in range(len(machines)):
        if idx >= len(machine_slots):
            return idx
        stage_machines = _stage_machines_from_layout(machines, machine_slots, idx)
        if evaluate_placed_subset(stage_machines, nodes, grid=grid).blockers:
            return idx
    return None


def _repair_layout(layout, machine_slots, nodes, grid):
    """Backtrack to overlap or I/O failure, then walk-forward to refill."""
    target_len = len(machine_slots)
    machines = list(layout.get("machines", []))[:target_len]
    layout["machines"] = machines

    bad = _first_invalid_slot(machines, machine_slots, grid)
    viability_bad = _first_nonviable_prefix_slot(
        machines, machine_slots, nodes, grid
    )
    if viability_bad is not None:
        bad = viability_bad if bad is None else min(bad, viability_bad)

    if bad is not None:
        layout["machines"] = machines[:bad]
        _walkforward_extend_from(
            layout, bad, machine_slots, nodes, grid, random, jitter=False
        )
    elif len(machines) < target_len:
        _walkforward_extend_from(
            layout, len(machines), machine_slots, nodes, grid, random, jitter=False
        )
    elif len(machines) > target_len:
        layout["machines"] = machines[:target_len]

    if len(layout["machines"]) == target_len:
        full = evaluate_machine_positions(
            layout["machines"], machine_slots, nodes, grid
        )
        if full.blockers:
            back = _first_nonviable_prefix_slot(
                layout["machines"], machine_slots, nodes, grid
            )
            if back is not None:
                layout["machines"] = layout["machines"][:back]
                _walkforward_extend_from(
                    layout, back, machine_slots, nodes, grid, random, jitter=True
                )

    layout["fitness"] = 0
    return layout


def _crossover_uniform(parent1, parent2, machine_slots_len):
    """Per-machine uniform crossover: each slot from parent1 or parent2."""
    child = {"machines": [], "belts": [], "splitters": [], "fitness": 0}
    for i in range(machine_slots_len):
        p1_m = parent1["machines"][i] if i < len(parent1["machines"]) else None
        p2_m = parent2["machines"][i] if i < len(parent2["machines"]) else None
        if p1_m is None:
            child["machines"].append(p2_m)
        elif p2_m is None:
            child["machines"].append(p1_m)
        elif random.random() < 0.5:
            child["machines"].append(p1_m)
        else:
            child["machines"].append(p2_m)
    return child


def _crossover_two_point(parent1, parent2, machine_slots_len):
    """Two-point crossover on the machine sequence."""
    child = {"machines": [], "belts": [], "splitters": [], "fitness": 0}
    if machine_slots_len < 2:
        return _crossover_uniform(parent1, parent2, machine_slots_len)

    points = sorted(random.sample(range(machine_slots_len), min(2, machine_slots_len)))
    a, b = points[0], points[-1]

    for i in range(machine_slots_len):
        use_p2 = a <= i <= b
        src = parent2 if use_p2 else parent1
        fallback = parent1 if use_p2 else parent2
        if i < len(src["machines"]):
            child["machines"].append(src["machines"][i])
        elif i < len(fallback["machines"]):
            child["machines"].append(fallback["machines"][i])
    return child


def _crossover_layout(parent1, parent2, machine_slots_len):
    """Pick a standard crossover operator at random."""
    if random.random() < 0.5:
        return _crossover_uniform(parent1, parent2, machine_slots_len)
    return _crossover_two_point(parent1, parent2, machine_slots_len)


def _mutate_relocate(layout, machine_slots, grid):
    """Move one machine to a new random non-overlapping position."""
    if not layout["machines"]:
        return
    idx = random.randrange(len(layout["machines"]))
    w, h = _machine_size_at_index(machine_slots, idx)
    used = _occupied_by_others(layout, idx, machine_slots)
    pos = _random_open_position(used, w, h, grid)
    if pos is not None:
        item = layout["machines"][idx][2]
        layout["machines"][idx] = (pos[0], pos[1], item)


def _mutate_nudge(layout, machine_slots, grid):
    """Shift one machine by a small random offset."""
    if not layout["machines"]:
        return
    idx = random.randrange(len(layout["machines"]))
    mx, my, item = layout["machines"][idx]
    w, h = _machine_size_at_index(machine_slots, idx)
    dx = random.randint(-3, 3)
    dy = random.randint(-2, 2)
    nx = max(PLACEMENT_X_MIN, min(PLACEMENT_X_MAX - w, int(mx) + dx))
    ny = max(PLACEMENT_Y_MIN, min(PLACEMENT_Y_MAX - h, int(my) + dy))
    used = _occupied_by_others(layout, idx, machine_slots)
    cells = _cells_for_machine(nx, ny, w, h)
    if not (cells & used) and not (
        grid is not None and any(grid.is_occupied(cx, cy) for cx, cy in cells)
    ):
        layout["machines"][idx] = (nx, ny, item)


def _mutate_backtrack(layout, machine_slots, nodes, grid):
    """Truncate at a slot and walk-forward again (dependency-aware backtrack)."""
    if not machine_slots:
        return layout
    slot = random.randrange(len(machine_slots))
    layout["machines"] = layout["machines"][:slot]
    _walkforward_extend_from(
        layout, slot, machine_slots, nodes, grid, random, jitter=True
    )
    return layout


def _mutate_swap_positions(layout, machine_slots, nodes, grid):
    """Swap (x, y) between two machines; item types stay at their indices."""
    if len(layout["machines"]) < 2:
        return
    i, j = random.sample(range(len(layout["machines"])), 2)
    mi = layout["machines"][i]
    mj = layout["machines"][j]
    layout["machines"][i] = (mj[0], mj[1], mi[2])
    layout["machines"][j] = (mi[0], mi[1], mj[2])
    _repair_layout(layout, machine_slots, nodes, grid)


def _backtrack_improve(layout, machine_slots, nodes, grid, rng):
    """Try a few backtrack points on the best layout (local hill-climb)."""
    if not layout.get("machines") or len(machine_slots) < 2:
        return layout

    best = copy.deepcopy(layout)
    best_score = best.get("fitness", float("-inf"))
    for _ in range(BACKTRACK_IMPROVE_ATTEMPTS):
        trial = copy.deepcopy(best)
        slot = rng.randrange(len(machine_slots))
        trial["machines"] = trial["machines"][:slot]
        _walkforward_extend_from(
            trial, slot, machine_slots, nodes, grid, rng, jitter=True
        )
        score = _evaluate_layout(trial, grid, machine_slots, nodes)
        if score > best_score:
            best_score = score
            best = trial
    return best


_MUTATION_OPERATORS = (
    _mutate_nudge,
    _mutate_relocate,
)


def _mutate_layout(layout, machine_slots, nodes, grid):
    """Backtrack walk-forward is primary; small nudges for fine tuning."""
    if random.random() > MUTATION_RATE:
        return _repair_layout(layout, machine_slots, nodes, grid)

    if random.random() < 0.75:
        _mutate_backtrack(layout, machine_slots, nodes, grid)
    else:
        ops_to_run = random.randint(1, 2)
        for _ in range(ops_to_run):
            op = random.choice(_MUTATION_OPERATORS)
            op(layout, machine_slots, grid)
        _repair_layout(layout, machine_slots, nodes, grid)

    return layout


def _tournament_select(population, tournament_size=3):
    """Pick one parent via tournament selection."""
    contenders = random.sample(population, min(tournament_size, len(population)))
    return max(contenders, key=lambda layout: layout.get("fitness", float("-inf")))


def _evolve_one_generation(
    population, population_size, machine_slots, nodes, grid, machine_slots_len
):
    """Tournament selection, crossover, mutation, and elitist retention."""
    elite_count = max(2, population_size // 4)
    top_layouts = select_top_layouts(population, top_n=elite_count)
    new_population = []

    while len(new_population) < population_size - len(top_layouts):
        p1 = _tournament_select(population)
        p2 = _tournament_select(population)
        child = _crossover_layout(p1, p2, machine_slots_len)
        child = _repair_layout(child, machine_slots, nodes, grid)
        child = _mutate_layout(child, machine_slots, nodes, grid)
        new_population.append(child)

    return top_layouts + new_population[: population_size - len(top_layouts)]


def run_genetic_layout(
    grid,
    machine_slots,
    nodes,
    population_size=DEFAULT_POPULATION_SIZE,
    progress_callback: GeneticProgressCallback | None = None,
) -> GeneticRunResult:
    """
    Evolve layouts until fitness stops improving or MAX_GENERATIONS is reached.

    Keeps the best individual seen across all generations (elitism).
    """
    empty = GeneticRunResult([], LayoutFitnessBreakdown(), 0, True)
    if not machine_slots:
        return empty

    population = _initialize_population(
        population_size, machine_slots, nodes, grid
    )
    best_ever = None
    best_ever_fitness = float("-inf")
    stale_generations = 0
    generation = 0
    converged = False

    while generation < MAX_GENERATIONS:
        generation += 1
        fitness_before_gen = best_ever_fitness

        for layout, fitness in _evaluate_population(
            population, grid, machine_slots, nodes
        ):
            if fitness > best_ever_fitness:
                best_ever_fitness = fitness
                best_ever = copy.deepcopy(layout)

        if best_ever_fitness <= fitness_before_gen + FITNESS_IMPROVEMENT_EPS:
            stale_generations += 1
        else:
            stale_generations = 0

        if progress_callback:
            progress_callback(
                generation, best_ever_fitness, stale_generations, False
            )

        if generation >= MIN_GENERATIONS and stale_generations >= STALE_GENERATIONS_LIMIT:
            converged = True
            logging.info(
                "Genetic placement converged at generation %s (score=%.0f/100)",
                generation,
                best_ever_fitness,
            )
            break

        population = _evolve_one_generation(
            population,
            population_size,
            machine_slots,
            nodes,
            grid,
            len(machine_slots),
        )
        if best_ever is not None:
            improved = _backtrack_improve(
                best_ever, machine_slots, nodes, grid, random
            )
            if improved.get("fitness", 0) >= best_ever_fitness:
                best_ever = improved
                best_ever_fitness = improved.get("fitness", best_ever_fitness)
            population[0] = copy.deepcopy(best_ever)

    if best_ever is None:
        _evaluate_population(population, grid, machine_slots, nodes)
        best_ever = select_top_layouts(population, top_n=1)[0]

    bd = best_ever.get("fitness_breakdown") or LayoutFitnessBreakdown()
    if progress_callback:
        progress_callback(generation, bd.total, stale_generations, True)

    logging.info(
        "Genetic finished: %s generations, score=%.0f/100, converged=%s",
        generation,
        bd.total,
        converged,
    )

    return GeneticRunResult(
        machines=best_ever["machines"][: len(machine_slots)],
        fitness_breakdown=bd,
        generations=generation,
        converged=converged,
    )


def place_machines_from_genetic_layout(planner, entities, entity_number, machine_slots, positions):
    """Place machines and I/O from genetic (x, y, item) positions."""
    stages_by_item = {}

    for idx, (pos, (item, recipe)) in enumerate(zip(positions, machine_slots)):
        if pos is None or len(pos) < 3:
            continue
        mx, my, pos_item = pos[0], pos[1], pos[2]
        if pos_item != item:
            item = pos_item
            recipe = planner.nodes[item].recipe if item in planner.nodes else recipe

        machine_name = machine_entity_for_recipe(item, recipe)
        w, h = recipe.get("machine_size", [3, 3])

        if planner.grid.is_occupied(mx, my, w, h):
            alt = planner.position_finder.find_next_available_position_with_spacing(w, h)
            if alt[0] is not None:
                mx, my = alt
            else:
                planner.logger.warning("Genetic placement: no space for %s", item)
                continue

        entity = {
            "entity_number": entity_number,
            "name": machine_name,
            "position": {"x": mx, "y": my},
        }
        if entity_accepts_recipe_field(machine_name):
            entity["recipe"] = item
        entities.append(entity)
        planner.grid.occupy(mx, my, machine_name, [w, h])
        entity_number += 1

        planner.stage_machines.setdefault(item, []).append((mx, my, w, h))

        from planners.machine_io import recipe_input_lane_count

        entity_number = place_machine_io_block(
            planner.grid,
            entities,
            entity_number,
            mx,
            my,
            w,
            h,
            flow_east=True,
            recipe=recipe,
            input_lane_count=recipe_input_lane_count(recipe),
        )

        if item not in stages_by_item:
            stages_by_item[item] = {
                "id": len(planner.production_stages) + 1,
                "type": item,
                "position": (mx, my),
                "recipe": recipe,
                "entities": [],
            }
            planner.production_stages.append(stages_by_item[item])

    return entity_number


def collect_machine_slots(planner):
    """Machine slots in topological order from a configured planner."""
    return _machine_slots_from_nodes(planner.nodes, planner.topological_order())
