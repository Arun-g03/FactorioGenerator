"""Route belts between production stages based on recipe dependencies."""

import logging

from core.constants import (
    BASE_MATERIALS,
    FACTORIO_EAST,
    FACTORIO_NORTH,
    FACTORIO_SOUTH,
    FACTORIO_WEST,
    UNDERGROUND_BELT_MAX_UNDERGROUND_TILES,
    direction_for_flow,
)

logger = logging.getLogger(__name__)
OUTPUT_ANY_PRODUCT = "any"


def _layout_produced_items(stage_machines) -> set[str]:
    return set(stage_machines.keys())


def terminal_products(stage_machines, nodes) -> set[str]:
    """Items produced in the layout that no other placed stage consumes."""
    produced = _layout_produced_items(stage_machines)
    consumed_internally: set[str] = set()
    for item in produced:
        node = nodes.get(item)
        if not node:
            continue
        recipe = getattr(node, "recipe", None) or {}
        for dep in recipe.get("ingredients", {}).keys():
            if dep in produced:
                consumed_internally.add(dep)
    return produced - consumed_internally


def _chain_depth(item: str, nodes, produced: set[str], memo: dict[str, int]) -> int:
    """Longest dependency path through layout-produced items ending at ``item``."""
    if item in memo:
        return memo[item]
    node = nodes.get(item)
    if not node:
        memo[item] = 0
        return 0
    internal_deps = [d for d in node.dependencies if d in produced]
    if not internal_deps:
        memo[item] = 0
        return 0
    memo[item] = 1 + max(_chain_depth(dep, nodes, produced, memo) for dep in internal_deps)
    return memo[item]


def latest_chain_product(stage_machines, nodes) -> str | None:
    """
    End-of-chain product for an unspecified output sink.

    Picks a terminal product (not consumed by another placed stage), preferring
    the deepest item in the internal dependency graph.
    """
    terminals = terminal_products(stage_machines, nodes)
    if not terminals:
        return None
    if len(terminals) == 1:
        return next(iter(terminals))
    produced = _layout_produced_items(stage_machines)
    memo: dict[str, int] = {}
    return max(
        terminals,
        key=lambda item: (_chain_depth(item, nodes, produced, memo), item),
    )

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


def _route_belt_path(grid, start, end, item: str | None = None):
    """Prefer belt-aware A*; fall back to empty-only L-shaped Manhattan."""
    if start == end:
        return [start]

    if item is not None:
        from planners.belt_network.occupancy import RoutingOccupancy
        from planners.belt_network.pathfinder import BeltPathfinder

        occupancy = RoutingOccupancy(grid)
        pathfinder = BeltPathfinder(occupancy, allow_underground=True)
        try:
            return pathfinder.route_or_conflict(start, end, item, allow_empty_manhattan=True)
        except Exception:
            pass

    from core.pathfinding import Pathfinder

    pathfinder = Pathfinder(grid)
    routed = pathfinder.shortest_path(start, end)
    if routed and len(routed) >= 2:
        return routed

    from planners.belt_network.occupancy import RoutingOccupancy
    from planners.belt_network.pathfinder import BeltPathfinder

    occupancy = RoutingOccupancy(grid)
    empty_path = BeltPathfinder(occupancy)._empty_only_manhattan(start, end, item or "")
    if empty_path:
        return empty_path
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


def _splitter_footprint(direction: int) -> tuple[int, int]:
    """Grid footprint (width, height) for a splitter facing ``direction``."""
    from core.splitter_geometry import splitter_footprint_size

    return splitter_footprint_size(direction)


def _splitter_input_tile(splitter_x: int, splitter_y: int, direction: int = FACTORIO_EAST) -> tuple[int, int]:
    """Primary belt tile that feeds the splitter input face."""
    from core.splitter_geometry import splitter_layout

    return splitter_layout((splitter_x, splitter_y), direction).input_belt


