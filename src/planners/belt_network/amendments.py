"""Amendment operators when routing hits conflicts."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from planners.belt_network.link_graph import BeltLink
from planners.belt_network.pathfinder import BeltPathfinder, RouteConflict

if TYPE_CHECKING:
    from planners.belt_network.occupancy import RoutingOccupancy

logger = logging.getLogger(__name__)

MAX_RETRIES_PER_LINK = 3


def try_amend_path(
    pathfinder: BeltPathfinder,
    link: BeltLink,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    attempt: int,
) -> list[tuple[int, int]] | None:
    """
    Try alternate routing strategies for a blocked link.

    attempt 0: standard A* with UG
    attempt 1: A* without UG meta-edges (wider empty search)
    attempt 2: relaxed — allow walking any untagged belt tile
    """
    item = link.item
    if attempt == 0:
        return pathfinder.shortest_path(start, end, item)

    if attempt == 1:
        strict = BeltPathfinder(pathfinder.occupancy, allow_underground=False)
        return strict.shortest_path(start, end, item)

    if attempt == 2:
        return pathfinder.route_or_conflict(
            start, end, item, allow_empty_manhattan=True
        )
    return None


def route_with_amendments(
    pathfinder: BeltPathfinder,
    link: BeltLink,
    start: tuple[int, int],
    end: tuple[int, int],
) -> list[tuple[int, int]]:
    """Route a link with bounded amendment retries."""
    last_error: RouteConflict | None = None
    for attempt in range(MAX_RETRIES_PER_LINK):
        try:
            if attempt == 2:
                return pathfinder.route_or_conflict(
                    start, end, link.item, allow_empty_manhattan=True
                )
            path = try_amend_path(pathfinder, link, start, end, attempt=attempt)
            if path and len(path) >= 1:
                return path
        except RouteConflict as exc:
            last_error = exc
            logger.debug("Amendment attempt %s failed for %s", attempt, link.link_id)
    if last_error:
        raise last_error
    raise RouteConflict(start, end, link.item, "amendments exhausted")


def bump_link_priority(links: list[BeltLink], link_id: str) -> list[BeltLink]:
    """Lower numeric priority so this link routes earlier on retry."""
    out: list[BeltLink] = []
    target = None
    for link in links:
        if link.link_id == link_id:
            target = link
            break
    if target is None:
        return links
    new_priority = max(0, target.priority - 10)
    for link in links:
        if link.link_id == link_id:
            out.append(
                BeltLink(
                    link_id=link.link_id,
                    item=link.item,
                    source=link.source,
                    sink=link.sink,
                    kind=link.kind,
                    group_key=link.group_key,
                    priority=new_priority,
                    source_knot=link.source_knot,
                    dest_knot=link.dest_knot,
                    lane_offset=link.lane_offset,
                    merge_from=link.merge_from,
                    metadata=dict(link.metadata),
                )
            )
        else:
            out.append(link)
    return out
