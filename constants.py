
import matplotlib.pyplot as plt
PRODUCTION_TARGETS = {
   "iron-gear-wheel": 20  # Produce 60 gear wheels per minute
}

BASE_MATERIALS = {"iron-ore", "copper-ore", "coal", "water", "crude-oil", "stone"}

DIRECTIONS = {
    "north": None,  # No direction needed for North (upward)
    "east": 4,      # Right-facing
    "south": 8,     # Downward-facing
    "west": 12       # Left-facing
}



def plot_grid_state(grid, title="Grid State Debug"):
    """
    Visualize the current state of the grid using matplotlib.
    :param grid: The Grid instance to visualize.
    :param title: Title for the plot.
    """
    plt.figure(figsize=(10, 10))
    ax = plt.gca()

    # Iterate over occupied cells and color them based on entity type
    for (x, y), entity_name in grid.occupied.items():
        color = "gray"  # Default color for unknown entities
        if "machine" in entity_name:
            color = "blue"
        elif "inserter" in entity_name:
            color = "green"
        elif "belt" in entity_name:
            color = "yellow"
        elif "pipe" in entity_name:
            color = "red"
        elif "resource" in entity_name:
            color = "brown"

        ax.add_patch(plt.Rectangle((x, y), 1, 1, color=color))

    # Set grid limits and labels
    ax.set_xlim(0, grid.width)
    ax.set_ylim(0, grid.height)
    ax.set_aspect('equal', adjustable='box')
    plt.grid(True)
    plt.title(title)
    plt.xlabel("X-axis")
    plt.ylabel("Y-axis")
    plt.show()