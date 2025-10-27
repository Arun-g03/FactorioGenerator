# Factorio Blueprint Generator

A standalone tool that programmatically generates **Factorio blueprints** for automated factory layouts.

This project allows users to define inputs (e.g., production goals, ratios, layout patterns) and outputs valid **Factorio blueprint strings** that can be copied directly into the game.

---

## 🧩 Features

- Generate complete factory blueprints automatically  
- Visualize layouts using Pygame  
- Save and load blueprint configurations  
- Supports scalable factory design logic (assemblers, belts, inserters, etc.)  
- Dynamic sprite loading from a user's **local Factorio installation** (no assets included)
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

The system will:
1. Show a main menu
2. Let you configure recipes and production targets
3. Generate a blueprint
4. Display it in a Pygame window for visualization

---

## 🕹️ Controls

### Main Menu
- **↑↓ or Mouse**: Navigate options
- **Enter**: Select option
- **ESC**: Exit

### Recipe Configuration & Blueprint Viewer
- **Mouse**: Click to interact, drag to pan blueprint
- **Mouse Wheel**: Zoom in/out
- **Keyboard**: Arrow keys to navigate menus, Enter to select
- **ESC**: Pause/Return to menu
- **S**: Save screenshot
- **R**: Reset camera

---

## 📁 Project Structure

```
src/
├── core/          # Game logic (grid, pathfinding, routing)
├── planners/      # Production algorithms
├── ui/            # Pygame visualization
└── data/          # Recipes, buildings JSON
```

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
