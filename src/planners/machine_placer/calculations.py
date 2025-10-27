"""Calculation utilities for production rates"""

import logging


class ProductionCalculator:
    """Utility class for production calculations"""
    
    def __init__(self, recipes_data):
        self.recipes_data = recipes_data
    
    def get_items_per_minute(self, recipe):
        """
        Unified logic for machine throughput (items/min).
        """
        # e.g., oil-refinery with 'crafting_time' and 'machine_speed'
        if "crafting_time" in recipe and "machine_speed" in recipe:
            return 60.0 / (recipe["crafting_time"] / recipe["machine_speed"])

        # e.g., assembling-machine with 'crafting_speed' as items/sec
        if "crafting_speed" in recipe:
            return 60.0 * recipe["crafting_speed"]

        logging.warning("Recipe has no recognized crafting rate info.")
        return 0.0
