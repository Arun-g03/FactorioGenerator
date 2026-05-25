# Generation

How blueprints are computed from production targets. Read [architecture.md](architecture.md) for module names, [data-model.md](data-model.md) for JSON shapes, and [placement-rules.md](placement-rules.md) for a full rule-by-rule reference.

## User-facing controls

Two settings are **orthogonal** — they combine freely.

### Production mode (`GenerationMode`)

Set in the targets modal: **Assemblers only** vs **From raw**.

| Value | Enum | Behavior |
|-------|------|----------|
| Assemblers only | `ASSEMBLER_ONLY` | Only items listed as targets get a stage |
| From raw | `FULL_CHAIN` | Recursively includes upstream crafted items (not raw ores) |

Rates are always **items per minute** (`PRODUCTION_RATE_UNIT` in `constants.py`).

**Full chain example:** Target `inserter: 5/min` expands to stages for intermediates (e.g. `iron-plate`, `iron-gear-wheel`, `electronic-circuit`) plus `inserter`, each with rates derived from recipe ingredient ratios.

**Raw materials** (`BASE_MATERIALS`: iron/copper ore, coal, stone, water, crude oil) are not given machine stages; they are fed via a **top bus** in `stage_connector.connect_base_materials()`.

### Placement strategy (`PlacementStrategy`)

Toolbar: **Place: Rules** / **Place: Genetic**.

| Value | Enum | Behavior |
|-------|------|----------|
| Rules | `RULE_BASED` | Stages left-to-right; machines in a row per stage; tries several `stage_y` rows and keeps best fitness |
| Genetic | `GENETIC` | Machine positions from GA in a bounded box; then same belt connection pass |

## End-to-end pipeline

```
RecipePanel targets + mode
        ↓
run_generation_pipeline(targets, recipes_data, mode, placement)
        ↓
PRODUCTION_TARGETS ← targets (module-level mutation)
        ↓
BlueprintManager.generate_blueprint()
        ↓
ProductionPlanner.generate() | generate_genetic()
        ↓
encode_blueprint() → BlueprintGenerationResult
        ↓
BlueprintRenderer.load_blueprint()
```

## Phase 1 — Rate graph

`ProductionPlanner.build_rate_graph(targets)`:

1. Accumulate demanded items/min per `GenerationMode`.
2. For each item, load recipe from `recipes_data["recipes"][item]`.
3. Build `RateNode`: `machine_count = ceil(target_rate / items_per_minute_per_machine)`.
4. `dependencies` = recipe ingredient keys.

Machine counts use `ProductionCalculator` (`machine_placer/calculations.py`):

- Smelting: `60 / (crafting_time / machine_speed)`
- Assembling: `60 * crafting_speed`

## Phase 2 — Machine placement

### Rule-based

1. Topological order (ingredients before products).
2. For each `RateNode`, `_allocate_stage_position()` advances `_next_stage_x` so stages sit in columns.
3. Each machine: place entity, `grid.occupy`, record `(mx, my, w, h)` in `stage_machines[item]`.
4. `place_machine_io_block(..., flow_east=True)` — see [Machine I/O block](#machine-io-block).
5. Tries `stage_y ∈ {12, 15, 18, 22}`; keeps layout with highest `evaluate_stage_layout().total`.

### Genetic

1. Same rate graph.
2. `collect_machine_slots()` — one slot per machine in topo order.
3. `run_genetic_layout()` — population evolves positions; fitness from `layout_fitness`.
4. `place_machines_from_genetic_layout()` — place machines + I/O at GA coordinates.

## Phase 3 — Stage connection

`_connect_production_stages()` calls:

### `connect_stages()`

For each consumer stage and each non-base dependency that is also a built stage:

- **Producer anchor:** east end of output belt lane (`output_end`).
- **Consumer anchor:** west start of input belt lane (`input_start`).
- **Path:** L-shaped Manhattan tiles; belts placed on free cells with flow direction via `direction_for_flow`.
- **Multiple ingredients:** `lane_offset = ingredient_index * 2` (parallel vertical feeds; simplified).

### `connect_base_materials()`

For stages that need ores/water/etc.:

- Horizontal bus at `BASE_BUS_Y` (and stacked rows per resource).
- Drop lines down to each stage’s `input_start`.

### Lane anchor math (`stage_connector.machine_io_lanes`)

For a machine at `(mx, my)` with size `(w, h)`:

- `lane_y = my + h // 2`
- Input lane starts at `(mx - 4, lane_y)` (west of inserter column)
- Output lane ends at `(mx + w + 3, lane_y)`

Connectors route from `(output_end_x + 1, y)` to `(input_start_x - 1, y)` (+ offset).

## Machine I/O block

`machine_io.place_machine_io_block` — standard east-flow cell:

```
[belt][belt][belt] → [inserter] → [machine] → [inserter] → [belt][belt][belt]
```

- Belts use `FACTORIO_EAST` (4) unless `flow_east=False`.
- Assembling machines and furnaces get `"recipe": <item>` on the entity dict.

## Phase 4 — Rate summary

`build_rate_summary(targets)` — for each **user** target:

- Compares requested vs `achieved_rate(recipe, machine_count)`.
- Warnings: under/over target, exceeds yellow belt throughput (`15 * 60` items/min).

## Layout fitness

`layout_fitness.evaluate_stage_layout()` scores **before** connector belts are placed (machines + estimated I/O only).

| Tier | Meaning |
|------|---------|
| **Viability** | Can production work? (counts, overlaps, connection feasibility, inserter reach) |
| **Efficiency** | Footprint, estimated belt tiles, clustering (only if viable) |

`LayoutFitnessBreakdown.total` is 0–100. Rule-based placement maximizes this over candidate `stage_y` values.

Genetic placement uses the same scorer inside the GA loop.

## Blueprint output

`BlueprintManager.create_blueprint()` wraps entities:

```json
{
  "blueprint": {
    "icons": [{"signal": {"name": "stone-furnace"}, "index": 1}],
    "entities": [ /* see data-model.md */ ],
    "item": "blueprint",
    "version": 281479276889473
  }
}
```

## Known limitations (read before “fixing”)

| Area | Current behavior |
|------|------------------|
| Multi-ingredient assemblers | One input belt lane per machine; extra ingredients use offset vertical feeds, not full splitter networks |
| `belt_router` / A* | Not used for inter-stage links; paths skip occupied tiles (gaps possible in dense layouts) |
| Fluids / power | Not modeled |
| Underground belts / splitters | Not used in `stage_connector` |
| `buildngs.json` | Present but not loaded by main pipeline |
| Module effects / beacons | Not in rate math |

Improvements should usually extend `stage_connector` or `machine_io`, not duplicate logic in legacy `machine_placer/`.
