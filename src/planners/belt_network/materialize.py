"""Stamp belts, splitters, and undergrounds for routed links."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.constants import FACTORIO_EAST
from planners.belt_network.amendments import route_with_amendments
from planners.belt_network.link_graph import BeltLink
from planners.belt_network.pathfinder import BeltPathfinder, RouteConflict
from planners.machine_io import place_inserter_knot
from planners.stage_connector import (
    _assign_splitter_branch_starts,
    _ensure_splitter_input_belt,
    _manhattan_path,
    _needs_splitter_fanout_from_links,
    _place_splitter,
    _route_from_splitter_branches,
    place_belt_path,
)

if TYPE_CHECKING:
    from planners.belt_network.occupancy import RoutingOccupancy

logger = logging.getLogger(__name__)


def _unique_sinks(links: list[BeltLink]) -> set[tuple[int, int]]:
    return {link.sink for link in links}


def materialize_fanout_group(
    grid,
    entities,
    entity_number: int,
    occupancy: RoutingOccupancy,
    links: list[BeltLink],
    *,
    feed_from: tuple[int, int] | None = None,
    source_knot=None,
) -> int:
    """Place splitter fan-out for a group sharing one feed tile."""
    if not links:
        return entity_number

    feed = feed_from or links[0].source
    entity_number = place_inserter_knot(grid, entities, entity_number, source_knot)

    routes = []
    for link in links:
        routes.append({"end": link.sink, "dest_knot": link.dest_knot, "anchor": link.metadata.get("anchor", link.sink)})

    unique_ends = {r["end"] for r in routes}
    if len(routes) == 1 or len(unique_ends) < 2:
        return materialize_single_link(
            grid, entities, entity_number, occupancy, links[0]
        )

    feed_x, feed_y = feed
    splitter_x = feed_x + 1
    splitter_y = feed_y
    entity_number = _ensure_splitter_input_belt(
        grid,
        entities,
        entity_number,
        splitter_x,
        splitter_y,
        feed_from=feed,
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
        logger.warning("Splitter blocked at %s; belt fallback", feed)
        for link in links:
            entity_number = materialize_single_link(
                grid, entities, entity_number, occupancy, link
            )
        return entity_number

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
        occupancy.register_trunk(links[0].item, tail)

    trunk_tiles = list(branch_starts) + sorted_ends
    occupancy.register_trunk(links[0].item, trunk_tiles)
    return entity_number


def materialize_single_link(
    grid,
    entities,
    entity_number: int,
    occupancy: RoutingOccupancy,
    link: BeltLink,
) -> int:
    """Route and stamp one belt link; register trunk tiles."""
    entity_number = place_inserter_knot(grid, entities, entity_number, link.source_knot)
    entity_number = place_inserter_knot(grid, entities, entity_number, link.dest_knot)

    start = link.source
    end = link.sink
    if start == end:
        return entity_number

    pathfinder = BeltPathfinder(occupancy, allow_underground=True)
    try:
        path = route_with_amendments(pathfinder, link, start, end)
    except RouteConflict:
        logger.warning(
            "Could not route %s from %s to %s; skipping belts",
            link.item,
            start,
            end,
        )
        return entity_number

    entity_number = place_belt_path(grid, entities, entity_number, path)
    occupancy.register_trunk(link.item, path)

    if link.lane_offset != 0:
        meta = link.metadata
        consumer_input = meta.get("consumer_input_start")
        if consumer_input:
            in_x, in_y = consumer_input
            target_y = meta.get("target_y", in_y)
            merge_start = (in_x - 1, target_y)
            try:
                merge_path = route_with_amendments(
                    pathfinder, link, merge_start, (in_x, in_y)
                )
            except RouteConflict:
                merge_path = _manhattan_path(merge_start, (in_x, in_y))
            entity_number = place_belt_path(
                grid, entities, entity_number, merge_path
            )
            occupancy.register_trunk(link.item, merge_path)

    return entity_number


def materialize_link_group(
    grid,
    entities,
    entity_number: int,
    occupancy: RoutingOccupancy,
    links: list[BeltLink],
) -> int:
    """Materialize one or more links that share a group_key."""
    if not links:
        return entity_number

    if _needs_splitter_fanout_from_links(links):
        feed = links[0].source
        source_knot = links[0].source_knot
        return materialize_fanout_group(
            grid,
            entities,
            entity_number,
            occupancy,
            links,
            feed_from=feed,
            source_knot=source_knot,
        )

    for link in links:
        entity_number = materialize_single_link(
            grid, entities, entity_number, occupancy, link
        )
    return entity_number
