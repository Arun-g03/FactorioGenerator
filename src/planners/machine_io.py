"""Unified belt + inserter placement for production blocks."""

from __future__ import annotations

from core.constants import (
    FACTORIO_EAST,
    FACTORIO_NORTH,
    FACTORIO_SOUTH,
    FACTORIO_WEST,
    INGREDIENT_LANE_SPACING,
    direction_for_flow,
    direction_for_inserter,
    inserter_pickup_tile,
)

BELT_COUNT = 3
IO_WEST_TILES = 4  # belts + inserter on the input side (east-flow layout)
IO_EAST_TILES = 3  # output belts east of machine (east-flow)


def recipe_input_lane_count(recipe: dict | None) -> int:
    """How many parallel input belt lanes a machine needs (one per recipe ingredient)."""
    if not recipe:
        return 1
    return max(1, len(recipe.get("ingredients") or {}))


def recipe_ingredient_order(recipe: dict | None) -> list[str]:
    """Stable ingredient order for lane index assignment."""
    if not recipe:
        return []
    return list(recipe.get("ingredients", {}).keys())


def ingredient_lane_index(recipe: dict | None, ingredient: str) -> int:
    """Map an ingredient name to its input lane index on the consumer machine."""
    order = recipe_ingredient_order(recipe)
    if ingredient not in order:
        return 0
    return order.index(ingredient)


def ingredient_lane_offsets(lane_count: int, spacing: int = INGREDIENT_LANE_SPACING) -> list[int]:
    """Perpendicular offsets (tiles) for each input lane, centered on the machine."""
    if lane_count <= 1:
        return [0]
    total_span = (lane_count - 1) * spacing
    start = -total_span // 2
    return [start + i * spacing for i in range(lane_count)]


def input_connect_tile(
    input_tiles: list[tuple[int, int]],
    flow_direction: int = FACTORIO_EAST,
) -> tuple[int, int] | None:
    """Tile where an upstream belt should meet this machine's input row."""
    if not input_tiles:
        return None
    x0, y0 = input_tiles[0]
    x1, y1 = input_tiles[-1]
    if flow_direction == FACTORIO_EAST:
        return (x0 - 1, y0)
    if flow_direction == FACTORIO_WEST:
        return (x1 + 1, y1)
    if flow_direction == FACTORIO_SOUTH:
        return (x0, y0 - 1)
    if flow_direction == FACTORIO_NORTH:
        return (x0, y1 + 1)
    return (x0 - 1, y0)


def _perpendicular_offset(flow_direction: int, lane_offset: int) -> tuple[int, int]:
    """(dx, dy) offset for an input lane index relative to machine center."""
    if flow_direction == FACTORIO_EAST:
        return 0, lane_offset
    if flow_direction == FACTORIO_WEST:
        return 0, lane_offset
    if flow_direction == FACTORIO_SOUTH:
        return lane_offset, 0
    if flow_direction == FACTORIO_NORTH:
        return lane_offset, 0
    return 0, lane_offset


def _input_lane_geometry(
    machine_x: int,
    machine_y: int,
    machine_w: int,
    machine_h: int,
    flow_direction: int,
    lane_offset: int,
) -> tuple[list[tuple[int, int]], tuple[int, int], tuple[int, int], int]:
    """
    Return (input_belt_tiles, inserter_pos, drop_pos, belt_direction) for one input lane.
    """
    cx = machine_x + machine_w // 2
    cy = machine_y + machine_h // 2
    pdx, pdy = _perpendicular_offset(flow_direction, lane_offset)
    lx, ly = cx + pdx, cy + pdy

    if flow_direction == FACTORIO_EAST:
        belt_direction = FACTORIO_EAST
        input_tiles = [
            (machine_x - BELT_COUNT - 1 + i, ly) for i in range(BELT_COUNT)
        ]
        inserter_pos = (machine_x - 1, ly)
        drop_pos = (machine_x, ly)
    elif flow_direction == FACTORIO_WEST:
        belt_direction = FACTORIO_WEST
        input_tiles = [
            (machine_x + machine_w + 1 + i, ly) for i in range(BELT_COUNT)
        ]
        inserter_pos = (machine_x + machine_w, ly)
        drop_pos = (machine_x + machine_w, ly)
    elif flow_direction == FACTORIO_SOUTH:
        belt_direction = FACTORIO_SOUTH
        input_tiles = [
            (lx, machine_y - BELT_COUNT - 1 + i) for i in range(BELT_COUNT)
        ]
        inserter_pos = (lx, machine_y - 1)
        drop_pos = (lx, machine_y)
    else:  # FACTORIO_NORTH
        belt_direction = FACTORIO_NORTH
        input_tiles = [
            (lx, machine_y + machine_h + 1 + i) for i in range(BELT_COUNT)
        ]
        inserter_pos = (lx, machine_y + machine_h)
        drop_pos = (lx, machine_y + machine_h - 1)

    return input_tiles, inserter_pos, drop_pos, belt_direction


