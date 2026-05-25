# Placement rules

Reference for how machines, belts, and inserters are positioned when generating a blueprint. This document describes the **active pipeline** (`ProductionPlanner` → `machine_io` → `stage_connector`). Legacy helpers under `machine_placer/` are noted at the end but are not wired into `main.py` by default.

See also: [generation.md](generation.md) (end-to-end flow), [architecture.md](architecture.md) (module map).

---

## Overview

Placement happens in three layers:

1. **Machine positions** — rule-based columns or genetic search
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
- Belts and inserters occupy **1×1** cells.
- Inter-stage belts are skipped on occupied tiles (no underground belts); dense layouts can leave gaps.

---

## Rule-based machine placement

**Source:** `ProductionPlanner.generate()` in `planners/production_planner.py`.

### Stage columns

Each rate-graph item (stage) gets one horizontal band:

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `_next_stage_x` start | `10` | First stage begins at x = 10 |
| Machine spacing | `w + 6` | Gap between machines in the same stage |
| Stage padding | `+ 6` inside width calc | Extra margin in stage width |
| `_stage_spacing` | `18` | Gap between stage columns after each stage |
| `_stage_y` | `12`, `15`, `18`, or `22` | Candidate row; best score wins |

Stage width:

```
total_width = machine_count * (machine_w + 6) + 6
```

Machines in a stage are placed at:

```
mx = x_start + i * (machine_w + 6)
my = y_start
```

### Overlap fallback

If `grid.is_occupied(mx, my, w, h)`:

1. Call `PositionFinder.find_next_available_position_with_spacing(w, h)`.
2. Search area: x ∈ [10, 60), y ∈ [10, 60) (within grid bounds).
3. Require **full I/O clearance**: tiles from `x - 3` through `x + 6 + width` and height `h` must be free.
4. If no position is found, that machine is **skipped** (logged).

### Row selection

For each candidate `stage_y`, the planner:

1. Resets grid occupancy from a backup.
2. Places all nodes in topological order.
3. Scores with `evaluate_stage_layout()` (machines only; no connector belts yet).
4. Keeps the layout with the highest `LayoutFitnessBreakdown.total`.

---

## Genetic machine placement

**Source:** `planners/genetic_placement.py`.

### Search bounds

| Constant | Value |
|----------|-------|
| `PLACEMENT_X_MIN` | 15 |
| `PLACEMENT_X_MAX` | 90 (minus machine width) |
| `PLACEMENT_Y_MIN` | 12 |
| `PLACEMENT_Y_MAX` | 55 (minus machine height) |

Top of the map (y ≈ 6) is reserved for the **base resource bus**; genetic search starts below that.

### Individual constraints

- One gene per machine slot (topological order, expanded by `machine_count`).
- Machine footprints must **not overlap** each other in a layout.
- Initialization tries up to **80** random positions per machine; fallback stacks at `(PLACEMENT_X_MIN + index * 8, PLACEMENT_Y_MIN)`.
- After evolution, placement uses the same `place_machine_io_block` and overlap fallback as rule-based mode.

### GA parameters (defaults)

| Parameter | Value |
|-----------|-------|
| Population | 48 |
| Min generations | 20 |
| Max generations | 2500 |
| Stale limit | 40 generations without improvement |
| Improvement epsilon | 0.5 fitness points |
| Mutation rate | 85% of children |
| Elite retention | top 25% of population |

Fitness uses the same `layout_fitness` scorer as rule-based row selection.

---

## Per-machine I/O block

**Source:** `planners/machine_io.py` — used by both strategies.

### East-flow layout (default: `flow_east=True`)

```
[belt][belt][belt] → [inserter] → [machine] → [inserter] → [belt][belt][belt]
```

| Element | Position rule |
|---------|----------------|
| Lane Y | `machine_y + machine_h // 2` |
| Input belts | 3 tiles west of machine, starting at `machine_x - 4` |
| Input inserter | `(machine_x - 1, lane_y)` |
| Output inserter | `(machine_x + machine_w, lane_y)` |
| Output belts | 3 tiles east of machine, starting at `machine_x + machine_w + 1` |
| Belt direction | `FACTORIO_EAST` (4) |

### Placement guards

