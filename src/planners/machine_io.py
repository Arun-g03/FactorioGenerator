"""Unified belt + inserter placement for production blocks."""

from core.constants import (
    FACTORIO_EAST,
    FACTORIO_NORTH,
    FACTORIO_SOUTH,
    FACTORIO_WEST,
    direction_for_flow,
    direction_for_inserter,
)

BELT_COUNT = 3
IO_WEST_TILES = 4  # belts + inserter west of machine (east-flow layout)


def machine_io_lanes(machine_x, machine_y, width, height, flow_direction=FACTORIO_EAST):
    """Return (input_start, output_end) belt lane anchor tiles for one machine."""
    cx = machine_x + width // 2
    cy = machine_y + height // 2

    if flow_direction == FACTORIO_EAST:
        lane_y = cy
        return (machine_x - IO_WEST_TILES, lane_y), (machine_x + width + 3, lane_y)
    if flow_direction == FACTORIO_WEST:
        lane_y = cy
        return (machine_x + width + 3, lane_y), (machine_x - IO_WEST_TILES, lane_y)
    if flow_direction == FACTORIO_SOUTH:
        lane_x = cx
        return (lane_x, machine_y - IO_WEST_TILES), (lane_x, machine_y + height + 3)
    if flow_direction == FACTORIO_NORTH:
        lane_x = cx
        return (lane_x, machine_y + height + 3), (lane_x, machine_y - IO_WEST_TILES)
    lane_y = cy
    return (machine_x - IO_WEST_TILES, lane_y), (machine_x + width + 3, lane_y)


def machine_row_step(flow_direction, stride, index):
    """Offset for machine index along the flow axis (multi-machine stages)."""
    if flow_direction in (FACTORIO_EAST, FACTORIO_WEST):
        return stride * index, 0
    return 0, stride * index


def place_machine_io_block(
    grid,
    entities,
    entity_number,
    machine_x,
    machine_y,
    machine_w,
    machine_h,
    flow_direction=FACTORIO_EAST,
    flow_east=None,
):
    """
    Place input belts, input inserter, output inserter, and output belts.

    ``flow_direction`` is the belt travel direction through the block (any cardinal).
    ``flow_east`` is deprecated; when set it overrides ``flow_direction``.
    """
    if flow_east is not None:
        flow_direction = FACTORIO_EAST if flow_east else FACTORIO_SOUTH

    belt_count = BELT_COUNT
    cx = machine_x + machine_w // 2
    cy = machine_y + machine_h // 2

    if flow_direction == FACTORIO_EAST:
        belt_direction = FACTORIO_EAST
        input_tiles = [(machine_x - belt_count - 1 + i, cy) for i in range(belt_count)]
        output_tiles = [(machine_x + machine_w + 1 + i, cy) for i in range(belt_count)]
        input_inserter_pos = (machine_x - 1, cy)
        output_inserter_pos = (machine_x + machine_w, cy)
        input_drop = (machine_x, cy)
        output_drop = (machine_x + machine_w + 1, cy)
    elif flow_direction == FACTORIO_WEST:
        belt_direction = FACTORIO_WEST
        input_tiles = [(machine_x + machine_w + 1 + i, cy) for i in range(belt_count)]
        output_tiles = [(machine_x - belt_count - 1 + i, cy) for i in range(belt_count)]
        input_inserter_pos = (machine_x + machine_w, cy)
        output_inserter_pos = (machine_x - 1, cy)
        input_drop = (machine_x + machine_w, cy)
        output_drop = (machine_x - 1, cy)
    elif flow_direction == FACTORIO_SOUTH:
        belt_direction = FACTORIO_SOUTH
        input_tiles = [(cx, machine_y - belt_count - 1 + i) for i in range(belt_count)]
        output_tiles = [(cx, machine_y + machine_h + 1 + i) for i in range(belt_count)]
        input_inserter_pos = (cx, machine_y - 1)
        output_inserter_pos = (cx, machine_y + machine_h)
        input_drop = (cx, machine_y)
        output_drop = (cx, machine_y + machine_h + 1)
    else:  # FACTORIO_NORTH
        belt_direction = FACTORIO_NORTH
        input_tiles = [(cx, machine_y + machine_h + 1 + i) for i in range(belt_count)]
        output_tiles = [(cx, machine_y - belt_count - 1 + i) for i in range(belt_count)]
        input_inserter_pos = (cx, machine_y + machine_h)
        output_inserter_pos = (cx, machine_y - 1)
        input_drop = (cx, machine_y + machine_h)
        output_drop = (cx, machine_y - 1)

    for bx, by in input_tiles:
        if not grid.is_occupied(bx, by):
            entities.append({
                "entity_number": entity_number,
                "name": "transport-belt",
                "position": {"x": bx, "y": by},
                "direction": belt_direction,
            })
            grid.occupy(bx, by, "transport-belt", [1, 1])
            entity_number += 1

    ix, iy = input_inserter_pos
    if not grid.is_occupied(ix, iy):
        entities.append({
            "entity_number": entity_number,
            "name": "inserter",
            "position": {"x": ix, "y": iy},
            "direction": direction_for_inserter(input_inserter_pos, input_drop),
        })
        grid.occupy(ix, iy, "inserter", [1, 1])
        entity_number += 1

    for bx, by in output_tiles:
        if not grid.is_occupied(bx, by):
            entities.append({
                "entity_number": entity_number,
                "name": "transport-belt",
                "position": {"x": bx, "y": by},
                "direction": belt_direction,
            })
            grid.occupy(bx, by, "transport-belt", [1, 1])
            entity_number += 1

    ox, oy = output_inserter_pos
    if not grid.is_occupied(ox, oy):
        entities.append({
            "entity_number": entity_number,
            "name": "inserter",
            "position": {"x": ox, "y": oy},
            "direction": direction_for_inserter(output_inserter_pos, output_drop),
        })
        grid.occupy(ox, oy, "inserter", [1, 1])
        entity_number += 1

    return entity_number
