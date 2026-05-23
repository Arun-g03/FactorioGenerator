import logging
from core.entity import Entity

class BeltRouter:
    def __init__(self, grid, pathfinder):
        self.grid = grid
        self.pathfinder = pathfinder

    def route_belt(self, entities, entity_number, start_x, start_y, end_x, end_y, resource):
        """
        Routes a belt from start to end position. Incorporates central positioning.
        """
        # If no specific start coordinates are given, use center
        if start_x is None or start_y is None:
            start_x = self.grid.width // 2
            start_y = self.grid.height // 2

        # If no specific end coordinates are given, adjust based on resource location
        if end_x is None or end_y is None:
            end_x = self.grid.width // 2 + 5
            end_y = self.grid.height // 2 + 5

        start = (start_x, start_y)
        end = (end_x, end_y)

        # Check if start and end positions are valid
        if self.grid.is_occupied(start[0], start[1]) or self.grid.is_occupied(end[0], end[1]):
            logging.warning(f"[BeltRouter] Invalid positions: start {start} or end {end} is occupied.")
            return entity_number

        path = self.pathfinder.shortest_path(start, end)
        if not path:
            logging.warning(f"[BeltRouter] Pathfinding failed for {resource} from {start} to {end}.")
            return entity_number

        # Place belts along the successful path
        for x, y in path:
            if not self.grid.is_occupied(x, y):
                entities.append({
                    "entity_number": entity_number,
                    "name": "transport-belt",
                    "position": {"x": x, "y": y}
                })
                self.grid.occupy(x, y, "transport-belt", [1, 1])
                entity_number += 1

        return entity_number




    def route_underground_pipe(self, entities, entity_number, start_x, start_y, end_x, end_y, resource, max_distance):
        distance = abs(end_x - start_x) if start_x != end_x else abs(end_y - start_y)
        if distance > max_distance:
            logging.error(f"Underground distance exceeds max distance ({max_distance})")
            return entity_number

        logging.info(f"Placing underground pipe from ({start_x}, {start_y}) to ({end_x}, {end_y})")

        entities.append(Entity(entity_number, "underground-pipe", {"x": start_x, "y": start_y}, direction=self.get_direction(start_x, start_y, end_x, end_y), underground_type="input").to_dict())
        self.grid.occupy(start_x, start_y, "underground-pipe", size=[1, 1])
        entity_number += 1

        entities.append(Entity(entity_number, "underground-pipe", {"x": end_x, "y": end_y}, direction=self.get_direction(start_x, start_y, end_x, end_y), underground_type="output").to_dict())
        self.grid.occupy(end_x, end_y, "underground-pipe", size=[1, 1])
        entity_number += 1

        return entity_number

    def get_direction(self, x, y, next_x, next_y):
        from core.constants import direction_for_flow
        return direction_for_flow((x, y), (next_x, next_y))

    def route_belt_with_splitters(self, entities, entity_number, start_x, start_y, end_x, end_y, resource, use_underground=False):
        """
        Routes a belt, using splitters and underground belts when necessary.
        """
        start = (start_x, start_y)
        end = (end_x, end_y)

        # Check if start and end positions are valid
        if self.grid.is_occupied(start[0], start[1]) or self.grid.is_occupied(end[0], end[1]):
            logging.error(f"One of the positions {start} or {end} is occupied.")
            return entity_number

        # Find the shortest path
        path = self.pathfinder.shortest_path(start, end)
        if not path:
            logging.error(f"Failed to find path for {resource} from {start} to {end}.")
            return entity_number

        # Place belts along the path
        for i, (x, y) in enumerate(path):
            if use_underground and i > 0 and i < len(path) - 1:
                # Place underground belt
                entities.append({
                    "entity_number": entity_number,
                    "name": "underground-belt",
                    "position": {"x": x, "y": y},
                    "direction": self.get_direction(path[i - 1], (x, y)),
                    "type": "input" if i == 1 else "output"
                })
            else:
                # Place regular transport belt
                entities.append({
                    "entity_number": entity_number,
                    "name": "transport-belt",
                    "position": {"x": x, "y": y}
                })

            self.grid.occupy(x, y, "transport-belt", [1, 1])
            entity_number += 1

        # Place splitters at the start and end
        entities.append({
            "entity_number": entity_number,
            "name": "splitter",
            "position": {"x": start_x, "y": start_y}
        })
        self.grid.occupy(start_x, start_y, "splitter", [1, 1])
        entity_number += 1

        entities.append({
            "entity_number": entity_number,
            "name": "splitter",
            "position": {"x": end_x, "y": end_y}
        })
        self.grid.occupy(end_x, end_y, "splitter", [1, 1])
        entity_number += 1

        return entity_number
