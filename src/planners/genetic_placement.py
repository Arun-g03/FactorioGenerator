"""Genetic algorithm layout for production machines (rate graph from ProductionPlanner)."""

import logging
import random

from core.generationalAlgorithm import crossover, mutate, select_top_layouts
from planners.machine_io import place_machine_io_block

# Placement search region (after ingredient bus at top)
PLACEMENT_X_MIN = 15
PLACEMENT_X_MAX = 90
PLACEMENT_Y_MIN = 12
PLACEMENT_Y_MAX = 55
DEFAULT_POPULATION_SIZE = 24
DEFAULT_GENERATIONS = 12


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


def _evaluate_layout(layout, grid, machine_slots):
    """Higher fitness = better layout."""
    fitness = 0
    occupied_cells = set()

    for idx, (x, y, item) in enumerate(layout["machines"]):
        if idx >= len(machine_slots):
            break
        _, recipe = machine_slots[idx]
        w, h = recipe.get("machine_size", [3, 3])
        cells = {(x + dx, y + dy) for dx in range(w) for dy in range(h)}

        if cells & occupied_cells:
            fitness -= 50
        occupied_cells |= cells

        for cx, cy in cells:
            if grid.is_occupied(cx, cy):
                fitness -= 20

        # Prefer compact rows, not too far from bus
        fitness -= abs(y - PLACEMENT_Y_MIN) * 0.5
        fitness -= x * 0.02

    # Reward placing same item types near each other
    by_item = {}
    for x, y, item in layout["machines"]:
        by_item.setdefault(item, []).append((x, y))
    for positions in by_item.values():
        if len(positions) > 1:
            cx = sum(p[0] for p in positions) / len(positions)
            cy = sum(p[1] for p in positions) / len(positions)
            spread = sum(abs(p[0] - cx) + abs(p[1] - cy) for p in positions)
            fitness -= spread * 0.3

    layout["fitness"] = fitness
    return fitness


def run_genetic_layout(grid, machine_slots, population_size=DEFAULT_POPULATION_SIZE, generations=DEFAULT_GENERATIONS):
    """Return best list of (x, y, item) machine positions."""
    if not machine_slots:
        return []

    population = _initialize_population(population_size, machine_slots, grid)

    for generation in range(generations):
        logging.info("Genetic placement generation %s/%s", generation + 1, generations)
        for layout in population:
            _evaluate_layout(layout, grid, machine_slots)

        top_layouts = select_top_layouts(population, top_n=max(2, population_size // 2))
        new_population = []
        while len(new_population) < population_size - len(top_layouts):
            p1, p2 = random.sample(top_layouts, 2)
            child = crossover(p1, p2)
            child = mutate(
                child,
                mutation_rate=0.15,
                grid_width=PLACEMENT_X_MAX,
                grid_height=PLACEMENT_Y_MAX,
            )
            if len(child["machines"]) < len(machine_slots):
                item = machine_slots[len(child["machines"])][0]
                child["machines"].append(
                    (
                        random.randint(PLACEMENT_X_MIN, PLACEMENT_X_MAX - 3),
                        random.randint(PLACEMENT_Y_MIN, PLACEMENT_Y_MAX - 3),
                        item,
                    )
                )
            new_population.append(child)

        population = top_layouts + new_population[: population_size - len(top_layouts)]

    best = select_top_layouts(population, top_n=1)[0]
    return best["machines"][: len(machine_slots)]


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

        machine_name = recipe.get("machine", "assembling-machine-1")
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
        if machine_name.startswith("assembling-machine") or "furnace" in machine_name:
            entity["recipe"] = item
        entities.append(entity)
        planner.grid.occupy(mx, my, machine_name, [w, h])
        entity_number += 1

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
