"""Position finding utilities for machine placement"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from core.constants import machine_io_stride


class PositionFinder:
    """Find open tiles on the grid, preferring positions near a network anchor."""

    def __init__(self, grid):
        self.grid = grid
        self.logger = logging.getLogger(__name__)

    def _io_block_fits(self, x: int, y: int, width: int, height: int) -> bool:
        """True when the machine plus belt/inserter margin is clear (any flow axis)."""
        if x < 0 or y < 0:
            return False
        margin = machine_io_stride(width)
        x0 = x - margin
        y0 = y - margin
        x1 = x + width + margin
        y1 = y + height + margin
        if x1 > self.grid.width or y1 > self.grid.height:
            return False
        for check_x in range(x0, x1):
            for check_y in range(y0, y1):
                if self.grid.is_occupied(check_x, check_y):
                    return False
        return True

    def find_placement_near(
        self, pref_x: int, pref_y: int, width: int, height: int
    ) -> Tuple[Optional[int], Optional[int]]:
        """Search outward from (pref_x, pref_y) for a valid I/O block (closest first)."""
        if self._io_block_fits(pref_x, pref_y, width, height):
            return pref_x, pref_y

        max_radius = min(160, max(self.grid.width, self.grid.height))
        for radius in range(1, max_radius + 1):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if max(abs(dx), abs(dy)) != radius:
                        continue
                    x, y = pref_x + dx, pref_y + dy
                    if self._io_block_fits(x, y, width, height):
                        return x, y

        self.logger.warning(
            "No open placement near (%s, %s) for %sx%s machine",
            pref_x,
            pref_y,
            width,
            height,
        )
        return None, None

    def find_next_available_position_with_spacing(
        self, width, height, pref_x=10, pref_y=10
    ):
        """Find a machine position with belt/inserter clearance (network-aware)."""
        return self.find_placement_near(pref_x, pref_y, width, height)

    def find_next_available_position(self, width, height, pref_x=10, pref_y=10):
        """Find any machine footprint without I/O margin checks."""
        if not self.grid.is_occupied(pref_x, pref_y, width, height):
            return pref_x, pref_y
        max_r = max(self.grid.width, self.grid.height)
        for radius in range(1, max_r):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    x, y = pref_x + dx, pref_y + dy
                    if 0 <= x <= self.grid.width - width and 0 <= y <= self.grid.height - height:
                        if not self.grid.is_occupied(x, y, width, height):
                            return x, y
        return None, None
