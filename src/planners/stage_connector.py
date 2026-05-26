"""Route belts between production stages based on recipe dependencies."""

import logging

from core.constants import (
    BASE_MATERIALS,
    FACTORIO_EAST,
    UNDERGROUND_BELT_MAX_UNDERGROUND_TILES,
    direction_for_flow,
)

logger = logging.getLogger(__name__)

# Horizontal bus for raw resources (iron ore, copper ore, etc.)
BASE_BUS_Y = 6
BASE_BUS_X_START = 8
BASE_BUS_LENGTH = 40
BLUEPRINT_START_CHEST = "wooden-chest"


def machine_io_lanes(
    machine_x,
    machine_y,
    width,
    height,
    flow_direction=FACTORIO_EAST,
    *,
    input_lane_count: int = 1,
):
    """Return belt lane anchor tiles for one machine (one input lane per ingredient)."""
    from planners.machine_io import machine_io_lanes as _io_lanes

    return _io_lanes(
        machine_x,
        machine_y,
        width,
        height,
        flow_direction,
        input_lane_count=input_lane_count,
    )


def stage_lanes_from_machines(machines, flow_direction=FACTORIO_EAST, recipe: dict | None = None):
    """Aggregate I/O lane anchors for a stage with one or more machines in a row."""
    if not machines:
        return None
    from planners.machine_io import recipe_input_lane_count

    ordered = sorted(machines, key=lambda m: (m[0], m[1]))
    lane_count = recipe_input_lane_count(recipe)
    first_lanes = machine_io_lanes(
        *ordered[0][:4], flow_direction, input_lane_count=lane_count
    )
    last_lanes = machine_io_lanes(
        *ordered[-1][:4], flow_direction, input_lane_count=lane_count
    )
    return {
        "input_starts": first_lanes["input_starts"],
        "input_connects": first_lanes.get(
            "input_connects", [first_lanes["input_start"]]
        ),
        "input_start": first_lanes["input_start"],
        "input_connect": first_lanes.get("input_connect", first_lanes["input_start"]),
        "output_start": first_lanes.get("output_start", first_lanes["output_end"]),
        "output_end": last_lanes["output_end"],
        "input_lane_count": lane_count,
    }


def _route_belt_path(grid, start, end):
    """Prefer A* around obstacles; fall back to an L-shaped Manhattan path."""
    from core.pathfinding import Pathfinder

    if start == end:
        return [start]

    pathfinder = Pathfinder(grid)
    routed = pathfinder.shortest_path(start, end)
    if routed and len(routed) >= 2:
        return routed
    return _manhattan_path(start, end)


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
    """Direction a belt should face on this path tile (straight or 90° curve)."""
    from core.constants import belt_direction_at_path_index

    return belt_direction_at_path_index(path, index)


def _is_belt_occupant(name: str) -> bool:
    return "transport-belt" in name or "underground-belt" in name


def _update_belt_direction(entities, x, y, direction):
    """Update direction on an existing surface belt at a tile."""
    for entity in entities:
        pos = entity.get("position") or {}
        if int(round(pos.get("x", 0))) == x and int(round(pos.get("y", 0))) == y:
            if _is_belt_occupant(entity.get("name", "")):
                entity["direction"] = direction
                return


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


def _place_storage_chest(grid, entities, entity_number, x, y, name=BLUEPRINT_START_CHEST):
    """Place a 1x1 chest if the tile is free."""
    if grid.is_occupied(x, y):
        return entity_number
    entities.append({
        "entity_number": entity_number,
        "name": name,
        "position": {"x": x, "y": y},
    })
    grid.occupy(x, y, name, [1, 1])
    return entity_number + 1


def _place_underground_pair(
    grid,
    entities,
    entity_number,
    input_pos,
    output_pos,
    direction,
    name="underground-belt",
):
    """
    Place one underground input/output pair for a straight run.

    Only endpoints occupy surface tiles; intervening underground span is clear.
    """
    input_x, input_y = input_pos
    output_x, output_y = output_pos

    if input_x != output_x and input_y != output_y:
        return entity_number
    if direction_for_flow(input_pos, output_pos) != direction:
        return entity_number

    span_tiles = abs(output_x - input_x) + abs(output_y - input_y) - 1
    max_tiles = UNDERGROUND_BELT_MAX_UNDERGROUND_TILES.get(name, 4)
    if span_tiles < 1 or span_tiles > max_tiles:
        return entity_number

    if grid.is_occupied(input_x, input_y):
        occupant = grid.occupied.get((input_x, input_y), "")
        if not _is_belt_occupant(occupant):
            return entity_number
    if grid.is_occupied(output_x, output_y):
        occupant = grid.occupied.get((output_x, output_y), "")
        if not _is_belt_occupant(occupant):
            return entity_number

    entities.append({
        "entity_number": entity_number,
        "name": name,
        "position": {"x": input_x, "y": input_y},
        "direction": direction,
        "type": "input",
    })
    grid.occupy(input_x, input_y, name, [1, 1])
    entity_number += 1

    entities.append({
        "entity_number": entity_number,
        "name": name,
        "position": {"x": output_x, "y": output_y},
        "direction": direction,
        "type": "output",
    })
    grid.occupy(output_x, output_y, name, [1, 1])
    return entity_number + 1


