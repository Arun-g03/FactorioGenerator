"""Orchestrate link graph build, ordered materialization, and validation retries."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from planners.belt_network.amendments import bump_link_priority
from planners.belt_network.link_graph import BeltLink, build_link_graph, sort_links
from planners.belt_network.materialize import materialize_link_group
from planners.belt_network.occupancy import RoutingOccupancy
from planners.belt_network.optimize import group_order_for_variant

logger = logging.getLogger(__name__)

MAX_VALIDATION_RETRIES = 2


@dataclass
class RouteRecord:
    """Tiles and entities placed for one link (incremental reroute)."""

    link_id: str
    group_key: str
    item: str
    tiles: set[tuple[int, int]] = field(default_factory=set)
    entity_indices: list[int] = field(default_factory=list)


class BeltNetworkRouter:
    """Materialize belt links on a growing occupancy map."""

    def __init__(self):
        self.records: dict[str, RouteRecord] = {}
        self.last_conflicts: list[str] = []

    def route(
        self,
        grid,
        entities,
        entity_number: int,
        stage_machines,
        nodes,
        *,
        input_sources: dict | None = None,
        output_sinks: dict | None = None,
        placement_recorder=None,
        validate: bool = False,
        link_order_variant: int = 0,
        links: list[BeltLink] | None = None,
        group_order: list[str] | None = None,
    ) -> tuple[int, dict[str, tuple[int, int]], list[BeltLink]]:
        occupancy = RoutingOccupancy(grid)
        if links is None:
            links = sort_links(
                build_link_graph(
                    stage_machines,
                    nodes,
                    input_sources=input_sources,
                    output_sinks=output_sinks,
                )
            )
        entity_number = self._materialize_all(
            grid,
            entities,
            entity_number,
            occupancy,
            links,
            placement_recorder=placement_recorder,
            link_order_variant=link_order_variant,
            group_order=group_order,
        )

        if validate and links:
            links, entity_number = self._validation_retry_loop(
                grid,
                entities,
                entity_number,
                occupancy,
                links,
                stage_machines,
                nodes,
                placement_recorder=placement_recorder,
            )

        blueprint_inputs = self._blueprint_inputs_from_links(links, input_sources)
        return entity_number, blueprint_inputs, links

    def _materialize_all(
        self,
        grid,
        entities,
        entity_number: int,
        occupancy: RoutingOccupancy,
        links: list[BeltLink],
        *,
        placement_recorder=None,
        link_order_variant: int = 0,
        group_order: list[str] | None = None,
    ) -> int:
        groups: dict[str, list[BeltLink]] = defaultdict(list)
        for link in links:
            groups[link.group_key].append(link)

        if group_order is not None:
            ordered_keys = list(group_order)
        else:
            ordered_keys = group_order_for_variant(links, link_order_variant)
        ordered_keys = [k for k in ordered_keys if k in groups]
        for link in links:
            if link.group_key not in ordered_keys:
                ordered_keys.append(link.group_key)

        start_entity_count = len(entities)
        for group_key in ordered_keys:
            group_links = groups[group_key]
            before = len(entities)
            entity_number = materialize_link_group(
                grid, entities, entity_number, occupancy, group_links
            )
            self._record_group(group_links, entities, before, len(entities))

        if placement_recorder is not None and links:
            placement_recorder.record(
                "network_route",
                "Network belt routing",
                [f"Links: {len(links)}", f"Groups: {len(ordered_keys)}"],
                entities,
            )
        _ = start_entity_count
        return entity_number

    def _record_group(
        self,
        links: list[BeltLink],
        entities: list,
        entity_start: int,
        entity_end: int,
    ) -> None:
        indices = list(range(entity_start, entity_end))
        tiles: set[tuple[int, int]] = set()
        for entity in entities[entity_start:entity_end]:
            pos = entity.get("position") or {}
            tiles.add((int(round(pos.get("x", 0))), int(round(pos.get("y", 0)))))
        for link in links:
            self.records[link.link_id] = RouteRecord(
                link_id=link.link_id,
                group_key=link.group_key,
                item=link.item,
                tiles=tiles,
                entity_indices=indices,
            )

    def _validation_retry_loop(
        self,
        grid,
        entities,
        entity_number: int,
        occupancy: RoutingOccupancy,
        links: list[BeltLink],
        stage_machines,
        nodes,
        *,
        placement_recorder=None,
    ) -> tuple[list[BeltLink], int]:
        from core.flow_connectivity import validate_blueprint_flow
        self.last_conflicts = []
        current_links = links

        for _attempt in range(MAX_VALIDATION_RETRIES):
            result = validate_blueprint_flow(entities, stage_machines, nodes)
            if result.ok:
                return current_links, entity_number

            failed_ids = self._links_for_errors(current_links, result.errors)
            if not failed_ids:
                self.last_conflicts = list(result.errors)
                logger.warning("Flow validation failed: %s", result.errors)
                return current_links, entity_number

            self.last_conflicts = list(result.errors)
            logger.info(
                "Flow validation retry for links: %s",
                failed_ids,
            )
            for link_id in failed_ids:
                current_links = bump_link_priority(current_links, link_id)

            current_links = sort_links(current_links)
            entity_number = self._reroute_links(
                grid,
                entities,
                entity_number,
                occupancy,
                current_links,
                failed_ids,
            )

        return current_links, entity_number

    def _links_for_errors(
        self, links: list[BeltLink], errors: list[str]
    ) -> list[str]:
        """Map validation error strings to link ids (best-effort)."""
        failed: list[str] = []
        for link in links:
            for err in errors:
                if link.item in err and (
                    "bus" in err
                    or "flow from" in err
                    or link.kind in err
                ):
                    failed.append(link.link_id)
                    break
        return list(dict.fromkeys(failed))

    def _reroute_links(
        self,
        grid,
        entities,
        entity_number: int,
        occupancy: RoutingOccupancy,
        links: list[BeltLink],
        link_ids: list[str],
    ) -> int:
        """Strip and rematerialize groups touching failed links."""
        keys_to_rerun: set[str] = set()
        for lid in link_ids:
            rec = self.records.get(lid)
            if rec:
                keys_to_rerun.add(rec.group_key)

        groups: dict[str, list[BeltLink]] = defaultdict(list)
        for link in links:
            if link.group_key in keys_to_rerun:
                groups[link.group_key].append(link)

        for group_key, group_links in groups.items():
            self._strip_group_entities(grid, entities, group_links)
            entity_number = materialize_link_group(
                grid, entities, entity_number, occupancy, group_links
            )
        return entity_number

    def _strip_group_entities(
        self, grid, entities: list, group_links: list[BeltLink]
    ) -> None:
        indices: set[int] = set()
        for link in group_links:
            rec = self.records.get(link.link_id)
            if rec:
                indices.update(rec.entity_indices)
        for index in sorted(indices, reverse=True):
            if 0 <= index < len(entities):
                ent = entities[index]
                pos = ent.get("position") or {}
                x = int(round(pos.get("x", 0)))
                y = int(round(pos.get("y", 0)))
                name = ent.get("name", "")
                if "belt" in name or "splitter" in name:
                    grid.release(x, y)
                    if "splitter" in name:
                        from planners.stage_connector import _splitter_footprint
                        from core.constants import FACTORIO_EAST

                        w, h = _splitter_footprint(ent.get("direction", FACTORIO_EAST))
                        for dx in range(w):
                            for dy in range(h):
                                if dx or dy:
                                    grid.release(x + dx, y + dy)
                entities.pop(index)

    def _blueprint_inputs_from_links(
        self,
        links: list[BeltLink],
        input_sources: dict | None,
    ) -> dict[str, tuple[int, int]]:
        out: dict[str, tuple[int, int]] = {}
        if input_sources:
            for resource, sources in input_sources.items():
                if sources:
                    out[resource] = sources[0]
        for link in links:
            if link.kind == "base_feed":
                chest = link.metadata.get("chest")
                if chest:
                    out.setdefault(link.item, chest)
        return out

    def strip_groups(self, grid, entities: list, group_keys: set[str]) -> list:
        """Remove routing entities for given group keys (incremental reroute)."""
        link_ids = [
            lid
            for lid, rec in self.records.items()
            if rec.group_key in group_keys
        ]
        links_stub = [
            BeltLink(
                link_id=lid,
                item=rec.item,
                source=(0, 0),
                sink=(0, 0),
                kind="stage",
                group_key=rec.group_key,
                priority=0,
            )
            for lid, rec in self.records.items()
            if rec.group_key in group_keys
        ]
        self._strip_group_entities(grid, entities, links_stub)
        for lid in link_ids:
            self.records.pop(lid, None)
        return entities


def route_placed_layout_network(
    grid,
    entities,
    entity_number: int,
    stage_machines,
    nodes,
    *,
    input_sources: dict | None = None,
    output_sinks: dict | None = None,
    placement_recorder=None,
    router: BeltNetworkRouter | None = None,
    link_order_variant: int = 0,
    links: list[BeltLink] | None = None,
    group_order: list[str] | None = None,
) -> tuple[int, dict[str, tuple[int, int]], BeltNetworkRouter]:
    """
    Network router entry: same outputs as legacy routing plus router state.

    Does not place machine endpoint inserters — caller handles that.
    """
    r = router or BeltNetworkRouter()
    entity_number, blueprint_inputs, _links = r.route(
        grid,
        entities,
        entity_number,
        stage_machines,
        nodes,
        input_sources=input_sources,
        output_sinks=output_sinks,
        placement_recorder=placement_recorder,
        link_order_variant=link_order_variant,
        links=links,
        group_order=group_order,
    )
    return entity_number, blueprint_inputs, r
