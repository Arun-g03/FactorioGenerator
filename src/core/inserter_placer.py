import logging
from core.entity import Entity

class InserterPlacer:
    def __init__(self, grid):
        self.grid = grid

    def place_inserter(self, entities, entity_number, machine_x, machine_y, belt_x, belt_y):
        position = {"x": (machine_x + belt_x) / 2, "y": (machine_y + belt_y) / 2}
        entities.append(Entity(entity_number, "inserter", position).to_dict())
        return entity_number + 1


    def get_direction(self, source_x, source_y, target_x, target_y):
        """Determine direction based on source and target positions."""
        if source_x < target_x:
            return 2  # East
        elif source_x > target_x:
            return 6  # West
        elif source_y < target_y:
            return 4  # South
        elif source_y > target_y:
            return None  # North
        return None