def _output_lane_geometry(
    machine_x: int,
    machine_y: int,
    machine_w: int,
    machine_h: int,
    flow_direction: int,
) -> tuple[list[tuple[int, int]], tuple[int, int], tuple[int, int], int]:
    """Output belts, inserter, drop, and belt direction (single product lane)."""
    cx = machine_x + machine_w // 2
    cy = machine_y + machine_h // 2

    if flow_direction == FACTORIO_EAST:
        return (
            [(machine_x + machine_w + 1 + i, cy) for i in range(BELT_COUNT)],
            (machine_x + machine_w, cy),
            (machine_x + machine_w + 1, cy),
            FACTORIO_EAST,
        )
    if flow_direction == FACTORIO_WEST:
        return (
            [(machine_x - BELT_COUNT - 1 + i, cy) for i in range(BELT_COUNT)],
            (machine_x - 1, cy),
            (machine_x - 1, cy),
            FACTORIO_WEST,
        )
    if flow_direction == FACTORIO_SOUTH:
        return (
            [(cx, machine_y + machine_h + 1 + i) for i in range(BELT_COUNT)],
            (cx, machine_y + machine_h),
            (cx, machine_y + machine_h + 1),
            FACTORIO_SOUTH,
        )
    return (
        [(cx, machine_y - BELT_COUNT - 1 + i) for i in range(BELT_COUNT)],
        (cx, machine_y - 1),
        (cx, machine_y - 2),
        FACTORIO_NORTH,
    )


def machine_io_lanes(
    machine_x: int,
    machine_y: int,
    width: int,
    height: int,
    flow_direction=FACTORIO_EAST,
    *,
    input_lane_count: int = 1,
) -> dict:
    """
    Belt lane anchors for one machine.

    Returns input_starts (one per recipe ingredient), output_end, and metadata.
    Each transport-belt tile can carry BELT_LANES_PER_TILE item lanes in Factorio;
    we still use one belt row per ingredient for routing clarity.
    """
    lane_count = max(1, input_lane_count)
    input_starts: list[tuple[int, int]] = []
    input_connects: list[tuple[int, int]] = []

    for lane_offset in ingredient_lane_offsets(lane_count):
        input_tiles, _, _, _ = _input_lane_geometry(
            machine_x, machine_y, width, height, flow_direction, lane_offset
        )
        if input_tiles:
            input_starts.append(input_tiles[0])
            connect = input_connect_tile(input_tiles, flow_direction)
            if connect is not None:
                input_connects.append(connect)

    if not input_starts:
        input_starts = [(machine_x, machine_y)]
        input_connects = [(machine_x - 1, machine_y)]

    output_tiles, _, output_end, _ = _output_lane_geometry(
        machine_x, machine_y, width, height, flow_direction
    )
    output_start = output_end
    if output_tiles:
        output_start = output_tiles[0]
        output_end = output_tiles[-1]

    return {
        "input_starts": input_starts,
        "input_connects": input_connects,
        "input_start": input_starts[0],
        "input_connect": input_connects[0],
        "output_start": output_start,
        "output_end": output_end,
        "input_lane_count": lane_count,
    }


