"""
Factorio splitter footprint and belt connection geometry.

A splitter is **2×1** when facing east/west (two parallel lanes along X) and **1×2**
when facing north/south (two parallel lanes along Y).

Vanilla splitters expose:
- **One merge input face** (two lane slots; belts usually meet one tile west/east/etc.)
- **Two output lanes** on the opposite face (offset perpendicular to flow so both
  branches can leave on separate belt rows).

Planner coordinates use the **top-left** footprint tile as ``anchor`` (same as
``position`` in entity dicts before blueprint export centering).
"""

from __future__ import annotations

from dataclasses import dataclass

from core.constants import (
    FACTORIO_EAST,
    FACTORIO_NORTH,
    FACTORIO_SOUTH,
    FACTORIO_WEST,
)


@dataclass(frozen=True)
class SplitterLayout:
    """Belt-relevant tiles for one placed splitter."""

    anchor: tuple[int, int]
    direction: int
    footprint: frozenset[tuple[int, int]]
    input_belt: tuple[int, int]
    output_belts: frozenset[tuple[int, int]]
    input_merge_lanes: frozenset[tuple[int, int]]

    @property
    def width(self) -> int:
        xs = [t[0] for t in self.footprint]
        return max(xs) - min(xs) + 1

    @property
    def height(self) -> int:
        ys = [t[1] for t in self.footprint]
        return max(ys) - min(ys) + 1


def splitter_footprint_size(direction: int) -> tuple[int, int]:
    """Grid (width, height) for a splitter facing ``direction``."""
    if direction in (FACTORIO_NORTH, FACTORIO_SOUTH):
        return 1, 2
    return 2, 1


def splitter_layout(
    anchor: tuple[int, int],
    direction: int = FACTORIO_EAST,
) -> SplitterLayout:
    """
    Return footprint and belt connection tiles for a splitter at ``anchor``.

    ``anchor`` is the top-left tile of the 2×1 / 1×2 footprint.
    """
    ax, ay = anchor

    if direction == FACTORIO_EAST:
        footprint = frozenset({(ax, ay), (ax + 1, ay)})
        return SplitterLayout(
            anchor=anchor,
            direction=direction,
            footprint=footprint,
            input_belt=(ax - 1, ay),
            output_belts=frozenset({(ax + 2, ay - 1), (ax + 2, ay + 1)}),
            input_merge_lanes=frozenset({(ax - 1, ay - 1), (ax - 1, ay + 1)}),
        )

    if direction == FACTORIO_WEST:
        footprint = frozenset({(ax, ay), (ax + 1, ay)})
        return SplitterLayout(
            anchor=anchor,
            direction=direction,
            footprint=footprint,
            input_belt=(ax + 2, ay),
            output_belts=frozenset({(ax - 1, ay - 1), (ax - 1, ay + 1)}),
            input_merge_lanes=frozenset({(ax + 2, ay - 1), (ax + 2, ay + 1)}),
        )

    if direction == FACTORIO_SOUTH:
        footprint = frozenset({(ax, ay), (ax, ay + 1)})
        return SplitterLayout(
            anchor=anchor,
            direction=direction,
            footprint=footprint,
            input_belt=(ax, ay - 1),
            output_belts=frozenset({(ax - 1, ay + 2), (ax + 1, ay + 2)}),
            input_merge_lanes=frozenset({(ax - 1, ay - 1), (ax + 1, ay - 1)}),
        )

    if direction == FACTORIO_NORTH:
        footprint = frozenset({(ax, ay), (ax, ay + 1)})
        return SplitterLayout(
            anchor=anchor,
            direction=direction,
            footprint=footprint,
            input_belt=(ax, ay + 2),
            output_belts=frozenset({(ax - 1, ay - 1), (ax + 1, ay - 1)}),
            input_merge_lanes=frozenset({(ax - 1, ay + 2), (ax + 1, ay + 2)}),
        )

    return splitter_layout(anchor, FACTORIO_EAST)


def splitter_flow_edges(
    anchor: tuple[int, int],
    direction: int = FACTORIO_EAST,
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """
    Directed belt-flow edges through a splitter (for flow_connectivity).

    Models internal lane transfer plus input/output belt tiles.
    """
    layout = splitter_layout(anchor, direction)
    edges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    footprint = sorted(layout.footprint)

    if len(footprint) == 2:
        edges.append((footprint[0], footprint[1]))
        edges.append((footprint[1], footprint[0]))

    edges.append((layout.input_belt, footprint[0]))
    if footprint[1] != footprint[0]:
        edges.append((layout.input_belt, footprint[1]))

    for lane in layout.input_merge_lanes:
        for tile in layout.footprint:
            edges.append((lane, tile))

    for tile in layout.footprint:
        for out in layout.output_belts:
            edges.append((tile, out))

    return edges


def anchor_for_feed(
    feed: tuple[int, int],
    direction: int = FACTORIO_EAST,
) -> tuple[int, int]:
    """Top-left splitter tile when the primary input belt sits at ``feed``."""
    layout = splitter_layout((0, 0), direction)
    fx, fy = feed
    ix, iy = layout.input_belt
    return (fx - ix, fy - iy)


def find_splitter_at(
    entities: list[dict],
    feed: tuple[int, int],
    *,
    flow_direction: int = FACTORIO_EAST,
) -> SplitterLayout | None:
    """Return splitter layout if a splitter is placed for ``feed`` (east-flow default)."""
    anchor = anchor_for_feed(feed, flow_direction)
    for entity in entities:
        if "splitter" not in entity.get("name", ""):
            continue
        pos = entity.get("position") or {}
        ex, ey = int(round(pos.get("x", 0))), int(round(pos.get("y", 0)))
        if (ex, ey) == anchor and entity.get("direction", flow_direction) == flow_direction:
            return splitter_layout((ex, ey), flow_direction)
    return None
