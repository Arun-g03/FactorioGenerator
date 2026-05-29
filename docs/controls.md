# Controls

How a user (or automated UI test) navigates the application.

## Application flow

```mermaid
stateDiagram-v2
    [*] --> MainMenu
    MainMenu --> Workspace: Autonomous Build
    MainMenu --> Assisted: Assisted Build
    MainMenu --> Replay: Placement Replay
    MainMenu --> Settings: Settings
    MainMenu --> [*]: Exit
    Settings --> MainMenu: Back
    Workspace --> MainMenu: Pause → Return to menu
    Assisted --> MainMenu: Pause → Return to menu
    Replay --> MainMenu: Esc
    Workspace --> Workspace: Generate / Options / Center / Pan
    Assisted --> Assisted: Place / Recipe / Route
    Replay --> Replay: Step / Play
```

1. **`python main.py`** → main menu.
2. **Autonomous Build** → blueprint workspace (may open targets modal first if configured).
3. **Assisted Build** → place machines, set each machine’s recipe, belts route automatically.
4. **Placement Replay** → set targets, generate with recording, step through placement reasoning.
5. **Set targets** (Autonomous Build / Replay) → add items and rates → **Generate** in modal or toolbar.
6. **Copy BP** → clipboard string for Factorio.

## Main menu

| Option | Action |
|--------|--------|
| **Autonomous Build** | Full pipeline: targets → generate → canvas preview |
| **Assisted Build** | Manual placement with automatic belt routing |
| **Placement Replay** | Recorded step-through of a generation run |
| **Settings** | Factorio path, window size |
| **Exit** | Quit application |

| Input | Action |
|-------|--------|
| ↑ / ↓ or mouse | Navigate |
| Enter | Select |
| ESC | Exit application |

## Settings

- Set **Factorio installation path** (saved to `config.json`, gitignored).
- Required for sprite preview; generation still runs without it (entities render as placeholders if sprites missing).

## Blueprint workspace (Autonomous Build)

### Toolbar

| Button | Action |
|--------|--------|
| **Targets** | Open modal: items, rates/min, Assemblers only / From raw |
| **Generate** | `run_generation_pipeline()` with current config |
| **Place: Rules / Genetic** | Toggle `PlacementStrategy` |
| **Options** | Open placement tunables for the active strategy (saved to `config.json`) |
| **Center** | Pan camera so blueprint bounding box is centered above toolbar |
| **Copy BP** | Copy `blueprint_string` (needs `pyperclip`) |
| **Pause** | Overlay: Resume or Return to menu |

### Targets modal (`RecipePanel`)

| Action | How |
|--------|-----|
| Add target | Type item name (autocomplete), rate, Add |
| Remove | Per-row control in panel |
| Generate | Button in panel → runs pipeline and closes modal on success |
| Close | ESC or close action |

### Placement options modal

Shown when **Options** is clicked (or `O` in workspace). Fields depend on **Place: Rules** vs **Place: Genetic**:

- **Rules:** connection gap, network seed X/Y, row spacing
- **Genetic:** population, generation limits, mutation rate, placement region bounds

**Save** persists to `config.json` under `placement_settings`. **Cancel** / ESC discards unsaved edits.

### Keyboard (workspace)

| Key | Action |
|-----|--------|
| `T` | Open targets modal |
| `G` | Generate (same as toolbar) |
| `O` | Open placement options modal |
| `C` | Center camera on blueprint |
| `R` | Reset camera to origin, zoom 1× |
| `S` | Screenshot (`blueprint_YYYYMMDD_HHMMSS.png` in cwd) |
| Mouse wheel | Zoom (0.1×–3×) |
| `W` `A` `S` `D` | Pan canvas (hold) |
| Left-drag | Pan |
| `ESC` | Close modal, or open/close pause |

### On-screen overlays

When entities exist and not paused:

- **Stage labels** — `S1: Iron Plate`, etc., from `production_stages`.
- **Top-left stats** — entity count, stages, zoom, placement mode, rate summary lines.
- **Green/red markers** — heuristic input/output hints (not exact belt endpoints).

