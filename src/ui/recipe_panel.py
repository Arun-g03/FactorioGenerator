"""
Recipe panel for configuring production targets.
Allows users to add/remove recipes and set production rates.
"""
import pygame
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.constants import (
    PYGAME_WINDOW_WIDTH,
    PYGAME_WINDOW_HEIGHT,
    PRODUCTION_RATE_UNIT,
    GenerationMode,
    production_rate_suffix,
)
import json


class RecipePanel:
    """Panel for managing recipe production targets."""

    def __init__(self):
        self.width = PYGAME_WINDOW_WIDTH
        self.height = PYGAME_WINDOW_HEIGHT
        self.logger = logging.getLogger(__name__)

        self.panel_width = 600
        self.panel_height = 560
        self.panel_x = (self.width - self.panel_width) // 2
        self.panel_y = (self.height - self.panel_height) // 2

        self.bg_color = (50, 50, 60)
        self.border_color = (100, 100, 120)
        self.item_bg_color = (60, 60, 70)
        self.item_text_color = (255, 255, 255)
        self.button_color = (60, 90, 150)
        self.button_hover_color = (80, 120, 200)
        self.remove_button_color = (150, 60, 60)
        self.remove_button_hover_color = (200, 80, 80)
        self.disabled_button_color = (70, 70, 75)

        self.title_font = pygame.font.Font(None, 48)
        self.item_font = pygame.font.Font(None, 32)
        self.button_font = pygame.font.Font(None, 28)
        self.input_font = pygame.font.Font(None, 28)

        self.recipes = []

        self.active_input_field = None
        self.typing_item_name = ""
        self.typing_count = ""

        self.editing_rate_index = None
        self.typing_rate_edit = ""

        self.suggestions = []
        self.max_suggestions = 5
        self.selected_suggestion = 0

        self.available_items = self._load_available_items()
        self.generation_mode = GenerationMode.ASSEMBLER_ONLY

    def set_window_size(self, width: int, height: int) -> None:
        """Re-center the modal when the window is resized."""
        self.width = width
        self.height = height
        self.panel_x = (self.width - self.panel_width) // 2
        self.panel_y = (self.height - self.panel_height) // 2

    # --- layout helpers ---

    def _add_row_y(self):
        return self.panel_y + 128

    def _list_y(self):
        return self.panel_y + 188

    def _footer_y(self):
        return self.panel_y + self.panel_height - 72

    def _item_name_input_rect(self):
        y = self._add_row_y()
        return pygame.Rect(self.panel_x + 20, y, 220, 40)

    def _add_row_rate_input_rect(self):
        y = self._add_row_y()
        return pygame.Rect(self.panel_x + 250, y, 80, 40)

    def _add_button_rect(self):
        y = self._add_row_y()
        rate_rect = self._add_row_rate_input_rect()
        return pygame.Rect(rate_rect.right + 8 + self._rate_suffix_width(), y, 72, 40)

    def _recipe_rate_input_rect(self, item_y):
        return pygame.Rect(self.panel_x + 250, item_y + 5, 80, 35)

    def _rate_suffix_width(self):
        return self.input_font.size(production_rate_suffix())[0]

    def _draw_rate_suffix(self, screen, x, y, color=None):
        color = color or (180, 180, 190)
        suffix_surface = self.input_font.render(production_rate_suffix(), True, color)
        screen.blit(suffix_surface, (x, y))

    # --- recipe data ---

    def add_recipe(self, item_name, count=1):
        if item_name and item_name not in [r["item"] for r in self.recipes]:
            self.recipes.append({"item": item_name, "count": count})
            self.logger.info("Added recipe: %s x%s", item_name, count)

    def remove_recipe(self, index):
        if 0 <= index < len(self.recipes):
            removed = self.recipes.pop(index)
            self.logger.info("Removed recipe: %s", removed["item"])
            if self.editing_rate_index == index:
                self.editing_rate_index = None
                self.typing_rate_edit = ""
            elif self.editing_rate_index is not None and self.editing_rate_index > index:
                self.editing_rate_index -= 1

    def update_recipe_count(self, index, count_value):
        if 0 <= index < len(self.recipes):
            text = str(count_value).strip()
            if text.isdigit():
                self.recipes[index]["count"] = max(1, int(text))
            else:
                self.recipes[index]["count"] = 1

    def _commit_rate_edit(self):
        if self.editing_rate_index is not None:
            self.update_recipe_count(self.editing_rate_index, self.typing_rate_edit)
            self.editing_rate_index = None
            self.typing_rate_edit = ""

    def _load_available_items(self):
        try:
            recipes_file = Path(__file__).parent.parent / "data" / "recipes.json"
            with open(recipes_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                all_items = list(data.get("recipes", {}).keys())
                excluded_items = [
                    "iron-ore",
                    "copper-ore",
                    "coal",
                    "stone",
                    "uranium-ore",
                    "water",
                    "crude-oil",
                ]
                return [item for item in all_items if item not in excluded_items]
        except Exception as e:
            self.logger.error("Failed to load recipes: %s", e)
            return []

    def _format_item_name(self, item_name):
        return item_name.replace("-", " ").title()

    def _rate_unit_long(self):
        return {"min": "minute", "sec": "second"}.get(
            PRODUCTION_RATE_UNIT, PRODUCTION_RATE_UNIT
        )

    def update_suggestions(self):
        if not self.typing_item_name or not self.available_items:
            self.suggestions = []
            self.selected_suggestion = 0
            return

        typed_lower = self.typing_item_name.lower()
        self.suggestions = [
            item
            for item in self.available_items
            if item.lower().startswith(typed_lower) or typed_lower in item.lower()
        ][: self.max_suggestions]

        def sort_key(item):
            item_lower = item.lower()
            typed = typed_lower
            if item_lower == typed:
                return (0, item_lower)
            if item_lower.startswith(typed):
                return (1, item_lower)
            return (2, item_lower)

        self.suggestions.sort(key=sort_key)
        self.suggestions = self.suggestions[: self.max_suggestions]
        self.selected_suggestion = 0

    def get_recipes(self):
        return {recipe["item"]: recipe["count"] for recipe in self.recipes}

    def get_generation_config(self):
        return {
            "targets": self.get_recipes(),
            "mode": self.generation_mode,
        }

    def _mode_button_rects(self):
        y = self.panel_y + 88
        w, h = 250, 32
        gap = 10
        cx = self.panel_x + self.panel_width // 2
        return {
            GenerationMode.ASSEMBLER_ONLY: pygame.Rect(cx - w - gap // 2, y, w, h),
            GenerationMode.FULL_CHAIN: pygame.Rect(cx + gap // 2, y, w, h),
        }

    def _draw_mode_selector(self, screen):
        labels = {
            GenerationMode.ASSEMBLER_ONLY: "Assemblers only",
            GenerationMode.FULL_CHAIN: "From raw",
        }
        mouse_pos = pygame.mouse.get_pos()
        for mode, rect in self._mode_button_rects().items():
            selected = mode == self.generation_mode
            hovered = rect.collidepoint(mouse_pos)
            color = (80, 120, 180) if selected else (55, 55, 65)
            if hovered and not selected:
                color = (70, 90, 120)
            pygame.draw.rect(screen, color, rect, border_radius=5)
            pygame.draw.rect(
                screen,
                (255, 220, 100) if selected else (120, 120, 130),
                rect,
                width=2,
                border_radius=5,
            )
            text = self.button_font.render(labels[mode], True, self.item_text_color)
            screen.blit(text, text.get_rect(center=rect.center))

    def _draw_input_box(self, screen, rect, active, text, placeholder):
        pygame.draw.rect(screen, (30, 30, 40), rect, border_radius=5)
        pygame.draw.rect(
            screen,
            (255, 255, 255) if active else (100, 100, 100),
            rect,
            width=2,
            border_radius=5,
        )
        if active:
            display = text + "_"
            color = self.item_text_color
        else:
            display = text if text else placeholder
            color = (140, 140, 150) if not text else self.item_text_color
        surface = self.input_font.render(display, True, color)
        screen.blit(surface, (rect.x + 10, rect.y + 8))

    def _draw_add_row(self, screen, mouse_pos):
        add_y = self._add_row_y()
        label = self.button_font.render("Add target:", True, (180, 180, 190))
        screen.blit(label, (self.panel_x + 20, add_y - 22))

        item_rect = self._item_name_input_rect()
        self._draw_input_box(
            screen,
            item_rect,
            self.active_input_field == "item_name",
            self.typing_item_name,
            "Item name...",
        )

        rate_rect = self._add_row_rate_input_rect()
        self._draw_input_box(
            screen,
            rate_rect,
            self.active_input_field == "count",
            self.typing_count,
            "1",
        )
        self._draw_rate_suffix(screen, rate_rect.right + 6, rate_rect.y + 8)

        add_btn = self._add_button_rect()
        can_add = bool(self.typing_item_name.strip())
        is_hovered = add_btn.collidepoint(mouse_pos)
        if can_add:
            add_color = self.button_hover_color if is_hovered else self.button_color
        else:
            add_color = self.disabled_button_color
        pygame.draw.rect(screen, add_color, add_btn, border_radius=5)
        pygame.draw.rect(
            screen,
            (255, 255, 255) if can_add else (100, 100, 100),
            add_btn,
            width=2,
            border_radius=5,
        )
        add_text = self.button_font.render("Add", True, (255, 255, 255))
        screen.blit(add_text, add_text.get_rect(center=add_btn.center))

    def _draw_recipe_list(self, screen, mouse_pos):
        y_offset = self._list_y()
        item_height = 45
        max_items = min(len(self.recipes), 6)

        if self.recipes:
            header = self.button_font.render("Targets", True, (180, 180, 190))
            screen.blit(header, (self.panel_x + 20, y_offset - 24))

        for i in range(max_items):
            recipe = self.recipes[i]
            item_y = y_offset + i * item_height
            item_rect = pygame.Rect(
                self.panel_x + 20, item_y, self.panel_width - 40, item_height
            )
            pygame.draw.rect(screen, self.item_bg_color, item_rect, border_radius=5)

            formatted_name = self._format_item_name(recipe["item"])
            name_surface = self.item_font.render(
                formatted_name, True, self.item_text_color
            )
            screen.blit(name_surface, (item_rect.x + 10, item_rect.y + 8))

            rate_rect = self._recipe_rate_input_rect(item_y)
            editing = self.editing_rate_index == i
            self._draw_input_box(
                screen,
                rate_rect,
                editing,
                self.typing_rate_edit if editing else str(recipe["count"]),
                "",
            )
            self._draw_rate_suffix(
                screen, rate_rect.right + 6, rate_rect.y + 6, self.item_text_color
            )

            remove_btn = pygame.Rect(item_rect.right - 40, item_rect.y + 5, 35, 35)
            is_hovered = remove_btn.collidepoint(mouse_pos)
            remove_color = (
                self.remove_button_hover_color
                if is_hovered
                else self.remove_button_color
            )
            pygame.draw.rect(screen, remove_color, remove_btn, border_radius=5)
            x_text = self.button_font.render("X", True, (255, 255, 255))
            screen.blit(x_text, x_text.get_rect(center=remove_btn.center))

    def load_targets(self, targets):
        for item_name, count in targets.items():
            self.add_recipe(item_name, count)

    def process_action(self, action):
        if action == "close":
            return "close"
        if action == "generate":
            return "generate"
        if action and action.startswith("remove_"):
            self.remove_recipe(int(action.split("_")[1]))
            return None
        if action == "add":
            if self.typing_item_name.strip():
                count = (
                    int(self.typing_count)
                    if self.typing_count and self.typing_count.isdigit()
                    else 1
                )
                self.add_recipe(self.typing_item_name.strip(), count)
                self.typing_item_name = ""
                self.typing_count = ""
                self.suggestions = []
                self.active_input_field = "item_name"
            return None
        if action and action.startswith("edit_rate_"):
            return None
        return None

    def draw(self, screen):
        overlay = pygame.Surface((self.width, self.height))
        overlay.set_alpha(180)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))

        panel_rect = pygame.Rect(
            self.panel_x, self.panel_y, self.panel_width, self.panel_height
        )
        pygame.draw.rect(screen, self.bg_color, panel_rect, border_radius=10)
        pygame.draw.rect(screen, self.border_color, panel_rect, width=3, border_radius=10)

        title_surface = self.title_font.render(
            "Set Production Targets", True, (255, 200, 50)
        )
        title_rect = title_surface.get_rect(
            center=(self.panel_x + self.panel_width // 2, self.panel_y + 40)
        )
        screen.blit(title_surface, title_rect)

        subtitle_surface = self.button_font.render(
            f"Rates in items per {self._rate_unit_long()}", True, (180, 180, 190)
        )
        subtitle_rect = subtitle_surface.get_rect(
            center=(self.panel_x + self.panel_width // 2, self.panel_y + 72)
        )
        screen.blit(subtitle_surface, subtitle_rect)

        self._draw_mode_selector(screen)

        mouse_pos = pygame.mouse.get_pos()
        self._draw_add_row(screen, mouse_pos)
        self._draw_recipe_list(screen, mouse_pos)

        footer_y = self._footer_y()
        generate_btn = pygame.Rect(
            self.panel_x + self.panel_width - 240, footer_y, 120, 40
        )
        gen_color = (
            (60, 150, 60)
            if generate_btn.collidepoint(mouse_pos)
            else (50, 130, 50)
        )
        pygame.draw.rect(screen, gen_color, generate_btn, border_radius=5)
        gen_text = self.button_font.render("Generate", True, (255, 255, 255))
        screen.blit(gen_text, gen_text.get_rect(center=generate_btn.center))

        close_btn = pygame.Rect(
            self.panel_x + self.panel_width - 120, footer_y, 100, 40
        )
        close_color = (
            self.button_hover_color
            if close_btn.collidepoint(mouse_pos)
            else self.button_color
        )
        pygame.draw.rect(screen, close_color, close_btn, border_radius=5)
        close_text = self.button_font.render("Close", True, (255, 255, 255))
        screen.blit(close_text, close_text.get_rect(center=close_btn.center))

        if self.active_input_field == "item_name" and self.suggestions:
            suggestion_y = self._add_row_y() + 45
            suggestion_height = 30
            for i, suggestion in enumerate(self.suggestions):
                sugg_rect = pygame.Rect(
                    self.panel_x + 20,
                    suggestion_y + i * suggestion_height,
                    220,
                    suggestion_height,
                )
                if i == self.selected_suggestion:
                    pygame.draw.rect(screen, (80, 120, 180), sugg_rect)
                    pygame.draw.rect(screen, (255, 255, 255), sugg_rect, width=2)
                else:
                    pygame.draw.rect(screen, (50, 50, 60), sugg_rect)
                formatted_name = self._format_item_name(suggestion)
                sugg_surface = self.button_font.render(
                    formatted_name, True, self.item_text_color
                )
                screen.blit(sugg_surface, (sugg_rect.x + 10, sugg_rect.y + 5))

        instructions = [
            "Pick item and rate, then click Add",
            "Click a target rate to edit it",
            "Generate updates the workspace | ESC to close",
        ]
        for i, instruction in enumerate(instructions):
            inst_surface = self.button_font.render(instruction, True, (150, 150, 150))
            inst_rect = inst_surface.get_rect(
                center=(
                    self.panel_x + self.panel_width // 2,
                    footer_y + 52 + i * 22,
                )
            )
            screen.blit(inst_surface, inst_rect)

    def _select_suggestion(self, suggestion):
        """Fill item name from autocomplete without adding to the list."""
        self.typing_item_name = suggestion
        self.suggestions = []
        if not self.typing_count:
            self.typing_count = "1"
        self.active_input_field = "count"

    def handle_click(self, mouse_pos):
        self._commit_rate_edit()

        for mode, rect in self._mode_button_rects().items():
            if rect.collidepoint(mouse_pos):
                self.generation_mode = mode
                return None

        y_offset = self._list_y()
        item_height = 45
        for i in range(len(self.recipes)):
            item_y = y_offset + i * item_height
            item_rect = pygame.Rect(
                self.panel_x + 20, item_y, self.panel_width - 40, item_height
            )
            remove_btn = pygame.Rect(item_rect.right - 40, item_rect.y + 5, 35, 35)
            if remove_btn.collidepoint(mouse_pos):
                return f"remove_{i}"

            rate_rect = self._recipe_rate_input_rect(item_y)
            if rate_rect.collidepoint(mouse_pos):
                self.editing_rate_index = i
                self.typing_rate_edit = str(self.recipes[i]["count"])
                self.active_input_field = None
                self.suggestions = []
                return f"edit_rate_{i}"

        item_name_input = self._item_name_input_rect()
        count_input = self._add_row_rate_input_rect()
        add_btn = self._add_button_rect()

        if item_name_input.collidepoint(mouse_pos):
            self.active_input_field = "item_name"
            self.update_suggestions()
            return None
        if count_input.collidepoint(mouse_pos):
            self.active_input_field = "count"
            self.suggestions = []
            return None

        if self.active_input_field == "item_name" and self.suggestions:
            suggestion_y = self._add_row_y() + 45
            suggestion_height = 30
            for i, suggestion in enumerate(self.suggestions):
                sugg_rect = pygame.Rect(
                    self.panel_x + 20,
                    suggestion_y + i * suggestion_height,
                    220,
                    suggestion_height,
                )
                if sugg_rect.collidepoint(mouse_pos):
                    self._select_suggestion(suggestion)
                    return None

        if add_btn.collidepoint(mouse_pos) and self.typing_item_name.strip():
            return "add"

        footer_y = self._footer_y()
        generate_btn = pygame.Rect(
            self.panel_x + self.panel_width - 240, footer_y, 120, 40
        )
        if generate_btn.collidepoint(mouse_pos) and len(self.recipes) > 0:
            return "generate"

        close_btn = pygame.Rect(
            self.panel_x + self.panel_width - 120, footer_y, 100, 40
        )
        if close_btn.collidepoint(mouse_pos):
            return "close"

        if not item_name_input.collidepoint(mouse_pos) and not count_input.collidepoint(
            mouse_pos
        ):
            self.active_input_field = None
            self.suggestions = []

        return None

    def handle_key(self, event):
        if event.type != pygame.KEYDOWN:
            return None

        if self.editing_rate_index is not None:
            if event.key == pygame.K_BACKSPACE:
                self.typing_rate_edit = self.typing_rate_edit[:-1]
            elif event.key == pygame.K_RETURN:
                self._commit_rate_edit()
            elif event.key == pygame.K_ESCAPE:
                self.editing_rate_index = None
                self.typing_rate_edit = ""
            elif event.unicode and event.unicode.isdigit():
                self.typing_rate_edit += event.unicode
            return None

        if self.active_input_field == "item_name" and self.suggestions:
            if event.key == pygame.K_UP:
                self.selected_suggestion = (self.selected_suggestion - 1) % len(
                    self.suggestions
                )
                return None
            if event.key == pygame.K_DOWN:
                self.selected_suggestion = (self.selected_suggestion + 1) % len(
                    self.suggestions
                )
                return None
            if event.key == pygame.K_TAB:
                if self.suggestions:
                    self._select_suggestion(self.suggestions[self.selected_suggestion])
                return None

        if not self.active_input_field:
            return None

        if event.key == pygame.K_BACKSPACE:
            if self.active_input_field == "item_name":
                self.typing_item_name = self.typing_item_name[:-1]
                self.update_suggestions()
            elif self.active_input_field == "count":
                self.typing_count = self.typing_count[:-1]
        elif event.key == pygame.K_RETURN:
            if self.active_input_field == "item_name":
                if self.suggestions:
                    self._select_suggestion(self.suggestions[self.selected_suggestion])
                else:
                    self.active_input_field = "count"
            elif self.active_input_field == "count":
                self.active_input_field = "item_name"
        elif event.unicode and event.unicode.isprintable():
            if self.active_input_field == "item_name":
                self.typing_item_name += event.unicode
                self.update_suggestions()
            elif self.active_input_field == "count" and event.unicode.isdigit():
                self.typing_count += event.unicode

        return None
