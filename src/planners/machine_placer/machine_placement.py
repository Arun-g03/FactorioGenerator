"""Machine placement methods"""

import logging


class MachinePlacement:
    """Methods for placing individual machines"""
    
    def __init__(self, grid, belt_router, inserter_placer, pathfinder, recipes_data, position_finder):
        self.grid = grid
        self.belt_router = belt_router
        self.inserter_placer = inserter_placer
        self.pathfinder = pathfinder
        self.recipes_data = recipes_data
        self.position_finder = position_finder

    def place_machine(self, entities, entity_number, target_item, x_start, y_start, attempt=0, max_attempts=10):
        """
        Places a single machine with recursive backtracking.
        Includes overlap detection at each step and retries alternate positions.
        """
        recipe = self.recipes_data["recipes"].get(target_item, {})
        machine_name = recipe.get("machine", "assembling-machine-1")
        w, h = recipe.get("machine_size", [1, 1])

        # Check for overlap of the machine
        if self.grid.is_occupied(x_start, y_start, w, h):
            if attempt >= max_attempts:
                logging.error(
                    f"[MachinePlacer] Max attempts reached: cannot place {machine_name} "
                    f"(size {w}x{h}) near ({x_start}, {y_start}). Backtracking."
                )
                return entity_number  # Backtrack or fail

            logging.warning(
                f"[MachinePlacer] Overlap detected: retrying {machine_name} placement near ({x_start}, {y_start})."
            )
            # Try an alternate nearby position
            offset = attempt + 1  # Increment offset with each attempt
            return self.place_machine(
                entities,
                entity_number,
                target_item,
                x_start + offset,
                y_start + offset,
                attempt=attempt + 1,
                max_attempts=max_attempts
            )

        # Place the machine if no overlap
        entities.append({
            "entity_number": entity_number,
            "name": machine_name,
            "position": {"x": x_start, "y": y_start},
            "recipe": target_item
        })
        self.grid.occupy(x_start, y_start, machine_name, [w, h])
        entity_number += 1

        # Place inserters with validation
        from core.constants import FACTORIO_EAST, FACTORIO_WEST

        directions = {
            "input": {"x_offset": -1, "y_offset": h // 2, "direction": FACTORIO_EAST},
            "output": {"x_offset": w, "y_offset": h // 2, "direction": FACTORIO_WEST},
        }

        for inserter_type, params in directions.items():
            inserter_x = x_start + params["x_offset"]
            inserter_y = y_start + params["y_offset"]

            # Validate inserter placement
            if self.grid.is_occupied(inserter_x, inserter_y):
                logging.warning(
                    f"[MachinePlacer] Overlap detected: cannot place {inserter_type} inserter "
                    f"at ({inserter_x}, {inserter_y}). Skipping."
                )
                continue

            entities.append({
                "entity_number": entity_number,
                "name": "inserter",
                "position": {"x": inserter_x, "y": inserter_y},
                "direction": params["direction"]
            })
            self.grid.occupy(inserter_x, inserter_y, "inserter", [1, 1])
            entity_number += 1

        return entity_number
    
    def place_cluster(self, entities, entity_number, target_item, x_start, y_start, cluster_size=3, spacing=5):
        """
        Example function to place a 'cluster' of machines.
        Each machine in the cluster has left/right inserters.
        """
        recipe = self.recipes_data["recipes"].get(target_item, {})
        w, h = recipe.get("machine_size", [1, 1])

        for i in range(cluster_size):
            mx = x_start + (i % cluster_size) * spacing
            my = y_start + (i // cluster_size) * spacing
            entity_number = self.place_machine(entities, entity_number, target_item, mx, my)

        self.pathfinder.update_graph()
        return entity_number
    
    def place_machine_along_bus(self, entities, entity_number, target_item, bus_x, bus_y, offset_x=5, machine_spacing=6):
        """
        Place a machine and connect it to the resource bus using inserters.
        """
        recipe = self.recipes_data["recipes"].get(target_item, {})
        machine_name = recipe.get("machine", "assembling-machine-1")
        w, h = recipe.get("machine_size", [3, 3])

        # Machine coordinates
        x_start = bus_x + offset_x
        y_start = bus_y

        # Place the machine
        entity_number = self.place_machine(entities, entity_number, target_item, x_start, y_start)

        # Add inserters for input/output
        inserter_positions = [
            {"x_offset": -1, "y_offset": h // 2},  # Input from bus
            {"x_offset": w, "y_offset": h // 2}   # Output to belt
        ]
        for pos in inserter_positions:
            inserter_x = x_start + pos["x_offset"]
            inserter_y = y_start + pos["y_offset"]
            entity_number = self.inserter_placer.place_inserter(
                entities,
                entity_number,
                inserter_x,
                inserter_y
            )

        return entity_number
