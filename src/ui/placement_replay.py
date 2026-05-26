"""
Step-through UI for blueprint placement and connection reasoning.

Separate from the main workspace visualizer; replays a recorded generation run.
"""

from __future__ import annotations

import logging
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
    PYGAME_TILE_SIZE,
    PYGAME_WINDOW_HEIGHT,
    PYGAME_WINDOW_WIDTH,
    GenerationMode,
    PlacementStrategy,
)
from core.placement_recorder import PlacementRecorder, PlacementStep
from screen_manager import ScreenManager
from blueprint_renderer import BlueprintRenderer
from recipe_panel import RecipePanel


def run_recorded_generation(
    targets: dict[str, float],
    recipes_data: dict,
    generation_mode: GenerationMode,
    placement_strategy: PlacementStrategy,
) -> PlacementRecorder:
    """Run the placement pipeline and return a filled recorder."""
    from core.grid_env import Grid
    from core.pathfinding import Pathfinder
    from core.belt_router import BeltRouter
    from core.blueprint_manager import BlueprintManager

    recorder = PlacementRecorder()
    recorder.set_run_context(
        targets,
        generation_mode.value,
        placement_strategy.value,
    )

    grid = Grid()
    pathfinder = Pathfinder(grid)
    belt_router = BeltRouter(grid, pathfinder)
    manager = BlueprintManager(
        grid,
        pathfinder,
        belt_router,
        recipes_data,
        generation_mode,
        placement_strategy,
    )
    manager.generate_blueprint(placement_recorder=recorder)
    return recorder


