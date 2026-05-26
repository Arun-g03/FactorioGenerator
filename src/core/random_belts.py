"""Defines the random belt placer for the Factorio Blueprint Generator."""

import random
import logging
import json
from core.blueprintEncoder import encode_blueprint

class ContinuousBeltPlacer:
    def __init__(self, recipes_file, grid_width=20, grid_height=20):
        self.grid_width = grid_width
        self.grid_height = grid_height
        self.grid = [[0 for _ in range(grid_width)] for _ in range(grid_height)]
        self.belt_positions = []

        # Load recipes
        with open(recipes_file, 'r') as f:
            self.recipes = json.load(f)["recipes"]

    def is_within_bounds(self, x, y):
        return 0 <= x < self.grid_width and 0 <= y < self.grid_height

    def is_occupied(self, x, y):
        return self.grid[y][x] == 1

    def add_belt_segment(self, x, y):
        if not self.is_within_bounds(x, y) or self.is_occupied(x, y):
            return False

        self.grid[y][x] = 1
        self.belt_positions.append((x, y))
        return True

    def get_neighbors(self, x, y):
        neighbors = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        return [(nx, ny) for nx, ny in neighbors if self.is_within_bounds(nx, ny)]

    def find_closest_belt(self, x, y):
        visited = set()
        queue = [(x, y, [])]

        while queue:
            cx, cy, path = queue.pop(0)
            if (cx, cy) in visited:
                continue

            visited.add((cx, cy))

            if self.is_occupied(cx, cy):
                return path + [(cx, cy)]

            for nx, ny in self.get_neighbors(cx, cy):
                if (nx, ny) not in visited:
                    queue.append((nx, ny, path + [(cx, cy)]))

        return []

    def place_random_belt(self):
        while True:
            x, y = random.randint(0, self.grid_width - 1), random.randint(0, self.grid_height - 1)

            if not self.belt_positions:
                # Place the first belt randomly
                self.add_belt_segment(x, y)
                logging.info(f"Placed first belt at ({x}, {y})")
                return

            # Find the closest existing belt
            path = self.find_closest_belt(x, y)

            if path:
                for px, py in path:
                    self.add_belt_segment(px, py)

                logging.info(f"Added belt path: {path}")
                return

    def create_belt_entities(self):
        entities = []
        entity_number = 1
        belt_name = "transport-belt"  # Default belt type

        # Use the recipe data to get belt info
        if "transport-belt" in self.recipes:
            belt_name = self.recipes["transport-belt"].get("machine", "transport-belt")

        for x, y in self.belt_positions:
            entities.append({
                "entity_number": entity_number,
                "name": belt_name,
                "position": {"x": x, "y": y}
            })
            entity_number += 1

        return entities

    def generate_blueprint(self):
        entities = self.create_belt_entities()
        blueprint = {
            "blueprint": {
                "icons": [{"signal": {"name": "transport-belt"}, "index": 1}],
                "entities": entities,
                "item": "blueprint",
                "version": 562949958402048
            }
        }
        return encode_blueprint(blueprint)

    def display_grid(self):
        print("\n".join(
            "".join("#" if cell == 1 else "." for cell in row)
            for row in self.grid
        ))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    recipes_file = "recipes.json"  # Path to the recipes file
    placer = ContinuousBeltPlacer(recipes_file, grid_width=10, grid_height=10)

    # Place 10 belts randomly
    for _ in range(10):
        placer.place_random_belt()

    print("Final Belt Layout:")
    placer.display_grid()

    blueprint_string = placer.generate_blueprint()
    print("Generated Blueprint String:")
    print(blueprint_string)
