# Factorio Blueprint Generator

A standalone tool that programmatically generates **Factorio blueprints** for automated factory layouts.

This project allows users to define inputs (e.g., production goals, ratios, layout patterns) and outputs valid **Factorio blueprint strings** that can be copied directly into the game.

---

## 🧩 Features

- **Autonomous Build** — generate complete factory blueprints from production targets (items/min)
- **Assisted Build** — place machines by hand; belts and inserters route automatically
- **Placement Replay** — step through recorded placement reasoning after a generation run
- Dependency-network rule placement or genetic layout search
- Configurable placement options (network spacing, GA population, search bounds)
- Visualize layouts in Pygame with sprites from your **local Factorio installation** (no assets bundled)
- Interactive recipe configuration with autocomplete
- Copy blueprints to clipboard with one click

---

## ⚙️ Setup

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv factorio_venv

# Activate virtual environment
# Windows:
factorio_venv\Scripts\activate
# Linux/Mac:
source factorio_venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 2. Configure Factorio Installation Path

To visualize blueprints, the tool needs to access sprites from your local Factorio installation.

**No copyrighted assets are bundled with this project.**

Configure the path in **Settings → Factorio Installation Path**.

The tool will automatically find the graphics folder. Enter your Factorio installation base directory:

- **Windows (Steam)**: `C:\Program Files (x86)\Steam\steamapps\common\Factorio`
- **Windows (GOG)**: `C:\GOG Games\Factorio`
- **Linux/Mac (Steam)**: `~/.steam/steam/steamapps/common/Factorio`
- **Mac**: `~/Library/Application Support/Steam/steamapps/common/Factorio`

⚠️ **Note:** Factorio sprites are © Wube Software Ltd. and are not distributed with this project.

### 3. Run the Generator

```bash
python main.py
```

The main menu offers:

1. **Autonomous Build** — configure targets, generate, preview on the canvas
2. **Assisted Build** — manual machine placement with automatic routing
3. **Placement Replay** — watch each placement step with on-screen reasoning
4. **Settings** — Factorio install path and window size

---

## 🕹️ Controls

### Main Menu
- **↑↓ or Mouse**: Navigate (Autonomous Build, Assisted Build, Placement Replay, Settings, Exit)
- **Enter**: Select option
- **ESC**: Exit

### Workspace & replay

See [docs/controls.md](docs/controls.md) for toolbar actions, **Options**, placement toggle, camera shortcuts, and replay transport controls.

---

## 📁 Project Structure

```
src/
├── core/          # Game logic (grid, pathfinding, routing)
├── planners/      # Production algorithms
├── ui/            # Pygame visualization
└── data/          # Recipes, buildings JSON
docs/              # Setup, architecture, generation, data model, development
```

**Documentation:** [docs/README.md](docs/README.md) — start here for architecture, generation pipeline, data formats, and contributor notes (including guidance for AI assistants).

---

## ⚖️ Legal

- This project is **not affiliated with** Wube Software Ltd.
- **Factorio assets are © Wube Software Ltd.** 
- No copyrighted files are included - tools reads from your local installation.
- Users must own a valid Factorio license.

---

## 📝 License

MIT License - see [LICENSE](LICENSE) for full details.

Tool reads Factorio assets from user's local installation.