def _ensure_splitter_input_belt(
    grid,
    entities,
    entity_number,
    splitter_x: int,
    splitter_y: int,
    *,
    feed_from: tuple[int, int] | None = None,
    direction: int = FACTORIO_EAST,
) -> int:
    """
    Route/place the belt segment that feeds a splitter before the splitter is placed.

    Avoids branch paths or A* later claiming the splitter's input tile.
    """
    input_x, input_y = _splitter_input_tile(splitter_x, splitter_y, direction)
    flow_dir = direction if direction in (FACTORIO_EAST, FACTORIO_WEST, FACTORIO_NORTH, FACTORIO_SOUTH) else FACTORIO_EAST

    if feed_from and feed_from != (input_x, input_y):
        path = _route_belt_path(feed_from, (input_x, input_y))
        entity_number = place_belt_path(grid, entities, entity_number, path)
    elif not grid.is_occupied(input_x, input_y):
        entity_number = _place_belt(
            grid, entities, entity_number, input_x, input_y, flow_dir
        )
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
    - Grid occupancy uses 2x1 (east/west) or 1x2 (north/south) so belts won't overlap.
    """
    width, height = _splitter_footprint(direction)
    if grid.is_occupied(x, y, width=width, height=height):
        return entity_number

    entities.append(
        {
            "entity_number": entity_number,
            "name": name,
            "position": {"x": x, "y": y},
            "direction": direction,
        }
    )
    grid.occupy(x, y, name, [width, height])
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


def _needs_splitter_fanout_from_links(links) -> bool:
    """True when a link group has two or more distinct sink endpoints."""
    if len(links) < 2:
        return False
    sinks = {link.sink for link in links}
    return len(sinks) >= 2


def _east_splitter_output_lanes(splitter_x: int, splitter_y: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Two output belt tiles for an east-facing splitter (north/south branches)."""
    from core.splitter_geometry import splitter_layout

    outputs = sorted(splitter_layout((splitter_x, splitter_y), FACTORIO_EAST).output_belts)
    return outputs[0], outputs[1]


