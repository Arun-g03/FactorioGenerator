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
python -m unittest discover -s tests -p "test_*.py" -v
```

Requires Python 3.10+. Tests insert `src/` on `sys.path` and cover:

| Module | Focus |
|--------|--------|
| `test_calculations` | `ProductionCalculator` rates |
| `test_rule_based_placement` | Network origins, stage depths |
| `test_belt_paths`, `test_layout_routing` | Stage connector paths |
| `test_splitters_generation`, `test_underground_belts` | Splitter / underground routing |
| `test_machine_io_lanes`, `test_inserter_directions` | I/O geometry and directions |
| `test_flow_connectivity`, `test_placement_validation` | Layout invariants |
| `test_assisted_routing` | Assisted Build belt logic |
| `test_entity_footprint` | Entity sizes |
| `test_sprite_sheets` | Sprite loading (needs Factorio path in `config.json`) |

There are no full end-to-end UI integration tests yet.

## Mental model

1. **UI collects intent** (targets, mode, placement).
2. **Pipeline mutates globals and runs planner** (side effect: `PRODUCTION_TARGETS`).
3. **Planner writes entities + grid occupancy**, then **connector adds belts**.
4. **Encoder produces string**; renderer displays entities.

If belts look wrong, trace: `stage_machines` → `route_placed_layout()` → `connect_stages` / `place_belt_path` → underground bridge or splitter fan-out.

## Safe places to change

| Task | Files |
|------|-------|
| Fix/add recipe | `src/data/recipes.json` |
| Default demo targets | `src/core/constants.py` → `PRODUCTION_TARGETS` |
| Stage belt routing | `src/planners/stage_connector.py` — see [belt-routing.md](../docs/belt-routing.md) |
| Per-machine I/O layout | `src/planners/machine_io.py` |
| Network rule placement | `src/planners/rule_based_placement.py` |
| Placement tunables | `src/core/placement_settings.py`, `src/ui/placement_options_modal.py` |
| Machine count / rates | `src/planners/machine_placer/calculations.py` |
| Genetic search | `src/planners/genetic_placement.py`, `layout_fitness.py` |
| Assisted Build routing | `src/planners/assisted_routing.py` |
| Placement replay | `src/core/placement_recorder.py`, `src/ui/placement_replay.py` |
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

- `planners.production_planner` — network depth, layout score
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
6. Optional tunables in `placement_options_modal.py` + `placement_settings.py`.
7. Document in [generation.md](generation.md).

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

- Balanced splitter networks for assemblers with many ingredients (basic splitters exist; complex balancing still simplified)
- Fluids / power not modeled
- Use `buildngs.json` as single source for sizes
- Integration tests: encode round-trip, entity count, connectivity invariants
- Remove or archive dead `machine_placer` entry points
