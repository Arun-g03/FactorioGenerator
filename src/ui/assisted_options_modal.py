"""
Modal for Assisted Build workspace options (routing and display).
"""

from __future__ import annotations

import pygame
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.assisted_settings import AssistedBuildSettings
from core.constants import PYGAME_WINDOW_HEIGHT, PYGAME_WINDOW_WIDTH


class AssistedBuildOptionsModal:
    """Overlay modal for Assisted Build tunables."""

    BOOL_FIELDS = [
        ("auto_route_on_change", "Auto-route when layout changes"),
        ("incremental_reroute", "Incremental reroute (experimental)"),
        ("show_machine_labels", "Show machine / I/O labels"),
    ]

    INT_FIELDS = [
        ("palette_width", "Palette width (pixels)", 160, 420, 10),
        ("optimization_stale_limit", "Opt. search stale limit (iters)", 3, 500, 5),
        ("optimization_max_iterations", "Opt. search max iters (0=∞)", 0, 10000, 50),
    ]

    def __init__(self, settings: AssistedBuildSettings):
        self.width = PYGAME_WINDOW_WIDTH
        self.height = PYGAME_WINDOW_HEIGHT
        self.logger = logging.getLogger(__name__)
        self.settings = settings

        self.panel_width = 520
        field_count = len(self.BOOL_FIELDS) + len(self.INT_FIELDS)
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
        self._row_rects: list[tuple[str, pygame.Rect, pygame.Rect, pygame.Rect, pygame.Rect]] = []

    def _reposition_panel(self) -> None:
        self.panel_x = (self.width - self.panel_width) // 2
        self.panel_y = max(40, (self.height - self.panel_height) // 2)

    def set_window_size(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._reposition_panel()

    def _is_bool_field(self, key: str) -> bool:
        return key in {spec[0] for spec in self.BOOL_FIELDS}

    def _get_value(self, key: str):
        return getattr(self.settings, key)

    def _set_value(self, key: str, value) -> None:
        setattr(self.settings, key, value)

    def _int_bounds(self, key: str):
        for spec in self.INT_FIELDS:
            if spec[0] == key:
                return spec[2], spec[3], spec[4]
        return None, None, 1

    def _adjust_field(self, key: str, delta: float) -> None:
        if self._is_bool_field(key):
            self._set_value(key, not self._get_value(key))
            return
        lo, hi, step = self._int_bounds(key)
        current = self._get_value(key)
        new_val = int(current) + int(delta * step)
        new_val = max(int(lo), min(int(hi), new_val))
        self._set_value(key, new_val)

    def _commit_typing(self) -> None:
        if not self.active_field or self._is_bool_field(self.active_field):
            self.active_field = None
            self.typing_buffer = ""
            return
        key = self.active_field
        lo, hi, _ = self._int_bounds(key)
        text = self.typing_buffer.strip()
        try:
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
        for key, _label in self.BOOL_FIELDS:
            row_rect = pygame.Rect(self.panel_x + 16, y, self.panel_width - 32, 44)
            minus_rect = pygame.Rect(row_rect.right - 148, row_rect.y + 6, 36, 32)
            plus_rect = pygame.Rect(row_rect.right - 104, row_rect.y + 6, 36, 32)
            value_rect = pygame.Rect(row_rect.right - 64, row_rect.y + 6, 56, 32)
            self._row_rects.append((key, row_rect, minus_rect, plus_rect, value_rect))
            y += 52
        for key, _label, _lo, _hi, _step in self.INT_FIELDS:
            row_rect = pygame.Rect(self.panel_x + 16, y, self.panel_width - 32, 44)
            minus_rect = pygame.Rect(row_rect.right - 148, row_rect.y + 6, 36, 32)
            plus_rect = pygame.Rect(row_rect.right - 104, row_rect.y + 6, 36, 32)
            value_rect = pygame.Rect(row_rect.right - 64, row_rect.y + 6, 56, 32)
            self._row_rects.append((key, row_rect, minus_rect, plus_rect, value_rect))
            y += 52

    def _format_value(self, key: str) -> str:
        val = self._get_value(key)
        if self._is_bool_field(key):
            return "On" if val else "Off"
        return str(val)

    def draw(self, screen: pygame.Surface) -> None:
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        panel_rect = pygame.Rect(self.panel_x, self.panel_y, self.panel_width, self.panel_height)
        pygame.draw.rect(screen, self.bg_color, panel_rect, border_radius=8)
        pygame.draw.rect(screen, self.border_color, panel_rect, width=2, border_radius=8)

        title_surf = self.title_font.render("Assisted Build options", True, (255, 200, 80))
        screen.blit(title_surf, (self.panel_x + 20, self.panel_y + 16))

        subtitle = "Routing behavior and workspace display"
        sub_surf = self.hint_font.render(subtitle, True, self.muted_color)
        screen.blit(sub_surf, (self.panel_x + 20, self.panel_y + 52))

        mouse_pos = pygame.mouse.get_pos()
        self._build_row_rects()
        labels = {k: lbl for k, lbl in self.BOOL_FIELDS}
        labels.update({k: lbl for k, lbl, *_ in self.INT_FIELDS})

        for key, row_rect, minus_rect, plus_rect, value_rect in self._row_rects:
            pygame.draw.rect(screen, self.row_bg, row_rect, border_radius=4)
            label_surf = self.label_font.render(labels[key], True, self.text_color)
            screen.blit(label_surf, (row_rect.x + 10, row_rect.y + 12))

            for rect, text, base in (
                (minus_rect, "-", self.button_color),
                (plus_rect, "+", self.button_color),
            ):
                color = self.button_hover_color if rect.collidepoint(mouse_pos) else base
                pygame.draw.rect(screen, color, rect, border_radius=4)
                t = self.button_font.render(text, True, self.text_color)
                screen.blit(t, t.get_rect(center=rect.center))

            if self.active_field == key and not self._is_bool_field(key):
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

        hint = "Click value to type (numbers)  |  +/- toggles  |  ESC closes without saving"
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
            self.settings = self.settings.clamp()
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
                if self._is_bool_field(key):
                    self._adjust_field(key, 1)
                else:
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
                if event.unicode.isdigit():
                    self.typing_buffer += event.unicode
                return None
        return None
