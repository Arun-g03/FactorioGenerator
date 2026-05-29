# Placement rules

Reference for how machines, belts, and inserters are positioned when generating a blueprint. This document describes the **active pipeline** (`ProductionPlanner` → `machine_io` → `stage_connector`). Legacy helpers under `machine_placer/` are noted at the end but are not wired into `main.py` by default.

See also: [generation.md](generation.md) (end-to-end flow), [belt-routing.md](belt-routing.md) (inter-stage belts), [architecture.md](architecture.md) (module map).

---

## Overview

Placement happens in three layers:

1. **Machine positions** — dependency-network rules or genetic search
2. **Per-machine I/O** — belts and inserters around each machine (`place_machine_io_block`)
3. **Inter-stage routing** — belts from producers and raw buses to consumers (`stage_connector`)

`PlacementStrategy` (toolbar: **Place: Rules** / **Place: Genetic**) only changes layer 1. Layers 2 and 3 are shared.

---

## Prerequisites

Before any entity is placed, `ProductionPlanner.build_rate_graph()` applies:

| Rule | Detail |
|------|--------|
| Rate unit | Targets are **items per minute** (`PRODUCTION_RATE_UNIT`) |
| Base materials | `iron-ore`, `copper-ore`, `coal`, `water`, `crude-oil`, `stone` are **not** given machine stages |
| Full chain | In `FULL_CHAIN` mode, ingredient rates propagate upstream (crafted items only) |
| Assembler only | In `ASSEMBLER_ONLY` mode, only user-listed targets get stages |
| Machine count | `ceil(target_rate / items_per_minute_per_machine)` via `ProductionCalculator` |
| Placement order | Topological: dependencies before products (`topological_order()`) |

---

## Grid occupancy

All placement uses `core/grid_env.py` `Grid`:

- A tile is blocked if **any** cell in an entity footprint is already in `grid.occupied`.
- `occupy(x, y, entity_name, [w, h])` marks every cell in the rectangle.
- Belts and inserters occupy **1×1** cells (splitters **2×1**).
- Inter-stage belts skip occupied surface tiles; straight blocked runs may use **underground-belt pairs**.

---

## Rule-based machine placement

**Source:** `ProductionPlanner.generate()` + `planners/rule_based_placement.py`.

Placement follows the **recipe dependency graph**, not a fixed left-to-right strip:

| Concept | Detail |
|---------|--------|
| Root stages | No upstream producers → `NetworkLayoutCursor.allocate_root_origin()` at seed X/Y |
| Downstream stages | Anchor near upstream `output_end` tiles; pick cardinal flow (E/S/W/N) minimizing Manhattan distance |
| Connection gap | Configurable clearance between producer output and consumer input (default 2 tiles) |
| Machine row | Machines in a stage offset along the chosen flow direction via `machine_row_step()` |
| Overlap fallback | `PositionFinder.find_placement_near()` if footprint blocked |

### Configurable parameters (`RuleBasedPlacementSettings`)

| Field | Default | Meaning |
|-------|---------|---------|
| `connection_gap` | 2 | Tiles between upstream output and consumer input lane |
| `network_seed_x` | 12 | First root stage X |
| `network_seed_y` | 14 | First root stage Y |
| `row_stride_y` | 14 | Vertical spacing when wrapping root stages to a new row |

Editable in workspace **Options**; saved to `config.json`.

### Scoring

After all machines + I/O are placed, `evaluate_rule_machine_layout()` scores viability and estimated connection distance **before** inter-stage belts are routed.

---

## Genetic machine placement

**Source:** `planners/genetic_placement.py`.

### Search bounds (defaults)

| Constant | Value |
|----------|-------|
| `PLACEMENT_X_MIN` | 5 |
| `PLACEMENT_X_MAX` | 160 (minus machine width) |
| `PLACEMENT_Y_MIN` | 4 |
| `PLACEMENT_Y_MAX` | 90 (minus machine height) |

