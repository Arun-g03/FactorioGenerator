"""Build ordered belt links from a placed layout (stage / base / sink)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from core.constants import BASE_MATERIALS, FACTORIO_EAST

from planners.stage_connector import (
    OUTPUT_ANY_PRODUCT,
    latest_chain_product,
    stage_lanes_from_machines,
)

logger = logging.getLogger(__name__)

LinkKind = Literal["base_feed", "stage", "output_sink"]

PRIORITY_BASE = 100
PRIORITY_STAGE = 200
PRIORITY_OUTPUT = 300


@dataclass
class BeltLink:
    """One logical item flow between belt-side knot tiles."""

    link_id: str
    item: str
    source: tuple[int, int]
    sink: tuple[int, int]
    kind: LinkKind
    group_key: str
    priority: int
    source_knot: tuple | None = None
    dest_knot: tuple | None = None
    lane_offset: int = 0
    merge_from: tuple[int, int] | None = None
    metadata: dict = field(default_factory=dict)


def sort_links(links: list[BeltLink]) -> list[BeltLink]:
    """Order links: base feeds, then stages, then outputs; stable within priority."""
    return sorted(links, key=lambda link: (link.priority, link.group_key, link.link_id))


def _stage_links(
    stage_machines,
    nodes,
    *,
    link_counter: list[int],
) -> list[BeltLink]:
    from planners.machine_io import (
        ingredient_lane_index,
        ingredient_lane_offsets,
        machine_input_inserter_knot,
        recipe_input_lane_count,
    )

    stage_lanes = {}
    for item, machines in stage_machines.items():
        recipe = getattr(nodes.get(item), "recipe", None)
        lanes = stage_lanes_from_machines(machines, recipe=recipe)
        if lanes:
            stage_lanes[item] = lanes

    links: list[BeltLink] = []
    requests_by_producer: dict[tuple[int, int], list[dict]] = {}

    for consumer_item, node in nodes.items():
        if consumer_item not in stage_lanes:
            continue
        consumer_lanes = stage_lanes[consumer_item]
        consumer_recipe = getattr(node, "recipe", None) or {}
        input_connects = consumer_lanes.get(
            "input_connects",
            consumer_lanes.get("input_starts", [consumer_lanes["input_start"]]),
        )

        for dep in node.dependencies:
            if dep in BASE_MATERIALS or dep not in stage_lanes:
                continue
            producer_lanes = stage_lanes[dep]
            producer_output = producer_lanes.get(
                "output_start", producer_lanes["output_end"]
            )
            lane_idx = ingredient_lane_index(consumer_recipe, dep)
            consumer_input_start = input_connects[
                min(lane_idx, len(input_connects) - 1)
            ]
            requests_by_producer.setdefault(producer_output, []).append(
                {
                    "consumer_item": consumer_item,
                    "consumer_input_start": consumer_input_start,
                    "target_y": consumer_input_start[1],
                    "lane_offset": 0,
                    "lane_idx": lane_idx,
                    "dep": dep,
                }
            )

    for producer_output, requests in requests_by_producer.items():
        seen = set()
        unique = []
        for req in requests:
            key = (
                req["consumer_item"],
                req["consumer_input_start"],
                req["target_y"],
                req["dep"],
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(req)

        group_key = f"stage:{producer_output[0]},{producer_output[1]}"
        for req in unique:
            consumer_machine = stage_machines.get(req["consumer_item"], [None])[0]
            dest_knot = None
            lane_offset = req["lane_offset"]
            if consumer_machine is not None:
                mx, my, w, h = consumer_machine
                lane_count = recipe_input_lane_count(
                    getattr(nodes.get(req["consumer_item"]), "recipe", None)
                )
                offsets = ingredient_lane_offsets(lane_count)
                lane_offset = offsets[min(req.get("lane_idx", 0), len(offsets) - 1)]
                dest_knot = machine_input_inserter_knot(
                    mx, my, w, h, FACTORIO_EAST, lane_offset=lane_offset
                )

            from planners.machine_io import knot_belt_tile

            sink = req["consumer_input_start"]
            dest_belt = knot_belt_tile(dest_knot)
            if dest_belt is not None:
                sink = dest_belt

            link_counter[0] += 1
            links.append(
                BeltLink(
                    link_id=f"stage-{link_counter[0]}",
                    item=req["dep"],
                    source=producer_output,
                    sink=sink,
                    kind="stage",
                    group_key=group_key,
                    priority=PRIORITY_STAGE,
                    dest_knot=dest_knot,
                    lane_offset=lane_offset,
                    metadata={
                        "consumer_item": req["consumer_item"],
                        "consumer_input_start": req["consumer_input_start"],
                        "target_y": req["target_y"],
                    },
                )
            )
    return links


def _base_feed_links(
    stage_machines,
    nodes,
    input_sources: dict[str, list[tuple[int, int]]],
    *,
    link_counter: list[int],
) -> list[BeltLink]:
    from planners.machine_io import (
        chest_belt_feed_start,
        chest_to_belt_knot,
        ingredient_lane_index,
        ingredient_lane_offsets,
        knot_belt_tile,
        machine_input_inserter_knot,
        recipe_input_lane_count,
    )
    from planners.stage_connector import machine_io_lanes

    input_sources = input_sources or {}
    base_demands: dict[str, list[dict]] = {}

    for item, node in nodes.items():
        if item not in stage_machines:
            continue
        consumer_recipe = getattr(node, "recipe", None) or {}
        for machine in stage_machines[item]:
            mx, my, w, h = machine
            lane_count = recipe_input_lane_count(consumer_recipe)
            lanes = machine_io_lanes(mx, my, w, h, input_lane_count=lane_count)
            input_connects = lanes.get(
                "input_connects",
                lanes.get("input_starts", [lanes["input_start"]]),
            )
            offsets = ingredient_lane_offsets(lane_count)
            for dep in node.dependencies:
                if dep not in BASE_MATERIALS:
                    continue
                lane_idx = ingredient_lane_index(consumer_recipe, dep)
                anchor = input_connects[min(lane_idx, len(input_connects) - 1)]
                lane_offset = offsets[min(lane_idx, len(offsets) - 1)]
                base_demands.setdefault(dep, []).append(
                    {
                        "anchor": anchor,
                        "machine": machine,
                        "lane_offset": lane_offset,
                        "resource": dep,
                    }
                )

    links: list[BeltLink] = []

    def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    for resource in sorted(base_demands.keys()):
        demand_points = base_demands[resource]
        sources = input_sources.get(resource, [])
        if not sources:
            logger.info(
                "No input cell for %s; place an input cell to route this resource",
                resource,
            )
            continue

        consumers_by_source: dict[tuple[int, int], list[dict]] = {
            src: [] for src in sources
        }
        for demand in demand_points:
            consumer_input = demand["anchor"]
            best_src = min(
                sources,
                key=lambda src: manhattan(
                    chest_belt_feed_start(src[0], src[1]), consumer_input
                ),
            )
            consumers_by_source[best_src].append(demand)

        for chest_x, chest_y in sources:
            grouped = consumers_by_source.get((chest_x, chest_y), [])
            if not grouped:
                continue
            feed_start = chest_belt_feed_start(chest_x, chest_y)
            chest_knot = chest_to_belt_knot(chest_x, chest_y)
            group_key = f"base:{resource}:{chest_x},{chest_y}"

            for demand in grouped:
                mx, my, w, h = demand["machine"]
                dest_knot = machine_input_inserter_knot(
                    mx,
                    my,
                    w,
                    h,
                    FACTORIO_EAST,
                    lane_offset=demand["lane_offset"],
                )
                sink = demand["anchor"]
                dest_belt = knot_belt_tile(dest_knot)
                if dest_belt is not None:
                    sink = dest_belt

                link_counter[0] += 1
                links.append(
                    BeltLink(
                        link_id=f"base-{link_counter[0]}",
                        item=resource,
                        source=feed_start,
                        sink=sink,
                        kind="base_feed",
                        group_key=group_key,
                        priority=PRIORITY_BASE,
                        source_knot=chest_knot,
                        dest_knot=dest_knot,
                        lane_offset=demand["lane_offset"],
                        metadata={"anchor": demand["anchor"], "chest": (chest_x, chest_y)},
                    )
                )
    return links


def _output_sink_links(
    stage_machines,
    nodes,
    output_sinks: dict[str, list[tuple[int, int]]],
    *,
    link_counter: list[int],
) -> list[BeltLink]:
    from planners.machine_io import belt_to_chest_knot, chest_belt_sink_connect, recipe_input_lane_count
    from planners.stage_connector import machine_io_lanes

    output_sinks = output_sinks or {}
    links: list[BeltLink] = []

    for product in sorted(output_sinks.keys()):
        if product == OUTPUT_ANY_PRODUCT:
            latest = latest_chain_product(stage_machines, nodes)
            if not latest:
                continue
            producer_items = [latest]
        elif product in stage_machines:
            producer_items = [product]
        else:
            continue

        for producer_item in producer_items:
            node = nodes.get(producer_item)
            recipe = getattr(node, "recipe", None)
            lane_count = recipe_input_lane_count(recipe)
            producer_outputs: list[tuple[int, int]] = []
            for mx, my, w, h in stage_machines.get(producer_item, []):
                lanes = machine_io_lanes(mx, my, w, h, input_lane_count=lane_count)
                producer_outputs.append(lanes.get("output_start", lanes["output_end"]))

            for chest_x, chest_y in output_sinks[product]:
                sink_connect = chest_belt_sink_connect(chest_x, chest_y)
                dest_knot = belt_to_chest_knot(chest_x, chest_y)
                group_key = f"sink:{product}:{chest_x},{chest_y}"

                for producer_output in producer_outputs:
                    link_counter[0] += 1
                    links.append(
                        BeltLink(
                            link_id=f"sink-{link_counter[0]}",
                            item=producer_item,
                            source=producer_output,
                            sink=sink_connect,
                            kind="output_sink",
                            group_key=group_key,
                            priority=PRIORITY_OUTPUT,
                            dest_knot=dest_knot,
                            metadata={
                                "product": product,
                                "chest": (chest_x, chest_y),
                            },
                        )
                    )
    return links


def build_link_graph(
    stage_machines,
    nodes,
    *,
    input_sources: dict[str, list[tuple[int, int]]] | None = None,
    output_sinks: dict[str, list[tuple[int, int]]] | None = None,
) -> list[BeltLink]:
    """Collect all belt links for a layout, unordered."""
    counter = [0]
    links: list[BeltLink] = []
    links.extend(_base_feed_links(stage_machines, nodes, input_sources or {}, link_counter=counter))
    links.extend(_stage_links(stage_machines, nodes, link_counter=counter))
    links.extend(
        _output_sink_links(
            stage_machines, nodes, output_sinks or {}, link_counter=counter
        )
    )
    return links
