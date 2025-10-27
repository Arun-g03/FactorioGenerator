"""Position finding utilities for machine placement"""

import logging


class PositionFinder:
    """Utility class for finding available positions on the grid"""
    
    def __init__(self, grid):
        self.grid = grid
    
    def find_next_available_position_with_spacing(self, width, height):
        """
        Find the next available position for a machine with proper spacing.
        Layout: [3 input belts] [machine] [3 output belts]
        """
        # Start from a reasonable position (not at the very edge)
        start_x = 10
        start_y = 10
        
        # Search in a reasonable area
        for y in range(start_y, min(start_y + 50, self.grid.height - height)):
            for x in range(start_x, min(start_x + 50, self.grid.width - width)):
                # Check if the machine itself can be placed
                if not self.grid.is_occupied(x, y, width, height):
                    # Layout: [3 input belts] [machine] [3 output belts]
                    # Total width needed: 3 + width + 3 = 6 + width
                    total_width_needed = 6 + width
                    
                    # Check bounds
                    if x >= 3 and x + total_width_needed < self.grid.width:
                        # Check if the entire area is clear
                        clear = True
                        for check_x in range(x - 3, x + total_width_needed):
                            for check_y in range(y, y + height):
                                if self.grid.is_occupied(check_x, check_y):
                                    clear = False
                                    break
                            if not clear:
                                break
                        
                        if clear:
                            return x, y
        
        return None, None
    
    def find_next_available_position(self, width, height):
        """
        Find the next available position for a machine of given size.
        Uses a simple grid search starting from top-left.
        """
        # Start from a reasonable position (not at the very edge)
        start_x = 10
        start_y = 10
        
        # Search in a reasonable area
        for y in range(start_y, min(start_y + 50, self.grid.height - height)):
            for x in range(start_x, min(start_x + 50, self.grid.width - width)):
                if not self.grid.is_occupied(x, y, width, height):
                    return x, y
        
        return None, None