class PlacementReplayViewer:
    """Replay recorded placement steps with canvas + reasoning panel."""

    PANEL_WIDTH = 380
    AUTO_MS = 900

    def __init__(self, recorder: PlacementRecorder, recipes_data: dict):
        self.recorder = recorder
        self.recipes_data = recipes_data
        self.logger = logging.getLogger(__name__)
        self.screen_manager = ScreenManager()
        self.screen = self.screen_manager.get_screen()
        self.screen_manager.set_caption("Placement Replay")
        self.width = PYGAME_WINDOW_WIDTH
        self.height = PYGAME_WINDOW_HEIGHT
        self.canvas_width = self.width - self.PANEL_WIDTH

        self.renderer = BlueprintRenderer(tile_size=PYGAME_TILE_SIZE)
        self.renderer.screen = self.screen
        self.renderer.width = self.canvas_width
        self.renderer.height = self.height

        self.current_index = 0
        self.playing = False
        self._last_advance_ms = 0
        self.dragging = False
        self.last_mouse_pos = (0, 0)

    def _current_step(self) -> PlacementStep | None:
        return self.recorder.get_step(self.current_index)

    def _apply_step_to_renderer(self) -> None:
        step = self._current_step()
        if not step:
            self.renderer.entities = []
            return
        self.renderer.entities = step.entities
        if step.entities and self.current_index == 0:
            self.renderer._center_camera_on_blueprint(step.entities)

    def _draw_panel(self) -> None:
        panel_x = self.canvas_width
        pygame.draw.rect(
            self.screen,
            (28, 30, 38),
            (panel_x, 0, self.PANEL_WIDTH, self.height),
        )
        pygame.draw.line(
            self.screen,
            (70, 75, 90),
            (panel_x, 0),
            (panel_x, self.height),
            2,
        )

        title_font = pygame.font.Font(None, 28)
        body_font = pygame.font.Font(None, 22)
        small_font = pygame.font.Font(None, 20)

        y = 16
        header = title_font.render("Placement replay", True, (255, 210, 80))
        self.screen.blit(header, (panel_x + 16, y))
        y += 36

        meta = [
            f"Mode: {self.recorder.mode_label}",
            f"Strategy: {self.recorder.strategy_label}",
            f"Step {self.current_index + 1} / {self.recorder.step_count()}",
        ]
        for line in meta:
            surf = small_font.render(line, True, (180, 185, 200))
            self.screen.blit(surf, (panel_x + 16, y))
            y += 22

        step = self._current_step()
        if not step:
            return

        y += 8
        kind_surf = small_font.render(step.kind, True, (120, 180, 255))
        self.screen.blit(kind_surf, (panel_x + 16, y))
        y += 24

        title = title_font.render(step.title[:42], True, (240, 240, 250))
        self.screen.blit(title, (panel_x + 16, y))
        y += 32

        for line in step.detail:
            wrapped = self._wrap_line(line, body_font, self.PANEL_WIDTH - 32)
            for part in wrapped:
                surf = body_font.render(part, True, (210, 212, 220))
                self.screen.blit(surf, (panel_x + 16, y))
                y += 22
                if y > self.height - 120:
                    break
            if y > self.height - 120:
                break

        y = self.height - 100
        controls = [
            "Left/Right arrows: prev / next step",
            "Space : play / pause",
            "Home / End : first / last",
            "Drag : pan | Scroll : zoom",
            "Esc : back to menu",
        ]
        for line in controls:
            surf = small_font.render(line, True, (130, 135, 150))
            self.screen.blit(surf, (panel_x + 16, y))
            y += 20

    @staticmethod
    def _wrap_line(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if font.size(trial)[0] <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _draw_highlights(self) -> None:
        step = self._current_step()
        if not step or not step.highlights:
            return
        tile = max(4, int(self.renderer.tile_size * self.renderer.zoom))
        for x, y in step.highlights:
            sx, sy = self.renderer.world_to_screen(x, y)
            rect = pygame.Rect(sx, sy, tile, tile)
            pygame.draw.rect(self.screen, (255, 220, 60), rect, 2)

    def _draw_transport(self) -> None:
        bar_y = self.height - 44
        pygame.draw.rect(self.screen, (22, 24, 32), (0, bar_y, self.canvas_width, 44))
        font = pygame.font.Font(None, 24)
        labels = [
            ("< Prev", 12),
            ("Next >", 100),
            ("Play" if not self.playing else "Pause", 188),
            ("|<< First", 280),
            ("Last >>|", 368),
        ]
        for text, x in labels:
            surf = font.render(text, True, (200, 205, 220))
            self.screen.blit(surf, (x, bar_y + 10))

    def _draw_canvas(self) -> None:
        clip = pygame.Rect(0, 0, self.canvas_width, self.height)
        self.screen.set_clip(clip)
        self.screen.fill((30, 30, 40), clip)
        self.renderer.render_grid()
        for entity in self.renderer.entities:
            self.renderer.render_entity(entity)
        self._draw_highlights()
        self.screen.set_clip(None)
        self._draw_transport()

    def _step_relative(self, delta: int) -> None:
        count = self.recorder.step_count()
        if count == 0:
            return
        self.current_index = max(0, min(count - 1, self.current_index + delta))
        self._apply_step_to_renderer()

    def _handle_canvas_input(self, event: pygame.event.Event) -> bool:
        """Return True if event was consumed (canvas area only)."""
        if hasattr(event, "pos") and event.pos[0] >= self.canvas_width:
            return False

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                self.dragging = True
                self.last_mouse_pos = event.pos
                return True
            if event.button == 4:
                self.renderer._zoom_at_screen(event.pos[0], event.pos[1], 1.15)
                return True
            if event.button == 5:
                self.renderer._zoom_at_screen(event.pos[0], event.pos[1], 1 / 1.15)
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
            return True
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            dx = event.pos[0] - self.last_mouse_pos[0]
            dy = event.pos[1] - self.last_mouse_pos[1]
            self.renderer.camera_x += dx
            self.renderer.camera_y += dy
            self.last_mouse_pos = event.pos
            return True
        return False

    def _on_window_resize(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.canvas_width = self.width - self.PANEL_WIDTH
        self.renderer.width = self.canvas_width
        self.renderer.height = self.height

    def handle_events(self) -> str | None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "exit"
            if self.screen_manager.handle_resize_event(event):
                w, h = self.screen_manager.get_size()
                self._on_window_resize(w, h)

            if self._handle_canvas_input(event):
                continue

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return "menu"
                if event.key in (pygame.K_RIGHT, pygame.K_d):
                    self._step_relative(1)
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    self._step_relative(-1)
                elif event.key == pygame.K_HOME:
                    self.current_index = 0
                    self._apply_step_to_renderer()
                elif event.key == pygame.K_END:
                    self.current_index = max(0, self.recorder.step_count() - 1)
                    self._apply_step_to_renderer()
                elif event.key == pygame.K_SPACE:
                    self.playing = not self.playing
                    self._last_advance_ms = pygame.time.get_ticks()

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                bar_y = self.height - 44
                if event.pos[1] >= bar_y and event.pos[0] < self.canvas_width:
                    x = event.pos[0]
                    if x < 90:
                        self._step_relative(-1)
                    elif x < 170:
                        self._step_relative(1)
                    elif x < 260:
                        self.playing = not self.playing
                    elif x < 340:
                        self.current_index = 0
                        self._apply_step_to_renderer()
                    else:
                        self.current_index = max(0, self.recorder.step_count() - 1)
                        self._apply_step_to_renderer()
        return None

    def _tick_autoplay(self) -> None:
        if not self.playing or self.recorder.step_count() == 0:
            return
        now = pygame.time.get_ticks()
        if now - self._last_advance_ms < self.AUTO_MS:
            return
        self._last_advance_ms = now
        if self.current_index >= self.recorder.step_count() - 1:
            self.playing = False
            return
        self._step_relative(1)

    def run(self) -> str:
        if self.recorder.step_count() == 0:
            self.logger.warning("No placement steps recorded.")
            return "menu"

        w, h = self.screen_manager.get_size()
        self._on_window_resize(w, h)
        self._apply_step_to_renderer()
        running = True
        result = None
        while running and result is None:
            result = self.handle_events()
            self._tick_autoplay()
            self._draw_canvas()
            self._draw_panel()
            self.screen_manager.flip()
            self.screen_manager.tick(60)
        return result or "menu"


def run_placement_replay_session(
    recipes_data: dict,
    initial_targets: dict | None = None,
) -> str:
    """
    Configure targets, run rule-based placement with recording, then open replay UI.

    Returns 'menu' or 'exit'.
    """
    from core.constants import PRODUCTION_TARGETS

    panel = RecipePanel()
    if initial_targets:
        panel.load_targets(initial_targets)
    else:
        panel.load_targets(PRODUCTION_TARGETS)

    screen_manager = ScreenManager()
    screen = screen_manager.get_screen()
    screen_manager.set_caption("Placement Replay - targets")
    clock = pygame.time.Clock()
    running = True
    outcome = "menu"

    generate_requested = False
    w, h = screen_manager.get_size()
    panel.set_window_size(w, h)

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                outcome = "exit"
                break
            if screen_manager.handle_resize_event(event):
                w, h = screen_manager.get_size()
                panel.set_window_size(w, h)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
                break
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                action = panel.handle_click(event.pos)
                if action:
                    result = panel.process_action(action)
                    if result == "generate":
                        generate_requested = True
            elif event.type == pygame.KEYDOWN:
                action = panel.handle_key(event)
                if action:
                    result = panel.process_action(action)
                    if result == "generate":
                        generate_requested = True

        screen.fill((30, 30, 40))
        font = pygame.font.Font(None, 32)
        hint = font.render(
            "Set targets, then Generate to start placement replay",
            True,
            (200, 200, 210),
        )
        pw, ph = screen_manager.get_size()
        screen.blit(hint, hint.get_rect(center=(pw // 2, 80)))
        panel.draw(screen)
        screen_manager.flip()
        clock.tick(60)

        if generate_requested:
            config = panel.get_generation_config()
            targets = config.get("targets", {})
            mode = config.get("mode", GenerationMode.FULL_CHAIN)
            placement = config.get("placement", PlacementStrategy.RULE_BASED)
            if not targets:
                generate_requested = False
                continue
            if placement != PlacementStrategy.RULE_BASED:
                logging.getLogger(__name__).info(
                    "Replay records rule-based steps; genetic placement has fewer steps."
                )
            recorder = run_recorded_generation(targets, recipes_data, mode, placement)
            viewer = PlacementReplayViewer(recorder, recipes_data)
            outcome = viewer.run()
            running = False

    return outcome