def machine_io_tiles_for_block(
    machine_x: int,
    machine_y: int,
    machine_w: int,
    machine_h: int,
    *,
    input_lane_count: int = 1,
    flow_direction: int = FACTORIO_EAST,
) -> set[tuple[int, int]]:
    """All grid tiles used by a machine I/O block (for collision checks)."""
    tiles: set[tuple[int, int]] = set()
    for lane_offset in ingredient_lane_offsets(max(1, input_lane_count)):
        input_tiles, inserter_pos, _, _ = _input_lane_geometry(
            machine_x, machine_y, machine_w, machine_h, flow_direction, lane_offset
        )
        tiles.update(input_tiles)
        tiles.add(inserter_pos)

    output_tiles, output_inserter, _, _ = _output_lane_geometry(
        machine_x, machine_y, machine_w, machine_h, flow_direction
    )
    tiles.update(output_tiles)
    tiles.add(output_inserter)
    return tiles


def machine_row_step(flow_direction, stride, index):
    """Offset for machine index along the flow axis (multi-machine stages)."""
    if flow_direction in (FACTORIO_EAST, FACTORIO_WEST):
        return stride * index, 0
    return 0, stride * index


InserterKnot = tuple[tuple[int, int], tuple[int, int]]


def machine_input_inserter_knot(
    machine_x: int,
    machine_y: int,
    width: int,
    height: int,
    flow_direction: int = FACTORIO_EAST,
    *,
    lane_offset: int = 0,
) -> InserterKnot:
    """Rope endpoint: belt -> machine (pickup belt, drop into machine)."""
    _input_tiles, inserter_pos, drop_pos, _ = _input_lane_geometry(
        machine_x, machine_y, width, height, flow_direction, lane_offset
    )
    return inserter_pos, drop_pos


def machine_output_inserter_knot(
    machine_x: int,
    machine_y: int,
    width: int,
    height: int,
    flow_direction: int = FACTORIO_EAST,
) -> InserterKnot:
    """Rope endpoint: machine -> belt (pickup machine, drop onto belt)."""
    _output_tiles, inserter_pos, drop_pos, _ = _output_lane_geometry(
        machine_x, machine_y, width, height, flow_direction
    )
    return inserter_pos, drop_pos


def chest_to_belt_knot(
    chest_x: int,
    chest_y: int,
    flow_direction: int = FACTORIO_EAST,
) -> InserterKnot:
    """Rope endpoint: input chest -> belt (east-flow layouts)."""
    if flow_direction == FACTORIO_EAST:
        return (chest_x + 1, chest_y), (chest_x + 2, chest_y)
    if flow_direction == FACTORIO_WEST:
        return (chest_x - 1, chest_y), (chest_x - 2, chest_y)
    if flow_direction == FACTORIO_SOUTH:
        return (chest_x, chest_y + 1), (chest_x, chest_y + 2)
    return (chest_x, chest_y - 1), (chest_x, chest_y - 2)


def belt_to_chest_knot(
    chest_x: int,
    chest_y: int,
    flow_direction: int = FACTORIO_EAST,
) -> InserterKnot:
    """Rope endpoint: belt -> output chest (east-flow layouts)."""
    if flow_direction == FACTORIO_EAST:
        return (chest_x - 1, chest_y), (chest_x, chest_y)
    if flow_direction == FACTORIO_WEST:
        return (chest_x + 1, chest_y), (chest_x, chest_y)
    if flow_direction == FACTORIO_SOUTH:
        return (chest_x, chest_y - 1), (chest_x, chest_y)
    return (chest_x, chest_y + 1), (chest_x, chest_y)


def chest_belt_feed_start(
    chest_x: int,
    chest_y: int,
    flow_direction: int = FACTORIO_EAST,
) -> tuple[int, int]:
    """First belt tile east of an input chest inserter knot."""
    _pos, drop = chest_to_belt_knot(chest_x, chest_y, flow_direction)
    return drop