Top of the map (y ≈ 6) is reserved for the **base resource bus**; genetic search starts below that.

### Individual constraints

- One gene per machine slot (topological order, expanded by `machine_count`).
- Machine footprints must **not overlap** each other in a layout.
- Initialization tries random positions within bounds; fallback stacks along X.
- After evolution, placement uses `place_machine_io_block` with east flow.

### GA parameters (defaults)

| Parameter | Value |
|-----------|-------|
| Population | 64 |
| Min generations | 20 |
| Max generations | 2500 |
| Stale limit | 120 generations without improvement |
| Improvement epsilon | 0.1 fitness points |
| Mutation rate | 85% of children |

Bounds and GA knobs are overridable via **Options** → saved to `config.json` (`GeneticPlacementSettings`).

---

## Per-machine I/O block

**Source:** `planners/machine_io.py` — used by both strategies.

### Cardinal-flow layout (parameter: `flow_direction`)

Default east; rule-based mode picks N/E/S/W per stage:

```
[belt][belt][belt] → [inserter] → [machine] → [inserter] → [belt][belt][belt]
```

| Element | Position rule |
|---------|----------------|
| Lane center | Perpendicular offset from machine origin based on flow direction |
| Input belts | 3 tiles on the input side of the machine |
| Input inserter | Adjacent to machine on input side |
| Output inserter | Adjacent to machine on output side |
| Output belts | 3 tiles on the output side |
| Multi-ingredient | One belt row per ingredient, offset perpendicular to flow (`INGREDIENT_LANE_SPACING`) |
| Belt direction | `direction_for_flow(flow_direction)` |

### Placement guards

- Each belt/inserter tile is placed only if `not grid.is_occupied(...)`.
- Inserter direction uses `direction_for_inserter(pickup, drop)` — **cardinals only** (0, 2, 4, 6). The inserter faces the drop tile and picks from the opposite side of the pickup tile. Blueprint values include a +90° CW offset so pasted blueprints match in-game arm orientation; the UI arrow uses `inserter_direction_for_display()` to show pick-up→drop facing.
- Assembling machines and furnaces get `"recipe": <item>` on the machine entity.

### Lane anchors (for stage connection)

From `stage_lanes_from_machines()` / `machine_io_lanes()`:

| Anchor | Meaning |
|--------|---------|
| `input_start` / `input_connects` | Where upstream belts meet the consumer (per ingredient lane) |
| `output_end` / `output_start` | Producer output side for routing |

For a stage with multiple machines in a row, connectors aggregate lanes across the machine row.

---

## Inter-stage connection rules

**Source:** `planners/stage_connector.py` — `route_placed_layout()`. Full routing reference: [belt-routing.md](belt-routing.md).

### Crafted ingredient links (`connect_stages`)

For each stage `item` and each dependency `dep` that is **not** a base material and has its own stage:

| Rule | Detail |
|------|--------|
| Producer anchor | Output lane for ingredient `dep` (lane index from recipe order) |
| Consumer anchor | Matching `input_connect` tile on consumer stage |
| Path shape | L-shaped Manhattan via `place_belt_path()` |
| Blocked straight run | May bridge with **underground-belt** input/output pair |
| Multiple targets | **Splitters** (2×1, east-facing) fan out when fan-out is required |
| Belt on occupied tile | Skipped on surface; try underground on eligible straight segments |
| Flow direction | `direction_for_flow()` along each path segment |

### Base material feeds (`connect_base_materials`)

| Rule | Detail |
|------|--------|
| Source | User-placed **Input Cells** (`input_sources`), not an automatic top bus |
| Assignment | Each consumer input lane routed from nearest input chest |
| Fan-out | Splitter when one chest feeds multiple distinct machine inputs |
| Missing input cell | Resource skipped (logged); no belt placed |

See [belt-routing.md](belt-routing.md) for the full feed algorithm. `BASE_BUS_*` constants are used only for layout fitness estimates.

