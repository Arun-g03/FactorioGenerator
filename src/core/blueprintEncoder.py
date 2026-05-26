"""Encode blueprint dicts to Factorio blueprint strings."""

from __future__ import annotations

import copy

_DEFAULT_SIZES: dict[str, tuple[int, int]] = {
    "transport-belt": (1, 1),
    "fast-transport-belt": (1, 1),
    "express-transport-belt": (1, 1),
    "underground-belt": (1, 1),
    "fast-underground-belt": (1, 1),
    "express-underground-belt": (1, 1),
    "turbo-underground-belt": (1, 1),
    "inserter": (1, 1),
    "fast-inserter": (1, 1),
    "long-handed-inserter": (1, 1),
    "wooden-chest": (1, 1),
    "iron-chest": (1, 1),
    "steel-chest": (1, 1),
    "splitter": (2, 1),
    "fast-splitter": (2, 1),
    "express-splitter": (2, 1),
    "turbo-splitter": (2, 1),
    "stone-furnace": (2, 2),
    "steel-furnace": (2, 2),
    "electric-furnace": (3, 3),
}


def _entity_footprint(entity: dict, recipes_data: dict | None) -> tuple[int, int]:
    """Tile width/height for an entity (planner uses top-left grid coords)."""
    name = entity.get("name", "")
    if "assembling-machine" in name:
        return 3, 3

    recipe_item = entity.get("recipe")
    if recipe_item and recipes_data:
        recipe = recipes_data.get("recipes", {}).get(recipe_item, {})
        size = recipe.get("machine_size")
        if size and len(size) >= 2:
            return int(size[0]), int(size[1])

    for key, size in _DEFAULT_SIZES.items():
        if key in name or name == key:
            return size
    if "furnace" in name:
        return 2, 2
    return 1, 1


def _uses_grid_corner_positions(entity: dict) -> bool:
    """True when position looks like planner grid origin (integer coords)."""
    pos = entity.get("position") or {}
    x, y = pos.get("x", 0), pos.get("y", 0)
    return abs(x - round(x)) < 1e-6 and abs(y - round(y)) < 1e-6


def blueprint_for_factorio_export(blueprint: dict, recipes_data: dict | None = None) -> dict:
    """
    Copy blueprint with entity positions converted to Factorio centers.

    Internal placement uses top-left tile indices; exported blueprints need
  entity center positions (e.g. a 3×3 assembler at grid (10,12) → (11.5, 13.5)).
    """
    out = copy.deepcopy(blueprint)
    entities = out.get("blueprint", {}).get("entities")
    if not entities:
        return out

    converted = []
    for entity in entities:
        ent = dict(entity)
        if _uses_grid_corner_positions(ent):
            w, h = _entity_footprint(ent, recipes_data)
            pos = ent["position"]
            ent["position"] = {
                "x": pos["x"] + w / 2,
                "y": pos["y"] + h / 2,
            }
        converted.append(ent)
    out["blueprint"]["entities"] = converted
    return out


def encode_blueprint(blueprint, recipes_data=None):
    """Encode the blueprint into a Factorio-compatible string."""
    import base64
    import json
    import zlib

    export = blueprint_for_factorio_export(blueprint, recipes_data)
    blueprint_json = json.dumps(export)
    compressed_data = zlib.compress(blueprint_json.encode())
    return "0" + base64.b64encode(compressed_data).decode()