def _try_underground_bridge(grid, entities, entity_number, path, start_index):
    """
    Bridge a straight blocked run with underground belts.

    Returns (entity_number, next_index) when a pair was placed, else (entity_number, None).
    """
    if start_index + 2 >= len(path):
        return entity_number, None

    start = path[start_index]
    direction = direction_for_flow(start, path[start_index + 1])
    blocked_end = start_index + 1
    while blocked_end < len(path):
        step = direction_for_flow(path[blocked_end - 1], path[blocked_end])
        if step != direction:
            break
        if not grid.is_occupied(*path[blocked_end]):
            break
        blocked_end += 1

    if blocked_end >= len(path) or blocked_end <= start_index + 1:
        return entity_number, None

    exit_pos = path[blocked_end]
    if grid.is_occupied(*exit_pos):
        return entity_number, None

    updated = _place_underground_pair(
        grid,
        entities,
        entity_number,
        start,
        exit_pos,
        direction,
        name="underground-belt",
    )
    if updated == entity_number:
        return entity_number, None
    return updated, blocked_end


def place_belt_path(grid, entities, entity_number, path):
    """
    Place belts along a tile path with correct flow directions.

    If a straight segment is blocked, bridge it with an underground-belt pair
    when the run satisfies vanilla underground constraints.
    """
    if len(path) < 2:
        return entity_number

    index = 0
    while index < len(path):
        x, y = path[index]
        direction = _belt_direction_at(path, index)

        if grid.is_occupied(x, y):
            occupant = grid.occupied.get((x, y), "")
            if _is_belt_occupant(occupant):
                _update_belt_direction(entities, x, y, direction)
                index += 1
                continue

            bridge_from = index - 1 if index > 0 else index
            entity_number, skip_to = _try_underground_bridge(
                grid, entities, entity_number, path, bridge_from
            )
            if skip_to is not None:
                index = skip_to
                continue

            index += 1
            continue

        entity_number = _place_belt(grid, entities, entity_number, x, y, direction)
        index += 1

    return entity_number


def _place_splitter(
    grid,
    entities,
    entity_number,
    x,
    y,
    direction,
    name="splitter",
):
    """
    Place a Factorio splitter with correct footprint (2x1).

    Notes:
    - Blueprint encoding converts planner top-left tile coords to entity centers.
    - Grid occupancy uses 2x1 so belts won't be placed on top of the splitter.
    """
    if grid.is_occupied(x, y, width=2, height=1):
        return entity_number

    entities.append(
        {
            "entity_number": entity_number,
            "name": name,
            "position": {"x": x, "y": y},
            "direction": direction,
        }
    )
    grid.occupy(x, y, name, [2, 1])
    return entity_number + 1


def _connection_target_key(req):
    """Unique consumer lane endpoint for a producer→consumer belt request."""
    return (req["consumer_item"], req["consumer_input_start"], req["target_y"])


