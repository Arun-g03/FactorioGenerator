"""Routing occupancy: item-tagged belts, trunks, and hard obstacles."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.grid_env import Grid


class TileRole(str, Enum):
    EMPTY = "empty"
    HARD = "hard"
    BELT = "belt"
    TRUNK = "trunk"
    UG_SPAN = "ug_span"


def _is_belt_name(name: str) -> bool:
    return "transport-belt" in name or "underground-belt" in name


def _is_hard_name(name: str) -> bool:
    if not name:
        return False
    if _is_belt_name(name):
        return False
    if "splitter" in name:
        return True
    if "inserter" in name:
        return True
    return True


class RoutingOccupancy:
    """
    Item-aware view over a placement grid.

    Uses ``grid.belt_lanes`` for per-tile item tags and a trunk registry for
    shared corridors built by earlier links in the same group.
    """

    def __init__(self, grid: Grid):
        self.grid = grid
        self._trunks: dict[str, set[tuple[int, int]]] = {}

    def item_at(self, x: int, y: int) -> str | None:
        lanes = self.grid.belt_lanes.get((x, y))
        if not lanes:
            return None
        return lanes[0] or lanes[1]

    def mark_belt(self, x: int, y: int, item: str) -> None:
        self.grid.mark_resource_lane(x, y, item)

    def register_trunk(self, item: str, tiles: list[tuple[int, int]]) -> None:
        self._trunks.setdefault(item, set()).update(tiles)
        for x, y in tiles:
            tagged = self.item_at(x, y)
            if tagged is None:
                self.mark_belt(x, y, item)
            elif tagged != item:
                self.mark_belt(x, y, item)

    def trunk_tiles(self, item: str) -> set[tuple[int, int]]:
        return self._trunks.get(item, set())

    def tile_role(self, x: int, y: int, item: str) -> TileRole:
        if (x, y) in self._trunks.get(item, set()):
            return TileRole.TRUNK
        if not self.grid.is_occupied(x, y):
            return TileRole.EMPTY
        occupant = self.grid.occupied.get((x, y), "")
        if _is_belt_name(occupant):
            tagged = self.item_at(x, y)
            if tagged is None or tagged == item:
                return TileRole.BELT
            return TileRole.HARD
        return TileRole.HARD

    def is_walkable(self, x: int, y: int, item: str) -> bool:
        role = self.tile_role(x, y, item)
        return role in (TileRole.EMPTY, TileRole.BELT, TileRole.TRUNK)

    def step_cost(self, x: int, y: int, item: str) -> int | None:
        role = self.tile_role(x, y, item)
        if role == TileRole.EMPTY:
            return 1
        if role in (TileRole.BELT, TileRole.TRUNK):
            return 2
        return None
