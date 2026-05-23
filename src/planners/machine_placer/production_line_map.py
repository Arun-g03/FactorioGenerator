import logging


class ProductionLineMap:
    """
    A better representation of the production line structure that tracks:
    - What entities are where
    - How they're connected
    - What resources flow where
    - The logical structure of the production line
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.entities = {}  # entity_id -> entity_data
        self.connections = {}  # entity_id -> [connected_entity_ids]
        self.resource_flows = {}  # resource_name -> [entity_ids that produce/consume it]
        self.production_stages = []  # List of production stages in order
        self.next_entity_id = 1
        self.next_stage_id = 1
        
    def add_entity(self, entity_type, position, properties=None):
        """Add an entity to the map and return its ID"""
        entity_id = self.next_entity_id
        self.next_entity_id += 1
        
        entity_data = {
            'id': entity_id,
            'type': entity_type,
            'position': position,
            'properties': properties or {}
        }
        
        self.entities[entity_id] = entity_data
        return entity_id
    
    def connect_entities(self, from_entity_id, to_entity_id, resource_type=None):
        """Connect two entities and track resource flow"""
        if from_entity_id not in self.connections:
            self.connections[from_entity_id] = []
        self.connections[from_entity_id].append(to_entity_id)
        
        if resource_type:
            if resource_type not in self.resource_flows:
                self.resource_flows[resource_type] = []
            self.resource_flows[resource_type].extend([from_entity_id, to_entity_id])
    
    def add_production_stage(self, stage_type, position, recipe=None):
        """Add a production stage (machine + its input/output)"""
        stage_id = self.next_stage_id
        self.next_stage_id += 1
        
        stage_data = {
            'id': stage_id,
            'type': stage_type,
            'position': position,
            'recipe': recipe,
            'entities': []
        }
        
        self.production_stages.append(stage_data)
        return stage_id
    
    def get_available_position_for_stage(self, stage_type, preferred_x=None, preferred_y=None):
        """Find the best position for a new production stage"""
        if preferred_x is not None and preferred_y is not None:
            return preferred_x, preferred_y
            
        # Simple positioning logic - place stages in a line
        base_x = 10
        base_y = 15
        spacing = 15
        
        x = base_x + (len(self.production_stages) * spacing)
        y = base_y
        return x, y
    
    def get_stage_output_position(self, stage_id):
        """Get the output position of a specific stage"""
        stage = self.production_stages[stage_id - 1]  # stages are 1-indexed
        return stage['position']
    
    def is_position_available(self, x, y, entity_type="entity"):
        """Check if a position is available for placing an entity"""
        # Check if any existing entity is at this position
        for entity in self.entities.values():
            if entity['position'] == (x, y):
                self.logger.debug(
                    "Position (%s, %s) occupied by %s (ID: %s)",
                    x, y, entity['type'], entity['id'],
                )
                return False
        return True
    
    def find_alternative_position(self, preferred_x, preferred_y, entity_type="entity", max_attempts=5):
        """Find an alternative position near the preferred position"""
        self.logger.debug(
            "Looking for alternative position for %s near (%s, %s)",
            entity_type, preferred_x, preferred_y,
        )
        
        # Try positions in a spiral pattern around the preferred position
        for radius in range(1, max_attempts + 1):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if abs(dx) == radius or abs(dy) == radius:  # Only check perimeter
                        new_x = preferred_x + dx
                        new_y = preferred_y + dy
                        if self.is_position_available(new_x, new_y, entity_type):
                            self.logger.debug("Found alternative position: (%s, %s)", new_x, new_y)
                            return new_x, new_y
        
        self.logger.warning("No alternative position found for %s", entity_type)
        return None, None
    
    def visualize_map(self):
        """Log the current production line map structure (generation stage summary)."""
        self.logger.info("=== PRODUCTION LINE MAP ===")
        self.logger.info("Total entities: %s", len(self.entities))
        self.logger.info("Total stages: %s", len(self.production_stages))
        self.logger.info("Resource flows: %s", list(self.resource_flows.keys()))

        for i, stage in enumerate(self.production_stages):
            self.logger.info(
                "Stage %s: %s at %s",
                i + 1, stage['type'], stage['position'],
            )

        for entity_id, connections in self.connections.items():
            entity = self.entities[entity_id]
            self.logger.debug(
                "Entity %s (%s) at %s -> %s",
                entity_id, entity['type'], entity['position'], connections,
            )

        for resource, entity_ids in self.resource_flows.items():
            self.logger.debug("Flow %s: %s", resource, entity_ids)

        self._log_spatial_layout()
    
    def _log_spatial_layout(self):
        """Log a simple ASCII representation of the spatial layout."""
        if not self.entities:
            self.logger.info("Spatial layout: no entities placed yet")
            return

        min_x = min(entity['position'][0] for entity in self.entities.values())
        max_x = max(entity['position'][0] for entity in self.entities.values())
        min_y = min(entity['position'][1] for entity in self.entities.values())
        max_y = max(entity['position'][1] for entity in self.entities.values())
        self.logger.info("Layout bounds: (%s, %s) to (%s, %s)", min_x, min_y, max_x, max_y)

        for y in range(min_y, max_y + 1):
            row = f"Y{y:2d}: "
            for x in range(min_x, max_x + 1):
                entity_here = next(
                    (e for e in self.entities.values() if e['position'] == (x, y)),
                    None,
                )
                if entity_here:
                    row += {"machine": "M", "belt": "B", "inserter": "I"}.get(
                        entity_here['type'], "?"
                    )
                else:
                    row += "."
            self.logger.info(row)
    
    def print_spatial_layout(self):
        """Backward-compatible alias for console debugging."""
        self._log_spatial_layout()
