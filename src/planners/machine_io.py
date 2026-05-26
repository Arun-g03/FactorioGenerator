"""Unified belt + inserter placement for production blocks."""

from core.constants import FACTORIO_EAST, direction_for_flow, direction_for_inserter


def place_machine_io_block(
    grid,
    entities,
    entity_number,
    machine_x,
    machine_y,
    machine_w,
    machine_h,
    flow_east=True,
):
    """
    Place input belts, input inserter, output inserter, and output belts for one machine.

    Layout (flow east): [belt][belt][belt] -> [inserter] -> [machine] -> [inserter] -> [belt][belt][belt]

    Inserter direction faces the drop tile (front); pickup is the tile behind the inserter.
    """
    belt_count = 3
    lane_y = machine_y + machine_h // 2

    if flow_east:
        belt_direction = FACTORIO_EAST
        input_belt_start_x = machine_x - belt_count - 1
        output_belt_start_x = machine_x + machine_w + 1
        input_inserter_pos = (machine_x - 1, lane_y)
        output_inserter_pos = (machine_x + machine_w, lane_y)
        input_drop = (machine_x, lane_y)
        output_drop = (machine_x + machine_w + 1, lane_y)
    else:
        belt_direction = direction_for_flow((machine_x, lane_y), (machine_x, lane_y + 1))
        input_belt_start_x = machine_x
        output_belt_start_x = machine_x
        input_inserter_pos = (machine_x + machine_w // 2, machine_y - 1)
        output_inserter_pos = (machine_x + machine_w // 2, machine_y + machine_h)
        input_drop = (machine_x + machine_w // 2, machine_y)
        output_drop = (machine_x + machine_w // 2, machine_y + machine_h + 1)

    for i in range(belt_count):
        if flow_east:
            bx = input_belt_start_x + i
            by = lane_y
        else:
            bx = machine_x + machine_w // 2
            by = machine_y - belt_count + i
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
        in_dir = direction_for_inserter(input_inserter_pos, input_drop)
        entities.append({
            "entity_number": entity_number,
            "name": "inserter",
            "position": {"x": ix, "y": iy},
            "direction": in_dir,
        })
        grid.occupy(ix, iy, "inserter", [1, 1])
        entity_number += 1

    for i in range(belt_count):
        if flow_east:
            bx = output_belt_start_x + i
            by = lane_y
        else:
            bx = machine_x + machine_w // 2
            by = machine_y + machine_h + i
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
        out_dir = direction_for_inserter(output_inserter_pos, output_drop)
        entities.append({
            "entity_number": entity_number,
            "name": "inserter",
            "position": {"x": ox, "y": oy},
            "direction": out_dir,
        })
        grid.occupy(ox, oy, "inserter", [1, 1])
        entity_number += 1

    return entity_number