- Each belt/inserter tile is placed only if `not grid.is_occupied(...)`.
- Inserter direction uses `direction_for_inserter(pickup, drop)` — **cardinals only** (0, 2, 4, 6). The inserter faces the drop tile and picks from the opposite side of the pickup tile. Blueprint values include a +90° CW offset so pasted blueprints match in-game arm orientation; the UI arrow uses `inserter_direction_for_display()` to show pick-up→drop facing.
- Assembling machines and furnaces get `"recipe": <item>` on the machine entity.

### Lane anchors (for stage connection)

From `stage_connector.machine_io_lanes()`:

| Anchor | Tile |
|--------|------|
| `input_start` | `(machine_x - 4, lane_y)` — west end of input belt run |
| `output_end` | `(machine_x + width + 3, lane_y)` — east end of output belt run |

For a stage with multiple machines in a row, connectors use the **leftmost** machine’s `input_start` and the **rightmost** machine’s `output_end`.

---

## Inter-stage connection rules

**Source:** `planners/stage_connector.py` — runs after machine + I/O placement.

### Crafted ingredient links (`connect_stages`)

For each stage `item` and each dependency `dep` that is **not** a base material and has its own stage:

| Rule | Detail |
|------|--------|
| Producer anchor | `output_end` of stage `dep` |
| Consumer anchor | `input_start` of stage `item` |
| Path shape | L-shaped Manhattan: horizontal first, then vertical |
| Path endpoints | From `(output_end_x + 1, y)` to `(input_start_x - 1, target_y)` |
| Multiple ingredients | `lane_offset = ingredient_index * 2` (parallel vertical feeds) |
| Belt on occupied tile | Skipped (no belt placed) |
| Flow direction | `direction_for_flow()` along each path segment |

### Base material bus (`connect_base_materials`)

| Rule | Detail |
|------|--------|
| Bus Y | `BASE_BUS_Y = 6`, stacked `+2` per additional resource |
| Bus X range | `BASE_BUS_X_START = 8` for `BASE_BUS_LENGTH = 40` tiles |
| Bus direction | East (`FACTORIO_EAST`) |
| Drop to stage | L-path from `(max(8, in_x - 5), bus_y)` to `(in_x - 1, in_y)` |

Base materials never get machine stages; they only appear on the top bus and drop lines.

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
| Backward route | Producer `output_end_x >= consumer input (with offset)` — violates east flow |
| Grid conflict | Machine cell occupied by non-machine entity (when `grid` passed in) |
| Empty genetic slot | Fewer `(x, y, item)` entries than machine slots |

### Efficiency penalties (when viable)

Normalized per machine count; combined weights: footprint **45%**, belts **40%**, layout **15%**.

| Factor | What it measures |
|--------|------------------|
| Footprint | Bounding box area and perimeter of all machines |
| Belts | Estimated belt tiles (per-machine I/O + Manhattan routes + base bus) |
| Layout | Outliers far from factory center, loose clusters within a stage, Y distance from preferred row (`15`) for bus-fed stages |

Rule-based placement maximizes this score across `stage_y` candidates. Genetic placement uses it inside every generation.

---

## Entity and recipe rules

| Rule | Detail |
|------|--------|
| Machine type | From `recipe["machine"]` (default `assembling-machine-1`) |
| Size | From `recipe["machine_size"]` (default `[3, 3]`) |
| Recipe field | Set on assemblers and furnaces for the crafted `item` |
| Belt entity | Always `transport-belt` in active pipeline |
| Inserter entity | Always `inserter` in active pipeline |

---

## What placement does not model

These are intentional simplifications (see [generation.md](generation.md#known-limitations-read-before-fixing)):

- Splitters, underground belts, loaders
- Fluids, power, modules, beacons
- A* / `belt_router` for inter-stage paths (Manhattan only)
- Full multi-lane splitter networks for assemblers with many ingredients
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
| Rule-based + orchestration | `planners/production_planner.py` |
| Genetic search | `planners/genetic_placement.py` |
| Machine I/O template | `planners/machine_io.py` |
| Stage / bus routing | `planners/stage_connector.py` |
| Fitness / viability | `planners/layout_fitness.py` |
| Position search | `planners/machine_placer/positioning.py` |
| Grid | `core/grid_env.py` |
| Strategy enum | `core/constants.py` (`PlacementStrategy`) |
