import logging

class LayoutOptimizer:
    def __init__(self, machine_placer, grid, belt_router, inserter_placer):
        self.machine_placer = machine_placer
        self.grid = grid
        self.belt_router = belt_router
        self.inserter_placer = inserter_placer
        self.best_layout_string = None
        self.best_blueprint = None

    def optimize_spacing(self, entities, entity_number, target_items):
        x_start, y_start = 10, 10
        max_row_width = 50
        cluster_spacing = 15

        for target_item in target_items:
            recipe = self.machine_placer.recipes_data["recipes"].get(target_item)
            machine_size = recipe.get("machine_size", [1, 1])  # Correct field name
            x_spacing, y_spacing = machine_size[0] + 2, machine_size[1] + 2

            if x_start + x_spacing > max_row_width:
                x_start = 10
                y_start += cluster_spacing

            entity_number = self.machine_placer.place_machine(entities, entity_number, target_item, x_start, y_start, x_spacing, y_spacing)
            x_start += x_spacing

        return entities





    def is_valid_layout(self, entities):
        """Check if the layout is valid (all machines connected, no overlaps)."""
        for entity in entities:
            x, y = entity["position"]["x"], entity["position"]["y"]
            size = entity.get("size", [1, 1])
            for i in range(size[0]):
                for j in range(size[1]):
                    if self.grid.is_occupied(x + i, y + j):
                        logging.error(f"Overlap detected at ({x + i}, {y + j}).")
                        return False
        return True

    def score_layout(self, entities):
        """Score the layout based on space used, number of belts/pipes, etc."""
        total_space_used = 0
        total_belts = sum(1 for e in entities if e["name"].startswith("transport-belt"))
        total_pipes = sum(1 for e in entities if e["name"].startswith("pipe"))

        for entity in entities:
            size = entity.get("size", [1, 1])
            total_space_used += size[0] * size[1]

        # Penalize excessive belts and pipes to encourage compact layouts
        score = total_space_used + (total_belts * 2) + (total_pipes * 3)
        return score

    def create_layout_string(self, entities):
        """Create a string representation of the layout."""
        layout_str = ""
        for entity in entities:
            layout_str += f"Entity {entity['name']} at ({entity['position']['x']}, {entity['position']['y']})\n"
        return layout_str
