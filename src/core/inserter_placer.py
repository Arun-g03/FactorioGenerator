"""Defines the inserter placer for the Factorio Blueprint Generator."""

import logging
from core.entity import Entity

class InserterPlacer:
    def __init__(self, grid):
        self.grid = grid

    def place_inserter(self, entities, entity_number, machine_x, machine_y, belt_x, belt_y):
        position = {"x": (machine_x + belt_x) / 2, "y": (machine_y + belt_y) / 2}
        entities.append(Entity(entity_number, "inserter", position).to_dict())
        return entity_number + 1


    def get_direction(self, inserter_x, inserter_y, drop_x, drop_y):
        """Blueprint direction: pickup side (tile the inserter pulls from)."""
        from core.constants import direction_for_inserter

        return direction_for_inserter((inserter_x, inserter_y), (drop_x, drop_y))
        return direction_for_inserter((inserter_x, inserter_y), (drop_x, drop_y))