def _assign_splitter_branch_starts(
    splitter_x: int,
    splitter_y: int,
    targets: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """
    Map each routing target to a splitter output lane (north or south).

    ``targets`` are path ends sorted by increasing y. Uses both splitter outputs
    when there are two or more distinct consumers.
    """
    north_out, south_out = _east_splitter_output_lanes(splitter_x, splitter_y)
    if len(targets) == 1:
        _, ty = targets[0]
        return [south_out if ty >= splitter_y else north_out]
    if len(targets) == 2:
        return [north_out, south_out]
    # Three or more: alternate north/south (vanilla splitters only have two outputs).
    starts = []
    for index, (_, ty) in enumerate(targets):
        if index == 0:
            starts.append(north_out)
        elif index == len(targets) - 1:
            starts.append(south_out)
        else:
            starts.append(south_out if ty >= splitter_y else north_out)
    return starts


def _route_from_splitter_branches(
    grid,
    entities,
    entity_number,
    branch_starts: list[tuple[int, int]],
    path_ends: list[tuple[int, int]],
) -> int:
    """Place belts from each splitter output lane to its consumer path end."""
    for start, end in zip(branch_starts, path_ends):
        path = _manhattan_path(start, end)
        entity_number = place_belt_path(grid, entities, entity_number, path)
    return entity_number


def connect_lane_to_lane(
    grid,
    entities,
    entity_number,
    producer_output,
    consumer_input,
    lane_offset=0,
    *,
    source_knot=None,
    dest_knot=None,
    placement_recorder=None,
    connection_detail: list[str] | None = None,
):
    """
    Route belts from a producer's output lane to a consumer's input lane.

    producer_output: (x, y) of the eastmost output belt tile
    consumer_input: (x, y) tile where upstream belts meet the consumer input row
    lane_offset: vertical offset for parallel ingredient feeds
    source_knot / dest_knot: optional (inserter_pos, drop_pos) rope endpoints
    """
    from planners.machine_io import knot_belt_tile, place_inserter_knot

    entity_number = place_inserter_knot(grid, entities, entity_number, source_knot)
    entity_number = place_inserter_knot(grid, entities, entity_number, dest_knot)

    out_x, out_y = producer_output
    in_x, in_y = consumer_input
    target_y = in_y + lane_offset

    start = (out_x, out_y)
    if lane_offset == 0:
        end = (in_x, in_y)
    else:
        end = (in_x - 1, target_y)

    # If a destination knot exists, route up to the inserter's belt-side pickup tile.
    # This avoids short belts when machine I/O side belts are not pre-placed.
    dest_belt = knot_belt_tile(dest_knot)
    if dest_belt is not None:
        end = dest_belt

    if start == end:
        return entity_number

    before = entity_number
    path = _route_belt_path(grid, start, end)
    entity_number = place_belt_path(grid, entities, entity_number, path)

    if lane_offset != 0:
        merge_path = _route_belt_path(grid, (in_x - 1, target_y), (in_x, in_y))
        entity_number = place_belt_path(grid, entities, entity_number, merge_path)

    placed = entity_number - before
    if placed > 0:
        logger.info(
            "Connected belt from %s to %s (offset=%s, segments=%s)",
            producer_output,
            consumer_input,
            lane_offset,
            placed,
        )
    else:
        logger.warning(
            "No new belt segments placed from %s to %s (offset=%s)",
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
    from planners.machine_io import (
        ingredient_lane_offsets,
        machine_input_inserter_knot,
        recipe_input_lane_count,
    )

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
                    "lane_idx": lane_idx,
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
                consumer_machine = stage_machines.get(req["consumer_item"], [None])[0]
                dest_knot = None
                if consumer_machine is not None:
                    mx, my, w, h = consumer_machine
                    lane_count = recipe_input_lane_count(
                        getattr(nodes.get(req["consumer_item"]), "recipe", None)
                    )
                    offsets = ingredient_lane_offsets(lane_count)
                    lane_offset = offsets[min(req.get("lane_idx", 0), len(offsets) - 1)]
                    dest_knot = machine_input_inserter_knot(
                        mx, my, w, h, FACTORIO_EAST, lane_offset=lane_offset
                    )
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
                    dest_knot=dest_knot,
                    placement_recorder=placement_recorder,
                    connection_detail=conn_detail,
                )
            continue

        splitter_x = out_x + 1
        splitter_y = out_y
        entity_number = _ensure_splitter_input_belt(
            grid,
            entities,
            entity_number,
            splitter_x,
            splitter_y,
            feed_from=producer_output_end,
            direction=FACTORIO_EAST,
        )
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
                consumer_machine = stage_machines.get(req["consumer_item"], [None])[0]
                dest_knot = None
                if consumer_machine is not None:
                    mx, my, w, h = consumer_machine
                    lane_count = recipe_input_lane_count(
                        getattr(nodes.get(req["consumer_item"]), "recipe", None)
                    )
                    offsets = ingredient_lane_offsets(lane_count)
                    lane_offset = offsets[min(req.get("lane_idx", 0), len(offsets) - 1)]
                    dest_knot = machine_input_inserter_knot(
                        mx, my, w, h, FACTORIO_EAST, lane_offset=lane_offset
                    )
                entity_number = connect_lane_to_lane(
                    grid,
                    entities,
                    entity_number,
                    producer_output_end,
                    req["consumer_input_start"],
                    lane_offset=req["lane_offset"],
                    dest_knot=dest_knot,
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

        path_ends = []
        for req in requests:
            in_x, _in_y = req["consumer_input_start"]
            path_ends.append((in_x - 1, req["target_y"]))

        sorted_pairs = sorted(
            zip(requests, path_ends), key=lambda pair: pair[1][1]
        )
        sorted_ends = [end for _, end in sorted_pairs]
        branch_starts = _assign_splitter_branch_starts(
            splitter_x, splitter_y, sorted_ends
        )
        entity_number = _route_from_splitter_branches(
            grid, entities, entity_number, branch_starts, sorted_ends
        )

        for req, end in sorted_pairs:
            if req["lane_offset"] == 0:
                continue
            in_x, in_y = req["consumer_input_start"]
            merge_path = _manhattan_path(end, (in_x, in_y))
            entity_number = place_belt_path(
                grid, entities, entity_number, merge_path
            )

    return entity_number


def route_placed_layout(
    grid,
    entities,
    entity_number,
    stage_machines,
    nodes,
    *,
    input_sources: dict[str, list[tuple[int, int]]] | None = None,
    output_sinks: dict[str, list[tuple[int, int]]] | None = None,
    placement_recorder=None,
    place_machine_knots: bool = True,
    use_network_router: bool = True,
    network_router=None,
    link_order_variant: int = 0,
    links=None,
    group_order=None,
) -> tuple[int, dict[str, tuple[int, int]]]:
    """
    Route belts for a fixed machine layout.

    Used by autonomous generation and assisted build: placement differs, routing
    does not. ``stage_machines`` maps output item to (mx, my, w, h) tuples;
    ``nodes`` is the rate graph keyed by item. Optional ``input_sources`` maps
    base material to user-placed chest positions (assisted input cells).
    Optional ``output_sinks`` maps product item to user-placed output chests.

    When ``use_network_router`` is True (default), routes via the belt network
    planner (link graph + shared trunks). Pass ``network_router`` to preserve
    state for incremental reroute in Assisted Build.
    """
    if place_machine_knots:
        from planners.machine_io import place_machine_endpoint_inserters

        entity_number = place_machine_endpoint_inserters(
            grid,
            entities,
            entity_number,
            stage_machines,
            nodes,
        )

    if use_network_router:
        from planners.belt_network.router import route_placed_layout_network

        entity_number, input_starts, router = route_placed_layout_network(
            grid,
            entities,
            entity_number,
            stage_machines,
            nodes,
            input_sources=input_sources,
            output_sinks=output_sinks,
            placement_recorder=placement_recorder,
            router=network_router,
            link_order_variant=link_order_variant,
            links=links,
            group_order=group_order,
        )
        route_placed_layout._last_router = router  # type: ignore[attr-defined]
        return entity_number, input_starts

    entity_number = connect_stages(
        grid,
        entities,
        entity_number,
        stage_machines,
        nodes,
        placement_recorder=placement_recorder,
    )
    entity_number, input_starts = connect_base_materials(
        grid,
        entities,
        entity_number,
        stage_machines,
        nodes,
        input_sources=input_sources,
        placement_recorder=placement_recorder,
    )
    entity_number = connect_output_sinks(
        grid,
        entities,
        entity_number,
        stage_machines,
        nodes,
        output_sinks=output_sinks,
        placement_recorder=placement_recorder,
    )
    return entity_number, input_starts


def connect_output_sinks(
    grid,
    entities,
    entity_number,
    stage_machines,
    nodes,
    *,
    output_sinks: dict[str, list[tuple[int, int]]] | None = None,
    placement_recorder=None,
):
    """
    Route belts from producer output lanes to user-placed output chests.

    Each sink is a (chest_x, chest_y) tile; belts approach from the west
    (east-flow layouts) and terminate at (chest_x - 1, chest_y).
    """
    output_sinks = output_sinks or {}
    if not output_sinks:
        return entity_number

    for product in sorted(output_sinks.keys()):
        if product == OUTPUT_ANY_PRODUCT:
            latest = latest_chain_product(stage_machines, nodes)
            if not latest:
                logger.warning("Output sink 'any' but no producers in layout")
                continue
            producer_items = [latest]
            route_label = latest
        elif product in stage_machines:
            producer_items = [product]
            route_label = product
        else:
            logger.warning(
                "Output sink for %s but no producer in layout", product
            )
            continue

        for producer_item in producer_items:
            node = nodes.get(producer_item)
            recipe = getattr(node, "recipe", None)
            producer_outputs: list[tuple[int, int]] = []
            from planners.machine_io import recipe_input_lane_count

            lane_count = recipe_input_lane_count(recipe)
            for mx, my, w, h in stage_machines.get(producer_item, []):
                lanes = machine_io_lanes(mx, my, w, h, input_lane_count=lane_count)
                producer_outputs.append(lanes.get("output_start", lanes["output_end"]))
            if not producer_outputs:
                continue
            for chest_x, chest_y in output_sinks[product]:
                from planners.machine_io import belt_to_chest_knot, chest_belt_sink_connect

                sink_connect = chest_belt_sink_connect(chest_x, chest_y)
                for producer_output in producer_outputs:
                    entity_number = connect_lane_to_lane(
                        grid,
                        entities,
                        entity_number,
                        producer_output,
                        sink_connect,
                        dest_knot=belt_to_chest_knot(chest_x, chest_y),
                    )
                    logger.info(
                        "Routed %s from %s to output chest at (%s, %s)",
                        route_label,
                        producer_output,
                        chest_x,
                        chest_y,
                    )
                    if placement_recorder is not None:
                        sink_title = (
                            f"Output sink: any -> {route_label}"
                            if product == OUTPUT_ANY_PRODUCT
                            else f"Output sink: {product}"
                        )
                        placement_recorder.record(
                            "output_sink",
                            sink_title,
                            [
                                f"From producer output {producer_output}",
                                f"Chest at ({chest_x}, {chest_y})",
                            ],
                            entities,
                            highlights=[producer_output, (chest_x, chest_y)],
                        )

    return entity_number


def _route_end_for_lane_anchor(anchor, dest_knot) -> tuple[int, int]:
    """Belt tile to route toward for a consumer lane anchor / inserter knot."""
    from planners.machine_io import knot_belt_tile

    end = anchor
    dest_belt = knot_belt_tile(dest_knot)
    if dest_belt is not None:
        end = dest_belt
    return end


def _dest_knot_for_base_demand(demand: dict) -> tuple | None:
    from planners.machine_io import machine_input_inserter_knot

    machine = demand.get("machine")
    if machine is None:
        return None
    mx, my, w, h = machine
    return machine_input_inserter_knot(
        mx, my, w, h, FACTORIO_EAST, lane_offset=demand.get("lane_offset", 0)
    )


def _connect_feed_fanout(
    grid,
    entities,
    entity_number,
    feed_start: tuple[int, int],
    chest_knot,
    demands: list[dict],
    *,
    resource: str = "",
    placement_recorder=None,
) -> int:
    """
    Route one input-cell feed to one or more machine inputs.

    Uses a splitter when multiple distinct consumers share the same feed tile,
    so adding a machine does not redirect the trunk away from existing ones.
    """
    from planners.machine_io import place_inserter_knot

    routes: list[dict] = []
    for demand in demands:
        dest_knot = _dest_knot_for_base_demand(demand)
        routes.append(
            {
                "anchor": demand["anchor"],
                "dest_knot": dest_knot,
                "end": _route_end_for_lane_anchor(demand["anchor"], dest_knot),
            }
        )

    entity_number = place_inserter_knot(grid, entities, entity_number, chest_knot)

    unique_ends = {r["end"] for r in routes}
    if len(routes) == 1 or len(unique_ends) < 2:
        route = routes[0]
        entity_number = connect_lane_to_lane(
            grid,
            entities,
            entity_number,
            feed_start,
            route["anchor"],
            source_knot=None,
            dest_knot=route["dest_knot"],
        )
        return entity_number

    feed_x, feed_y = feed_start
    splitter_x = feed_x + 1
    splitter_y = feed_y
    entity_number = _ensure_splitter_input_belt(
        grid,
        entities,
        entity_number,
        splitter_x,
        splitter_y,
        feed_from=feed_start,
        direction=FACTORIO_EAST,
    )

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
            "Splitter needed at feed %s for %s but tiles occupied; using belt fallback",
            feed_start,
            resource,
        )
        for route in routes:
            entity_number = connect_lane_to_lane(
                grid,
                entities,
                entity_number,
                feed_start,
                route["anchor"],
                source_knot=None,
                dest_knot=route["dest_knot"],
            )
        return entity_number

    logger.info(
        "Placed splitter at (%s, %s) feeding %s consumers from input feed %s",
        splitter_x,
        splitter_y,
        len(unique_ends),
        feed_start,
    )

    path_ends = []
    for route in routes:
        ex, ey = route["end"]
        approach = (ex - 1, ey) if ex > feed_x + 3 else (ex, ey)
        path_ends.append(approach if approach != route["end"] else route["end"])

    sorted_pairs = sorted(zip(routes, path_ends), key=lambda pair: pair[1][1])
    sorted_ends = [end for _, end in sorted_pairs]
    branch_starts = _assign_splitter_branch_starts(
        splitter_x, splitter_y, sorted_ends
    )
    entity_number = _route_from_splitter_branches(
        grid, entities, entity_number, branch_starts, sorted_ends
    )

    for route, end in sorted_pairs:
        if end == route["end"]:
            continue
        tail = _manhattan_path(end, route["end"])
        entity_number = place_belt_path(grid, entities, entity_number, tail)

    if placement_recorder is not None:
        placement_recorder.record(
            "splitter",
            f"Input feed splitter: {resource}",
            [
                f"Feed start {feed_start}",
                f"Consumers: {len(unique_ends)}",
                f"Splitter at ({splitter_x}, {splitter_y})",
            ],
            entities,
            highlights=[feed_start, (splitter_x, splitter_y)],
        )

    return entity_number


def connect_base_materials(
    grid,
    entities,
    entity_number,
    stage_machines,
    nodes,
    *,
    input_sources: dict[str, list[tuple[int, int]]] | None = None,
    placement_recorder=None,
):
    """
    Route base materials from input chests directly to machine input lanes.

    Uses the same ``connect_lane_to_lane`` pathing as stage-to-stage links.
    Requires a user-placed input cell per resource (``input_sources``); horizontal
    top-of-map buses are disabled for now.
    """
    from planners.machine_io import (
        chest_belt_feed_start,
        chest_to_belt_knot,
        ingredient_lane_offsets,
        machine_input_inserter_knot,
        recipe_input_lane_count,
    )

    input_sources = input_sources or {}
    base_demands: dict[str, list[dict]] = {}
    for item, node in nodes.items():
        if item not in stage_machines:
            continue
        consumer_recipe = getattr(node, "recipe", None) or {}
        from planners.machine_io import ingredient_lane_index

        for machine in stage_machines[item]:
            mx, my, w, h = machine
            lane_count = recipe_input_lane_count(consumer_recipe)
            lanes = machine_io_lanes(mx, my, w, h, input_lane_count=lane_count)
            input_connects = lanes.get(
                "input_connects",
                lanes.get("input_starts", [lanes["input_start"]]),
            )
            offsets = ingredient_lane_offsets(lane_count)

            for dep in node.dependencies:
                if dep not in BASE_MATERIALS:
                    continue
                lane_idx = ingredient_lane_index(consumer_recipe, dep)
                anchor = input_connects[min(lane_idx, len(input_connects) - 1)]
                lane_offset = offsets[min(lane_idx, len(offsets) - 1)]
                base_demands.setdefault(dep, []).append(
                    {
                        "anchor": anchor,
                        "machine": machine,
                        "lane_offset": lane_offset,
                    }
                )

    if not base_demands:
        return entity_number, {}

    blueprint_inputs: dict[str, tuple[int, int]] = {}

    for resource in sorted(base_demands.keys()):
        demand_points = base_demands[resource]
        input_points = [d["anchor"] for d in demand_points]
        sources = input_sources.get(resource, [])
        if not sources:
            logger.info(
                "No input cell for %s; place an input cell to route this resource",
                resource,
            )
            continue

        # Many-to-many: when there are multiple input cells for a resource, assign
        # each consumer lane to the nearest source and route those groups.
        # This prevents one arbitrary source from trying (and often failing) to
        # reach the entire layout.
        def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        # Keep legacy return shape (resource -> one representative chest).
        chest_x0, chest_y0 = sources[0]
        blueprint_inputs[resource] = (chest_x0, chest_y0)

        # Group consumer inputs by chosen source chest.
        consumers_by_source: dict[tuple[int, int], list[dict]] = {
            src: [] for src in sources
        }
        for demand in demand_points:
            consumer_input = demand["anchor"]
            best_src = min(
                sources,
                key=lambda src: _manhattan(
                    chest_belt_feed_start(src[0], src[1]), consumer_input
                ),
            )
            consumers_by_source[best_src].append(demand)

        used_sources = [(sx, sy) for (sx, sy), pts in consumers_by_source.items() if pts]
        logger.info(
            "Routing %s from %s input cell(s) to %s machine input(s)",
            resource,
            len(used_sources),
            len(input_points),
        )

        for chest_x, chest_y in used_sources:
            feed_start = chest_belt_feed_start(chest_x, chest_y)
            chest_knot = chest_to_belt_knot(chest_x, chest_y)
            grouped = consumers_by_source[(chest_x, chest_y)]
            logger.info(
                "Routing %s from input at (%s, %s) to %s machine input(s)",
                resource,
                chest_x,
                chest_y,
                len(grouped),
            )
            entity_number = _connect_feed_fanout(
                grid,
                entities,
                entity_number,
                feed_start,
                chest_knot,
                grouped,
                resource=resource,
                placement_recorder=placement_recorder,
            )
            for demand in grouped:
                logger.info(
                    "Routed %s from %s to %s",
                    resource,
                    feed_start,
                    demand["anchor"],
                )

        if placement_recorder is not None:
            all_sources = list(sources)
            placement_recorder.record(
                "base_feed",
                f"Base material feed: {resource}",
                [
                    f"Input cells: {', '.join(f'({sx}, {sy})' for sx, sy in all_sources)}",
                    f"Direct routes to {len(input_points)} machine input(s)",
                ],
                entities,
                highlights=all_sources + list(input_points),
            )

    return entity_number, blueprint_inputs
