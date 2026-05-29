"""Belt-aware A* with optional underground meta-edges."""

from __future__ import annotations

import heapq
import logging
from typing import TYPE_CHECKING

from core.constants import (
    FACTORIO_EAST,
    FACTORIO_NORTH,
    FACTORIO_SOUTH,
    FACTORIO_WEST,
    UNDERGROUND_BELT_MAX_UNDERGROUND_TILES,
    direction_for_flow,
)

from planners.belt_network.occupancy import TileRole

if TYPE_CHECKING:
    from planners.belt_network.occupancy import RoutingOccupancy

logger = logging.getLogger(__name__)

_NEIGHBORS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


class RouteConflict(Exception):
    """Raised when no valid path exists after search and amendments."""

    def __init__(self, start, end, item: str, reason: str = ""):
        self.start = start
        self.end = end
        self.item = item
        self.reason = reason
        super().__init__(f"No route for {item} from {start} to {end}: {reason}")


class BeltPathfinder:
    """A* on empty / same-item belt tiles; optional straight UG jumps."""

    def __init__(self, occupancy: RoutingOccupancy, *, allow_underground: bool = True):
        self.occupancy = occupancy
        self.allow_underground = allow_underground
        self.grid = occupancy.grid
        self._bounds: tuple[int, int, int, int] | None = None

    def _set_search_bounds(self, start, goal, margin: int = 48) -> None:
        min_x = min(start[0], goal[0]) - margin
        max_x = max(start[0], goal[0]) + margin
        min_y = min(start[1], goal[1]) - margin
        max_y = max(start[1], goal[1]) + margin
        self._bounds = (min_x, max_x, min_y, max_y)

    def _in_bounds(self, x: int, y: int) -> bool:
        if self._bounds is None:
            return True
        min_x, max_x, min_y, max_y = self._bounds
        return min_x <= x <= max_x and min_y <= y <= max_y

    def heuristic(self, a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _goal_walkable(self, pos: tuple[int, int], item: str) -> bool:
        x, y = pos
        if not self.grid.is_occupied(x, y):
            return True
        return self.occupancy.is_walkable(x, y, item)

    def _neighbors(self, pos: tuple[int, int], item: str) -> list[tuple[tuple[int, int], int]]:
        x, y = pos
        out: list[tuple[tuple[int, int], int]] = []
        for dx, dy in _NEIGHBORS:
            nx, ny = x + dx, y + dy
            if not self._in_bounds(nx, ny):
                continue
            cost = self.occupancy.step_cost(nx, ny, item)
            if cost is not None:
                out.append(((nx, ny), cost))
        if self.allow_underground:
            out.extend(self._underground_neighbors(pos, item))
        return out

    def _underground_neighbors(
        self, pos: tuple[int, int], item: str
    ) -> list[tuple[tuple[int, int], int]]:
        """Meta-edges: jump up to 4 tiles along a straight axis (vanilla UG span)."""
        x, y = pos
        results: list[tuple[tuple[int, int], int]] = []
        max_span = UNDERGROUND_BELT_MAX_UNDERGROUND_TILES.get("underground-belt", 4)
        for dx, dy in _NEIGHBORS:
            direction = direction_for_flow(pos, (x + dx, y + dy))
            if direction is None:
                continue
            cx, cy = x + dx, y + dy
            span = 0
            while span < max_span:
                if not self._can_underground_step(cx, cy, item):
                    break
                span += 1
                nx, ny = cx, cy
                exit_cost = 3 + span
                if self._goal_walkable((nx, ny), item) or self.occupancy.is_walkable(nx, ny, item):
                    results.append(((nx, ny), exit_cost))
                cx += dx
                cy += dy
        return results

    def _can_underground_step(self, x: int, y: int, item: str) -> bool:
        if not self.grid.is_occupied(x, y):
            return True
        role = self.occupancy.tile_role(x, y, item)
        return role in (TileRole.BELT, TileRole.TRUNK)

    def shortest_path(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        item: str,
    ) -> list[tuple[int, int]] | None:
        if start == end:
            return [start]
        self._set_search_bounds(start, end)
        if not self._goal_walkable(end, item):
            logger.error("Goal %s not walkable for item %s", end, item)
            return None

        open_set: list[tuple[int, tuple[int, int]]] = []
        heapq.heappush(open_set, (0, start))
        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        g_score: dict[tuple[int, int], int] = {start: 0}

        while open_set:
            _, current = heapq.heappop(open_set)
            if current == end:
                return self._reconstruct(came_from, current)

            for neighbor, step_cost in self._neighbors(current, item):
                tentative = g_score[current] + step_cost
                if neighbor not in g_score or tentative < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative
                    f = tentative + self.heuristic(neighbor, end)
                    heapq.heappush(open_set, (f, neighbor))

        return None

    def _reconstruct(
        self, came_from: dict[tuple[int, int], tuple[int, int]], current: tuple[int, int]
    ) -> list[tuple[int, int]]:
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path

    def route_or_conflict(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        item: str,
        *,
        allow_empty_manhattan: bool = True,
    ) -> list[tuple[int, int]]:
        path = self.shortest_path(start, end, item)
        if path and len(path) >= 1:
            return path
        if allow_empty_manhattan:
            empty_path = self._empty_only_manhattan(start, end, item)
            if empty_path:
                logger.warning(
                    "A* failed for %s %s->%s; using empty-only Manhattan",
                    item,
                    start,
                    end,
                )
                return empty_path
        raise RouteConflict(start, end, item, "no path")

    def _empty_only_manhattan(
        self, start: tuple[int, int], end: tuple[int, int], item: str
    ) -> list[tuple[int, int]] | None:
        """L-shaped path using only empty or same-item walkable tiles (no hard obstacles)."""
        path = [start]
        x, y = start
        end_x, end_y = end

        step = 1 if end_x >= x else -1
        while x != end_x:
            x += step
            if not self.occupancy.is_walkable(x, y, item):
                return None
            path.append((x, y))

        step = 1 if end_y >= y else -1
        while y != end_y:
            y += step
            if not self.occupancy.is_walkable(x, y, item):
                return None
            path.append((x, y))

        return path
