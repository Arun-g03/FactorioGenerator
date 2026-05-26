"""Generational algorithm for optimizing factory layouts."""

import random
import logging

def initialize_population(population_size, grid_width, grid_height, num_machines, base_resources):
    """
    Initialize a population of random layouts.
    """
    population = []

    for _ in range(population_size):
        layout = {
            "machines": [],
            "belts": [],
            "splitters": [],
            "fitness": 0
        }

        # Randomly place machines
        for _ in range(num_machines):
            x = random.randint(grid_width // 4, 3 * grid_width // 4)
            y = random.randint(grid_height // 4, 3 * grid_height // 4)
            target_item = random.choice(list(base_resources))
            layout["machines"].append((x, y, target_item))

        # Add empty belts and splitters (to be filled during routing)
        layout["belts"] = []
        layout["splitters"] = []

        population.append(layout)

    return population

def evaluate_fitness(layout, grid):
    """
    Evaluate the fitness of a layout.
    """
    fitness = 0

    # Penalty for belt length
    fitness -= len(layout["belts"])

    # Penalty for overlaps
    for (x, y) in layout["belts"] + [m[:2] for m in layout["machines"]]:
        if grid.is_occupied(x, y):
            fitness -= 10

    # Bonus for proximity to resource bus
    for (x, y, _) in layout["machines"]:
        fitness -= abs(x - grid.width // 2) + abs(y - grid.height // 2)

    layout["fitness"] = fitness
    return fitness

def select_top_layouts(population, top_n):
    """
    Select the top N layouts based on fitness.
    """
    population.sort(key=lambda layout: layout["fitness"], reverse=True)
    return population[:top_n]

def crossover(parent1, parent2):
    """
    Combine two parent layouts to produce an offspring.
    """
    child = {
        "machines": [],
        "belts": [],
        "splitters": [],
        "fitness": 0
    }

    # Combine machines from both parents
    mid_point = len(parent1["machines"]) // 2
    child["machines"] = parent1["machines"][:mid_point] + parent2["machines"][mid_point:]

    # Combine belts and splitters
    child["belts"] = list(set(parent1["belts"] + parent2["belts"]))
    child["splitters"] = list(set(parent1["splitters"] + parent2["splitters"]))

    return child

def mutate(layout, mutation_rate, grid_width, grid_height):
    """
    Introduce random changes to a layout.
    """
    if random.random() < mutation_rate:
        # Randomly move a machine
        if layout["machines"]:
            idx = random.randint(0, len(layout["machines"]) - 1)
            x = random.randint(0, grid_width - 1)
            y = random.randint(0, grid_height - 1)
            layout["machines"][idx] = (x, y, layout["machines"][idx][2])

    if random.random() < mutation_rate:
        # Add a random belt
        x = random.randint(0, grid_width - 1)
        y = random.randint(0, grid_height - 1)
        layout["belts"].append((x, y))

    return layout

def run_generational_algorithm(population_size, generations, grid, base_resources, num_machines):
    """
    Run the generational algorithm to optimize a factory layout.
    """
    population = initialize_population(population_size, grid.width, grid.height, num_machines, base_resources)

    for generation in range(generations):
        logging.info(f"Generation {generation}")

        # Evaluate fitness
        for layout in population:
            evaluate_fitness(layout, grid)

        # Select top layouts
        top_layouts = select_top_layouts(population, top_n=population_size // 2)

        # Generate new population through crossover and mutation
        new_population = []
        for i in range(len(top_layouts) - 1):
            child = crossover(top_layouts[i], top_layouts[i + 1])
            child = mutate(child, mutation_rate=0.1, grid_width=grid.width, grid_height=grid.height)
            new_population.append(child)

        # Add top layouts to the next generation
        population = top_layouts + new_population

    # Return the best layout
    return select_top_layouts(population, top_n=1)[0]
