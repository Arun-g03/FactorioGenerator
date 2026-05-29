"""

Defines the pathfinder for the Factorio Blueprint Generator.
Used for constructing paths for belts and inserters.


"""

import heapq
import logging

class Pathfinder:
    def __init__(self, grid):
        self.grid = grid
        self._bounds: tuple[int, int, int, int] | None = None

    def _set_search_bounds(self, start, goal, margin: int = 48) -> None:
        """Limit A* expansion on sparse unbounded grids."""
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

    def heuristic(self, a, b):
        """Heuristic function (Manhattan distance) for A*."""
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def get_neighbors(self, position):
        """Get valid neighboring cells in the grid (ignores occupied cells)."""
        neighbors = []
        x, y = position
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            neighbor = (x + dx, y + dy)
            nx, ny = neighbor
            if not self._in_bounds(nx, ny):
                continue
            if not self.grid.is_occupied(nx, ny):
                neighbors.append(neighbor)
        return neighbors

    def _is_belt_tile(self, x, y) -> bool:
        name = self.grid.occupied.get((x, y), "")
        return "belt" in name

    def shortest_path(self, start, goal):
        """A* algorithm to find the shortest path from start to goal."""
        logging.info(f"Finding shortest path from {start} to {goal}")
        self._set_search_bounds(start, goal)

        if self.grid.is_occupied(goal[0], goal[1]) and not self._is_belt_tile(
            goal[0], goal[1]
        ):
            logging.error(f"Goal position {goal} is occupied. Cannot find a valid path.")
            return None

        open_set = []
        heapq.heappush(open_set, (0, start))
        came_from = {}
        g_score = {start: 0}
        f_score = {start: self.heuristic(start, goal)}

        while open_set:
            _, current = heapq.heappop(open_set)

            if current == goal:
                return self.reconstruct_path(came_from, current)

            for neighbor in self.get_neighbors(current):
                tentative_g_score = g_score[current] + 1

                if neighbor not in g_score or tentative_g_score < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g_score
                    f_score[neighbor] = g_score[neighbor] + self.heuristic(neighbor, goal)
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))

        logging.error(f"No path found from {start} to {goal}")
        return None

    def reconstruct_path(self, came_from, current):
        """Reconstructs the path from the came_from dictionary."""
        total_path = [current]
        while current in came_from:
            current = came_from[current]
            total_path.append(current)
        total_path.reverse()
        logging.info(f"Path found: {total_path}")
        return total_path

    def update_graph(self):
        """No-op for compatibility - A* doesn't need a pre-built graph."""
        pass
