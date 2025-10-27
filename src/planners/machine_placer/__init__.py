"""MachinePlacer module for placing machines and production lines in Factorio"""

from .production_line_map import ProductionLineMap
from .positioning import PositionFinder
from .calculations import ProductionCalculator
from .machine_placement import MachinePlacement
from .production_line_placement import ProductionLinePlacement


class MachinePlacer:
    """Main class for placing machines and production lines"""
    
    def __init__(self, grid, belt_router, inserter_placer, pathfinder, recipes_data):
        self.grid = grid
        self.belt_router = belt_router
        self.inserter_placer = inserter_placer
        self.pathfinder = pathfinder
        self.recipes_data = recipes_data
        self.already_placed = set()
        
        # Initialize modules
        self.production_map = ProductionLineMap()
        self.position_finder = PositionFinder(grid)
        self.production_calculator = ProductionCalculator(recipes_data)
        
        # Initialize specialized placement classes
        self.machine_placement = MachinePlacement(
            grid, belt_router, inserter_placer, pathfinder, 
            recipes_data, self.position_finder
        )
        
        self.production_line_placement = ProductionLinePlacement(
            grid, belt_router, inserter_placer, pathfinder, 
            recipes_data, self.position_finder, self.production_map, 
            self.production_calculator
        )
    
    # Delegate to machine_placement methods
    def place_machine(self, *args, **kwargs):
        return self.machine_placement.place_machine(*args, **kwargs)
    
    def place_cluster(self, *args, **kwargs):
        return self.machine_placement.place_cluster(*args, **kwargs)
    
    def place_machine_along_bus(self, *args, **kwargs):
        return self.machine_placement.place_machine_along_bus(*args, **kwargs)
    
    # Delegate to production_line_placement methods
    def place_production_line(self, *args, **kwargs):
        return self.production_line_placement.place_production_line(*args, **kwargs)
    
    def place_production_line_recursive(self, *args, **kwargs):
        return self.production_line_placement.place_production_line_recursive(*args, **kwargs)
    
    def place_compact_production_line(self, *args, **kwargs):
        return self.production_line_placement.place_compact_production_line(*args, **kwargs)
    
    def place_connected_production_line(self, *args, **kwargs):
        return self.production_line_placement.place_connected_production_line(*args, **kwargs)
    
    def place_connected_production_line_at_position(self, *args, **kwargs):
        return self.production_line_placement.place_connected_production_line_at_position(*args, **kwargs)
    
    def build_connected_production_line(self, *args, **kwargs):
        return self.production_line_placement.build_connected_production_line(*args, **kwargs)
    
    def place_base_resource_belt(self, *args, **kwargs):
        return self.production_line_placement.place_base_resource_belt(*args, **kwargs)
    
    def place_resource_bus(self, *args, **kwargs):
        return self.production_line_placement.place_resource_bus(*args, **kwargs)
    
    def place_multiple_production_lines(self, *args, **kwargs):
        return self.production_line_placement.place_multiple_production_lines(*args, **kwargs)
    
    # Utility methods
    def get_items_per_minute(self, recipe):
        return self.production_calculator.get_items_per_minute(recipe)
    
    def find_next_available_position(self, *args, **kwargs):
        return self.position_finder.find_next_available_position(*args, **kwargs)
    
    def find_next_available_position_with_spacing(self, *args, **kwargs):
        return self.position_finder.find_next_available_position_with_spacing(*args, **kwargs)
