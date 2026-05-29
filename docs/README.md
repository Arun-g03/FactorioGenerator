# Documentation

Factorio Blueprint Generator — guides for humans and for AI assistants working in this repo.

## Reading order

| If you want to… | Start here |
|-----------------|------------|
| Run the app locally | [setup.md](setup.md) |
| Understand how blueprints are built | [generation.md](generation.md) |
| Belt routing (stages, splitters, underground, chests) | [belt-routing.md](belt-routing.md) |
| See placement / layout rules in detail | [placement-rules.md](placement-rules.md) |
| Navigate the codebase | [architecture.md](architecture.md) |
| Change recipes or entity data | [data-model.md](data-model.md) |
| Add features or fix bugs | [development.md](development.md) |
| Use the UI (menus, replay, shortcuts) | [controls.md](controls.md) |

## Document map

| Document | Contents |
|----------|----------|
| [setup.md](setup.md) | Install, Python version, Factorio path, tests, troubleshooting |
| [controls.md](controls.md) | Menus, workspace toolbar, shortcuts, UI flow |
| [generation.md](generation.md) | Rate graph, placement strategies, belts, fitness, limits |
| [belt-routing.md](belt-routing.md) | Inter-stage paths, underground belts, splitters, input/output chests, Assisted reroute |
| [placement-rules.md](placement-rules.md) | Machine placement, I/O blocks, connectors, fitness blockers |
| [architecture.md](architecture.md) | Modules, call graph, active vs legacy code, imports |
| [data-model.md](data-model.md) | `recipes.json`, blueprint entities, `config.json` |
| [development.md](development.md) | Conventions, safe change points, anti-patterns, testing |

## Project snapshot (30 seconds)

- **What it does:** User sets production targets (items/min) → planner places machines, belts, inserters → encodes a Factorio blueprint string → Pygame previews it using local game sprites.
- **Entry point:** `main.py` → main menu → **Autonomous Build** (`BlueprintRenderer.run_workspace()`), **Assisted Build**, or **Placement Replay**.
- **Core loop:** `ProductionPlanner` builds a rate graph, places machines + I/O (cardinal belt flow), `stage_connector.route_placed_layout()` links stages (belts, underground belts, splitters), `encode_blueprint` exports.
- **Two independent toggles:** `GenerationMode` (how much of the chain to build) and `PlacementStrategy` (dependency-network rules vs genetic layout).
- **Optional tunables:** `PlacementSettingsBundle` in workspace **Options** (saved to `config.json`).
- **Python:** 3.10+ (`from __future__ import annotations` and `dict | None` hints in newer modules).

## For AI assistants

When editing this repo:

1. **Follow the active pipeline** in `src/core/pipeline.py` → `BlueprintManager` → `ProductionPlanner` → `stage_connector.route_placed_layout()`. Do not assume `machine_placer/` is wired in unless the task says so.
2. **Respect import paths:** `main.py` prepends `src/` and `src/ui/` to `sys.path`. Code under `src/` often uses `from core...` / `from planners...`; `main.py` uses `from src.core...`.
3. **Targets flow:** UI `RecipePanel` → `run_generation_pipeline(custom_recipes, ...)` → mutates `constants.PRODUCTION_TARGETS` → `BlueprintManager.generate_blueprint()`.
4. **Inter-stage belts** — full reference in [belt-routing.md](belt-routing.md); implementation in `planners/stage_connector.py`, not `belt_router.py`.
5. **Main menu modes:** Autonomous Build (`generate`), Assisted Build, Placement Replay — see [controls.md](controls.md).
6. **Read [development.md](development.md)** for known limitations before “fixing” multi-ingredient or splitter logic.

Quick start command (from repo root, venv active):

```bash
python main.py
python -m unittest discover -s tests -p "test_*.py" -v
```
