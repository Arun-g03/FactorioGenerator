"""
Assisted Build workspace: place machines, assign recipes, auto-route belts.
"""

from __future__ import annotations

import json
import logging
import math
import sys
from pathlib import Path

import pygame

_ui = Path(__file__).parent
_src = _ui.parent
for _path in (_ui, _src):
    _p = str(_path)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.constants import (
    BASE_MATERIALS,
    PYGAME_TILE_SIZE,
    PYGAME_WINDOW_HEIGHT,
    PYGAME_WINDOW_WIDTH,
)
from core.grid_env import Grid
from planners.assisted_routing import (
    AssistedBuildState,
    recipes_for_entity,
)

INPUT_CELL_PALETTE = "input-cell"
PALETTE_ENTRIES = [INPUT_CELL_PALETTE] + [
    "stone-furnace",
    "steel-furnace",
    "electric-furnace",
    "assembling-machine-1",
    "assembling-machine-2",
    "assembling-machine-3",
    "chemical-plant",
]
from blueprint_renderer import BlueprintRenderer
from screen_manager import ScreenManager
from toolbar import Toolbar

PALETTE_WIDTH = 160
DRAG_CLICK_THRESHOLD_PX = 5


class RecipePickerModal:
    """Modal to pick a recipe for one or many machines."""

    def __init__(
        self,
        recipes: list[str],
        *,
        machine=None,
        selection_count: int = 1,
        entity_names: list[str] | None = None,
    ):
        self.machine = machine
        self.selection_count = selection_count
        self.entity_names = entity_names or (
            [machine.entity_name] if machine else []
        )
        self.recipes = recipes
        self.scroll = 0
        self.selected = 0
        self.visible_rows = 12
        self.filter_text = ""
        self.typing = False

    @property
    def is_mass(self) -> bool:
        return self.selection_count > 1

    def _filtered(self) -> list[str]:
        if not self.filter_text.strip():
            return self.recipes
        q = self.filter_text.strip().lower()
        return [r for r in self.recipes if q in r.replace("-", " ")]

    def panel_rect(self, width: int, height: int) -> pygame.Rect:
        pw, ph = 420, min(520, height - 80)
        return pygame.Rect((width - pw) // 2, (height - ph) // 2, pw, ph)

    def handle_key(self, event) -> str | None:
        items = self._filtered()
        if event.key == pygame.K_ESCAPE:
            return "close"
        if event.key == pygame.K_UP:
            self.selected = max(0, self.selected - 1)
            if self.selected < self.scroll:
                self.scroll = self.selected
        elif event.key == pygame.K_DOWN:
            self.selected = min(len(items) - 1, self.selected + 1) if items else 0
            if self.selected >= self.scroll + self.visible_rows:
                self.scroll = self.selected - self.visible_rows + 1
        elif event.key == pygame.K_RETURN and items:
            return f"pick:{items[self.selected]}"
        elif event.unicode and event.unicode.isprintable():
            self.filter_text += event.unicode
            self.selected = 0
            self.scroll = 0
        elif event.key == pygame.K_BACKSPACE:
            self.filter_text = self.filter_text[:-1]
            self.selected = 0
        return None

    def handle_click(self, mouse_pos, width: int, height: int) -> str | None:
        panel = self.panel_rect(width, height)
        if not panel.collidepoint(mouse_pos):
            return "close"
        items = self._filtered()
        row_h = 32
        list_top = panel.y + 100
        for i, item in enumerate(items[self.scroll : self.scroll + self.visible_rows]):
            row_rect = pygame.Rect(panel.x + 16, list_top + i * row_h, panel.width - 32, row_h - 4)
            if row_rect.collidepoint(mouse_pos):
                return f"pick:{item}"
        close_rect = pygame.Rect(panel.right - 100, panel.bottom - 44, 84, 36)
        if close_rect.collidepoint(mouse_pos):
            return "close"
        return None

    def draw(self, screen, width: int, height: int) -> None:
        overlay = pygame.Surface((width, height))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))

        panel = self.panel_rect(width, height)
        pygame.draw.rect(screen, (35, 38, 48), panel, border_radius=8)
        pygame.draw.rect(screen, (90, 95, 110), panel, width=2, border_radius=8)

        title_font = pygame.font.Font(None, 32)
        row_font = pygame.font.Font(None, 26)
        small = pygame.font.Font(None, 22)

        if self.is_mass:
            title = title_font.render(
                f"Set recipe ({self.selection_count} selected)", True, (255, 210, 80)
            )
        else:
            title = title_font.render("Set recipe", True, (255, 210, 80))
        screen.blit(title, (panel.x + 16, panel.y + 12))
        if self.is_mass:
            types = ", ".join(n.replace("-", " ").title() for n in self.entity_names[:3])
            if len(self.entity_names) > 3:
                types += f" +{len(self.entity_names) - 3}"
            sub = f"Applies to matching machines: {types}"
        else:
            sub = self.entity_names[0].replace("-", " ").title()
        screen.blit(small.render(sub, True, (180, 180, 190)), (panel.x + 16, panel.y + 42))
        filt = f"Filter: {self.filter_text or '(type to search)'}"
        screen.blit(small.render(filt, True, (150, 155, 170)), (panel.x + 16, panel.y + 68))

        items = self._filtered()
        row_h = 32
        list_top = panel.y + 100
        for vis_i, item in enumerate(items[self.scroll : self.scroll + self.visible_rows]):
            idx = self.scroll + vis_i
            row_rect = pygame.Rect(panel.x + 16, list_top + vis_i * row_h, panel.width - 32, row_h - 4)
            sel = idx == self.selected
            color = (70, 100, 150) if sel else (50, 55, 65)
            pygame.draw.rect(screen, color, row_rect, border_radius=4)
            label = item.replace("-", " ").title()
            screen.blit(row_font.render(label, True, (240, 240, 245)), (row_rect.x + 8, row_rect.y + 6))

        close_rect = pygame.Rect(panel.right - 100, panel.bottom - 44, 84, 36)
        pygame.draw.rect(screen, (90, 70, 70), close_rect, border_radius=5)
        close_surf = row_font.render("Close", True, (255, 255, 255))
        screen.blit(close_surf, close_surf.get_rect(center=close_rect.center))
        hint = small.render("Enter=select  Esc=close  Type to filter", True, (130, 130, 140))
        screen.blit(hint, (panel.x + 16, panel.bottom - 28))


