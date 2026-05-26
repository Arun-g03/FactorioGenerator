"""
Modal for placement-strategy-specific options in the blueprint workspace.
Shows rule-based or genetic settings depending on the active placement method.
"""

from __future__ import annotations

import pygame
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.constants import PYGAME_WINDOW_HEIGHT, PYGAME_WINDOW_WIDTH, PlacementStrategy
from core.placement_settings import PlacementSettingsBundle


class PlacementOptionsModal:
    """Overlay modal for rule-based or genetic placement tunables."""

    RULE_FIELDS = [
        ("connection_gap", "Gap to upstream (tiles)", 1, 12, 1),
        ("network_seed_x", "Network start X", 0, 120, 1),
        ("network_seed_y", "Network start Y", 0, 120, 1),
        ("row_stride_y", "Row spacing (tiles)", 6, 48, 2),
    ]

    GENETIC_FIELDS = [
        ("population_size", "Population per generation", 8, 256, 8),
        ("min_generations", "Minimum generations", 1, 500, 5),
        ("max_generations", "Maximum generations", 50, 10000, 50),
        ("stale_generations_limit", "Stale limit (no improvement)", 5, 1000, 10),
        ("mutation_rate", "Mutation rate (0-1)", 0.05, 1.0, 0.05),
        ("placement_x_min", "Placement region X min", 0, 200, 1),
        ("placement_x_max", "Placement region X max", 20, 300, 5),
        ("placement_y_min", "Placement region Y min", 0, 200, 1),
        ("placement_y_max", "Placement region Y max", 10, 300, 5),
    ]

    def __init__(self, placement_strategy: PlacementStrategy, bundle: PlacementSettingsBundle):
        self.width = PYGAME_WINDOW_WIDTH
        self.height = PYGAME_WINDOW_HEIGHT
        self.logger = logging.getLogger(__name__)
        self.placement_strategy = placement_strategy
        self.bundle = bundle

        self.panel_width = 520
        field_count = (
            len(self.GENETIC_FIELDS)
            if placement_strategy == PlacementStrategy.GENETIC
            else len(self.RULE_FIELDS)
        )
        self.panel_height = 120 + field_count * 52 + 100
        self._reposition_panel()

        self.bg_color = (50, 50, 60)
        self.border_color = (100, 100, 120)
        self.row_bg = (60, 60, 72)
        self.text_color = (255, 255, 255)
        self.muted_color = (160, 160, 170)
        self.button_color = (60, 90, 150)
        self.button_hover_color = (80, 120, 200)
        self.save_color = (50, 130, 50)
        self.save_hover_color = (60, 150, 60)

        self.title_font = pygame.font.Font(None, 44)
        self.label_font = pygame.font.Font(None, 26)
        self.value_font = pygame.font.Font(None, 32)
        self.button_font = pygame.font.Font(None, 28)
        self.hint_font = pygame.font.Font(None, 22)

        self.active_field: str | None = None
        self.typing_buffer = ""
        self._row_rects: list[tuple[str, pygame.Rect, pygame.Rect, pygame.Rect]] = []

    def _reposition_panel(self) -> None:
        self.panel_x = (self.width - self.panel_width) // 2
        self.panel_y = max(40, (self.height - self.panel_height) // 2)

    def set_window_size(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._reposition_panel()

    def set_strategy(self, placement_strategy: PlacementStrategy) -> None:
        """Switch visible fields when the user toggles Rules / Genetic."""
        self.placement_strategy = placement_strategy
        field_count = (
            len(self.GENETIC_FIELDS)
            if placement_strategy == PlacementStrategy.GENETIC
            else len(self.RULE_FIELDS)
        )
        self.panel_height = 120 + field_count * 52 + 100
        self._reposition_panel()
        self.active_field = None
        self.typing_buffer = ""

    def _active_fields(self):
        if self.placement_strategy == PlacementStrategy.GENETIC:
            return self.GENETIC_FIELDS
        return self.RULE_FIELDS

    def _settings_obj(self):
        if self.placement_strategy == PlacementStrategy.GENETIC:
            return self.bundle.genetic
        return self.bundle.rule_based

    def _get_value(self, key: str):
        return getattr(self._settings_obj(), key)

    def _set_value(self, key: str, value) -> None:
        setattr(self._settings_obj(), key, value)

    def _field_bounds(self, key: str):
        for spec in self._active_fields():
            if spec[0] == key:
                return spec[2], spec[3], spec[4]
        return None, None, 1

    def _adjust_field(self, key: str, delta: float) -> None:
        lo, hi, step = self._field_bounds(key)
        current = self._get_value(key)
        if isinstance(current, float):
            new_val = round(current + delta * step, 2)
            new_val = max(lo, min(hi, new_val))
        else:
            new_val = int(current) + int(delta * step)
            new_val = max(int(lo), min(int(hi), new_val))
        self._set_value(key, new_val)

    def _commit_typing(self) -> None:
        if not self.active_field:
            return
        key = self.active_field
        lo, hi, _ = self._field_bounds(key)
        text = self.typing_buffer.strip()
        try:
            if isinstance(self._get_value(key), float):
                val = float(text) if text else lo
                val = max(lo, min(hi, val))
            else:
                val = int(text) if text else int(lo)
                val = max(int(lo), min(int(hi), val))
            self._set_value(key, val)
        except ValueError:
            pass
        self.active_field = None
        self.typing_buffer = ""

    def _rows_top(self) -> int:
        return self.panel_y + 88

    def _footer_y(self) -> int:
        return self.panel_y + self.panel_height - 64

    def _build_row_rects(self) -> None:
        self._row_rects = []
        y = self._rows_top()
        for key, _label, _lo, _hi, _step in self._active_fields():
            row_rect = pygame.Rect(self.panel_x + 16, y, self.panel_width - 32, 44)
            minus_rect = pygame.Rect(row_rect.right - 148, row_rect.y + 6, 36, 32)
            plus_rect = pygame.Rect(row_rect.right - 104, row_rect.y + 6, 36, 32)
            value_rect = pygame.Rect(row_rect.right - 64, row_rect.y + 6, 56, 32)
            self._row_rects.append((key, row_rect, minus_rect, plus_rect, value_rect))
            y += 52

    def _format_value(self, key: str) -> str:
        val = self._get_value(key)
        if isinstance(val, float):
            return f"{val:.2f}".rstrip("0").rstrip(".")
        return str(val)

    def draw(self, screen: pygame.Surface) -> None:
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        panel_rect = pygame.Rect(self.panel_x, self.panel_y, self.panel_width, self.panel_height)
        pygame.draw.rect(screen, self.bg_color, panel_rect, border_radius=8)
        pygame.draw.rect(screen, self.border_color, panel_rect, width=2, border_radius=8)

        title = (
            "Genetic placement options"
            if self.placement_strategy == PlacementStrategy.GENETIC
            else "Rule-based placement options"
        )
        title_surf = self.title_font.render(title, True, (255, 200, 80))
        screen.blit(title_surf, (self.panel_x + 20, self.panel_y + 16))

        subtitle = (
            "Evolution and search region for machine positions"
            if self.placement_strategy == PlacementStrategy.GENETIC
            else "Network layout spacing and seed position"
        )
        sub_surf = self.hint_font.render(subtitle, True, self.muted_color)
        screen.blit(sub_surf, (self.panel_x + 20, self.panel_y + 52))

        mouse_pos = pygame.mouse.get_pos()
        self._build_row_rects()

        for key, row_rect, minus_rect, plus_rect, value_rect in self._row_rects:
            pygame.draw.rect(screen, self.row_bg, row_rect, border_radius=4)
            label = next(l for k, l, *_ in self._active_fields() if k == key)
            label_surf = self.label_font.render(label, True, self.text_color)
            screen.blit(label_surf, (row_rect.x + 10, row_rect.y + 12))

            for rect, text, base in (
                (minus_rect, "-", self.button_color),
                (plus_rect, "+", self.button_color),
            ):
                color = self.button_hover_color if rect.collidepoint(mouse_pos) else base
                pygame.draw.rect(screen, color, rect, border_radius=4)
                t = self.button_font.render(text, True, self.text_color)
                screen.blit(t, t.get_rect(center=rect.center))

            if self.active_field == key:
                pygame.draw.rect(screen, (80, 90, 110), value_rect, border_radius=4)
                pygame.draw.rect(screen, (255, 255, 255), value_rect, width=2, border_radius=4)
                display = self.typing_buffer + "|"
            else:
                pygame.draw.rect(screen, (45, 48, 58), value_rect, border_radius=4)
                display = self._format_value(key)
            val_surf = self.value_font.render(display, True, self.text_color)
            screen.blit(val_surf, val_surf.get_rect(center=value_rect.center))

        footer_y = self._footer_y()
        save_rect = pygame.Rect(self.panel_x + self.panel_width - 240, footer_y, 110, 40)
        close_rect = pygame.Rect(self.panel_x + self.panel_width - 120, footer_y, 100, 40)

        for rect, label, base, hover in (
            (save_rect, "Save", self.save_color, self.save_hover_color),
            (close_rect, "Close", self.button_color, self.button_hover_color),
        ):
            color = hover if rect.collidepoint(mouse_pos) else base
            pygame.draw.rect(screen, color, rect, border_radius=5)
            t = self.button_font.render(label, True, self.text_color)
            screen.blit(t, t.get_rect(center=rect.center))

        hint = "Click value to type  |  +/- buttons  |  ESC to close without saving"
        hint_surf = self.hint_font.render(hint, True, self.muted_color)
        screen.blit(
            hint_surf,
            hint_surf.get_rect(midtop=(self.panel_x + self.panel_width // 2, footer_y + 48)),
        )

    def handle_click(self, mouse_pos) -> str | None:
        """Return 'save', 'close', or None."""
        self._commit_typing()
        self._build_row_rects()

        footer_y = self._footer_y()
        save_rect = pygame.Rect(self.panel_x + self.panel_width - 240, footer_y, 110, 40)
        close_rect = pygame.Rect(self.panel_x + self.panel_width - 120, footer_y, 100, 40)
        if save_rect.collidepoint(mouse_pos):
            self.bundle.rule_based = self.bundle.rule_based.clamp()
            self.bundle.genetic = self.bundle.genetic.clamp()
            return "save"
        if close_rect.collidepoint(mouse_pos):
            return "close"

        panel_rect = pygame.Rect(self.panel_x, self.panel_y, self.panel_width, self.panel_height)
        if not panel_rect.collidepoint(mouse_pos):
            return "close"

        for key, _row, minus_rect, plus_rect, value_rect in self._row_rects:
            if minus_rect.collidepoint(mouse_pos):
                self._adjust_field(key, -1)
                return None
            if plus_rect.collidepoint(mouse_pos):
                self._adjust_field(key, 1)
                return None
            if value_rect.collidepoint(mouse_pos):
                self.active_field = key
                self.typing_buffer = self._format_value(key)
                return None

        return None

    def handle_key(self, event) -> str | None:
        if event.type != pygame.KEYDOWN:
            return None
        if event.key == pygame.K_ESCAPE:
            self._commit_typing()
            return "close"
        if self.active_field:
            if event.key == pygame.K_RETURN:
                self._commit_typing()
                return None
            if event.key == pygame.K_BACKSPACE:
                self.typing_buffer = self.typing_buffer[:-1]
                return None
            if event.unicode and event.unicode.isprintable():
                if event.unicode.isdigit() or event.unicode in ".-":
                    self.typing_buffer += event.unicode
                return None
        return None

    def blocks_workspace_input(self) -> bool:
        return True
