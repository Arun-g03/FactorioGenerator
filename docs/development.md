# Development guide

For humans and AI agents making changes in this repository.

## Environment

```bash
python -m venv factorio_venv
factorio_venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

**Python 3.10+** required. Older versions fail on `dict | None` in dataclasses (e.g. `production_planner.RateNode`).

### Run

```bash
python main.py
```

### Tests

```bash
python -m unittest tests.test_calculations -v
```

Tests insert `src/` on `sys.path` and cover `ProductionCalculator` only. There are no integration tests for placement or encoding yet.

## Mental model

1. **UI collects intent** (targets, mode, placement).
2. **Pipeline mutates globals and runs planner** (side effect: `PRODUCTION_TARGETS`).
3. **Planner writes entities + grid occupancy**, then **connector adds belts**.
4. **Encoder produces string**; renderer displays entities.

If belts look wrong, trace: `stage_machines` → `connect_stages` → `_manhattan_path` → `_place_belt` (skips occupied cells).

## Safe places to change

| Task | Files |
|------|-------|
| Fix/add recipe | `src/data/recipes.json` |
| Default demo targets | `src/core/constants.py` → `PRODUCTION_TARGETS` |
| Stage belt routing | `src/planners/stage_connector.py` |
| Per-machine I/O layout | `src/planners/machine_io.py` |
| Machine count / rates | `src/planners/machine_placer/calculations.py` |
| Rule-based columns | `src/planners/production_planner.py` (`_allocate_stage_position`, `_stage_spacing`) |
| Genetic search | `src/planners/genetic_placement.py`, `layout_fitness.py` |
| New toolbar action | `src/ui/toolbar.py` + `blueprint_renderer.run_workspace` / `handle_events` |
| Clipboard / encode | `src/core/blueprintEncoder.py` |

## Anti-patterns

| Avoid | Why |
|-------|-----|
| Wiring `machine_placer.ProductionLinePlacement` without removing duplicate logic | Legacy path; diverges from `ProductionPlanner` |
| Using `belt_router` for stage links without fixing occupied endpoints | `route_belt` aborts if start/end tile is occupied |
| Assuming `pathfinder` sees belt tiles as walkable | Neighbors must be unoccupied |
| Importing `from constants` in new code | Works only in some legacy files; use `core.constants` |
| Committing `config.json` | Gitignored; user-specific paths |

## Debugging generation

Enable logging (already INFO on Generate from `main.py`):

```python
logging.basicConfig(level=logging.DEBUG, ...)
```

Useful log sources:

- `planners.production_planner` — stage_y choice, layout score
- `planners.stage_connector` — connection endpoints
- `core.pathfinding` — A* paths (if router used)

Headless smoke test pattern:

```python
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path("src")))
from core.constants import GenerationMode, PlacementStrategy
from core.pipeline import run_generation_pipeline

with open("src/data/recipes.json") as f:
    recipes = json.load(f)

result = run_generation_pipeline(
    {"inserter": 5},
    recipes,
    generation_mode=GenerationMode.FULL_CHAIN,
    placement_strategy=PlacementStrategy.RULE_BASED,
)
print(len(result.blueprint["blueprint"]["entities"]), "entities")
print(result.layout_fitness)
```

## Adding a placement strategy

1. Add enum value in `core/constants.py` → `PlacementStrategy`.
2. Branch in `BlueprintManager.generate_blueprint()`.
3. Implement method on `ProductionPlanner` (mirror `generate` / `generate_genetic`).
4. Call `_connect_production_stages()` and `_score_layout()` for consistency.
5. Toolbar label in `toolbar.py`; toggle in `blueprint_renderer._toggle_placement_strategy()`.
6. Document in [generation.md](generation.md).

## Adding recipes

1. Add entry under `recipes` in `recipes.json` (match Factorio internal names).
2. Ensure every ingredient is either in `BASE_MATERIALS`, has its own recipe, or is acceptable as bus-only.
3. Run calculator test or manual generate with `FULL_CHAIN`.
4. Verify `machine` and `machine_size` match game (affects I/O lane math).

## Code style in this repo

- Prefer extending existing planner hooks over new parallel systems.
- Use `logging` not `print` in library code (`production_line_placement` still has some prints — do not copy).
- `from __future__ import annotations` in newer modules.
- Minimal comments; name functions by behavior.

## Open improvement areas

Documented for prioritization — not bugs in the sense of crashes:

- Splitters / balanced multi-lane inputs for assemblers with 2+ ingredients
- Continuous belt paths through gaps (pathfinding through belt layer or reserved corridors)
- Use `buildngs.json` as single source for sizes
- Integration tests: encode round-trip, entity count, connectivity invariants
- Remove or archive dead `machine_placer` entry points
