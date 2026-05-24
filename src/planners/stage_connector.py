"""Route belts between production stages based on recipe dependencies."""

import logging

from core.constants import BASE_MATERIALS, FACTORIO_EAST, direction_for_flow

logger = logging.getLogger(__name__)

# Horizontal bus for raw resources (iron ore, copper ore, etc.)
BASE_BUS_Y = 6
BASE_BUS_X_START = 8
BASE_BUS_LENGTH = 40


def machine_io_lanes(machine_x, machine_y, width, height):
    """Return (input_start, output_end) belt lane anchor tiles for one machine."""
    lane_y = machine_y + height // 2
    input_start = (machine_x - 4, lane_y)
    output_end = (machine_x + width + 3, lane_y)
    return input_start, output_end


def stage_lanes_from_machines(machines):
    """Aggregate I/O lane anchors for a stage with one or more machines in a row."""
    if not machines:
        return None
    ordered = sorted(machines, key=lambda m: (m[0], m[1]))
    input_start, _ = machine_io_lanes(*ordered[0])
    _, output_end = machine_io_lanes(*ordered[-1])
    return {"input_start": input_start, "output_end": output_end}


def _manhattan_path(start, end):
    """Build an L-shaped path from start to end (horizontal first, then vertical)."""
    path = [start]
    x, y = start
    end_x, end_y = end

    step = 1 if end_x >= x else -1
    while x != end_x:
        x += step
        path.append((x, y))

    step = 1 if end_y >= y else -1
    while y != end_y:
        y += step
        path.append((x, y))

    return path


def _belt_direction_at(path, index):
    """Direction a belt should face to carry items along path[index] -> path[index+1]."""
    if index + 1 >= len(path):
        return FACTORIO_EAST
    return direction_for_flow(path[index], path[index + 1])


def _place_belt(grid, entities, entity_number, x, y, direction):
    """Place one transport belt if the tile is free."""
    if grid.is_occupied(x, y):
        return entity_number
    entities.append({
        "entity_number": entity_number,
        "name": "transport-belt",
        "position": {"x": x, "y": y},
        "direction": direction,
    })
    grid.occupy(x, y, "transport-belt", [1, 1])
    return entity_number + 1


def place_belt_path(grid, entities, entity_number, path):
    """Place belts along a tile path with correct flow directions."""
    if len(path) < 2:
        return entity_number

    for index, (x, y) in enumerate(path[:-1]):
        direction = _belt_direction_at(path, index)
        entity_number = _place_belt(grid, entities, entity_number, x, y, direction)

    last_x, last_y = path[-1]
    prev_x, prev_y = path[-2]
    direction = direction_for_flow((prev_x, prev_y), (last_x, last_y))
    entity_number = _place_belt(grid, entities, entity_number, last_x, last_y, direction)
    return entity_number


def connect_lane_to_lane(
    grid,
    entities,
    entity_number,
    producer_output,
    consumer_input,
    lane_offset=0,
):
    """
    Route belts from a producer's output lane to a consumer's input lane.

    producer_output: (x, y) of the eastmost output belt tile
    consumer_input: (x, y) of the westmost input belt tile
    lane_offset: vertical offset for parallel ingredient feeds
    """
    out_x, out_y = producer_output
    in_x, in_y = consumer_input
    target_y = in_y + lane_offset

    start = (out_x + 1, out_y)
    end = (in_x - 1, target_y)

    if start == end:
        return entity_number

    path = _manhattan_path(start, end)
    entity_number = place_belt_path(grid, entities, entity_number, path)

    # Merge offset lane into the consumer input row when needed
    if lane_offset != 0:
        merge_path = _manhattan_path((in_x - 1, target_y), (in_x - 1, in_y))
        entity_number = place_belt_path(grid, entities, entity_number, merge_path)

    logger.info(
        "Connected belt from %s to %s (offset=%s)",
        producer_output,
        consumer_input,
        lane_offset,
    )
    return entity_number


def connect_stages(grid, entities, entity_number, stage_machines, nodes):
    """
    Connect each stage's output belts to downstream stages that consume its product.

    stage_machines: item -> list of (mx, my, w, h) for machines in that stage
    nodes: rate graph nodes keyed by item
    """
    stage_lanes = {}
    for item, machines in stage_machines.items():
        lanes = stage_lanes_from_machines(machines)
        if lanes:
            stage_lanes[item] = lanes

    for item, node in nodes.items():
        if item not in stage_lanes:
            continue

        consumer_lanes = stage_lanes[item]
        ingredient_index = 0

        for dep in node.dependencies:
            if dep in BASE_MATERIALS:
                continue
            if dep not in stage_lanes:
                continue

            producer_lanes = stage_lanes[dep]
            entity_number = connect_lane_to_lane(
                grid,
                entities,
                entity_number,
                producer_lanes["output_end"],
                consumer_lanes["input_start"],
                lane_offset=ingredient_index * 2,
            )
            ingredient_index += 1

    return entity_number


def connect_base_materials(grid, entities, entity_number, stage_machines, nodes):
    """
    Place a top resource bus and route base materials into stages that need them.
    """
    base_demands = {}
    for item, node in nodes.items():
        if item not in stage_machines:
            continue
        lanes = stage_lanes_from_machines(stage_machines[item])
        if not lanes:
            continue
        for dep in node.dependencies:
            if dep in BASE_MATERIALS:
                base_demands.setdefault(dep, []).append(lanes["input_start"])

    if not base_demands:
        return entity_number

    bus_index = 0
    for resource, input_points in base_demands.items():
        bus_y = BASE_BUS_Y + bus_index * 2
        bus_index += 1

        for belt_x in range(BASE_BUS_X_START, BASE_BUS_X_START + BASE_BUS_LENGTH):
            entity_number = _place_belt(
                grid, entities, entity_number, belt_x, bus_y, FACTORIO_EAST
            )

        for input_start in input_points:
            in_x, in_y = input_start
            drop_x = max(BASE_BUS_X_START, in_x - 5)
            path = _manhattan_path((drop_x, bus_y), (in_x - 1, in_y))
            entity_number = place_belt_path(grid, entities, entity_number, path)
            logger.info("Routed base material %s bus to %s", resource, input_start)

    return entity_number
