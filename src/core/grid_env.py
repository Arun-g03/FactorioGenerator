"Defines the grid environment for the Factorio Blueprint Generator."

import logging

class Grid:
    
    def __init__(self, width=1000, height=1000):
        self.width = width
        self.height = height
        self.occupied = {}
        self.belt_lanes = {}


    def reset(self):
        logging.info("Resetting the grid...")
        self.occupied.clear()
        self.belt_lanes.clear()

    def is_occupied(self, x, y, width=1, height=1):
        for i in range(width):
            for j in range(height):
                if (x + i, y + j) in self.occupied:
                    return True
        return False

    def occupy(self, x_start, y_start, entity_name, size=[1,1]):
        width, height = size
        for dx in range(width):
            for dy in range(height):
                cell_x = x_start + dx
                cell_y = y_start + dy
                self.occupied[(cell_x, cell_y)] = entity_name

    def mark_resource_lane(self, x, y, resource):
        if (x, y) not in self.belt_lanes:
            self.belt_lanes[(x, y)] = [None, None]
        if self.belt_lanes[(x, y)][0] is None:
            self.belt_lanes[(x, y)][0] = resource
        elif self.belt_lanes[(x, y)][1] is None:
            self.belt_lanes[(x, y)][1] = resource
        else:
            logging.error(f"Belt at ({x}, {y}) is fully occupied.")
            return False
        return True

    def release(self, x, y):
        if (x, y) in self.occupied:
            logging.info(f"Releasing position ({x}, {y}) previously occupied by {self.occupied[(x, y)]}.")
            del self.occupied[(x, y)]

    