class ProductionLineMap:
    """
    A better representation of the production line structure that tracks:
    - What entities are where
    - How they're connected
    - What resources flow where
    - The logical structure of the production line
    """
    def __init__(self):
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
                print(f"Position ({x}, {y}) occupied by {entity['type']} (ID: {entity['id']})")
                return False
        return True
    
    def find_alternative_position(self, preferred_x, preferred_y, entity_type="entity", max_attempts=5):
        """Find an alternative position near the preferred position"""
        print(f"Looking for alternative position for {entity_type} near ({preferred_x}, {preferred_y})")
        
        # Try positions in a spiral pattern around the preferred position
        for radius in range(1, max_attempts + 1):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if abs(dx) == radius or abs(dy) == radius:  # Only check perimeter
                        new_x = preferred_x + dx
                        new_y = preferred_y + dy
                        if self.is_position_available(new_x, new_y, entity_type):
                            print(f"Found alternative position: ({new_x}, {new_y})")
                            return new_x, new_y
        
        print(f"No alternative position found for {entity_type}")
        return None, None
    
    def visualize_map(self):
        """Visualize the current production line map structure"""
        print("\n=== PRODUCTION LINE MAP ===")
        print(f"Total entities: {len(self.entities)}")
        print(f"Total stages: {len(self.production_stages)}")
        print(f"Resource flows: {list(self.resource_flows.keys())}")
        
        print("\n--- PRODUCTION STAGES ---")
        for i, stage in enumerate(self.production_stages):
            print(f"Stage {i+1}: {stage['type']} at {stage['position']}")
        
        print("\n--- ENTITY CONNECTIONS ---")
        for entity_id, connections in self.connections.items():
            entity = self.entities[entity_id]
            print(f"Entity {entity_id} ({entity['type']}) at {entity['position']} -> {connections}")
        
        print("\n--- RESOURCE FLOWS ---")
        for resource, entity_ids in self.resource_flows.items():
            print(f"{resource}: {entity_ids}")
        
        print("\n--- SPATIAL LAYOUT ---")
        self.print_spatial_layout()
        print("=" * 30)
    
    def print_spatial_layout(self):
        """Print a simple ASCII representation of the spatial layout"""
        # Find bounds
        if not self.entities:
            print("No entities placed yet")
            return
            
        min_x = min(entity['position'][0] for entity in self.entities.values())
        max_x = max(entity['position'][0] for entity in self.entities.values())
        min_y = min(entity['position'][1] for entity in self.entities.values())
        max_y = max(entity['position'][1] for entity in self.entities.values())
        
        print(f"Layout bounds: ({min_x}, {min_y}) to ({max_x}, {max_y})")
        
        # Create a simple grid representation
        for y in range(min_y, max_y + 1):
            row = f"Y{y:2d}: "
            for x in range(min_x, max_x + 1):
                # Find entity at this position
                entity_here = None
                for entity in self.entities.values():
                    if entity['position'] == (x, y):
                        entity_here = entity
                        break
                
                if entity_here:
                    if entity_here['type'] == 'machine':
                        row += "M"
                    elif entity_here['type'] == 'belt':
                        row += "B"
                    elif entity_here['type'] == 'inserter':
                        row += "I"
                    else:
                        row += "?"
                else:
                    row += "."
            print(row)
