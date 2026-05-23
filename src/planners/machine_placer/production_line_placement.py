"""Production line placement methods"""

import logging
import math
from core.constants import BASE_MATERIALS


class ProductionLinePlacement:
    """Methods for placing complete production lines"""
    
    def __init__(self, grid, belt_router, inserter_placer, pathfinder, recipes_data, 
                 position_finder, production_map, production_calculator):
        self.grid = grid
        self.belt_router = belt_router
        self.inserter_placer = inserter_placer
        self.pathfinder = pathfinder
        self.recipes_data = recipes_data
        self.position_finder = position_finder
        self.production_map = production_map
        self.production_calculator = production_calculator
        self.already_placed = set()

    def place_production_line(self, entities, entity_number, target_item, target_rate):
        """
        Places enough machines (and belts) to produce target_item
        at 'target_rate' items per minute.
        """
        recipe = self.recipes_data["recipes"].get(target_item, {})
        if not recipe:
            logging.error(f"No recipe found for {target_item}. Skipping placement.")
            return entity_number

        # Calculate how many items/min one machine can produce
        items_per_minute_per_machine = self.production_calculator.get_items_per_minute(recipe)
        if items_per_minute_per_machine <= 0:
            logging.error(f"Invalid production rate for {target_item}.")
            return entity_number

        # Determine how many machines are required
        num_machines = math.ceil(target_rate / items_per_minute_per_machine)
        logging.info(f"{target_item}: needing {num_machines} machine(s) to meet {target_rate} items/min")

        # Start from the center of the grid
        x_start = self.grid.width // 2
        y_start = self.grid.height // 2
        w, h = recipe.get("machine_size", [3, 3])  # fallback if missing

        for i in range(num_machines):
            # Route input belts for each ingredient
            inputs = recipe.get("ingredients", {})
            for input_resource in inputs.keys():
                bus_x = x_start - 5  # Example offset for input resources
                bus_y = y_start - (i * 2)  # Adjusted offset
                inserter_in_x = x_start - 1
                inserter_in_y = y_start + (h // 2)

                entity_number = self.belt_router.route_belt(
                    entities,
                    entity_number,
                    start_x=bus_x,
                    start_y=bus_y,
                    end_x=inserter_in_x,
                    end_y=inserter_in_y,
                    resource=input_resource
                )

            # Route the output belt to collect the finished product
            out_belt_start_x = x_start + w
            out_belt_start_y = y_start + (h // 2)
            out_belt_end_x = out_belt_start_x + 5
            out_belt_end_y = out_belt_start_y

            entity_number = self.belt_router.route_belt(
                entities,
                entity_number,
                start_x=out_belt_start_x,
                start_y=out_belt_start_y,
                end_x=out_belt_end_x,
                end_y=out_belt_end_y,
                resource=target_item
            )

            # Move horizontally to place the next machine
            x_start += (w + 6)

        # Update graph after placements
        self.pathfinder.update_graph()
        return entity_number
    
    def place_production_line_recursive(self, entities, entity_number, item_name, item_rate):
        """
        Recursively places production lines starting from the last machine and working backwards.
        """
        # Check if the item is already placed to avoid redundancy
        if item_name in self.already_placed:
            logging.info(f"{item_name} is already placed, skipping.")
            return entity_number

        # If the item is a base resource, only place an input belt
        if item_name in BASE_MATERIALS:
            logging.info(f"{item_name} is a base resource. Placing input belt only.")
            entity_number = self.place_base_resource_belt(entities, entity_number, item_name)
            self.already_placed.add(item_name)
            return entity_number

        # Fetch the recipe for the given item
        recipe = self.recipes_data["recipes"].get(item_name)
        if not recipe:
            logging.error(f"No recipe for {item_name}, cannot place.")
            return entity_number

        # Recursively place production lines for each ingredient in the recipe
        ingredients = recipe.get("ingredients", {})
        for ingredient, amount_per_item in ingredients.items():
            required_rate = item_rate * amount_per_item
            entity_number = self.place_production_line_recursive(entities, entity_number, ingredient, required_rate)

        # Place the production line for the current item
        entity_number = self.place_connected_production_line(entities, entity_number, item_name, item_rate)

        # Mark the item as placed to prevent redundant placements
        self.already_placed.add(item_name)
        return entity_number

    def place_compact_production_line(self, entities, entity_number, item_name, item_rate):
        """
        Place a compact, properly connected production line for a single item.
        Creates a layout like: [Input Belt] -> [Inserter] -> [Machine] -> [Inserter] -> [Output Belt]
        """
        recipe = self.recipes_data["recipes"].get(item_name, {})
        machine_name = recipe.get("machine", "assembling-machine-1")
        w, h = recipe.get("machine_size", [3, 3])
        
        # Find a good position for this production line with proper spacing
        x_start, y_start = self.position_finder.find_next_available_position_with_spacing(w, h)
        if x_start is None:
            logging.error(f"No available position for {item_name}")
            return entity_number
            
        logging.info(f"Placing {item_name} production line at ({x_start}, {y_start})")
        
        # Place the machine
        entities.append({
            "entity_number": entity_number,
            "name": machine_name,
            "position": {"x": x_start, "y": y_start},
            "recipe": item_name
        })
        self.grid.occupy(x_start, y_start, machine_name, [w, h])
        entity_number += 1
        
        # Place input belt (left side of machine) - 3 belts long, flowing right
        input_belt_x = x_start - 4  # Start further left to avoid overlap
        input_belt_y = y_start + h // 2
        
        # Create input belt line flowing right (direction 2)
        for i in range(3):
            belt_x = input_belt_x + i
            if not self.grid.is_occupied(belt_x, input_belt_y):
                entities.append({
                    "entity_number": entity_number,
                    "name": "transport-belt",
                    "position": {"x": belt_x, "y": input_belt_y},
                    "direction": 4  # East (flowing right)
                })
                self.grid.occupy(belt_x, input_belt_y, "transport-belt", [1, 1])
                entity_number += 1
        
        # Place input inserter (between belt and machine)
        inserter_x = x_start - 1
        inserter_y = y_start + h // 2
        if not self.grid.is_occupied(inserter_x, inserter_y):
            entities.append({
                "entity_number": entity_number,
                "name": "inserter",
                "position": {"x": inserter_x, "y": inserter_y},
                "direction": 4  # East (facing machine)
            })
            self.grid.occupy(inserter_x, inserter_y, "inserter", [1, 1])
            entity_number += 1
        
        # Place output belt (right side of machine) - 3 belts long, flowing right
        output_belt_x = x_start + w + 1  # Start after the machine + 1 space
        output_belt_y = y_start + h // 2
        
        # Create output belt line flowing right (direction 2)
        for i in range(3):
            belt_x = output_belt_x + i
            if not self.grid.is_occupied(belt_x, output_belt_y):
                entities.append({
                    "entity_number": entity_number,
                    "name": "transport-belt",
                    "position": {"x": belt_x, "y": output_belt_y},
                    "direction": 4  # East (flowing right)
                })
                self.grid.occupy(belt_x, output_belt_y, "transport-belt", [1, 1])
                entity_number += 1
        
        # Place output inserter (between machine and belt)
        output_inserter_x = x_start + w
        output_inserter_y = y_start + h // 2
        if not self.grid.is_occupied(output_inserter_x, output_inserter_y):
            entities.append({
                "entity_number": entity_number,
                "name": "inserter",
                "position": {"x": output_inserter_x, "y": output_inserter_y},
                "direction": 4  # East (facing away from machine, toward output belt)
            })
            self.grid.occupy(output_inserter_x, output_inserter_y, "inserter", [1, 1])
            entity_number += 1
        
        return entity_number

    def place_connected_production_line(self, entities, entity_number, item_name, item_rate):
        """
        Place a production line with CORRECT Factorio mechanics.
        Layout: [Input Belt] -> [Inserter at belt end] -> [Machine] -> [Inserter at belt start] -> [Output Belt]
        """
        recipe = self.recipes_data["recipes"].get(item_name, {})
        machine_name = recipe.get("machine", "assembling-machine-1")
        w, h = recipe.get("machine_size", [3, 3])
        
        # Find position for this production line
        x_start, y_start = self.position_finder.find_next_available_position_with_spacing(w, h)
        if x_start is None:
            logging.error(f"No available position for {item_name}")
            return entity_number
            
        logging.info(f"Placing {item_name} production line at ({x_start}, {y_start})")
        
        # Place the machine
        entities.append({
            "entity_number": entity_number,
            "name": machine_name,
            "position": {"x": x_start, "y": y_start},
            "recipe": item_name
        })
        self.grid.occupy(x_start, y_start, machine_name, [w, h])
        entity_number += 1
        
        # Create input belt line (horizontal, flowing right)
        input_belt_x = x_start - 3
        input_belt_y = y_start + h // 2
        
        # Place input belts
        for i in range(3):
            belt_x = input_belt_x + i
            if not self.grid.is_occupied(belt_x, input_belt_y):
                entities.append({
                    "entity_number": entity_number,
                    "name": "transport-belt",
                    "position": {"x": belt_x, "y": input_belt_y},
                    "direction": 4  # East (flowing right)
                })
                self.grid.occupy(belt_x, input_belt_y, "transport-belt", [1, 1])
                entity_number += 1
        
        # Place input inserter at the END of the input belt (correct Factorio mechanics)
        inserter_x = input_belt_x + 2  # End of the belt
        inserter_y = input_belt_y
        if not self.grid.is_occupied(inserter_x, inserter_y):
            entities.append({
                "entity_number": entity_number,
                "name": "inserter",
                "position": {"x": inserter_x, "y": inserter_y},
                "direction": 4  # East (facing right toward machine)
            })
            self.grid.occupy(inserter_x, inserter_y, "inserter", [1, 1])
            entity_number += 1
        
        # Create output belt line (horizontal, flowing right)
        output_belt_x = x_start + w + 1
        output_belt_y = y_start + h // 2
        
        # Place output belts
        for i in range(3):
            belt_x = output_belt_x + i
            if not self.grid.is_occupied(belt_x, output_belt_y):
                entities.append({
                    "entity_number": entity_number,
                    "name": "transport-belt",
                    "position": {"x": belt_x, "y": output_belt_y},
                    "direction": 4  # East (flowing right)
                })
                self.grid.occupy(belt_x, output_belt_y, "transport-belt", [1, 1])
                entity_number += 1
        
        # Place output inserter at the START of the output belt (correct Factorio mechanics)
        output_inserter_x = output_belt_x
        output_inserter_y = output_belt_y
        if not self.grid.is_occupied(output_inserter_x, output_inserter_y):
            entities.append({
                "entity_number": entity_number,
                "name": "inserter",
                "position": {"x": output_inserter_x, "y": output_inserter_y},
                "direction": 4  # East (facing right toward output belt)
            })
            self.grid.occupy(output_inserter_x, output_inserter_y, "inserter", [1, 1])
            entity_number += 1
        
        return entity_number

    def place_connected_production_line_at_position(self, entities, entity_number, item_name, item_rate, x_start, y_start):
        """
        Place a production line at a specific position with proper connections.
        """
        recipe = self.recipes_data["recipes"].get(item_name, {})
        machine_name = recipe.get("machine", "assembling-machine-1")
        w, h = recipe.get("machine_size", [3, 3])
        
        logging.info(f"Placing {item_name} production line at ({x_start}, {y_start})")
        
        # Place the machine
        entities.append({
            "entity_number": entity_number,
            "name": machine_name,
            "position": {"x": x_start, "y": y_start},
            "recipe": item_name
        })
        self.grid.occupy(x_start, y_start, machine_name, [w, h])
        entity_number += 1
        
        # Create input belt line (horizontal, flowing right)
        input_belt_x = x_start - 3
        input_belt_y = y_start + h // 2
        
        # Place input belts
        for i in range(3):
            belt_x = input_belt_x + i
            if not self.grid.is_occupied(belt_x, input_belt_y):
                entities.append({
                    "entity_number": entity_number,
                    "name": "transport-belt",
                    "position": {"x": belt_x, "y": input_belt_y},
                    "direction": 4  # East (flowing right)
                })
                self.grid.occupy(belt_x, input_belt_y, "transport-belt", [1, 1])
                entity_number += 1
        
        # Place input inserter at the END of the input belt
        inserter_x = input_belt_x + 2  # End of the belt
        inserter_y = input_belt_y
        if not self.grid.is_occupied(inserter_x, inserter_y):
            entities.append({
                "entity_number": entity_number,
                "name": "inserter",
                "position": {"x": inserter_x, "y": inserter_y},
                "direction": 4  # East (facing right toward machine)
            })
            self.grid.occupy(inserter_x, inserter_y, "inserter", [1, 1])
            entity_number += 1
        
        # Create output belt line (horizontal, flowing right)
        output_belt_x = x_start + w + 1
        output_belt_y = y_start + h // 2
        
        # Place output belts
        for i in range(3):
            belt_x = output_belt_x + i
            if not self.grid.is_occupied(belt_x, output_belt_y):
                entities.append({
                    "entity_number": entity_number,
                    "name": "transport-belt",
                    "position": {"x": belt_x, "y": output_belt_y},
                    "direction": 4  # East (flowing right)
                })
                self.grid.occupy(belt_x, output_belt_y, "transport-belt", [1, 1])
                entity_number += 1
        
        # Place output inserter at the START of the output belt
        output_inserter_x = output_belt_x
        output_inserter_y = output_belt_y
        if not self.grid.is_occupied(output_inserter_x, output_inserter_y):
            entities.append({
                "entity_number": entity_number,
                "name": "inserter",
                "position": {"x": output_inserter_x, "y": output_inserter_y},
                "direction": 4  # East (facing right toward output belt)
            })
            self.grid.occupy(output_inserter_x, output_inserter_y, "inserter", [1, 1])
            entity_number += 1
        
        return entity_number

    def build_connected_production_line(self, entities, entity_number, target_item, target_rate):
        """
        Build a properly connected production line using the ProductionLineMap.
        This method understands the structure and creates proper connections.
        """
        recipe = self.recipes_data["recipes"].get(target_item, {})
        machine_name = recipe.get("machine", "assembling-machine-1")
        w, h = recipe.get("machine_size", [3, 3])
        
        # Get position for this production stage
        x_start, y_start = self.production_map.get_available_position_for_stage(target_item)
        
        logging.info(f"Building connected production line for {target_item} at ({x_start}, {y_start})")
        
        # Add this as a production stage
        stage_id = self.production_map.add_production_stage(target_item, (x_start, y_start), recipe)
        
        # Place the machine
        machine_entity = {
            "entity_number": entity_number,
            "name": machine_name,
            "position": {"x": x_start, "y": y_start},
            "recipe": target_item
        }
        entities.append(machine_entity)
        self.grid.occupy(x_start, y_start, machine_name, [w, h])
        entity_number += 1
        
        # Add machine to production map
        machine_id = self.production_map.add_entity("machine", (x_start, y_start), {"recipe": target_item})
        
        # Create input system with proper spacing
        input_belt_x = x_start - 3
        input_belt_y = y_start + h // 2
        
        # Place input belts
        input_belt_ids = []
        for i in range(3):
            belt_x = input_belt_x + i
            belt_entity = {
                "entity_number": entity_number,
                "name": "transport-belt",
                "position": {"x": belt_x, "y": input_belt_y},
                "direction": 4  # East (flowing right)
            }
            entities.append(belt_entity)
            self.grid.occupy(belt_x, input_belt_y, "transport-belt", [1, 1])
            entity_number += 1
            
            # Add to production map
            belt_id = self.production_map.add_entity("belt", (belt_x, input_belt_y), {"direction": 4})
            input_belt_ids.append(belt_id)
        
        # Place input inserter with proper spacing
        inserter_x = input_belt_x + 2  # End of the belt
        inserter_y = input_belt_y
        print(f"Trying to place input inserter at ({inserter_x}, {inserter_y})")
        
        # Check if position is available using ProductionLineMap
        if self.production_map.is_position_available(inserter_x, inserter_y, "inserter"):
            inserter_entity = {
                "entity_number": entity_number,
                "name": "inserter",
                "position": {"x": inserter_x, "y": inserter_y},
                "direction": 4  # East (facing right toward machine)
            }
            entities.append(inserter_entity)
            self.grid.occupy(inserter_x, inserter_y, "inserter", [1, 1])
            entity_number += 1
            
            # Add to production map
            inserter_id = self.production_map.add_entity("inserter", (inserter_x, inserter_y), {"direction": 4})
            print(f"Placed input inserter with ID {inserter_id}")
        else:
            print(f"Input inserter position ({inserter_x}, {inserter_y}) is occupied!")
            # Try alternative position using ProductionLineMap
            alt_x, alt_y = self.production_map.find_alternative_position(inserter_x, inserter_y, "inserter")
            if alt_x is not None and alt_y is not None:
                inserter_entity = {
                    "entity_number": entity_number,
                    "name": "inserter",
                    "position": {"x": alt_x, "y": alt_y},
                    "direction": 4
                }
                entities.append(inserter_entity)
                self.grid.occupy(alt_x, alt_y, "inserter", [1, 1])
                entity_number += 1
                inserter_id = self.production_map.add_entity("inserter", (alt_x, alt_y), {"direction": 4})
                print(f"Placed input inserter at alternative position ({alt_x}, {alt_y}) with ID {inserter_id}")
            else:
                print("No available position for input inserter!")
                inserter_id = None
        
        # Create output system
        output_belt_x = x_start + w + 1
        output_belt_y = y_start + h // 2
        
        # Place output belts
        output_belt_ids = []
        for i in range(3):
            belt_x = output_belt_x + i
            belt_entity = {
                "entity_number": entity_number,
                "name": "transport-belt",
                "position": {"x": belt_x, "y": output_belt_y},
                "direction": 4  # East (flowing right)
            }
            entities.append(belt_entity)
            self.grid.occupy(belt_x, output_belt_y, "transport-belt", [1, 1])
            entity_number += 1
            
            # Add to production map
            belt_id = self.production_map.add_entity("belt", (belt_x, output_belt_y), {"direction": 4})
            output_belt_ids.append(belt_id)
        
        # Place output inserter
        output_inserter_x = output_belt_x
        output_inserter_y = output_belt_y
        print(f"Trying to place output inserter at ({output_inserter_x}, {output_inserter_y})")
        if self.production_map.is_position_available(output_inserter_x, output_inserter_y, "inserter"):
            output_inserter_entity = {
                "entity_number": entity_number,
                "name": "inserter",
                "position": {"x": output_inserter_x, "y": output_inserter_y},
                "direction": 4  # East (facing right toward output belt)
            }
            entities.append(output_inserter_entity)
            self.grid.occupy(output_inserter_x, output_inserter_y, "inserter", [1, 1])
            entity_number += 1
            
            # Add to production map
            output_inserter_id = self.production_map.add_entity("inserter", (output_inserter_x, output_inserter_y), {"direction": 4})
            print(f"Placed output inserter with ID {output_inserter_id}")
        else:
            print(f"Output inserter position ({output_inserter_x}, {output_inserter_y}) is occupied!")
            # Try alternative position using ProductionLineMap
            alt_x, alt_y = self.production_map.find_alternative_position(output_inserter_x, output_inserter_y, "inserter")
            if alt_x is not None and alt_y is not None:
                output_inserter_entity = {
                    "entity_number": entity_number,
                    "name": "inserter",
                    "position": {"x": alt_x, "y": alt_y},
                    "direction": 4
                }
                entities.append(output_inserter_entity)
                self.grid.occupy(alt_x, alt_y, "inserter", [1, 1])
                entity_number += 1
                output_inserter_id = self.production_map.add_entity("inserter", (alt_x, alt_y), {"direction": 4})
                print(f"Placed output inserter at alternative position ({alt_x}, {alt_y}) with ID {output_inserter_id}")
            else:
                print("No available position for output inserter!")
                output_inserter_id = None
        
        # Connect input belts to inserter
        if input_belt_ids and inserter_id is not None:
            for belt_id in input_belt_ids:
                self.production_map.connect_entities(belt_id, inserter_id, target_item)
                print(f"Connected belt {belt_id} to inserter {inserter_id} for {target_item}")
        
        # Connect output inserter to output belts
        if output_belt_ids and output_inserter_id is not None:
            for belt_id in output_belt_ids:
                self.production_map.connect_entities(output_inserter_id, belt_id, target_item)
                print(f"Connected output inserter {output_inserter_id} to belt {belt_id} for {target_item}")
        
        # Connect input inserter to machine
        if inserter_id is not None:
            self.production_map.connect_entities(inserter_id, machine_id, target_item)
            print(f"Connected inserter {inserter_id} to machine {machine_id} for {target_item}")
        
        # Connect machine to output inserter
        if output_inserter_id is not None:
            self.production_map.connect_entities(machine_id, output_inserter_id, target_item)
            print(f"Connected machine {machine_id} to output inserter {output_inserter_id} for {target_item}")
        
        return entity_number

    def place_base_resource_belt(self, entities, entity_number, resource_name):
        """
        Place input belts for base resources at the top of the layout.
        """
        logging.info(f"Placing input belt for base resource: {resource_name}")
        
        # Place input belts at the top of the layout, avoiding conflicts
        belt_y = 5
        belt_x_start = 5
        
        # Create a horizontal input belt line flowing right (direction 2)
        for i in range(15):
            belt_x = belt_x_start + i
            if not self.grid.is_occupied(belt_x, belt_y):
                entities.append({
                    "entity_number": entity_number,
                    "name": "transport-belt",
                    "position": {"x": belt_x, "y": belt_y},
                    "direction": 4  # East (flowing right)
                })
                self.grid.occupy(belt_x, belt_y, "transport-belt", [1, 1])
                entity_number += 1
        
        return entity_number

    def place_resource_bus(self, entities, entity_number, resource_list, x_start, y_start, belt_length=20, spacing=2):
        """
        Place a bus with source belts for base resources.
        :param resource_list: List of resources (e.g., ['iron-plate', 'copper-plate'])
        :param x_start: Starting X-coordinate of the bus.
        :param y_start: Starting Y-coordinate of the bus.
        :param belt_length: Length of each belt in the bus.
        :param spacing: Spacing between resource belts.
        """
        current_y = y_start

        for resource in resource_list:
            for i in range(belt_length):
                if self.grid.is_occupied(x_start + i, current_y):
                    logging.error(f"Cannot place belt for {resource} at ({x_start + i}, {current_y}). Skipping.")
                    continue

                # Place transport belt
                entities.append({
                    "entity_number": entity_number,
                    "name": "transport-belt",
                    "position": {"x": x_start + i, "y": current_y}
                })
                self.grid.occupy(x_start + i, current_y, "transport-belt", [1, 1])
                entity_number += 1

            # Add spacing between resource belts
            current_y += spacing

        return entity_number

    def place_multiple_production_lines(self, entities, entity_number):
        """
        1) Places a resource bus for all needed base materials.
        2) Places production lines for each item in PRODUCTION_TARGETS.
        """
        from constants import PRODUCTION_TARGETS
        
        # Step 1: The bus
        entity_number = self.place_resource_bus(entities, entity_number)

        # Step 2: Each target item's production line
        for item, rate in PRODUCTION_TARGETS.items():
            logging.info(f"Placing production line for {item} at {rate}/min")
            entity_number = self.place_production_line(
                entities,
                entity_number,
                item,
                rate
            )
        return entity_number