---

## Layout fitness rules

**Source:** `planners/layout_fitness.py` — scores layouts **before** connector belts are placed.

Scoring is two-tier: **viability** (must pass) then **efficiency** (0–100 when viable).

### Viability blockers (score = 0)

| Check | Failure condition |
|-------|-------------------|
| Machine overlap | Two machines share a tile |
| Machine count | Fewer machines placed than `machine_count` for an item |
| Missing stage | Item in rate graph has no machines / lanes |
| I/O vs machine body | Belt/inserter lane tile inside a machine footprint |
| I/O collision | Two machines’ I/O lane tiles overlap |
| Broken chain | Upstream crafted `dep` has no stage for consumer `item` |
| Flow connectivity | `validate_blueprint_flow()` errors when entities are provided (post-routing score) |
| Grid conflict | Machine cell occupied by non-machine entity (when `grid` passed in) |
| Empty genetic slot | Fewer `(x, y, item)` entries than machine slots |

### Efficiency penalties (when viable)

Normalized per machine count; combined weights: footprint **45%**, belts **40%**, layout **15%**.

| Factor | What it measures |
|--------|------------------|
| Footprint | Bounding box area and perimeter of all machines |
| Belts | Estimated belt tiles (per-machine I/O + Manhattan routes + base bus) |
| Layout | Outliers far from factory center, loose clusters within a stage, Y distance from preferred row (`15`) for bus-fed stages |

Rule-based placement scores with `evaluate_rule_machine_layout()` before connectors; genetic placement uses `layout_fitness` inside the GA loop. After routing, `_score_layout(entities)` re-evaluates with belt entities present.

---

## Entity and recipe rules

| Rule | Detail |
|------|--------|
| Machine type | From `recipe["machine"]` (default `assembling-machine-1`) |
| Size | From `recipe["machine_size"]` (default `[3, 3]`) |
| Recipe field | Set on assemblers and furnaces for the crafted `item` |
| Belt entity | `transport-belt`; `underground-belt` for bridges |
| Inserter entity | Always `inserter` in active pipeline |
| Splitter entity | `splitter` (2×1 footprint) when fan-out needed |

---

## What placement does not model

These are intentional simplifications (see [generation.md](generation.md#known-limitations-read-before-fixing)):

- Loaders, fluid handling, power poles
- Full balancer-grade splitter networks for complex multi-ingredient lines
- A* / `belt_router` for inter-stage paths (Manhattan + underground instead)
- `buildngs.json` (not loaded by the main pipeline)

---

## Legacy `machine_placer/` rules

Not used by `run_generation_pipeline()` unless explicitly wired. Documented for completeness:

| Module | Behavior |
|--------|----------|
| `machine_placement.place_machine` | Overlap → retry with `(x + attempt, y + attempt)` up to 10 times; inserters west/east of machine |
| `machine_placement.place_cluster` | Grid of machines with configurable `spacing` |
| `production_line_placement` | Alternate layouts (compact line, recursive chain, resource bus at top) with different belt/inserter offsets |
| `positioning` | Grid search with optional full I/O width clearance |

Prefer extending `machine_io.py` and `stage_connector.py` over duplicating logic in legacy modules.

---

## Quick reference: source files

| Concern | File |
|---------|------|
| Rule-based network layout | `planners/rule_based_placement.py` |
| Rule-based + orchestration | `planners/production_planner.py` |
| Genetic search | `planners/genetic_placement.py` |
| Machine I/O template | `planners/machine_io.py` |
| Stage / bus routing | `planners/stage_connector.py` |
| Placement replay log | `core/placement_recorder.py` |
| Fitness / viability | `planners/layout_fitness.py` |
| Placement tunables | `core/placement_settings.py` |
| Position search | `planners/machine_placer/positioning.py` |
| Grid | `core/grid_env.py` |
| Strategy enum | `core/constants.py` (`PlacementStrategy`) |