def _dedupe_connection_requests(requests):
    """Drop duplicate routes to the same consumer lane from the same ingredient."""
    seen = set()
    unique = []
    for req in requests:
        key = (_connection_target_key(req), req["dep"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(req)
    return unique


def _needs_splitter_fanout(requests):
    """
    True only when one producer output must reach two or more distinct consumer lanes.

    A single consumer with one ingredient, or duplicate requests, does not need a splitter.
    """
    if len(requests) < 2:
        return False
    targets = {_connection_target_key(req) for req in requests}
    return len(targets) >= 2


def connect_lane_to_lane(
    grid,
    entities,
    entity_number,
    producer_output,
    consumer_input,
    lane_offset=0,
    *,
    placement_recorder=None,
    connection_detail: list[str] | None = None,
):
    """
    Route belts from a producer's output lane to a consumer's input lane.

    producer_output: (x, y) of the eastmost output belt tile
    consumer_input: (x, y) tile where upstream belts meet the consumer input row
    lane_offset: vertical offset for parallel ingredient feeds
    """
    out_x, out_y = producer_output
    in_x, in_y = consumer_input
    target_y = in_y + lane_offset

    start = (out_x, out_y)
    if lane_offset == 0:
        end = (in_x, in_y)
    else:
        end = (in_x - 1, target_y)

    if start == end:
        return entity_number

    path = _route_belt_path(grid, start, end)
    entity_number = place_belt_path(grid, entities, entity_number, path)

    if lane_offset != 0:
        merge_path = _route_belt_path(grid, (in_x - 1, target_y), (in_x, in_y))
        entity_number = place_belt_path(grid, entities, entity_number, merge_path)

    logger.info(
        "Connected belt from %s to %s (offset=%s)",
        producer_output,
        consumer_input,
        lane_offset,
    )
    if placement_recorder is not None:
        detail = list(connection_detail or [])
        detail.append(f"Path tiles placed: {len(path)}")
        if lane_offset != 0:
            detail.append(f"Merge lane offset: {lane_offset}")
        placement_recorder.record(
            "connect",
            detail[0] if detail else "Connect stages",
            detail[1:],
            entities,
            highlights=[producer_output, consumer_input],
        )
    return entity_number


def connect_stages(
    grid,
    entities,
    entity_number,
    stage_machines,
    nodes,
    *,
    placement_recorder=None,
):
    """
    Connect each stage's output belts to downstream stages that consume its product.

    stage_machines: item -> list of (mx, my, w, h) for machines in that stage
    nodes: rate graph nodes keyed by item
    """
    stage_lanes = {}
    for item, machines in stage_machines.items():
        recipe = getattr(nodes.get(item), "recipe", None)
        lanes = stage_lanes_from_machines(machines, recipe=recipe)
        if lanes:
            stage_lanes[item] = lanes

    requests_by_producer: dict[tuple[int, int], list[dict]] = {}

    for consumer_item, node in nodes.items():
        if consumer_item not in stage_lanes:
            continue

        consumer_lanes = stage_lanes[consumer_item]
        consumer_recipe = getattr(node, "recipe", None) or {}
        input_connects = consumer_lanes.get(
            "input_connects",
            consumer_lanes.get("input_starts", [consumer_lanes["input_start"]]),
        )

        from planners.machine_io import ingredient_lane_index

        for dep in node.dependencies:
            if dep in BASE_MATERIALS:
                continue
            if dep not in stage_lanes:
                continue

            producer_lanes = stage_lanes[dep]
            producer_output = producer_lanes.get(
                "output_start", producer_lanes["output_end"]
            )
            lane_idx = ingredient_lane_index(consumer_recipe, dep)
            consumer_input_start = input_connects[
                min(lane_idx, len(input_connects) - 1)
            ]

            requests_by_producer.setdefault(producer_output, []).append(
                {
                    "consumer_input_start": consumer_input_start,
                    "target_y": consumer_input_start[1],
                    "lane_offset": 0,
                    "consumer_item": consumer_item,
                    "dep": dep,
                }
            )

    if placement_recorder is not None:
        placement_recorder.record(
            "connect_start",
            "Connect production stages",
            [
                f"Stages with lanes: {', '.join(sorted(stage_lanes.keys()))}",
                f"Producer groups to route: {len(requests_by_producer)}",
            ],
            entities,
        )

    for producer_output_end, requests in requests_by_producer.items():
        requests = _dedupe_connection_requests(requests)
        out_x, out_y = producer_output_end

        if not _needs_splitter_fanout(requests):
            for req in requests:
                title = f"Belt: {req['dep']} -> {req['consumer_item']}"
                conn_detail = [
                    title,
                    f"From output {producer_output_end} to input {req['consumer_input_start']}",
                ]
                entity_number = connect_lane_to_lane(
                    grid,
                    entities,
                    entity_number,
                    producer_output_end,
                    req["consumer_input_start"],
                    lane_offset=req["lane_offset"],
                    placement_recorder=placement_recorder,
                    connection_detail=conn_detail,
                )
            continue

        splitter_x = out_x + 1
        splitter_y = out_y
        before = entity_number
        entity_number = _place_splitter(
            grid,
            entities,
            entity_number,
            splitter_x,
            splitter_y,
            direction=FACTORIO_EAST,
            name="splitter",
        )

        if entity_number == before:
            logger.warning(
                "Splitter needed at %s but tiles occupied; using belt fallback",
                producer_output_end,
            )
            for req in requests:
                entity_number = connect_lane_to_lane(
                    grid,
                    entities,
                    entity_number,
                    producer_output_end,
                    req["consumer_input_start"],
                    lane_offset=req["lane_offset"],
                    placement_recorder=placement_recorder,
                    connection_detail=[
                        f"Belt fallback: {req['dep']} -> {req['consumer_item']}",
                        f"Splitter blocked at {producer_output_end}",
                    ],
                )
            continue

        if placement_recorder is not None:
            consumers = ", ".join(req["consumer_item"] for req in requests)
            placement_recorder.record(
                "splitter",
                f"Splitter fan-out at {producer_output_end}",
                [
                    f"Feeds: {consumers}",
                    f"Placed at ({splitter_x}, {splitter_y})",
                ],
                entities,
                highlights=[producer_output_end, (splitter_x, splitter_y)],
            )

        logger.info(
            "Placed splitter at (%s, %s) for %s consumer lane(s) from %s",
            splitter_x,
            splitter_y,
            len(requests),
            producer_output_end,
        )

        splitter_exit_x = out_x + 3
        for req in requests:
            in_x, in_y = req["consumer_input_start"]
            target_y = req["target_y"]

            path = _manhattan_path((splitter_exit_x, target_y), (in_x - 1, target_y))
            entity_number = place_belt_path(grid, entities, entity_number, path)

            if req["lane_offset"] != 0:
                merge_path = _manhattan_path(
                    (in_x - 1, target_y), (in_x - 1, in_y)
                )
                entity_number = place_belt_path(
                    grid, entities, entity_number, merge_path
                )

    return entity_number


def connect_base_materials(
    grid,
    entities,
    entity_number,
    stage_machines,
    nodes,
    *,
    placement_recorder=None,
):
    """
    Place a top resource bus per base material and route into stage inputs.

    Each starting item (iron ore, copper ore, etc.) gets its own wooden chest on
    the first tile of its bus; belts run east from the next tile.
    """
    base_demands = {}
    for item, node in nodes.items():
        if item not in stage_machines:
            continue
        lanes = stage_lanes_from_machines(
            stage_machines[item], recipe=getattr(node, "recipe", None)
        )
        if not lanes:
            continue
        input_starts = lanes.get("input_starts", [lanes["input_start"]])
        consumer_recipe = getattr(node, "recipe", None) or {}
        from planners.machine_io import ingredient_lane_index

        for dep in node.dependencies:
            if dep in BASE_MATERIALS:
                lane_idx = ingredient_lane_index(consumer_recipe, dep)
                anchor = input_starts[min(lane_idx, len(input_starts) - 1)]
                base_demands.setdefault(dep, []).append(anchor)

    if not base_demands:
        return entity_number, {}

    input_starts: dict[str, tuple[int, int]] = {}
    bus_index = 0

    for resource in sorted(base_demands.keys()):
        input_points = base_demands[resource]
        bus_y = BASE_BUS_Y + bus_index * 2
        chest_x = BASE_BUS_X_START
        bus_x_start = BASE_BUS_X_START + 1

        entity_number = _place_storage_chest(
            grid, entities, entity_number, chest_x, bus_y
        )
        input_starts[resource] = (chest_x, bus_y)
        logger.info(
            "Input start chest for %s at (%s, %s)",
            resource,
            chest_x,
            bus_y,
        )

        for belt_x in range(bus_x_start, BASE_BUS_X_START + BASE_BUS_LENGTH):
            entity_number = _place_belt(
                grid, entities, entity_number, belt_x, bus_y, FACTORIO_EAST
            )

        for input_start in input_points:
            in_x, in_y = input_start
            drop_x = max(bus_x_start, in_x - 5)
            path = _manhattan_path((drop_x, bus_y), (in_x - 1, in_y))
            entity_number = place_belt_path(grid, entities, entity_number, path)
            logger.info("Routed base material %s bus to %s", resource, input_start)

        if placement_recorder is not None:
            placement_recorder.record(
                "base_bus",
                f"Base material bus: {resource}",
                [
                    f"Chest at ({chest_x}, {bus_y})",
                    f"Feeds {len(input_points)} stage input(s)",
                    f"Bus runs east from x={bus_x_start}",
                ],
                entities,
                highlights=[(chest_x, bus_y)] + list(input_points),
            )

        bus_index += 1

    return entity_number, input_starts
