# Generation

How blueprints are computed from production targets. Read [architecture.md](architecture.md) for module names, [belt-routing.md](belt-routing.md) for inter-stage belt logic, [data-model.md](data-model.md) for JSON shapes, and [placement-rules.md](placement-rules.md) for machine placement.

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

**Raw materials** (`BASE_MATERIALS`: iron/copper ore, coal, stone, water, crude oil) are not given machine stages. In **Assisted Build**, route them from **Input Cells** via `connect_base_materials()`. Autonomous generation links crafted stages only unless input chests are provided — see [belt-routing.md](belt-routing.md).

### Placement strategy (`PlacementStrategy`)

Toolbar: **Place: Rules** / **Place: Genetic**.

| Value | Enum | Behavior |
|-------|------|----------|
| Rules | `RULE_BASED` | Dependency-network placement: each stage anchors near upstream outputs; cardinal belt flow chosen per stage |
| Genetic | `GENETIC` | Machine positions from GA in a configurable region; then same belt connection pass |

### Placement options (`PlacementSettingsBundle`)

Toolbar **Options** (or `O`) edits strategy-specific tunables, persisted in `config.json`:

- **Rule-based:** connection gap, network seed X/Y, row stride
- **Genetic:** population size, generation limits, stale limit, mutation rate, placement region bounds

See `core/placement_settings.py` and `ui/placement_options_modal.py`.

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
2. For each `RateNode`, `network_origin_for_stage()` picks origin and **cardinal belt flow** (east/south/west/north) to minimize distance from upstream output lanes.
3. Root stages (no upstream producers) allocate from `NetworkLayoutCursor` at configurable seed coordinates.
4. Each machine: place entity, `grid.occupy`, `place_machine_io_block(..., flow_direction=...)`.
5. Score with `evaluate_rule_machine_layout()` before connectors run.

### Genetic

1. Same rate graph.
2. `collect_machine_slots()` — one slot per machine in topo order.
3. `run_genetic_layout()` — population evolves positions (defaults: pop 64, stale limit 120); fitness from `layout_fitness`.
4. `place_machines_from_genetic_layout()` — place machines + I/O at GA coordinates (east flow).

## Phase 3 — Stage connection

`_connect_production_stages()` calls **`route_placed_layout()`** — see [belt-routing.md](belt-routing.md) for pathing, underground belts, splitters, and chest feeds.

### `connect_stages()`

For each consumer stage and each non-base dependency that is also a built stage:

- **Producer anchor:** output lane end (per ingredient lane index on multi-input recipes).
- **Consumer anchor:** matching input connect tile on the consumer machine row.
- **Path:** L-shaped Manhattan tiles via `place_belt_path()`; blocked straight runs may use **underground-belt pairs**.
- **Multiple consumers / ingredients:** east-facing **splitters** fan out when `_needs_splitter_fanout()` applies.

### `connect_base_materials()`

Routes raw resources from **Input Cells** (Assisted Build) to machine input lanes. Nearest-chest assignment and splitter fan-out when one chest feeds many consumers. No automatic top bus in Autonomous mode — details in [belt-routing.md](belt-routing.md).

### Lane anchor math (`machine_io` / `stage_connector`)

For a machine at `(mx, my)` with size `(w, h)` and a given **flow direction**:

- Input/output lanes are computed by `machine_io_lanes()` and aggregated per stage via `stage_lanes_from_machines()`.
- Multi-ingredient recipes get parallel input lanes with perpendicular offsets (`INGREDIENT_LANE_SPACING`).
- Connectors route between producer output and consumer input connect tiles for the matching ingredient index.

## Machine I/O block

`machine_io.place_machine_io_block` — standard layout for a chosen cardinal flow (default east):

```
[belt][belt][belt] → [inserter] → [machine] → [inserter] → [belt][belt][belt]
```

- Belt and inserter directions follow `flow_direction` (N/E/S/W).
- Multi-ingredient machines get one belt row per ingredient, offset perpendicular to flow.
- Assembling machines and furnaces get `"recipe": <item>` on the entity dict.

## Phase 4 — Rate summary

`build_rate_summary(targets)` — for each **user** target:

- Compares requested vs `achieved_rate(recipe, machine_count)`.
- Warnings: under/over target, exceeds yellow belt throughput (`15 * 60` items/min).

## Layout fitness

`layout_fitness.evaluate_stage_layout()` scores machine placement; rule-based mode also uses `evaluate_rule_machine_layout()` for network connection distance before connectors run.

| Tier | Meaning |
|------|---------|
| **Viability** | Can production work? (counts, overlaps, connection feasibility, inserter reach) |
| **Efficiency** | Footprint, estimated belt tiles, clustering (only if viable) |

`LayoutFitnessBreakdown.total` is 0–100. Rule-based placement uses network fitness; genetic placement uses the same scorer inside the GA loop. After connectors, `_score_layout(entities)` re-evaluates with belt/inserter entities included.

## Blueprint output

`BlueprintManager.create_blueprint()` wraps entities:

```json
{
  "blueprint": {
    "icons": [{"signal": {"name": "stone-furnace"}, "index": 1}],
    "entities": [ /* see data-model.md */ ],
    "item": "blueprint",
    "version": 562949958402048
  }
}
```

## Known limitations (read before “fixing”)

| Area | Current behavior |
|------|------------------|
| Multi-ingredient assemblers | Parallel input lanes + ingredient-index routing; splitters for fan-out; not full balancer-grade splitter networks |
| Dense layouts | Underground belts bridge some blocked straight segments; complex obstructions may still leave gaps |
| Fluids / power | Not modeled |
| `buildngs.json` | Present but not loaded by main pipeline |
| Module effects / beacons | Not in rate math |
| Placement replay | Best step detail with rule-based placement; genetic runs record fewer steps |

Improvements should usually extend `stage_connector` or `machine_io`, not duplicate logic in legacy `machine_placer/`.