### Pause menu

| Option | Effect |
|--------|--------|
| Resume | Continue workspace |
| Return to menu | `run_workspace()` returns `"menu"` |

## Placement Replay

After **Placement Replay** from the main menu:

1. Set targets in the same `RecipePanel` modal as Autonomous Build.
2. **Generate** runs the pipeline with a `PlacementRecorder` attached.
3. The replay viewer opens with a canvas (left) and reasoning panel (right).

### Replay transport

| Input | Action |
|-------|--------|
| ← / → or `A` / `D` | Previous / next step |
| Space | Play / pause auto-advance (~900 ms per step) |
| Home / End | First / last step |
| Click transport bar | `< Prev`, `Next >`, `Play`/`Pause`, `|<< First`, `Last >>|` |
| Drag on canvas | Pan |
| Scroll | Zoom |
| ESC | Return to main menu |

Each step shows a **kind** (e.g. `rate_graph`, `stage_plan`, `machine`, `lanes`, `complete`), title, detail lines, cumulative entity snapshot, and optional tile **highlights**.

Genetic placement produces fewer recorded steps than rule-based; replay works best with **Place: Rules**.

## Assisted Build workspace

### Flow

1. Pick a building in the **left palette** (`0` = Input Cell, `1`–`7` = machines).
2. **Left-click** the grid to place; the **recipe picker** opens immediately.
3. Press **`Q`** or choose **None (Q)** in the palette to clear the placement tool.
4. With no building selected, **drag** on the grid to box-select machines (highlighted in blue).
5. With a selection: **Del** deletes all selected; **E** or **Enter** opens the recipe picker (applies to every selected machine that can craft that item).
6. **Esc** clears the selection; single **click** on a machine selects only that machine.
7. Choose a recipe → local I/O and belts route automatically.
8. **Right-click** or **Del** (with no selection) removes the machine under the cursor.

### Toolbar

| Button | Action |
|--------|--------|
| **Route all** | Re-run belt routing for every machine with a recipe |
| **Optimize** / **Stop opt** | Toggle continuous belt optimization search (stops when no improvement for N iterations, or max iters in Options) |
| **Options** | Open Assisted Build tunables (saved to `config.json`) |
| **Center** | Center camera on blueprint |
| **Copy BP** | Copy encoded blueprint string |
| **Pause** | Resume or return to main menu |

### Options modal

Shown when **Options** is clicked (or `O` in workspace):

- **Auto-route when layout changes** — reroute after recipe/cell assign or machine delete (toolbar **Route all** always runs)
- **Show machine / I/O labels** — toggle on-canvas labels
- **Palette width** — left sidebar width in pixels
- **Opt. search stale limit** — stop search after this many trials without a better layout (default 20)
- **Opt. search max iters** — hard cap on trials (`0` = no cap)

**Save** persists to `config.json` under `assisted_build_settings`. **Close** / ESC discards unsaved edits.

### Keyboard

| Key | Action |
|-----|--------|
| `0` | Select Input Cell |
| `1`–`7` | Select machine in palette (order in sidebar) |
| `Q` | Clear placement tool and selection |
| `E` / `Enter` | Set recipe for selected machine(s) |
| `Del` | Delete selected machine(s), or machine under cursor |
| `Esc` | Stop optimization search if active; else clear selection (or pause if nothing selected) |
| `R` | Route all (same as toolbar) |
| `U` | Toggle continuous optimization search (same as **Optimize** toolbar) |
| `O` | Open Assisted Build options modal |
| `C` | Center camera |
| Mouse wheel | Zoom on canvas |
| `W` `A` `S` `D` | Pan canvas (hold) |
| Left-drag (empty area) | Pan |
| `ESC` | Pause menu |

Place an **Input Cell** (`0`) where you want each raw resource chest; belts run east from there. If a resource has no placed input cell, a default bus is still created at the fixed legacy position.

## Defaults on first open

`main.py` passes `initial_targets=PRODUCTION_TARGETS` from `constants.py` and may open the targets modal immediately (`open_targets_modal=True`) for **Autonomous Build** only.
