# Controls

How a user (or automated UI test) navigates the application.

## Application flow

```mermaid
stateDiagram-v2
    [*] --> MainMenu
    MainMenu --> Workspace: Start
    MainMenu --> Assisted: Assisted Build
    MainMenu --> Settings: Settings
    MainMenu --> [*]: Exit
    Settings --> MainMenu: Back
    Workspace --> MainMenu: Pause → Return to menu
    Assisted --> MainMenu: Pause → Return to menu
    Workspace --> Workspace: Generate / Center / Pan
    Assisted --> Assisted: Place / Recipe / Route
```

1. **`python main.py`** → main menu.
2. **Start** → blueprint workspace (may open targets modal first if configured).
3. **Assisted Build** → place machines, set each machine’s recipe, belts route automatically.
4. **Set targets** (full generate only) → add items and rates → **Generate** in modal or toolbar.
5. **Copy BP** → clipboard string for Factorio.

## Main menu

| Input | Action |
|-------|--------|
| ↑ / ↓ or mouse | Navigate |
| Enter | Select |
| ESC | Exit application |

## Settings

- Set **Factorio installation path** (saved to `config.json`, gitignored).
- Required for sprite preview; generation still runs without it (entities render as placeholders if sprites missing).

## Blueprint workspace

### Toolbar

| Button | Action |
|--------|--------|
| **Set Targets** | Open modal: items, rates/min, Assemblers only / From raw |
| **Generate** | `run_generation_pipeline()` with current config |
| **Place: Rules / Genetic** | Toggle `PlacementStrategy` |
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

### Keyboard (workspace)

| Key | Action |
|-----|--------|
| `T` | Open targets modal |
| `G` | Generate (same as toolbar) |
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
| **Center** | Center camera on blueprint |
| **Copy BP** | Copy encoded blueprint string |
| **Pause** | Resume or return to main menu |

### Keyboard

| Key | Action |
|-----|--------|
| `0` | Select Input Cell |
| `1`–`7` | Select machine in palette (order in sidebar) |
| `Q` | Clear placement tool and selection |
| `E` / `Enter` | Set recipe for selected machine(s) |
| `Del` | Delete selected machine(s), or machine under cursor |
| `Esc` | Clear selection (or pause if nothing selected) |
| `R` | Route all (same as toolbar) |
| `C` | Center camera |
| `Del` | Remove machine under cursor |
| Mouse wheel | Zoom on canvas |
| `W` `A` `S` `D` | Pan canvas (hold) |
| Left-drag (empty area) | Pan |
| `ESC` | Pause menu |

Place an **Input Cell** (`0`) where you want each raw resource chest; belts run east from there. If a resource has no placed input cell, a default bus is still created at the fixed legacy position.

## Defaults on first open

`main.py` passes `initial_targets=PRODUCTION_TARGETS` from `constants.py` and may open the targets modal immediately (`open_targets_modal=True`) for **Start** only.
