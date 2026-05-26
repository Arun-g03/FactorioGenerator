"""Genetic algorithm layout for production machines (rate graph from ProductionPlanner)."""

from __future__ import annotations

import copy
import logging
import random
from dataclasses import dataclass
from typing import Callable

from core.generationalAlgorithm import select_top_layouts
from planners.layout_fitness import LayoutFitnessBreakdown, evaluate_machine_positions
from planners.machine_io import place_machine_io_block
from planners.machine_placer.calculations import (
    entity_accepts_recipe_field,
    machine_entity_for_recipe,
)

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


def _initialize_population(population_size, machine_slots, grid):
    """Build random non-overlapping layouts for each individual."""
    population = []

    for _ in range(population_size):
        layout = {"machines": [], "belts": [], "splitters": [], "fitness": 0}
        used = set()

        for item, recipe in machine_slots:
            placed = False
            for _ in range(80):
                w, h = recipe.get("machine_size", [3, 3])
                x = random.randint(PLACEMENT_X_MIN, PLACEMENT_X_MAX - w)
                y = random.randint(PLACEMENT_Y_MIN, PLACEMENT_Y_MAX - h)
                cells = {(x + dx, y + dy) for dx in range(w) for dy in range(h)}
                if cells & used:
                    continue
                if any(grid.is_occupied(cx, cy) for cx, cy in cells):
                    continue
                used |= cells
                layout["machines"].append((x, y, item))
                placed = True
                break
            if not placed:
                x = PLACEMENT_X_MIN + len(layout["machines"]) * 8
                y = PLACEMENT_Y_MIN
                layout["machines"].append((x, y, item))

        population.append(layout)
    return population


def _evaluate_layout(layout, grid, machine_slots, nodes):
    """Higher fitness = better layout (shared scoring with rule-based)."""
    breakdown = evaluate_machine_positions(
        layout["machines"], machine_slots, nodes, grid
    )
    layout["fitness"] = breakdown.total
    layout["fitness_breakdown"] = breakdown
    return breakdown.total


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


def _repair_layout(layout, machine_slots, grid):
    """Fix overlaps and length mismatches after crossover or mutation."""
    target_len = len(machine_slots)
    machines = list(layout.get("machines", []))

    while len(machines) < target_len:
        idx = len(machines)
        item, recipe = machine_slots[idx]
        w, h = recipe.get("machine_size", [3, 3])
        used = set()
        for i, (mx, my, _) in enumerate(machines):
            bw, bh = _machine_size_at_index(machine_slots, i)
            used |= _cells_for_machine(int(mx), int(my), bw, bh)
        pos = _random_open_position(used, w, h, grid)
        if pos is None:
            pos = (PLACEMENT_X_MIN + idx * 8, PLACEMENT_Y_MIN)
        machines.append((pos[0], pos[1], item))

    machines = machines[:target_len]
    for idx in range(target_len):
        item, recipe = machine_slots[idx]
        w, h = recipe.get("machine_size", [3, 3])
        used = _occupied_by_others({"machines": machines}, idx, machine_slots)
        mx, my = machines[idx][0], machines[idx][1]
        cells = _cells_for_machine(int(mx), int(my), w, h)
        if cells & used or (
            grid is not None and any(grid.is_occupied(cx, cy) for cx, cy in cells)
        ):
            pos = _random_open_position(used, w, h, grid)
            if pos is not None:
                machines[idx] = (pos[0], pos[1], item)
            else:
                machines[idx] = (PLACEMENT_X_MIN + idx * 8, PLACEMENT_Y_MIN, item)
        else:
            machines[idx] = (int(mx), int(my), item)

    layout["machines"] = machines
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


def _mutate_swap_positions(layout, machine_slots, grid):
    """Swap (x, y) between two machines; item types stay at their indices."""
    if len(layout["machines"]) < 2:
        return
    i, j = random.sample(range(len(layout["machines"])), 2)
    mi = layout["machines"][i]
    mj = layout["machines"][j]
    layout["machines"][i] = (mj[0], mj[1], mi[2])
    layout["machines"][j] = (mi[0], mi[1], mj[2])
    _repair_layout(layout, machine_slots, grid)


def _mutate_scramble_segment(layout, machine_slots, grid):
    """Shuffle positions within a random contiguous slice (order crossover style)."""
    n = len(layout["machines"])
    if n < 2:
        return
    a = random.randint(0, n - 2)
    b = random.randint(a + 1, n)
    segment = layout["machines"][a:b]
    positions = [(m[0], m[1]) for m in segment]
    random.shuffle(positions)
    for k, (x, y) in enumerate(positions):
        item = segment[k][2]
        segment[k] = (x, y, item)
    layout["machines"][a:b] = segment
    _repair_layout(layout, machine_slots, grid)


def _mutate_reset_one(layout, machine_slots, grid):
    """Re-randomize every machine of one item type (keeps them clustered)."""
    items = list({m[2] for m in layout["machines"]})
    if not items:
        return
    target_item = random.choice(items)
    delta_x = random.randint(-6, 6)
    delta_y = random.randint(-4, 4)
    for idx, (mx, my, item) in enumerate(layout["machines"]):
        if item != target_item:
            continue
        w, h = _machine_size_at_index(machine_slots, idx)
        nx = max(PLACEMENT_X_MIN, min(PLACEMENT_X_MAX - w, int(mx) + delta_x))
        ny = max(PLACEMENT_Y_MIN, min(PLACEMENT_Y_MAX - h, int(my) + delta_y))
        layout["machines"][idx] = (nx, ny, item)
    _repair_layout(layout, machine_slots, grid)


_MUTATION_OPERATORS = (
    _mutate_relocate,
    _mutate_nudge,
    _mutate_swap_positions,
    _mutate_scramble_segment,
    _mutate_reset_one,
)


def _mutate_layout(layout, machine_slots, grid):
    """Apply standard GA mutation operators (random subset per child)."""
    if random.random() > MUTATION_RATE:
        return layout

    ops_to_run = random.randint(MUTATIONS_PER_CHILD_MIN, MUTATIONS_PER_CHILD_MAX)
    for _ in range(ops_to_run):
        op = random.choice(_MUTATION_OPERATORS)
        op(layout, machine_slots, grid)

    return _repair_layout(layout, machine_slots, grid)


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
        child = _mutate_layout(child, machine_slots, grid)
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

    population = _initialize_population(population_size, machine_slots, grid)
    best_ever = None
    best_ever_fitness = float("-inf")
    stale_generations = 0
    generation = 0
    converged = False

    while generation < MAX_GENERATIONS:
        generation += 1
        fitness_before_gen = best_ever_fitness

        for layout in population:
            fitness = _evaluate_layout(layout, grid, machine_slots, nodes)
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
            population[0] = copy.deepcopy(best_ever)

    if best_ever is None:
        for layout in population:
            _evaluate_layout(layout, grid, machine_slots, nodes)
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

        entity_number = place_machine_io_block(
            planner.grid, entities, entity_number, mx, my, w, h, flow_east=True
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
