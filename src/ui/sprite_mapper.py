import logging


class SpriteMapper:
    """
    Maps entity names and directions to sprite filenames.
    Handles directional variants for belts and inserters.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_sprite_name(self, entity_name, direction=None):
        from core.constants import BELT_ENTITIES, direction_sprite_suffix

        if entity_name in BELT_ENTITIES:
            suffix = direction_sprite_suffix(direction)
            return f"{entity_name}-{suffix}"

        if "underground-belt" in entity_name:
            return f"{entity_name}-structure"

        if "inserter" in entity_name:
            suffix = direction_sprite_suffix(direction)
            directional = f"{entity_name}-platform-{suffix}"
            if direction is not None:
                return directional
            return f"{entity_name}-platform"

        if "splitter" in entity_name:
            suffix = direction_sprite_suffix(direction)
            directional = f"{entity_name}-{suffix}"
            return directional

        if entity_name.startswith("pipe"):
            return entity_name

        if "pole" in entity_name:
            return entity_name

        return entity_name

    def get_pipe_sprite_for_connections(self, entity_name, connections):
        if not connections:
            return "pipe-straight-horizontal"

        up = connections.get("up", False)
        down = connections.get("down", False)
        left = connections.get("left", False)
        right = connections.get("right", False)

        count = sum([up, down, left, right])

        if count == 0:
            return "pipe-ending-down"
        if count == 1:
            if up:
                return "pipe-ending-up"
            if down:
                return "pipe-ending-down"
            if left:
                return "pipe-ending-left"
            if right:
                return "pipe-ending-right"
        if count == 2:
            if up and down:
                return "pipe-straight-vertical"
            if left and right:
                return "pipe-straight-horizontal"
            if up and left:
                return "pipe-corner-up-left"
            if up and right:
                return "pipe-corner-up-right"
            if down and left:
                return "pipe-corner-down-left"
            if down and right:
                return "pipe-corner-down-right"
        if count == 3:
            if up and down and left:
                return "pipe-t-left"
            if up and down and right:
                return "pipe-t-right"
            if up and left and right:
                return "pipe-t-up"
            if down and left and right:
                return "pipe-t-down"
        if count == 4:
            return "pipe-cross"

        return "pipe-straight-horizontal"
