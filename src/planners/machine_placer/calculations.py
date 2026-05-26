"""Calculation utilities for production rates"""

import logging
import math


def machine_entity_for_recipe(item: str, recipe: dict) -> str:
    """
    Entity to place when producing ``item``.

    Recipe ``machine`` may be null for buildings (e.g. assembling-machine-1);
    in that case the product name is the placed entity.
    """
    machine = recipe.get("machine")
    if machine:
        return machine
    return item


def entity_accepts_recipe_field(entity_name: str) -> bool:
    """True when a blueprint entity should include a ``recipe`` field."""
    if not entity_name:
        return False
    return entity_name.startswith("assembling-machine") or "furnace" in entity_name


class ProductionCalculator:
    """Utility class for production calculations (items per minute per machine)."""

    def __init__(self, recipes_data):
        self.recipes_data = recipes_data

    def get_items_per_minute(self, recipe):
        """
        Machine output in items/min for one machine running this recipe.

        Smelting: uses crafting_time (seconds per craft) and optional machine_speed.
        Assembling: uses crafting_speed as crafts per second when no crafting_time.
        """
        if "crafting_time" in recipe:
            craft_time = recipe["crafting_time"]
            machine_speed = recipe.get("machine_speed", 1.0)
            if craft_time <= 0 or machine_speed <= 0:
                logging.warning("Invalid smelting timing in recipe.")
                return 0.0
            effective_time = craft_time / machine_speed
            return 60.0 / effective_time

        if "crafting_speed" in recipe:
            return 60.0 * recipe["crafting_speed"]

        logging.warning("Recipe has no recognized crafting rate info.")
        return 0.0

    def machines_needed(self, recipe, target_rate):
        """Number of machines required to meet target_rate (items/min)."""
        per_machine = self.get_items_per_minute(recipe)
        if per_machine <= 0:
            return 1
        return max(1, math.ceil(target_rate / per_machine))

    def achieved_rate(self, recipe, machine_count):
        """Items/min produced by machine_count machines."""
        return self.get_items_per_minute(recipe) * machine_count