def chest_belt_sink_connect(
    chest_x: int,
    chest_y: int,
    flow_direction: int = FACTORIO_EAST,
) -> tuple[int, int]:
    """Belt tile that feeds the inserter in front of an output chest."""
    pos, _drop = belt_to_chest_knot(chest_x, chest_y, flow_direction)
    if flow_direction == FACTORIO_EAST:
        return (pos[0] - 1, pos[1])
    if flow_direction == FACTORIO_WEST:
        return (pos[0] + 1, pos[1])
    if flow_direction == FACTORIO_SOUTH:
        return (pos[0], pos[1] - 1)
    return (pos[0], pos[1] + 1)


def place_inserter_knot(
    grid,
    entities,
    entity_number: int,
    knot: InserterKnot | None,
    *,
    name: str = "inserter",
) -> int:
    """Place one inserter for a connection endpoint if the tile is free."""
    if not knot:
        return entity_number
    pos, drop = knot
    x, y = pos
    if grid.is_occupied(x, y):
        occupant = grid.occupied.get((x, y), "")
        if "inserter" in occupant:
            return entity_number
        return entity_number

    entities.append({
        "entity_number": entity_number,
        "name": name,
        "position": {"x": x, "y": y},
        "direction": direction_for_inserter(pos, drop),
    })
    grid.occupy(x, y, name, [1, 1])
    return entity_number + 1


def knot_belt_tile(knot: InserterKnot | None) -> tuple[int, int] | None:
    """Return the belt-side tile that should touch this inserter knot."""
    if not knot:
        return None
    pos, drop = knot
    direction = direction_for_inserter(pos, drop)
    return inserter_pickup_tile(pos, direction)


def place_machine_endpoint_inserters(
    grid,
    entities,
    entity_number: int,
    stage_machines: dict[str, list[tuple[int, int, int, int]]],
    nodes,
    *,
    flow_direction: int = FACTORIO_EAST,
) -> int:
    """
    Place inserter knots on every machine before belt routing.

    Each machine gets one output inserter and one input inserter per recipe
    ingredient lane — the "knots" at machine ends of belt ropes.
    """
    for item, machines in stage_machines.items():
        node = nodes.get(item)
        recipe = getattr(node, "recipe", None)
        lane_count = recipe_input_lane_count(recipe)
        for mx, my, w, h in machines:
            for lane_offset in ingredient_lane_offsets(lane_count):
                knot = machine_input_inserter_knot(
                    mx, my, w, h, flow_direction, lane_offset=lane_offset
                )
                entity_number = place_inserter_knot(
                    grid, entities, entity_number, knot
                )
            knot = machine_output_inserter_knot(mx, my, w, h, flow_direction)
            entity_number = place_inserter_knot(grid, entities, entity_number, knot)
    return entity_number


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
    *,
    recipe: dict | None = None,
    input_lane_count: int | None = None,
):
    """
    Place input belts/inserters (one lane per recipe ingredient) and output I/O.

    ``flow_direction`` is the belt travel direction through the block (any cardinal).
    ``recipe`` or ``input_lane_count`` sets how many parallel input lanes to build.
    """
    if flow_east is not None:
        flow_direction = FACTORIO_EAST if flow_east else FACTORIO_SOUTH

    lane_count = input_lane_count
    if lane_count is None:
        lane_count = recipe_input_lane_count(recipe)

    for lane_offset in ingredient_lane_offsets(lane_count):
        input_tiles, inserter_pos, drop_pos, belt_direction = _input_lane_geometry(
            machine_x, machine_y, machine_w, machine_h, flow_direction, lane_offset
        )

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

        ix, iy = inserter_pos
        if not grid.is_occupied(ix, iy):
            entities.append({
                "entity_number": entity_number,
                "name": "inserter",
                "position": {"x": ix, "y": iy},
                "direction": direction_for_inserter(inserter_pos, drop_pos),
            })
            grid.occupy(ix, iy, "inserter", [1, 1])
            entity_number += 1

    output_tiles, output_inserter_pos, output_drop, belt_direction = _output_lane_geometry(
        machine_x, machine_y, machine_w, machine_h, flow_direction
    )

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
