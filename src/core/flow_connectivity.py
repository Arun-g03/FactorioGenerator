"""
Directed item-flow graph for blueprint entities.

Builds adjacency from belts (flow direction), inserters (pickup → drop),
machine interiors, underground pairs, and splitters; then uses BFS to verify
that production stages are connected belt → inserter → machine → inserter → belt.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from core.constants import (
    BELT_CORNER_DIRECTIONS,
    BELT_ENTITIES,
    DIRECTION_FRONT_OFFSET,
    FACTORIO_EAST,
    FACTORIO_NORTH,
    FACTORIO_SOUTH,
    FACTORIO_WEST,
    INSERTER_ENTITIES,
    UNDERGROUND_BELT_ENTITIES,
    inserter_drop_tile,
    inserter_pickup_tile,
)

_CORNER_TO_ARMS = {curve: arms for arms, curve in BELT_CORNER_DIRECTIONS.items()}

SPLITTER_NAMES = frozenset(
    {"splitter", "fast-splitter", "express-splitter", "turbo-splitter"}
)
CHEST_NAMES = frozenset({"wooden-chest", "iron-chest", "steel-chest"})


@dataclass
class FlowValidationResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)

    def add(self, message: str) -> None:
        self.ok = False
        if message not in self.errors:
            self.errors.append(message)


def _entity_tile(entity: dict) -> tuple[int, int]:
    pos = entity.get("position") or {}
    x = pos.get("x", 0)
    y = pos.get("y", 0)
    return int(round(x)), int(round(y))


def _is_belt(name: str) -> bool:
    return any(name == b or name.endswith(b) for b in BELT_ENTITIES)


def _is_inserter(name: str) -> bool:
    return any(name == i or "inserter" in name for i in INSERTER_ENTITIES)


def _is_underground(name: str) -> bool:
    return any(name == u or "underground-belt" in name for u in UNDERGROUND_BELT_ENTITIES)


def _is_machine(name: str) -> bool:
    return (
        "assembling-machine" in name
        or "furnace" in name
        or name in ("chemical-plant", "oil-refinery")
    )


def _add_edge(adj: dict[tuple[int, int], set[tuple[int, int]]], src, dst) -> None:
    if src is None or dst is None or src == dst:
        return
    adj.setdefault(src, set()).add(dst)


def build_tile_map(entities: list[dict]) -> dict[tuple[int, int], dict]:
    """Map grid corner tiles to entity dicts (last writer wins on overlap)."""
    from core.splitter_geometry import splitter_layout

    tile_map: dict[tuple[int, int], dict] = {}
    for entity in entities:
        x, y = _entity_tile(entity)
        name = entity.get("name", "")
        if name in SPLITTER_NAMES:
            layout = splitter_layout((x, y), entity.get("direction", FACTORIO_EAST))
            for tile in layout.footprint:
                tile_map[tile] = entity
            continue
        tile_map[(x, y)] = entity
        size = entity.get("size")
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            ew, eh = int(size[0]), int(size[1])
            if ew > 1 or eh > 1:
                for dx in range(ew):
                    for dy in range(eh):
                        tile_map[(x + dx, y + dy)] = entity
    return tile_map


def _machine_footprints(stage_machines: dict[str, list]) -> list[tuple[str, set[tuple[int, int]]]]:
    footprints = []
    for item, machines in stage_machines.items():
        for mx, my, w, h in machines:
            cells = {
                (int(mx) + dx, int(my) + dy)
                for dx in range(int(w))
                for dy in range(int(h))
            }
            footprints.append((item, cells))
    return footprints


def _link_underground_pairs(
    entities: list[dict],
    adj: dict[tuple[int, int], set[tuple[int, int]]],
) -> None:
    """Teleport flow from each underground input to its paired output."""
    inputs = []
    outputs = []
    for entity in entities:
        name = entity.get("name", "")
        if not _is_underground(name):
            continue
        pos = _entity_tile(entity)
        direction = entity.get("direction", FACTORIO_EAST)
        if entity.get("type") == "input":
            inputs.append((pos, direction, name))
        elif entity.get("type") == "output":
            outputs.append((pos, direction, name))

    used_outputs: set[tuple[int, int]] = set()
    for in_pos, direction, in_name in inputs:
        dx, dy = DIRECTION_FRONT_OFFSET.get(direction, (1, 0))
        best_out = None
        best_span = None
        max_span = 10
        for out_pos, out_dir, out_name in outputs:
            if out_pos in used_outputs or out_dir != direction or in_name != out_name:
                continue
            ix, iy = in_pos
            ox, oy = out_pos
            if iy != oy and ix != ox:
                continue
            if direction == FACTORIO_EAST:
                if iy != oy or ox <= ix:
                    continue
                span = ox - ix
            elif direction == FACTORIO_WEST:
                if iy != oy or ox >= ix:
                    continue
                span = ix - ox
            elif direction == FACTORIO_SOUTH:
                if ix != ox or oy <= iy:
                    continue
                span = oy - iy
            elif direction == FACTORIO_NORTH:
                if ix != ox or oy >= iy:
                    continue
                span = iy - oy
            else:
                continue
            if span < 1 or span > max_span:
                continue
            if best_span is None or span < best_span:
                best_span = span
                best_out = out_pos
        if best_out is None:
            continue
        used_outputs.add(best_out)
        ox, oy = best_out
        _add_edge(adj, (in_pos[0] - dx, in_pos[1] - dy), (ox + dx, oy + dy))


def build_flow_adjacency(
    tile_map: dict[tuple[int, int], dict],
    entities: list[dict],
    machine_footprints: list[tuple[str, set[tuple[int, int]]]],
) -> dict[tuple[int, int], set[tuple[int, int]]]:
    """Directed edges for item movement between adjacent tiles."""
    adj: dict[tuple[int, int], set[tuple[int, int]]] = {}

    for (x, y), entity in tile_map.items():
        name = entity.get("name", "")
        direction = entity.get("direction", FACTORIO_EAST)
        dx, dy = DIRECTION_FRONT_OFFSET.get(direction, (1, 0))

        if _is_belt(name):
            arms = _CORNER_TO_ARMS.get(direction)
            if arms is not None:
                in_dir, out_dir = arms
                in_dx, in_dy = DIRECTION_FRONT_OFFSET[in_dir]
                out_dx, out_dy = DIRECTION_FRONT_OFFSET[out_dir]
                _add_edge(adj, (x - in_dx, y - in_dy), (x, y))
                _add_edge(adj, (x, y), (x + out_dx, y + out_dy))
            else:
                _add_edge(adj, (x - dx, y - dy), (x, y))
                _add_edge(adj, (x, y), (x + dx, y + dy))
        elif _is_inserter(name):
            pickup = inserter_pickup_tile((x, y), direction)
            drop = inserter_drop_tile((x, y), direction)
            _add_edge(adj, pickup, drop)
        elif name in SPLITTER_NAMES:
            from core.splitter_geometry import splitter_flow_edges

            anchor = _entity_tile(entity)
            if (x, y) != anchor:
                continue
            for src, dst in splitter_flow_edges(anchor, direction):
                _add_edge(adj, src, dst)
        elif name in CHEST_NAMES:
            _add_edge(adj, (x, y), (x + dx, y + dy))

    for _item, cells in machine_footprints:
        input_drops: list[tuple[int, int]] = []
        output_pickups: list[tuple[int, int]] = []
        for (x, y), entity in tile_map.items():
            if not _is_inserter(entity.get("name", "")):
                continue
            direction = entity.get("direction", FACTORIO_EAST)
            pickup = inserter_pickup_tile((x, y), direction)
            drop = inserter_drop_tile((x, y), direction)
            if drop in cells:
                input_drops.append(drop)
            if pickup in cells:
                output_pickups.append(pickup)
        for drop in input_drops:
            for pickup in output_pickups:
                _add_edge(adj, drop, pickup)

    _link_underground_pairs(entities, adj)
    return adj


def flow_reachable(
    sources: set[tuple[int, int]],
    targets: set[tuple[int, int]],
    adj: dict[tuple[int, int], set[tuple[int, int]]],
) -> bool:
    """BFS from any source until any target tile is reached."""
    if not sources or not targets:
        return False
    if sources & targets:
        return True
    queue = deque(sources)
    seen = set(sources)
    while queue:
        node = queue.popleft()
        for nxt in adj.get(node, ()):
            if nxt in targets:
                return True
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


def _flow_endpoint_tiles(
    anchor: tuple[int, int],
    tile_map: dict[tuple[int, int], dict],
    radius: int = 14,
) -> set[tuple[int, int]]:
    """All belt/splitter/underground tiles near a stage I/O anchor (any flow axis)."""
    ax, ay = anchor
    tiles: set[tuple[int, int]] = set()
    for (x, y), entity in tile_map.items():
        name = entity.get("name", "")
        if not (_is_belt(name) or _is_underground(name) or name in SPLITTER_NAMES):
            continue
        if abs(x - ax) + abs(y - ay) <= radius:
            tiles.add((x, y))
    if anchor in tile_map:
        tiles.add(anchor)
    return tiles


def _belt_outputs_to(pickup: tuple[int, int], tile_map: dict[tuple[int, int], dict], adj) -> bool:
    """True if a belt delivers items into ``pickup`` (neighbor or same tile)."""
    on_tile = tile_map.get(pickup)
    if on_tile and _is_belt(on_tile.get("name", "")):
        for src, targets in adj.items():
            if src != pickup and pickup in targets:
                return True
    for neighbor, entity in _neighbors(pickup, tile_map):
        if _is_belt(entity.get("name", "")) and pickup in adj.get(neighbor, ()):
            return True
    return False


def _belt_receives_from(drop: tuple[int, int], tile_map: dict[tuple[int, int], dict], adj) -> bool:
    """True if a belt accepts items from ``drop`` (neighbor or same tile)."""
    on_tile = tile_map.get(drop)
    if on_tile and _is_belt(on_tile.get("name", "")) and adj.get(drop):
        return True
    for neighbor, entity in _neighbors(drop, tile_map):
        if _is_belt(entity.get("name", "")) and neighbor in adj.get(drop, ()):
            return True
    return False


def _neighbors(pos: tuple[int, int], tile_map: dict[tuple[int, int], dict]):
    x, y = pos
    for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        npos = (x + dx, y + dy)
        ent = tile_map.get(npos)
        if ent is not None:
            yield npos, ent


def validate_machine_io(
    item: str,
    cells: set[tuple[int, int]],
    tile_map: dict[tuple[int, int], dict],
    adj: dict[tuple[int, int], set[tuple[int, int]]],
    result: FlowValidationResult,
) -> None:
    """Each machine must have belt → inserter → body → inserter → belt."""
    input_drops: list[tuple[int, int]] = []
    output_pickups: list[tuple[int, int]] = []
    input_belts: set[tuple[int, int]] = set()
    output_belts: set[tuple[int, int]] = set()

    for (x, y), entity in tile_map.items():
        name = entity.get("name", "")
        if _is_inserter(name):
            direction = entity.get("direction", FACTORIO_EAST)
            pickup = inserter_pickup_tile((x, y), direction)
            drop = inserter_drop_tile((x, y), direction)
            if drop in cells:
                input_drops.append(drop)
                if _is_belt(tile_map.get(pickup, {}).get("name", "")):
                    input_belts.add(pickup)
            if pickup in cells:
                output_pickups.append(pickup)
                drop_pos = inserter_drop_tile((x, y), direction)
                if _is_belt(tile_map.get(drop_pos, {}).get("name", "")):
                    output_belts.add(drop_pos)

    if not input_drops:
        result.add(f"{item}: missing input inserter onto machine")
    else:
        for (x, y), entity in tile_map.items():
            if not _is_inserter(entity.get("name", "")):
                continue
            direction = entity.get("direction", FACTORIO_EAST)
            drop = inserter_drop_tile((x, y), direction)
            pickup = inserter_pickup_tile((x, y), direction)
            if drop not in cells:
                continue
            if not _belt_outputs_to(pickup, tile_map, adj):
                result.add(f"{item}: input inserter not fed by belt (pickup side)")

    if not output_pickups:
        result.add(f"{item}: missing output inserter from machine")
    else:
        for (x, y), entity in tile_map.items():
            if not _is_inserter(entity.get("name", "")):
                continue
            direction = entity.get("direction", FACTORIO_EAST)
            pickup = inserter_pickup_tile((x, y), direction)
            drop = inserter_drop_tile((x, y), direction)
            if pickup not in cells:
                continue
            if not _belt_receives_from(drop, tile_map, adj):
                result.add(f"{item}: output inserter not connected to belt (drop side)")


def validate_blueprint_flow(
    entities: list[dict],
    stage_machines: dict[str, list],
    nodes: dict,
    *,
    stage_lanes: dict | None = None,
) -> FlowValidationResult:
    """
    Verify item flow through belts, inserters, machines, and stage links.

    Uses graph search (BFS) on a directed adjacency built from entity directions.
    """
    result = FlowValidationResult()
    if not entities or not stage_machines:
        return result

    tile_map = build_tile_map(entities)
    footprints = _machine_footprints(stage_machines)
    adj = build_flow_adjacency(tile_map, entities, footprints)

    for item, cells in footprints:
        validate_machine_io(item, cells, tile_map, adj, result)

    if stage_lanes is None:
        from planners.stage_connector import stage_lanes_from_machines

        stage_lanes = {}
        for item, machines in stage_machines.items():
            node = nodes.get(item)
            recipe = getattr(node, "recipe", None) if node else None
            lanes = stage_lanes_from_machines(machines, recipe=recipe)
            if lanes:
                stage_lanes[item] = lanes

    from core.constants import BASE_MATERIALS
    from planners.machine_io import ingredient_lane_index

    for item, node in nodes.items():
        if item not in stage_lanes:
            continue
        consumer = stage_lanes[item]
        consumer_recipe = getattr(node, "recipe", None) or {}
        input_starts = consumer.get("input_starts", [consumer["input_start"]])

        for dep in node.dependencies:
            lane_idx = ingredient_lane_index(consumer_recipe, dep)
            consumer_in = input_starts[min(lane_idx, len(input_starts) - 1)]
            consumer_targets = _flow_endpoint_tiles(consumer_in, tile_map)

            if dep in BASE_MATERIALS:
                chest_sources = {
                    pos
                    for pos, ent in tile_map.items()
                    if ent.get("name") in CHEST_NAMES
                }
                bus_belts = _flow_endpoint_tiles(consumer_in, tile_map, radius=20)
                if chest_sources and not flow_reachable(chest_sources, bus_belts, adj):
                    result.add(f"no flow from {dep} bus to {item} input")
                continue

            if dep not in stage_lanes:
                continue

            producer_out = stage_lanes[dep].get(
                "output_start", stage_lanes[dep]["output_end"]
            )
            producer_sources = _flow_endpoint_tiles(producer_out, tile_map)
            if not flow_reachable(producer_sources, consumer_targets, adj):
                result.add(f"no belt flow from {dep} stage to {item} stage")

    return result