class ResourcePickerModal:
    """Modal to assign a raw resource to input cell(s)."""

    def __init__(self, resources: list[str], selection_count: int = 1):
        self.resources = sorted(resources)
        self.selection_count = selection_count
        self.scroll = 0
        self.selected = 0
        self.visible_rows = 12
        self.filter_text = ""

    def _filtered(self) -> list[str]:
        if not self.filter_text.strip():
            return self.resources
        q = self.filter_text.strip().lower()
        return [r for r in self.resources if q in r.replace("-", " ")]

    def panel_rect(self, width: int, height: int) -> pygame.Rect:
        pw, ph = 420, min(520, height - 80)
        return pygame.Rect((width - pw) // 2, (height - ph) // 2, pw, ph)

    def handle_key(self, event) -> str | None:
        items = self._filtered()
        if event.key == pygame.K_ESCAPE:
            return "close"
        if event.key == pygame.K_UP:
            self.selected = max(0, self.selected - 1)
            if self.selected < self.scroll:
                self.scroll = self.selected
        elif event.key == pygame.K_DOWN:
            self.selected = min(len(items) - 1, self.selected + 1) if items else 0
            if self.selected >= self.scroll + self.visible_rows:
                self.scroll = self.selected - self.visible_rows + 1
        elif event.key == pygame.K_RETURN and items:
            return f"pick:{items[self.selected]}"
        elif event.unicode and event.unicode.isprintable():
            self.filter_text += event.unicode
            self.selected = 0
            self.scroll = 0
        elif event.key == pygame.K_BACKSPACE:
            self.filter_text = self.filter_text[:-1]
            self.selected = 0
        return None

    def handle_click(self, mouse_pos, width: int, height: int) -> str | None:
        panel = self.panel_rect(width, height)
        if not panel.collidepoint(mouse_pos):
            return "close"
        items = self._filtered()
        row_h = 32
        list_top = panel.y + 100
        for i, item in enumerate(items[self.scroll : self.scroll + self.visible_rows]):
            row_rect = pygame.Rect(panel.x + 16, list_top + i * row_h, panel.width - 32, row_h - 4)
            if row_rect.collidepoint(mouse_pos):
                return f"pick:{item}"
        close_rect = pygame.Rect(panel.right - 100, panel.bottom - 44, 84, 36)
        if close_rect.collidepoint(mouse_pos):
            return "close"
        return None

    def draw(self, screen, width: int, height: int) -> None:
        overlay = pygame.Surface((width, height))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))

        panel = self.panel_rect(width, height)
        pygame.draw.rect(screen, (35, 38, 48), panel, border_radius=8)
        pygame.draw.rect(screen, (90, 95, 110), panel, width=2, border_radius=8)

        title_font = pygame.font.Font(None, 32)
        row_font = pygame.font.Font(None, 26)
        small = pygame.font.Font(None, 22)

        title = (
            f"Input resource ({self.selection_count} cell(s))"
            if self.selection_count > 1
            else "Input resource"
        )
        screen.blit(title_font.render(title, True, (255, 210, 80)), (panel.x + 16, panel.y + 12))
        screen.blit(
            small.render("Chest feeds belts east to machines", True, (180, 180, 190)),
            (panel.x + 16, panel.y + 42),
        )
        filt = f"Filter: {self.filter_text or '(type to search)'}"
        screen.blit(small.render(filt, True, (150, 155, 170)), (panel.x + 16, panel.y + 68))

        items = self._filtered()
        row_h = 32
        list_top = panel.y + 100
        for vis_i, item in enumerate(items[self.scroll : self.scroll + self.visible_rows]):
            idx = self.scroll + vis_i
            row_rect = pygame.Rect(panel.x + 16, list_top + vis_i * row_h, panel.width - 32, row_h - 4)
            sel = idx == self.selected
            color = (70, 130, 100) if sel else (50, 55, 65)
            pygame.draw.rect(screen, color, row_rect, border_radius=4)
            label = item.replace("-", " ").title()
            screen.blit(row_font.render(label, True, (240, 240, 245)), (row_rect.x + 8, row_rect.y + 6))

        close_rect = pygame.Rect(panel.right - 100, panel.bottom - 44, 84, 36)
        pygame.draw.rect(screen, (90, 70, 70), close_rect, border_radius=5)
        close_surf = row_font.render("Close", True, (255, 255, 255))
        screen.blit(close_surf, close_surf.get_rect(center=close_rect.center))
        hint = small.render("Enter=select  Esc=close", True, (130, 130, 140))
        screen.blit(hint, (panel.x + 16, panel.bottom - 28))


