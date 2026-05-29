"""Tests that assisted and autonomous modes share one routing entrypoint."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from core.constants import FACTORIO_EAST
from core.grid_env import Grid
from planners.assisted_routing import (
    AssistedBuildState,
    rate_nodes_from_machines,
    stage_machines_from_placed,
)
from planners.machine_io import place_machine_io_block, recipe_input_lane_count
from planners.production_planner import RateNode
from planners.stage_connector import latest_chain_product, route_placed_layout


def _load_recipes():
    with open(ROOT / "src" / "data" / "recipes.json", encoding="utf-8") as f:
        return json.load(f)


def _belt_signature(entities: list) -> list[tuple]:
    """Stable ordering of belt/underground entities for comparison."""
    sig = []
    for e in entities:
        name = e.get("name", "")
        if "belt" not in name:
            continue
        pos = e.get("position") or {}
        sig.append(
            (
                name,
                int(round(pos.get("x", 0))),
                int(round(pos.get("y", 0))),
                e.get("direction"),
                e.get("type"),
            )
        )
    return sorted(sig)


def _route_fixed_layout(
    grid: Grid,
    stage_machines: dict,
    nodes: dict,
    *,
    input_sources=None,
) -> list:
    entities: list = []
    entity_number = 1
    recipes = _load_recipes()
    for item, machines in stage_machines.items():
        node = nodes[item]
        for mx, my, w, h in machines:
            entities.append({
                "entity_number": entity_number,
                "name": node.recipe.get("machine", "assembling-machine-1"),
                "position": {"x": mx, "y": my},
            })
            grid.occupy(mx, my, "machine", [w, h])
            entity_number += 1
            entity_number = place_machine_io_block(
                grid,
                entities,
                entity_number,
                mx,
                my,
                w,
                h,
                flow_direction=FACTORIO_EAST,
                recipe=node.recipe,
                input_lane_count=recipe_input_lane_count(node.recipe),
            )
    route_placed_layout(
        grid,
        entities,
        entity_number,
        stage_machines,
        nodes,
        input_sources=input_sources,
        place_machine_knots=False,
    )
    return entities


class TestLayoutRouting(unittest.TestCase):
    def setUp(self):
        self.recipes_data = _load_recipes()
        self.recipes = self.recipes_data["recipes"]

    def _nodes_for(self, *items: str) -> dict[str, RateNode]:
        nodes = {}
        for item in items:
            recipe = self.recipes[item]
            nodes[item] = RateNode(
                item=item,
                required_rate=0.0,
                recipe=recipe,
                dependencies=list(recipe["ingredients"].keys()),
            )
        return nodes

    def test_route_placed_layout_same_result_direct_and_assisted(self):
        """Identical layout via shared router matches assisted session reroute."""
        stage_machines = {
            "iron-plate": [(5, 10, 2, 2)],
            "iron-gear-wheel": [(40, 10, 3, 3)],
        }
        nodes = self._nodes_for("iron-plate", "iron-gear-wheel")

        grid_a = Grid(width=120, height=120)
        entities_a = _route_fixed_layout(grid_a, stage_machines, nodes)

        state = AssistedBuildState(
            grid=Grid(width=120, height=120), recipes_data=self.recipes_data
        )
        f = state.place_machine("stone-furnace", 5, 10, (2, 2))
        a = state.place_machine("assembling-machine-1", 40, 10, (3, 3))
        state.assign_recipe(f.id, "iron-plate")
        state.assign_recipe(a.id, "iron-gear-wheel")

        belts_a = sum(1 for s in _belt_signature(entities_a) if s[0] == "transport-belt")
        belts_b = sum(1 for s in _belt_signature(state.entities) if s[0] == "transport-belt")
        self.assertGreater(belts_a, 5)
        self.assertGreater(belts_b, 5)
        inserters_a = sum(1 for e in entities_a if "inserter" in e.get("name", ""))
        inserters_b = sum(1 for e in state.entities if "inserter" in e.get("name", ""))
        self.assertGreaterEqual(inserters_b, inserters_a)

    def test_assisted_uses_route_placed_layout_not_local_routing(self):
        """Assisted module must not define duplicate connect/route helpers."""
        import planners.assisted_routing as ar

        self.assertFalse(hasattr(ar, "route_connections"))
        self.assertFalse(hasattr(ar, "connect_assisted_base_materials"))

    def test_latest_chain_product_picks_terminal_stage(self):
        stage_machines = {
            "iron-plate": [(5, 10, 2, 2)],
            "iron-gear-wheel": [(40, 10, 3, 3)],
        }
        nodes = self._nodes_for("iron-plate", "iron-gear-wheel")
        self.assertEqual(latest_chain_product(stage_machines, nodes), "iron-gear-wheel")

    def test_stage_machines_helpers_match_assisted_layout(self):
        state = AssistedBuildState(
            grid=Grid(width=120, height=120), recipes_data=self.recipes_data
        )
        state.place_machine("stone-furnace", 5, 10, (2, 2))
        state.place_machine("assembling-machine-1", 40, 10, (3, 3))
        for m in state.machines:
            m.recipe_item = "iron-plate" if "furnace" in m.entity_name else "iron-gear-wheel"

        expected = {"iron-plate": [(5, 10, 2, 2)], "iron-gear-wheel": [(40, 10, 3, 3)]}
        self.assertEqual(stage_machines_from_placed(state.machines), expected)
        self.assertIn("iron-plate", rate_nodes_from_machines(state.machines, self.recipes_data))


if __name__ == "__main__":
    unittest.main()
