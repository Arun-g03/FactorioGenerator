# Data model

Schemas and files that define behavior. Item names use Factorio **internal IDs** (e.g. `iron-plate`, not display names).

## `src/data/recipes.json`

Top-level shape:

```json
{
  "recipes": {
    "<item-id>": { ... recipe fields ... }
  }
}
```

### Raw resources

```json
"iron-ore": {
  "type": "raw",
  "ingredients": {}
}
```

Listed in `BASE_MATERIALS` (`constants.py`). No machine stage — fed from bus only.

### Crafted items

| Field | Type | Purpose |
|-------|------|---------|
| `ingredients` | `{item: amount}` | Per **one** craft output |
| `machine` | string \| null | Entity name (`assembling-machine-1`, `stone-furnace`, …) |
| `machine_size` | `[width, height]` | Tiles (default often `[3, 3]`) |
| `crafting_speed` | number | Assembler: crafts per second → `60 * speed` items/min |
| `crafting_time` | number | Furnace: seconds per craft |
| `machine_speed` | number | Furnace multiplier (optional, default 1.0) |
| `belt_speed` | number | Optional metadata for belts (not used in core planner) |

**Examples:**

- Furnace: `"crafting_time": 3.2`, `"machine_speed": 1.0` → `60/3.2` plates/min per furnace.
- Assembler: `"crafting_speed": 0.5` → 30 items/min per machine.

Missing recipe for a demanded item → stage skipped with warning; rate summary shows `"No recipe"`.

### Lookup

```python
recipe = recipes_data["recipes"].get(item_name)
```

Used by `ProductionPlanner._recipe()` and `ProductionCalculator`.

## `src/data/buildngs.json`

Building metadata (sizes, categories). **Not loaded** by `main.py` or `BlueprintManager` today. Recipes embed `machine` + `machine_size` directly.

## Blueprint entities

Each entity in `blueprint["blueprint"]["entities"]` is a dict compatible with Factorio’s map exchange format (simplified subset).

| Field | Required | Notes |
|-------|----------|-------|
| `entity_number` | yes | Unique index in blueprint |
| `name` | yes | Prototype name (`transport-belt`, `assembling-machine-1`, …) |
| `position` | yes | `{"x": float, "y": float}` — tile position |
| `direction` | belts/inserters | `0–7` = N/NE/E/SE/S/SW/W/NW (`constants.DIRECTIONS`) |
| `recipe` | assemblers/furnaces | Product item id |

Example machine:

```json
{
  "entity_number": 1,
  "name": "assembling-machine-1",
  "position": {"x": 42, "y": 15},
  "recipe": "iron-gear-wheel"
}
```

Example belt:

```json
{
  "entity_number": 2,
  "name": "transport-belt",
  "position": {"x": 38, "y": 16},
  "direction": 2
}
```

## Production stages (UI metadata)

`production_stages` is **not** part of the Factorio export — it is for labels in the workspace:

```python
{
  "id": 1,
  "type": "iron-plate",           # item id
  "position": (10, 15),           # stage origin (first machine)
  "recipe": { ... },              # recipe dict copy
  "entities": []                  # reserved
}
```

## Runtime configuration

### `constants.PRODUCTION_TARGETS`

```python
PRODUCTION_TARGETS = {"inserter": 20}  # items/min
```

Overwritten when generating:

```python
# pipeline.py
constants_module.PRODUCTION_TARGETS = custom_recipes
```

`BlueprintManager` reads this global at generate time.

### `config.json` (repo root, gitignored)

Created by Settings UI. Example:

```json
{
  "factorio_install_path": "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Factorio"
}
```

`main.load_config()` sets:

- `constants.FACTORIO_INSTALL_PATH`
- `constants.FACTORIO_BASE_GRAPHICS_PATH` → `{install}/data/base/graphics/entity`

Legacy key `factorio_graphics_path` (full path) still supported.

## UI generation config

`RecipePanel.get_generation_config()`:

```python
{
  "targets": {"iron-plate": 20, ...},   # item → rate/min
  "mode": GenerationMode.ASSEMBLER_ONLY | FULL_CHAIN
}
```

`BlueprintRenderer` adds `"placement": PlacementStrategy` before calling the pipeline.
