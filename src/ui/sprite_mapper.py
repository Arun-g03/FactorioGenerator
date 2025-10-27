import logging

class SpriteMapper:
    """
    Maps entity names and directions to sprite filenames.
    Handles directional variants and special cases.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Direction mapping: Factorio direction values to sprite suffixes
        self.direction_map = {
            None: "north",  # 0 or None = North
            2: "northeast",
            4: "east",
            6: "southeast",
            8: "south",
            10: "southwest",
            12: "west",
            14: "northwest"
        }
    
    def get_sprite_name(self, entity_name, direction=None):
        """
        Get the sprite name for an entity.
        
        Args:
            entity_name: Name of the entity (e.g., "transport-belt", "assembling-machine-1")
            direction: Direction value from entity (None, 4, 8, 12, etc.)
        
        Returns:
            Sprite name string (e.g., "transport-belt-east", "transport-belt-east-to-north")
        """
        # Handle transport belts - they have directional sprites extracted from sprite sheets
        if entity_name in ["transport-belt", "fast-transport-belt", "express-transport-belt"]:
            if direction is not None:
                dir_suffix = self._direction_to_belt_direction(direction)
                return f"{entity_name}-{dir_suffix}"
            return f"{entity_name}-east"  # Default direction
        
        # Handle splitters - they always use north sprite
        if "splitter" in entity_name:
            return f"{entity_name}-north"
        
        # Handle underground belts - they have "structure" sprite
        if "underground-belt" in entity_name:
            return f"{entity_name}-structure"
        
        # Handle inserters - use directional mapping
        if "inserter" in entity_name:
            if direction is not None:
                dir_suffix = self.direction_map.get(direction, "north")
                # Most inserters use "platform" suffix
                if "platform" not in entity_name:
                    return f"{entity_name}-platform"
                return entity_name
            return f"{entity_name}-platform"
        
        # Handle pipes - need special handling based on connections
        if entity_name.startswith("pipe"):
            return entity_name
        
        # Handle poles - use base name
        if "pole" in entity_name:
            return entity_name
        
        # For most other entities (machines, furnaces, etc.), return as-is
        return entity_name
    
    def _direction_to_belt_direction(self, direction):
        """
        Convert entity direction value to belt sprite direction name.
        
        Args:
            direction: Direction value (None, 4, 8, 12, etc.)
        
        Returns:
            Direction string (east, west, north, south, or corner variant)
        """
        # Simple direction mapping for now - just the 4 cardinal directions
        # TODO: Implement corner detection for belts that need corner sprites
        if direction is None:
            return "east"
        
        direction_map = {
            2: "north",      # 2 = northeast, but use north for straight
            4: "east",       # 4 = east
            6: "south",      # 6 = southeast, but use south for straight
            8: "south",      # 8 = south
            10: "west",      # 10 = southwest, but use west for straight
            12: "west",      # 12 = west
            14: "north",     # 14 = northwest, but use north for straight
        }
        
        return direction_map.get(direction, "east")
    
    def get_pipe_sprite_for_connections(self, entity_name, connections):
        """
        Get the correct pipe sprite based on connection pattern.
        
        Args:
            entity_name: Base pipe name
            connections: Dict with 'up', 'down', 'left', 'right' boolean values
        
        Returns:
            Sprite name string
        """
        if not connections:
            return "pipe-straight-horizontal"
        
        up = connections.get('up', False)
        down = connections.get('down', False)
        left = connections.get('left', False)
        right = connections.get('right', False)
        
        count = sum([up, down, left, right])
        
        if count == 0:
            return "pipe-ending-down"
        elif count == 1:
            if up:
                return "pipe-ending-up"
            elif down:
                return "pipe-ending-down"
            elif left:
                return "pipe-ending-left"
            elif right:
                return "pipe-ending-right"
        elif count == 2:
            # Straight pipes
            if (up and down):
                return "pipe-straight-vertical"
            elif (left and right):
                return "pipe-straight-horizontal"
            # Corner pipes
            elif (up and left):
                return "pipe-corner-up-left"
            elif (up and right):
                return "pipe-corner-up-right"
            elif (down and left):
                return "pipe-corner-down-left"
            elif (down and right):
                return "pipe-corner-down-right"
        elif count == 3:
            # T-junctions
            if (up and down and left):
                return "pipe-t-left"
            elif (up and down and right):
                return "pipe-t-right"
            elif (up and left and right):
                return "pipe-t-up"
            elif (down and left and right):
                return "pipe-t-down"
        elif count == 4:
            return "pipe-cross"
        
        # Fallback
        return "pipe-straight-horizontal"