class AssistedBuildWorkspace:
    """Session controller for Assisted Build mode."""

    def __init__(self, recipes_data: dict, buildings_data: dict):
        self.recipes_data = recipes_data
        self.buildings = buildings_data.get("buildings", {})
        self.logger = logging.getLogger(__name__)
        self.screen_manager = ScreenManager()
        self.renderer = BlueprintRenderer(tile_size=PYGAME_TILE_SIZE)
        self.state = AssistedBuildState(grid=Grid(), recipes_data=recipes_data)

        self.width = PYGAME_WINDOW_WIDTH
        self.height = PYGAME_WINDOW_HEIGHT
        self.placement_building: str | None = None
        self.hover_tile: tuple[int, int] | None = None
        self.recipe_modal: RecipePickerModal | None = None
        self.resource_modal: ResourcePickerModal | None = None
        self.pending_machine_ids: list[str] | None = None
        self.selected_machine_ids: set[str] = set()
        self.drag_mode: str | None = None  # "pan" | "place" | "box_select"
        self.drag_start_screen: tuple[int, int] | None = None
        self.box_select_start_tile: tuple[int, int] | None = None
        self.box_select_end_tile: tuple[int, int] | None = None
        self.last_mouse_pos = (0, 0)
        self.blueprint_string: str | None = None
        self.paused = False
        self.pause_selected_button = 0

    def _canvas_left(self) -> int:
        return PALETTE_WIDTH

    def _canvas_bottom(self) -> int:
        if self.renderer.toolbar:
            return self.renderer.toolbar.y_position
        return self.height

    def _screen_to_tile(self, screen_x: int, screen_y: int) -> tuple[int, int]:
        wx, wy = self.renderer.screen_to_world(screen_x, screen_y)
        return int(math.floor(wx)), int(math.floor(wy))

    def _tile_on_canvas(self, screen_pos) -> bool:
        x, y = screen_pos
        return (
            self._canvas_left() <= x < self.width
            and 0 <= y < self._canvas_bottom()
        )

    def _building_size(self, name: str) -> tuple[int, int]:
        if name == INPUT_CELL_PALETTE:
            return (1, 1)
        info = self.buildings.get(name, {})
        size = info.get("size", [3, 3])
        return tuple(size)

    def _production_machines(self, machines: list) -> list:
        return [m for m in machines if not m.is_input_cell]

    def _input_cells(self, machines: list) -> list:
        return [m for m in machines if m.is_input_cell]

    def _selected_machines(self) -> list:
        return [m for m in self.state.machines if m.id in self.selected_machine_ids]

    def _clear_selection(self) -> None:
        self.selected_machine_ids.clear()

    def _set_selection(self, machines: list) -> None:
        self.selected_machine_ids = {m.id for m in machines}

    def _recipes_for_machines(self, machines: list) -> list[str]:
        seen: set[str] = set()
        items: list[str] = []
        for m in machines:
            for recipe in recipes_for_entity(m.entity_name, self.recipes_data):
                if recipe not in seen:
                    seen.add(recipe)
                    items.append(recipe)
        return sorted(items)

    def _open_resource_modal(self, machines: list) -> None:
        if not machines:
            return
        self.pending_machine_ids = [m.id for m in machines]
        self.resource_modal = ResourcePickerModal(
            sorted(BASE_MATERIALS),
            selection_count=len(machines),
        )

    def _open_recipe_modal_for_selection(self) -> None:
        machines = self._selected_machines()
        if not machines:
            return
        prod = self._production_machines(machines)
        inputs = self._input_cells(machines)
        if inputs and not prod:
            self._open_resource_modal(inputs)
            return
        if not prod:
            return
        recipes = self._recipes_for_machines(prod)
        entity_names = sorted({m.entity_name for m in prod})
        self.pending_machine_ids = [m.id for m in prod]
        if len(prod) == 1:
            self.recipe_modal = RecipePickerModal(
                recipes, machine=prod[0], selection_count=1
            )
        else:
            self.recipe_modal = RecipePickerModal(
                recipes,
                selection_count=len(prod),
                entity_names=entity_names,
            )

    def _open_recipe_modal(self, machine) -> None:
        self._set_selection([machine])
        self._open_recipe_modal_for_selection()

    def _open_edit_modal(self, machine) -> None:
        if machine.is_input_cell:
            self._set_selection([machine])
            self._open_resource_modal([machine])
        else:
            self._open_recipe_modal(machine)

    def _apply_recipe_pick(self, recipe_item: str) -> None:
        if self.pending_machine_ids:
            applied = self.state.assign_recipes_bulk(
                self.pending_machine_ids, recipe_item
            )
            if applied:
                self._sync_renderer_entities()
                self.blueprint_string = self.state.encode_blueprint_string()
            self._clear_selection()
        self.recipe_modal = None
        self.pending_machine_ids = None

    def _apply_resource_pick(self, resource: str) -> None:
        if self.pending_machine_ids:
            applied = self.state.assign_input_resources_bulk(
                self.pending_machine_ids, resource
            )
            if applied:
                self._sync_renderer_entities()
                self.blueprint_string = self.state.encode_blueprint_string()
            self._clear_selection()
        self.resource_modal = None
        self.pending_machine_ids = None

    def _delete_selection(self) -> None:
        if not self.selected_machine_ids:
            return
        removed = self.state.remove_machines(list(self.selected_machine_ids))
        if removed:
            self._sync_renderer_entities()
            self.blueprint_string = self.state.encode_blueprint_string()
        self._clear_selection()

    def _sync_renderer_entities(self) -> None:
        self.renderer.entities = list(self.state.entities)
        self.renderer.input_positions.clear()
        self.renderer.output_positions.clear()
        self.renderer.identify_inputs_outputs(self.renderer.entities)

    def _clear_placement_tool(self) -> None:
        self.placement_building = None
        self.drag_mode = None
        self.box_select_start_tile = None
        self.box_select_end_tile = None
        self._clear_selection()

    def _select_palette_building(self, name: str) -> None:
        self.placement_building = name
        self.drag_mode = None
        self.box_select_start_tile = None
        self.box_select_end_tile = None
        self._clear_selection()

    def _place_at_tile(self, x: int, y: int) -> None:
        if not self.placement_building:
            return
        if self.placement_building == INPUT_CELL_PALETTE:
            machine = self.state.place_input_cell(x, y)
            if machine:
                self._sync_renderer_entities()
                self._open_resource_modal([machine])
            return
        w, h = self._building_size(self.placement_building)
        machine = self.state.place_machine(self.placement_building, x, y, (w, h))
        if machine:
            self._sync_renderer_entities()
            self._open_recipe_modal(machine)

    def _remove_at_hover(self) -> None:
        if self.selected_machine_ids:
            self._delete_selection()
            return
        if not self.hover_tile:
            return
        tx, ty = self.hover_tile
        machine = self.state.machine_at_tile(tx, ty)
        if machine:
            self.state.remove_machine(machine.id)
            self._sync_renderer_entities()
            self.blueprint_string = self.state.encode_blueprint_string()

    def _finish_box_select(self, *, click_only: bool = False) -> None:
        if not self.box_select_start_tile or not self.box_select_end_tile:
            return
        x0, y0 = self.box_select_start_tile
        x1, y1 = self.box_select_end_tile
        if click_only:
            machine = self.state.machine_at_tile(x0, y0)
            if machine:
                self._set_selection([machine])
            else:
                self._clear_selection()
        else:
            machines = self.state.machines_in_tile_rect(x0, y0, x1, y1)
            self._set_selection(machines)
        self.box_select_start_tile = None
        self.box_select_end_tile = None

    def _screen_drag_distance(self, pos: tuple[int, int]) -> float:
        if not self.drag_start_screen:
            return 0.0
        dx = pos[0] - self.drag_start_screen[0]
        dy = pos[1] - self.drag_start_screen[1]
        return math.hypot(dx, dy)

    def _handle_canvas_click(self, tx: int, ty: int) -> None:
        existing = self.state.machine_at_tile(tx, ty)
        if existing:
            self._open_edit_modal(existing)
        elif self.placement_building:
            self._place_at_tile(tx, ty)

    def _draw_palette(self) -> None:
        screen = self.renderer.screen
        pygame.draw.rect(screen, (28, 30, 38), (0, 0, PALETTE_WIDTH, self._canvas_bottom()))
        pygame.draw.line(
            screen, (70, 75, 90), (PALETTE_WIDTH, 0), (PALETTE_WIDTH, self._canvas_bottom())
        )
        font = pygame.font.Font(None, 24)
        small = pygame.font.Font(None, 20)
        title = font.render("Buildings", True, (255, 210, 80))
        screen.blit(title, (12, 12))
        mouse = pygame.mouse.get_pos()
        none_rect = pygame.Rect(8, 40, PALETTE_WIDTH - 16, 32)
        none_active = self.placement_building is None
        none_hover = none_rect.collidepoint(mouse)
        none_color = (90, 70, 70) if none_active else (55, 58, 68)
        if none_hover and not none_active:
            none_color = (110, 85, 85)
        pygame.draw.rect(screen, none_color, none_rect, border_radius=5)
        screen.blit(small.render("None (Q)", True, (255, 255, 255)), (none_rect.x + 8, none_rect.y + 8))

        y = 80
        for i, name in enumerate(PALETTE_ENTRIES):
            rect = pygame.Rect(8, y, PALETTE_WIDTH - 16, 36)
            active = name == self.placement_building
            hover = rect.collidepoint(mouse)
            if name == INPUT_CELL_PALETTE:
                base = (55, 100, 75)
                active_color = (70, 140, 100)
            else:
                base = (50, 55, 68)
                active_color = (80, 120, 180)
            color = active_color if active else (60, 90, 150) if hover else base
            pygame.draw.rect(screen, color, rect, border_radius=5)
            if name == INPUT_CELL_PALETTE:
                label = "Input Cell"
            else:
                label = name.replace("-", " ").title()
            if len(label) > 18:
                label = label[:16] + "…"
            key_hint = str(i)
            screen.blit(font.render(label, True, (255, 255, 255)), (rect.x + 8, rect.y + 6))
            screen.blit(small.render(key_hint, True, (180, 185, 200)), (rect.right - 22, rect.y + 12))
            y += 42

        hint_font = pygame.font.Font(None, 20)
        sel = len(self.selected_machine_ids)
        if self.placement_building:
            mode = "Place: click grid"
        elif sel:
            mode = f"Selected: {sel}  Del=delete  E=recipe"
        else:
            mode = "Drag to select machines"
        hints = [
            mode,
            "Palette picks building",
            "Q clears tool/selection",
            "Enter/E edit recipe",
        ]
        hy = self._canvas_bottom() - 100
        for line in hints:
            screen.blit(hint_font.render(line, True, (130, 135, 150)), (10, hy))
            hy += 22

    def _draw_box_selection(self) -> None:
        if not self.box_select_start_tile or not self.box_select_end_tile:
            return
        x0, y0 = self.box_select_start_tile
        x1, y1 = self.box_select_end_tile
        min_x, max_x = min(x0, x1), max(x0, x1)
        min_y, max_y = min(y0, y1), max(y0, y1)
        sx0, sy0 = self.renderer.world_to_screen(min_x, min_y)
        sx1, sy1 = self.renderer.world_to_screen(max_x + 1, max_y + 1)
        rect = pygame.Rect(
            min(sx0, sx1),
            min(sy0, sy1),
            abs(sx1 - sx0),
            abs(sy1 - sy0),
        )
        surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        surf.fill((100, 160, 255, 40))
        self.renderer.screen.blit(surf, rect.topleft)
        pygame.draw.rect(self.renderer.screen, (120, 180, 255), rect, width=2)

    def _draw_selection_highlights(self) -> None:
        if not self.selected_machine_ids:
            return
        tile = int(self.renderer.tile_size * self.renderer.zoom)
        for m in self._selected_machines():
            mx, my = m.position
            w, h = m.size
            sx, sy = self.renderer.world_to_screen(mx, my)
            pw, ph = w * tile, h * tile
            rect = pygame.Rect(sx, sy, pw, ph)
            surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
            surf.fill((100, 180, 255, 55))
            self.renderer.screen.blit(surf, rect.topleft)
            pygame.draw.rect(self.renderer.screen, (80, 200, 255), rect, width=2)

    def _draw_placement_preview(self) -> None:
        if (
            not self.placement_building
            or not self.hover_tile
            or self.recipe_modal
            or self.resource_modal
        ):
            return
        x, y = self.hover_tile
        w, h = self._building_size(self.placement_building)
        sx, sy = self.renderer.world_to_screen(x, y)
        tile = int(self.renderer.tile_size * self.renderer.zoom)
        pw, ph = w * tile, h * tile
        occupied = self.state.grid.is_occupied(x, y, w, h)
        if self.placement_building == INPUT_CELL_PALETTE:
            ok = (100, 200, 140, 100)
            bad = (255, 80, 80, 100)
        else:
            ok = (80, 200, 120, 100)
            bad = (255, 80, 80, 100)
        color = bad if occupied else ok
        surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
        surf.fill(color)
        self.renderer.screen.blit(surf, (sx, sy))

    def _draw_machine_labels(self) -> None:
        font = pygame.font.Font(None, 20)
        for m in self.state.machines:
            mx, my = m.position
            sx, sy = self.renderer.world_to_screen(mx, my)
            if m.is_input_cell:
                label = (m.input_resource or "input ?").replace("-", " ")
                color = (255, 230, 120) if not m.input_resource else (140, 230, 180)
            else:
                label = (m.recipe_item or "?").replace("-", " ")
                color = (255, 230, 120) if not m.recipe_item else (200, 220, 255)
            if len(label) > 14:
                label = label[:12] + "…"
            text = font.render(label, True, color)
            self.renderer.screen.blit(text, (sx + 4, sy - 16))

    def _draw_selection_status(self) -> None:
        if not self.selected_machine_ids or self.recipe_modal or self.resource_modal:
            return
        n = len(self.selected_machine_ids)
        font = pygame.font.Font(None, 24)
        text = font.render(
            f"{n} selected — Del delete  |  E or Enter set recipe  |  Esc clear",
            True,
            (180, 220, 255),
        )
        x = self._canvas_left() + 12
        pygame.draw.rect(
            self.renderer.screen,
            (20, 24, 32),
            (x - 4, 8, text.get_width() + 8, text.get_height() + 8),
            border_radius=4,
        )
        self.renderer.screen.blit(text, (x, 12))

    def _draw_empty_hint(self) -> None:
        cx = self._canvas_left() + (self.width - self._canvas_left()) // 2
        cy = self._canvas_bottom() // 2
        font = pygame.font.Font(None, 32)
        sub = pygame.font.Font(None, 24)
        hint = font.render("Place a machine → set recipe → belts route automatically", True, (160, 165, 175))
        sub_t = sub.render(
            "Drag to select  |  Del/E on selection  |  Q=clear  |  WASD pan",
            True,
            (120, 125, 135),
        )
        self.renderer.screen.blit(hint, hint.get_rect(center=(cx, cy - 16)))
        self.renderer.screen.blit(sub_t, sub_t.get_rect(center=(cx, cy + 20)))

    def _draw_pause_menu(self) -> None:
        self.renderer.width = self.width
        self.renderer.height = self.height
        self.renderer.pause_selected_button = self.pause_selected_button
        self.renderer._draw_pause_menu()

    def handle_events(self) -> str | None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "exit"
            if self.screen_manager.handle_resize_event(event):
                self.width, self.height = self.screen_manager.get_size()
                self.renderer._on_window_resize(self.width, self.height)
                if self.renderer.toolbar:
                    self.renderer.toolbar.resize(self.width, self.height)

            if self.resource_modal and event.type == pygame.KEYDOWN:
                action = self.resource_modal.handle_key(event)
                if action == "close":
                    self.resource_modal = None
                    self.pending_machine_ids = None
                elif action and action.startswith("pick:"):
                    self._apply_resource_pick(action.split(":", 1)[1])
                continue

            if self.resource_modal and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                action = self.resource_modal.handle_click(event.pos, self.width, self.height)
                if action == "close":
                    self.resource_modal = None
                    self.pending_machine_ids = None
                elif action and action.startswith("pick:"):
                    self._apply_resource_pick(action.split(":", 1)[1])
                continue

            if self.recipe_modal and event.type == pygame.KEYDOWN:
                action = self.recipe_modal.handle_key(event)
                if action == "close":
                    self.recipe_modal = None
                    self.pending_machine_ids = None
                elif action and action.startswith("pick:"):
                    self._apply_recipe_pick(action.split(":", 1)[1])
                continue

            if self.recipe_modal and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                action = self.recipe_modal.handle_click(event.pos, self.width, self.height)
                if action == "close":
                    self.recipe_modal = None
                    self.pending_machine_ids = None
                elif action and action.startswith("pick:"):
                    self._apply_recipe_pick(action.split(":", 1)[1])
                continue

            if self.paused:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.paused = False
                    elif event.key == pygame.K_UP:
                        self.pause_selected_button = max(0, self.pause_selected_button - 1)
                    elif event.key == pygame.K_DOWN:
                        self.pause_selected_button = min(1, self.pause_selected_button + 1)
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        if self.pause_selected_button == 1:
                            return "menu"
                        self.paused = False
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    button_width, button_height = 400, 60
                    button_y_start = 250
                    for i in range(2):
                        button_y = button_y_start + i * (button_height + 20)
                        button_rect = pygame.Rect(
                            (self.width - button_width) // 2, button_y, button_width, button_height
                        )
                        if button_rect.collidepoint(event.pos):
                            if i == 0:
                                self.paused = False
                            else:
                                return "menu"
                continue

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.selected_machine_ids and not self.recipe_modal:
                        self._clear_selection()
                    else:
                        self.paused = True
                elif event.key == pygame.K_q:
                    self._clear_placement_tool()
                elif event.key == pygame.K_DELETE:
                    self._remove_at_hover()
                elif event.key == pygame.K_e and self.selected_machine_ids:
                    self._open_recipe_modal_for_selection()
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.selected_machine_ids:
                    self._open_recipe_modal_for_selection()
                elif event.key == pygame.K_r:
                    self.state.full_reroute()
                    self._sync_renderer_entities()
                    self.blueprint_string = self.state.encode_blueprint_string()
                elif event.key == pygame.K_c:
                    self.renderer._center_camera_on_blueprint()
                elif not self.recipe_modal and not self.resource_modal:
                    if event.key == pygame.K_0:
                        self._select_palette_building(INPUT_CELL_PALETTE)
                    elif pygame.K_1 <= event.key <= pygame.K_9:
                        idx = event.key - pygame.K_1
                        if idx < len(PALETTE_ENTRIES):
                            self._select_palette_building(PALETTE_ENTRIES[idx])

            if self.recipe_modal or self.resource_modal:
                continue

            if event.type == pygame.MOUSEMOTION:
                if self._tile_on_canvas(event.pos):
                    self.hover_tile = self._screen_to_tile(*event.pos)
                else:
                    self.hover_tile = None

                if self.drag_mode == "pan":
                    dx, dy = event.pos
                    self.renderer.camera_x += dx - self.last_mouse_pos[0]
                    self.renderer.camera_y += dy - self.last_mouse_pos[1]
                    self.last_mouse_pos = event.pos
                elif self.drag_mode == "box_select" and self.hover_tile:
                    self.box_select_end_tile = self.hover_tile
                elif self.drag_mode == "place" and self.drag_start_screen:
                    if (
                        self._screen_drag_distance(event.pos)
                        > DRAG_CLICK_THRESHOLD_PX
                    ):
                        self.drag_mode = "pan"
                        self.last_mouse_pos = event.pos

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    pos = event.pos
                    if pos[0] < PALETTE_WIDTH:
                        none_rect = pygame.Rect(8, 40, PALETTE_WIDTH - 16, 32)
                        if none_rect.collidepoint(pos):
                            self._clear_placement_tool()
                        else:
                            y = 80
                            for name in PALETTE_ENTRIES:
                                rect = pygame.Rect(8, y, PALETTE_WIDTH - 16, 36)
                                if rect.collidepoint(pos):
                                    self._select_palette_building(name)
                                    break
                                y += 42
                        continue
                    if self.renderer.toolbar:
                        action = self.renderer.toolbar.handle_click(pos)
                        if action:
                            return self._toolbar_action(action)
                    if self._tile_on_canvas(pos):
                        self.drag_start_screen = pos
                        self.last_mouse_pos = pos
                        tx, ty = self._screen_to_tile(*pos)
                        if self.placement_building:
                            self.drag_mode = "place"
                        else:
                            self.drag_mode = "box_select"
                            self.box_select_start_tile = (tx, ty)
                            self.box_select_end_tile = (tx, ty)
                    else:
                        self.drag_mode = "pan"
                        self.drag_start_screen = pos
                        self.last_mouse_pos = pos
                elif event.button == 3 and self._tile_on_canvas(event.pos):
                    self._remove_at_hover()
                elif event.button in (4, 5) and self._tile_on_canvas(event.pos):
                    factor = 1.1 if event.button == 4 else 1.0 / 1.1
                    self.renderer._zoom_at_screen(*event.pos, factor)

            elif event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                if self._tile_on_canvas((mx, my)):
                    factor = 1.1 if event.y > 0 else 1.0 / 1.1
                    self.renderer._zoom_at_screen(mx, my, factor)

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.drag_mode == "place" and self.drag_start_screen:
                    if (
                        self._screen_drag_distance(event.pos)
                        <= DRAG_CLICK_THRESHOLD_PX
                        and self.hover_tile
                    ):
                        self._handle_canvas_click(*self.hover_tile)
                elif self.drag_mode == "box_select":
                    click_only = (
                        self.box_select_start_tile == self.box_select_end_tile
                        and self.drag_start_screen is not None
                        and self._screen_drag_distance(event.pos)
                        <= DRAG_CLICK_THRESHOLD_PX
                    )
                    self._finish_box_select(click_only=click_only)
                self.drag_mode = None
                self.drag_start_screen = None

        return None

    def _update_keyboard_pan(self) -> None:
        can_pan = (
            not self.paused
            and not self.recipe_modal
            and not self.resource_modal
            and self.drag_mode not in ("box_select",)
        )
        self.renderer.update_keyboard_pan(enabled=can_pan)

    def _toolbar_action(self, action: str) -> str | None:
        if action == "route":
            self.state.full_reroute()
            self._sync_renderer_entities()
            self.blueprint_string = self.state.encode_blueprint_string()
        elif action == "copy":
            if self.blueprint_string and self.renderer.toolbar:
                self.renderer.toolbar.copy_to_clipboard(self.blueprint_string)
        elif action == "center":
            self.renderer._center_camera_on_blueprint()
        elif action == "pause":
            self.paused = not self.paused
        return None

    def _draw_frame(self) -> None:
        screen = self.renderer.screen
        screen.fill((30, 30, 40))
        clip = pygame.Rect(self._canvas_left(), 0, self.width - self._canvas_left(), self._canvas_bottom())
        screen.set_clip(clip)
        self.renderer.render_grid()
        for entity in self.renderer.entities:
            self.renderer.render_entity(entity)
        if self.renderer.entities:
            self.renderer.render_position_markers()
        else:
            self._draw_empty_hint()
        self._draw_placement_preview()
        self._draw_box_selection()
        self._draw_selection_highlights()
        self._draw_machine_labels()
        self._draw_selection_status()
        screen.set_clip(None)
        self._draw_palette()
        if self.renderer.toolbar:
            self.renderer.toolbar.draw(screen)
        if self.resource_modal:
            self.resource_modal.draw(screen, self.width, self.height)
        elif self.recipe_modal:
            self.recipe_modal.draw(screen, self.width, self.height)
        if self.paused:
            self._draw_pause_menu()

    def run(self) -> str:
        """Run until menu or exit. Returns 'menu' or 'exit'."""
        self.renderer.screen = self.screen_manager.get_screen()
        self.screen_manager.set_caption("Assisted Build")
        w, h = self.screen_manager.get_size()
        self.width, self.height = w, h
        self.renderer.width = w
        self.renderer.height = h
        self.renderer.camera_x = w // 2
        self.renderer.camera_y = h // 4
        self.renderer.toolbar = Toolbar(w, h, h, mode="assisted")
        self.renderer.toolbar.resize(w, h)
        self._sync_renderer_entities()

        while True:
            result = self.handle_events()
            if result == "menu":
                return "menu"
            if result == "exit":
                return "exit"
            self._update_keyboard_pan()
            self._draw_frame()
            self.screen_manager.flip()
            self.screen_manager.tick(60)


def run_assisted_build_session(recipes_data: dict) -> str:
    """Entry point from main.py. Loads buildings and starts workspace."""
    buildings_path = Path(__file__).resolve().parents[1] / "data" / "buildngs.json"
    with open(buildings_path, encoding="utf-8") as f:
        buildings_data = json.load(f)
    workspace = AssistedBuildWorkspace(recipes_data, buildings_data)
    return workspace.run()
