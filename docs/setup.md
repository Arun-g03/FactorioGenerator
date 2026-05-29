# Setup

## Requirements

| Requirement | Notes |
|-------------|--------|
| **Python 3.10+** | Required for `X \| Y` type syntax in dataclasses |
| **Factorio install** | Optional for generation; needed for accurate sprites in preview |
| **pygame, pyperclip** | See `requirements.txt` |

## Install

```bash
cd FactorioGenerator
python -m venv factorio_venv

# Windows
factorio_venv\Scripts\activate

# Linux / macOS
source factorio_venv/bin/activate

pip install -r requirements.txt
```

## Factorio graphics path

Sprites are read from disk at runtime. **No game assets are in the repo.**

1. Run `python main.py`
2. **Settings** → set installation path to the **game root** (folder containing `data/`)
3. Path is saved to `config.json` (gitignored)

Resolved graphics directory:

```
{factorio_install_path}/data/base/graphics/entity
```

| Platform | Typical install path |
|----------|----------------------|
| Windows (Steam) | `C:\Program Files (x86)\Steam\steamapps\common\Factorio` |
| Windows (GOG) | `C:\GOG Games\Factorio` |
| Linux (Steam) | `~/.steam/steam/steamapps/common/Factorio` |
| macOS (Steam) | `~/Library/Application Support/Steam/steamapps/common/Factorio` |

Factorio © Wube Software Ltd. — own a valid license.

## Run

```bash
python main.py
```

## Verify install

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Requires **Python 3.10+** (see Requirements). With 3.10+, tests cover calculations, rule-based layout, belt routing, splitters, underground belts, inserter directions, placement validation, and more. `test_sprite_sheets` needs a valid Factorio graphics path in `config.json`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `TypeError: unsupported operand type(s) for \|` | Python &lt; 3.10 | Recreate venv with 3.10+ |
| Blank / missing sprites | Wrong Factorio path | Settings → correct root folder |
| `No module named 'pygame'` | Deps not installed | `pip install -r requirements.txt` |
| Copy button missing | No pyperclip | `pip install pyperclip` |
| Import errors from `src/` | Wrong cwd | Run `main.py` from repo root |
| Generation warning “No recipe” | Item id not in `recipes.json` | Add recipe or fix spelling (use internal ids) |

## Optional: headless generation check

From repo root with venv active:

```bash
python -c "import sys,json; from pathlib import Path; sys.path.insert(0,'src'); from core.pipeline import run_generation_pipeline; from core.constants import *; r=json.load(open('src/data/recipes.json')); o=run_generation_pipeline({'iron-plate':20},r,FULL_CHAIN,RULE_BASED); print(o.entity_count,'entities')"
```

Should print an entity count with no traceback.
