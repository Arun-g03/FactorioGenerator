"""Entity for Factorio blueprints.
    This class represents an entity in the Factorio blueprint.

"""
class Entity:
    def __init__(self, entity_number, name, position, direction=None, recipe=None, crafting_speed=None):
        self.entity_number = entity_number
        self.name = name
        self.position = position
        self.direction = direction
        self.recipe = recipe
        self.crafting_speed = crafting_speed

    def to_dict(self):
        entity_dict = {
            'entity_number': self.entity_number,
            'name': self.name,
            'position': self.position,
        }
        if self.direction is not None:
            entity_dict['direction'] = self.direction
        if self.recipe is not None:
            entity_dict['recipe'] = self.recipe
        if self.crafting_speed is not None:
            entity_dict['crafting_speed'] = self.crafting_speed
        return entity_dict
