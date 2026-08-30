from __future__ import annotations

import copy
import heapq
import math
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.x

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center(self) -> Point:
        return Point(self.x + self.width / 2, self.y + self.height / 2)

    def expanded(self, clearance: float) -> Rect:
        return Rect(
            self.x - clearance,
            self.y - clearance,
            self.width + clearance * 2,
            self.height + clearance * 2,
        )


@dataclass(frozen=True)
class RoutingResult:
    xml: str
    metrics: dict[str, int | float]
    status: str = "applied"
    issues: tuple[dict[str, object], ...] = ()


class DrawioRoutingError(ValueError):
    def __init__(self, issue: dict[str, object]) -> None:
        super().__init__(str(issue.get("message") or issue.get("code") or "edge routing failed"))
        self.issue = issue


def route_drawio_candidate(
    xml: str,
    *,
    clearance: float = 12,
    search_step: float = 20,
    max_offset: float = 300,
) -> RoutingResult:
    root = ET.fromstring(xml)
    _normalize_waypoint_elements(root)
    cells = {
        cell.attrib["id"]: cell
        for cell in root.iter("mxCell")
        if cell.attrib.get("id") not in {None, "0", "1"}
    }
    _repair_container_child_coordinates(cells)
    vertex_rects = _absolute_vertex_rects(cells)
    obstacles = _obstacle_rects(cells, vertex_rects, clearance)

    routed_edge_count = 0
    rerouted_edge_count = 0
    maximum_offset = 0.0
    edge_routes: dict[str, list[Point]] = {}
    original_edges: dict[str, ET.Element] = {}
    routing_outcomes: dict[str, tuple[int, int, float]] = {}
    routing_issues: list[dict[str, object]] = []
    eligible_edge_count = 0

    for edge in (cell for cell in cells.values() if cell.attrib.get("edge") == "1"):
        source_id = edge.attrib.get("source", "")
        target_id = edge.attrib.get("target", "")
        edge_id = edge.attrib.get("id", "")
        if source_id not in vertex_rects or target_id not in vertex_rects:
            continue
        eligible_edge_count += 1
        original_edge = copy.deepcopy(edge)
        original_edges[edge_id] = original_edge
        try:
            route, routed, rerouted, offset, issue = _route_single_edge(
                edge=edge,
                cells=cells,
                vertex_rects=vertex_rects,
                obstacles=obstacles,
                accepted_routes=list(edge_routes.values()),
                search_step=search_step,
                max_offset=max_offset,
                clearance=clearance,
            )
        except Exception as exc:
            _restore_element(edge, original_edge)
            routing_issues.append(
                _preserved_edge_issue(
                    {
                        "code": "edge_routing_failed",
                        "cause": "edge_router_internal_error",
                        "edge_id": edge_id,
                        "source_id": source_id,
                        "target_id": target_id,
                        "blocking_node_ids": [],
                        "repair_actions": [],
                        "retry_strategy": "preserve_original_edge",
                        "failure_fingerprint": f"{edge_id}:edge_router_internal_error",
                        "message": f"连线 {edge_id} 自动避让出现异常；已保留原始连线",
                        "error": str(exc),
                    }
                )
            )
            continue
        if issue is not None:
            _restore_element(edge, original_edge)
            routing_issues.append(_preserved_edge_issue(issue))
            continue
        if route is not None:
            edge_routes[edge_id] = route
        routed_edge_count += routed
        rerouted_edge_count += rerouted
        maximum_offset = max(maximum_offset, offset)
        routing_outcomes[edge_id] = (routed, rerouted, offset)

    serialized_xml = ET.tostring(root, encoding="unicode")
    final_root = ET.fromstring(serialized_xml)
    final_cells = {
        cell.attrib["id"]: cell
        for cell in final_root.iter("mxCell")
        if cell.attrib.get("id") not in {None, "0", "1"}
    }
    final_vertex_rects = _absolute_vertex_rects(final_cells)
    final_obstacles = _obstacle_rects(final_cells, final_vertex_rects, clearance)
    final_routes, final_terminals = _serialized_route_maps(final_cells, final_vertex_rects)
    remaining = _route_map_intersections(
        final_routes,
        final_terminals,
        final_obstacles,
        cells=final_cells,
        vertex_rects=final_vertex_rects,
    )
    remaining_by_edge: dict[str, set[str]] = defaultdict(set)
    for edge_id, blocker_id in remaining:
        remaining_by_edge[edge_id].add(blocker_id.removesuffix("#header"))
    for edge_id, blocker_ids in remaining_by_edge.items():
        if any(issue.get("edge_id") == edge_id for issue in routing_issues):
            continue
        public_blockers = sorted(blocker_ids)
        original_edge = original_edges.get(edge_id)
        current_edge = cells.get(edge_id)
        if original_edge is not None and current_edge is not None:
            _restore_element(current_edge, original_edge)
        routed, rerouted, _ = routing_outcomes.pop(edge_id, (0, 0, 0.0))
        routed_edge_count -= routed
        rerouted_edge_count -= rerouted
        edge_routes.pop(edge_id, None)
        routing_issues.append(
            _preserved_edge_issue({
                "code": "edge_vertex_intersection",
                "cause": "post_route_intersection",
                "edge_id": edge_id,
                "blocking_node_ids": public_blockers,
                "repair_actions": [
                    {
                        "action": "regenerate_edge_and_local_layout",
                        "edge_id": edge_id,
                        "avoid_cell_ids": public_blockers,
                    }
                ],
                "retry_strategy": "regenerate_local_layout_then_edges",
                "failure_fingerprint": (
                    f"{edge_id}:post_route_intersection:{','.join(public_blockers)}"
                ),
                "message": (
                    f"连线 {edge_id} 仍穿过节点 {', '.join(public_blockers)}；"
                    "已保留该连线并继续生成画板"
                ),
            })
        )

    serialized_xml = ET.tostring(root, encoding="unicode")
    final_root = ET.fromstring(serialized_xml)
    final_cells = {
        cell.attrib["id"]: cell
        for cell in final_root.iter("mxCell")
        if cell.attrib.get("id") not in {None, "0", "1"}
    }
    final_vertex_rects = _absolute_vertex_rects(final_cells)
    final_obstacles = _obstacle_rects(final_cells, final_vertex_rects, clearance)
    final_routes, final_terminals = _serialized_route_maps(final_cells, final_vertex_rects)
    final_remaining = _route_map_intersections(
        final_routes,
        final_terminals,
        final_obstacles,
        cells=final_cells,
        vertex_rects=final_vertex_rects,
    )
    maximum_offset = max((outcome[2] for outcome in routing_outcomes.values()), default=0.0)
    degraded_edge_count = len({str(issue.get("edge_id") or "") for issue in routing_issues})
    safe_edge_count = eligible_edge_count - degraded_edge_count
    routing_status = (
        "not_needed"
        if eligible_edge_count == 0
        else "partial"
        if routing_issues
        else "applied"
    )
    return RoutingResult(
        xml=serialized_xml,
        metrics={
            "edge_count": eligible_edge_count,
            "safe_edge_count": safe_edge_count,
            "unchanged_safe_edge_count": max(0, safe_edge_count - routed_edge_count),
            "degraded_edge_count": degraded_edge_count,
            "remaining_intersection_count": len(final_remaining),
            "routed_edge_count": routed_edge_count,
            "rerouted_edge_count": rerouted_edge_count,
            "edge_vertex_intersection_count": len(final_remaining),
            "edge_edge_crossing_count": _count_edge_crossings(final_routes, final_terminals),
            "max_route_offset": _clean_number(maximum_offset),
        },
        status=routing_status,
        issues=tuple(routing_issues),
    )


def _preserved_edge_issue(issue: dict[str, object]) -> dict[str, object]:
    message = str(issue.get("message") or "连线自动避让未完成")
    continuation = "已保留原始连线并继续生成画板"
    if continuation not in message:
        message = f"{message.rstrip('；。')}；{continuation}"
    return {
        **issue,
        "message": message,
        "severity": "warning",
        "blocking": False,
        "retry_required": False,
        "preserved_original_edge": True,
    }


def _restore_element(target: ET.Element, source: ET.Element) -> None:
    target.clear()
    target.attrib.update(source.attrib)
    target.text = source.text
    target.tail = source.tail
    target.extend(copy.deepcopy(list(source)))


def _route_single_edge(
    *,
    edge: ET.Element,
    cells: dict[str, ET.Element],
    vertex_rects: dict[str, Rect],
    obstacles: dict[str, Rect],
    accepted_routes: list[list[Point]],
    search_step: float,
    max_offset: float,
    clearance: float,
) -> tuple[list[Point] | None, int, int, float, dict[str, object] | None]:
    style = _style_map(edge.attrib.get("style", ""))
    edge_style = style.values.get("edgeStyle", "")
    source_id = edge.attrib.get("source", "")
    target_id = edge.attrib.get("target", "")
    edge_id = edge.attrib.get("id", "")
    source = vertex_rects[source_id]
    target = vertex_rects[target_id]
    blocked = {
        cell_id: rect
        for cell_id, rect in obstacles.items()
        if not _belongs_to_terminal(cell_id, {source_id, target_id})
        and not _belongs_inside_non_obstacle_terminal(
            cell_id,
            {source_id, target_id},
            cells,
            vertex_rects,
        )
    }
    existing_points = _geometry_points(edge, cells)
    supported_orthogonal = edge_style in {"", "orthogonalEdgeStyle", "segmentEdgeStyle"}
    if not supported_orthogonal:
        if existing_points:
            inspected_route, _ = _route_from_existing_points(
                source, target, existing_points, style
            )
        else:
            inspected_route = _straight_route(source, target)
            inspected_route = [
                _constrained_port(source, style, "exit", inspected_route[0]),
                _constrained_port(target, style, "entry", inspected_route[-1]),
            ]
        collisions = _route_collisions(inspected_route, blocked)
        if collisions:
            public_collisions = _public_blocker_ids(collisions)
            return None, 0, 0, 0.0, {
                "code": "unsupported_colliding_edge_style",
                "cause": "unsupported_edge_style",
                "edge_id": edge_id,
                "source_id": source_id,
                "target_id": target_id,
                "blocking_node_ids": public_collisions,
                "repair_actions": [{
                    "action": "convert_edge_to_orthogonal",
                    "edge_id": edge_id,
                    "avoid_cell_ids": public_collisions,
                }],
                "retry_strategy": "regenerate_edge_only",
                "failure_fingerprint": (
                    f"{edge_id}:unsupported_edge_style:{','.join(public_collisions)}"
                ),
                "message": f"非正交连线 {edge_id} 穿过节点；已保留原始连线",
            }
        return inspected_route, 0, 0, 0.0, None
    if existing_points:
        existing_route, ports = _route_from_existing_points(
            source, target, existing_points, style
        )
        if (
            _is_orthogonal(existing_route)
            and _route_avoids_terminal_interiors(existing_route, source, target)
            and not _route_collisions(existing_route, blocked)
            and not any(_routes_cross(existing_route, accepted) for accepted in accepted_routes)
        ):
            _write_route(edge, existing_route, ports, cells)
            return existing_route, 0, 0, 0.0, None

    route, ports, was_detour, offset = _find_route(
        source,
        target,
        blocked,
        accepted_routes=accepted_routes,
        search_step=search_step,
        max_offset=max_offset,
    )
    if route is None and max_offset < 600:
        route, ports, was_detour, offset = _find_route(
            source,
            target,
            blocked,
            accepted_routes=accepted_routes,
            search_step=search_step,
            max_offset=600,
        )
    if route is None:
        visibility_route = _find_visibility_graph_route(
            source,
            target,
            blocked,
            accepted_routes=accepted_routes,
        )
        if visibility_route is not None:
            route, ports = visibility_route
            was_detour = True
            offset = _route_excursion(route, source, target)
    if route is None or ports is None:
        return None, 0, 0, 0.0, _unroutable_issue(
            edge_id=edge_id,
            source_id=source_id,
            target_id=target_id,
            source=source,
            target=target,
            obstacles=blocked,
            escape_distance=max(search_step, clearance + 1),
        )

    _write_route(edge, route, ports, cells)
    return route, 1, int(was_detour or bool(existing_points)), offset, None


@dataclass
class _Style:
    flags: list[str]
    values: dict[str, str]

    def serialize(self) -> str:
        parts = self.flags + [f"{key}={value}" for key, value in self.values.items()]
        return ";".join(parts) + (";" if parts else "")


def _style_map(style: str) -> _Style:
    flags: list[str] = []
    values: dict[str, str] = {}
    for raw_part in str(style or "").split(";"):
        part = raw_part.strip()
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
            values[key] = value
        elif part not in flags:
            flags.append(part)
    return _Style(flags, values)


def _normalize_waypoint_elements(root: ET.Element) -> None:
    """Accept a common LLM waypoint spelling and emit canonical diagrams.net XML."""
    for array in root.iter("Array"):
        if array.attrib.get("as") != "points":
            continue
        for point in list(array):
            if point.tag == "Object" and ("x" in point.attrib or "y" in point.attrib):
                point.tag = "mxPoint"


def _repair_container_child_coordinates(cells: dict[str, ET.Element]) -> None:
    """Repair page coordinates accidentally used for swimlane/container children.

    The repair is deliberately cohort based: all direct children are rebased only when
    rebasing reduces overflow for the container as a whole. This avoids guessing from
    a single valid local coordinate.
    """
    absolute = _absolute_vertex_rects(cells)
    candidates: list[
        tuple[
            Rect,
            float,
            float,
            list[tuple[ET.Element, ET.Element, float, float, float, float]],
        ]
    ] = []
    evidence_axes: set[str] = set()
    for container_id, container in cells.items():
        if container.attrib.get("vertex") != "1":
            continue
        style = _style_map(container.attrib.get("style", ""))
        if "swimlane" not in style.flags and style.values.get("container") != "1":
            continue
        # Nested containers are ambiguous and would need parent-by-parent coordinate
        # recomputation. The observed LLM mistake concerns page-level swimlanes.
        if container.attrib.get("parent", "") in absolute:
            continue
        container_rect = absolute.get(container_id)
        if container_rect is None or (
            math.isclose(container_rect.x, 0) and math.isclose(container_rect.y, 0)
        ):
            continue
        children: list[tuple[ET.Element, ET.Element, float, float, float, float]] = []
        for child in cells.values():
            if child.attrib.get("parent") != container_id or child.attrib.get("vertex") != "1":
                continue
            geometry = child.find("mxGeometry")
            if geometry is None or geometry.attrib.get("relative") == "1":
                continue
            children.append(
                (
                    child,
                    geometry,
                    _number(geometry.attrib.get("x")),
                    _number(geometry.attrib.get("y")),
                    _number(geometry.attrib.get("width")),
                    _number(geometry.attrib.get("height")),
                )
            )
        if not children:
            continue

        horizontal = style.values.get("horizontal", "1") != "0"
        header = max(0.0, _number(style.values.get("startSize") or 40))

        min_x = 0.0 if horizontal else min(header, container_rect.width)
        min_y = min(header, container_rect.height) if horizontal else 0.0

        candidates.append((container_rect, min_x, min_y, children))
        for axis in ("x", "y"):
            current, rebased, overflow_count = _axis_overflow_totals(
                axis, container_rect, min_x, min_y, children
            )
            axis_size = container_rect.width if axis == "x" else container_rect.height
            # Require large, repeated overflow. Two deliberately border-crossing
            # nodes or a minor layout slip must not reinterpret the coordinate axis.
            if overflow_count >= 2 and current >= axis_size and rebased < current:
                evidence_axes.add(axis)

    # A single slightly overflowing node is not enough evidence to reinterpret every
    # sibling coordinate. Require another top-level container/cohort that clearly uses
    # page coordinates, then repair all compatible cohorts in the same generated XML.
    if not evidence_axes:
        return
    for container_rect, min_x, min_y, children in candidates:
        repair_axes: set[str] = set()
        for axis in evidence_axes:
            current, rebased, overflow_count = _axis_overflow_totals(
                axis, container_rect, min_x, min_y, children
            )
            child_limit = max(
                (width if axis == "x" else height for _, _, _, _, width, height in children),
                default=0.0,
            )
            if (
                current > 0
                and rebased < current
                and rebased <= child_limit * max(1, overflow_count)
            ):
                repair_axes.add(axis)
        for _, geometry, x, y, width, height in children:
            max_x = max(min_x, container_rect.width - width)
            max_y = max(min_y, container_rect.height - height)
            if "x" in repair_axes:
                new_x = x - container_rect.x
                geometry.set("x", _format_number(min(max(new_x, min_x), max_x)))
            if "y" in repair_axes:
                new_y = y - container_rect.y
                geometry.set("y", _format_number(min(max(new_y, min_y), max_y)))


def _axis_overflow_totals(
    axis: str,
    container: Rect,
    min_x: float,
    min_y: float,
    children: list[tuple[ET.Element, ET.Element, float, float, float, float]],
) -> tuple[float, float, int]:
    current = 0.0
    rebased = 0.0
    overflow_count = 0
    for _, _, x, y, width, height in children:
        value = x if axis == "x" else y
        offset = container.x if axis == "x" else container.y
        minimum = min_x if axis == "x" else min_y
        maximum = max(
            minimum,
            (container.width - width) if axis == "x" else (container.height - height),
        )
        child_overflow = max(0.0, minimum - value) + max(0.0, value - maximum)
        current += child_overflow
        rebased_value = value - offset
        rebased += max(0.0, minimum - rebased_value) + max(0.0, rebased_value - maximum)
        overflow_count += int(child_overflow > 0)
    return current, rebased, overflow_count


def _absolute_vertex_rects(cells: dict[str, ET.Element]) -> dict[str, Rect]:
    cache: dict[str, Rect] = {}
    visiting: set[str] = set()

    def resolve(cell_id: str) -> Rect | None:
        if cell_id in cache:
            return cache[cell_id]
        cell = cells.get(cell_id)
        if cell is None or cell.attrib.get("vertex") != "1" or cell_id in visiting:
            return None
        geometry = cell.find("mxGeometry")
        if geometry is None:
            return None
        visiting.add(cell_id)
        x = _number(geometry.attrib.get("x"))
        y = _number(geometry.attrib.get("y"))
        width = _number(geometry.attrib.get("width"))
        height = _number(geometry.attrib.get("height"))
        parent = resolve(cell.attrib.get("parent", ""))
        if parent is not None:
            if geometry.attrib.get("relative") == "1":
                offset = geometry.find("mxPoint[@as='offset']")
                x = (
                    parent.x
                    + x * parent.width
                    + _number(offset.attrib.get("x") if offset is not None else 0)
                )
                y = (
                    parent.y
                    + y * parent.height
                    + _number(offset.attrib.get("y") if offset is not None else 0)
                )
            else:
                x += parent.x
                y += parent.y
        rect = Rect(x, y, width, height)
        cache[cell_id] = rect
        visiting.remove(cell_id)
        return rect

    for candidate_id in cells:
        resolve(candidate_id)
    return cache


def _is_obstacle(cell: ET.Element, _cells: dict[str, ET.Element]) -> bool:
    style = _style_map(cell.attrib.get("style", ""))
    if style.values.get("pointerEvents") == "0":
        return False
    if (
        "text" in style.flags
        and style.values.get("strokeColor") == "none"
        and style.values.get("fillColor") == "none"
    ):
        return False
    cell_id = str(cell.attrib.get("id") or "").lower()
    if (
        cell.attrib.get("parent") in {None, "1"}
        and not str(cell.attrib.get("value") or "").strip()
        and (cell_id.endswith("_bg") or cell_id.endswith("_background"))
    ):
        return False
    # LLM-produced diagrams often omit ``container=1`` on a large vertex that
    # owns real child nodes. Treat that parent as a routing frame, not as a
    # solid obstacle. Decorative badges/labels normally use relative geometry;
    # keeping those parents as obstacles preserves the ordinary node semantics.
    if any(
        child.attrib.get("parent") == cell.attrib.get("id")
        and child.attrib.get("vertex") == "1"
        and (child.find("mxGeometry") is None or child.find("mxGeometry").attrib.get("relative") != "1")
        for child in _cells.values()
    ):
        return False
    if "group" in style.flags or style.values.get("container") == "1" or "swimlane" in style.flags:
        return False
    return True


def _belongs_to_terminal(obstacle_id: str, terminal_ids: set[str] | frozenset[str]) -> bool:
    return obstacle_id in terminal_ids or obstacle_id.removesuffix("#header") in terminal_ids


def _belongs_inside_non_obstacle_terminal(
    obstacle_id: str,
    terminal_ids: set[str] | frozenset[str],
    cells: dict[str, ET.Element],
    vertex_rects: dict[str, Rect],
) -> bool:
    obstacle = vertex_rects.get(obstacle_id.removesuffix("#header"))
    if obstacle is None:
        return False
    for terminal_id in terminal_ids:
        terminal_cell = cells.get(terminal_id)
        terminal = vertex_rects.get(terminal_id)
        if terminal_cell is None or terminal is None or _is_obstacle(terminal_cell, cells):
            continue
        if (
            terminal.left <= obstacle.left
            and terminal.right >= obstacle.right
            and terminal.top <= obstacle.top
            and terminal.bottom >= obstacle.bottom
        ):
            return True
    return False


def _obstacle_rects(
    cells: dict[str, ET.Element],
    vertex_rects: dict[str, Rect],
    clearance: float,
) -> dict[str, Rect]:
    return {
        cell_id: rect.expanded(clearance)
        for cell_id, rect in vertex_rects.items()
        if _is_obstacle(cells[cell_id], cells)
    }


def _find_route(
    source: Rect,
    target: Rect,
    obstacles: dict[str, Rect],
    *,
    accepted_routes: list[list[Point]],
    search_step: float,
    max_offset: float,
) -> tuple[list[Point] | None, tuple[str, str] | None, bool, float]:
    delta_x = target.center.x - source.center.x
    delta_y = target.center.y - source.center.y
    horizontal = abs(delta_x) >= abs(delta_y)
    if horizontal:
        direction = 1 if delta_x >= 0 else -1
        source_side = "right" if direction > 0 else "left"
        target_side = "left" if direction > 0 else "right"
        start = _port(source, source_side)
        end = _port(target, target_side)
        base = _normalize_route(
            [
                start,
                Point((start.x + end.x) / 2, start.y),
                Point((start.x + end.x) / 2, end.y),
                end,
            ]
        )
        if not _route_collisions(base, obstacles) and not any(
            _routes_cross(base, accepted) for accepted in accepted_routes
        ):
            return base, (source_side, target_side), False, 0.0
        channel_values = _channel_values(
            start.y,
            end.y,
            (rect.top for rect in obstacles.values()),
            (rect.bottom for rect in obstacles.values()),
            search_step,
            max_offset,
        )
        candidates = []
        escape_starts = (start.x + direction * search_step, start.x)
        escape_ends = (end.x - direction * search_step, end.x)
        for channel in channel_values:
            for escape_start in escape_starts:
                for escape_end in escape_ends:
                    route = _normalize_route(
                        [
                            start,
                            Point(escape_start, start.y),
                            Point(escape_start, channel),
                            Point(escape_end, channel),
                            Point(escape_end, end.y),
                            end,
                        ]
                    )
                    if (
                        _ports_respected(route, (source_side, target_side))
                        and _route_avoids_terminal_interiors(route, source, target)
                        and not _route_collisions(route, obstacles)
                    ):
                        offset = max(abs(channel - start.y), abs(channel - end.y))
                        crossings = sum(
                            _routes_cross(route, accepted) for accepted in accepted_routes
                        )
                        candidates.append(
                            (crossings, offset, len(route), _route_length(route), route)
                        )
    else:
        direction = 1 if delta_y >= 0 else -1
        source_side = "bottom" if direction > 0 else "top"
        target_side = "top" if direction > 0 else "bottom"
        start = _port(source, source_side)
        end = _port(target, target_side)
        base = _normalize_route(
            [
                start,
                Point(start.x, (start.y + end.y) / 2),
                Point(end.x, (start.y + end.y) / 2),
                end,
            ]
        )
        if not _route_collisions(base, obstacles) and not any(
            _routes_cross(base, accepted) for accepted in accepted_routes
        ):
            return base, (source_side, target_side), False, 0.0
        channel_values = _channel_values(
            start.x,
            end.x,
            (rect.left for rect in obstacles.values()),
            (rect.right for rect in obstacles.values()),
            search_step,
            max_offset,
        )
        candidates = []
        escape_starts = (start.y + direction * search_step, start.y)
        escape_ends = (end.y - direction * search_step, end.y)
        for channel in channel_values:
            for escape_start in escape_starts:
                for escape_end in escape_ends:
                    route = _normalize_route(
                        [
                            start,
                            Point(start.x, escape_start),
                            Point(channel, escape_start),
                            Point(channel, escape_end),
                            Point(end.x, escape_end),
                            end,
                        ]
                    )
                    if (
                        _ports_respected(route, (source_side, target_side))
                        and _route_avoids_terminal_interiors(route, source, target)
                        and not _route_collisions(route, obstacles)
                    ):
                        offset = max(abs(channel - start.x), abs(channel - end.x))
                        crossings = sum(
                            _routes_cross(route, accepted) for accepted in accepted_routes
                        )
                        candidates.append(
                            (crossings, offset, len(route), _route_length(route), route)
                        )

    if not candidates:
        alternate = _find_alternate_port_route(
            source,
            target,
            obstacles,
            horizontal=horizontal,
            accepted_routes=accepted_routes,
            search_step=search_step,
            max_offset=max_offset,
        )
        if alternate is None:
            return None, None, True, 0.0
        return alternate
    _, offset, _, _, best = min(candidates, key=lambda candidate: candidate[:4])
    return best, (source_side, target_side), True, offset


def _find_alternate_port_route(
    source: Rect,
    target: Rect,
    obstacles: dict[str, Rect],
    *,
    horizontal: bool,
    accepted_routes: list[list[Point]],
    search_step: float,
    max_offset: float,
) -> tuple[list[Point], tuple[str, str], bool, float] | None:
    candidates: list[tuple[float, int, int, float, list[Point], tuple[str, str]]] = []
    if horizontal:
        for source_side in ("right", "left"):
            for target_side in ("left", "right"):
                start = _port(source, source_side)
                end = _port(target, target_side)
                channels = _channel_values(
                    start.y,
                    end.y,
                    (rect.top for rect in obstacles.values()),
                    (rect.bottom for rect in obstacles.values()),
                    search_step,
                    max_offset,
                )
                escape_starts = (start.x - search_step, start.x, start.x + search_step)
                escape_ends = (end.x - search_step, end.x, end.x + search_step)
                for channel in channels:
                    for escape_start in escape_starts:
                        for escape_end in escape_ends:
                            route = _normalize_route(
                                [
                                    start,
                                    Point(escape_start, start.y),
                                    Point(escape_start, channel),
                                    Point(escape_end, channel),
                                    Point(escape_end, end.y),
                                    end,
                                ]
                            )
                            if (
                                not _ports_respected(route, (source_side, target_side))
                                or not _route_avoids_terminal_interiors(route, source, target)
                                or _route_collisions(route, obstacles)
                            ):
                                continue
                            offset = max(abs(channel - start.y), abs(channel - end.y))
                            crossings = sum(
                                _routes_cross(route, accepted) for accepted in accepted_routes
                            )
                            candidates.append(
                                (
                                    crossings,
                                    offset,
                                    len(route),
                                    _route_length(route),
                                    route,
                                    (source_side, target_side),
                                )
                            )
    else:
        for source_side in ("bottom", "top"):
            for target_side in ("top", "bottom"):
                start = _port(source, source_side)
                end = _port(target, target_side)
                channels = _channel_values(
                    start.x,
                    end.x,
                    (rect.left for rect in obstacles.values()),
                    (rect.right for rect in obstacles.values()),
                    search_step,
                    max_offset,
                )
                escape_starts = (start.y - search_step, start.y, start.y + search_step)
                escape_ends = (end.y - search_step, end.y, end.y + search_step)
                for channel in channels:
                    for escape_start in escape_starts:
                        for escape_end in escape_ends:
                            route = _normalize_route(
                                [
                                    start,
                                    Point(start.x, escape_start),
                                    Point(channel, escape_start),
                                    Point(channel, escape_end),
                                    Point(end.x, escape_end),
                                    end,
                                ]
                            )
                            if (
                                not _ports_respected(route, (source_side, target_side))
                                or not _route_avoids_terminal_interiors(route, source, target)
                                or _route_collisions(route, obstacles)
                            ):
                                continue
                            offset = max(abs(channel - start.x), abs(channel - end.x))
                            crossings = sum(
                                _routes_cross(route, accepted) for accepted in accepted_routes
                            )
                            candidates.append(
                                (
                                    crossings,
                                    offset,
                                    len(route),
                                    _route_length(route),
                                    route,
                                    (source_side, target_side),
                                )
                            )
    if not candidates:
        return None
    _, offset, _, _, route, ports = min(candidates, key=lambda candidate: candidate[:4])
    return route, ports, True, offset


def _find_visibility_graph_route(
    source: Rect,
    target: Rect,
    obstacles: dict[str, Rect],
    *,
    accepted_routes: list[list[Point]],
) -> tuple[list[Point], tuple[str, str]] | None:
    """Find multi-channel orthogonal routes that fixed templates cannot express."""
    candidates: list[tuple[float, int, float, list[Point], tuple[str, str]]] = []
    source_ports = {side: _port(source, side) for side in ("right", "bottom", "left", "top")}
    target_ports = {side: _port(target, side) for side in ("left", "top", "right", "bottom")}
    graph = _build_visibility_graph([*source_ports.values(), *target_ports.values()], obstacles)
    if graph is None:
        return None
    for source_side, start in source_ports.items():
        for target_side, end in target_ports.items():
            route = _visibility_path(start, end, graph, accepted_routes)
            if route is None:
                continue
            if not _ports_respected(route, (source_side, target_side)):
                continue
            if not _route_avoids_terminal_interiors(route, source, target):
                continue
            crossings = sum(_routes_cross(route, accepted) for accepted in accepted_routes)
            bends = max(0, len(route) - 2)
            candidates.append(
                (
                    crossings,
                    bends,
                    _route_length(route),
                    route,
                    (source_side, target_side),
                )
            )
    if not candidates:
        return None
    _, _, _, route, ports = min(candidates, key=lambda candidate: candidate[:3])
    return route, ports


def _visibility_path(
    start: Point,
    end: Point,
    neighbors: dict[Point, list[tuple[Point, str]]],
    accepted_routes: list[list[Point]],
) -> list[Point] | None:
    if start not in neighbors or end not in neighbors:
        return None

    # Direction is part of the state so bends can be penalized without losing
    # a potentially better arrival orientation at the same graph point.
    queue: list[tuple[float, int, Point, str | None]] = []
    sequence = 0
    heapq.heappush(queue, (0.0, sequence, start, None))
    distances: dict[tuple[Point, str | None], float] = {(start, None): 0.0}
    previous: dict[tuple[Point, str | None], tuple[Point, str | None]] = {}
    final_state: tuple[Point, str | None] | None = None
    while queue:
        cost, _, point, incoming = heapq.heappop(queue)
        state = (point, incoming)
        if cost > distances.get(state, math.inf):
            continue
        if point == end:
            final_state = state
            break
        for neighbor, direction in neighbors.get(point, []):
            segment_length = abs(point.x - neighbor.x) + abs(point.y - neighbor.y)
            bend_cost = 24.0 if incoming is not None and incoming != direction else 0.0
            crossing_cost = 0.0
            segment = [point, neighbor]
            for accepted in accepted_routes:
                if _routes_cross(segment, accepted):
                    crossing_cost += 250.0
            next_cost = cost + segment_length + bend_cost + crossing_cost
            next_state = (neighbor, direction)
            if next_cost >= distances.get(next_state, math.inf):
                continue
            distances[next_state] = next_cost
            previous[next_state] = state
            sequence += 1
            heapq.heappush(queue, (next_cost, sequence, neighbor, direction))
    if final_state is None:
        return None
    path: list[Point] = []
    state = final_state
    while True:
        path.append(state[0])
        if state == (start, None):
            break
        state = previous[state]
    path.reverse()
    return _normalize_route(path)


def _build_visibility_graph(
    terminals: list[Point],
    obstacles: dict[str, Rect],
) -> dict[Point, list[tuple[Point, str]]] | None:
    valid_terminals = [
        terminal for terminal in terminals if not _point_blockers(terminal, obstacles)
    ]
    if not valid_terminals:
        return None
    x_values = {point.x for point in valid_terminals}
    y_values = {point.y for point in valid_terminals}
    for rect in obstacles.values():
        x_values.update((rect.left - 1, rect.right + 1))
        y_values.update((rect.top - 1, rect.bottom + 1))
    if len(x_values) * len(y_values) > 10_000:
        return None
    points = {
        Point(x, y)
        for x in x_values
        for y in y_values
        if not _point_blockers(Point(x, y), obstacles)
    }
    points.update(valid_terminals)

    rows: dict[float, list[Point]] = defaultdict(list)
    columns: dict[float, list[Point]] = defaultdict(list)
    for point in points:
        rows[point.y].append(point)
        columns[point.x].append(point)
    neighbors: dict[Point, list[tuple[Point, str]]] = defaultdict(list)

    def connect(line: list[Point], *, horizontal: bool) -> None:
        line.sort(key=(lambda point: point.x) if horizontal else (lambda point: point.y))
        for first, second in zip(line, line[1:], strict=False):
            if _route_collisions([first, second], obstacles):
                continue
            direction = "h" if horizontal else "v"
            neighbors[first].append((second, direction))
            neighbors[second].append((first, direction))

    for row in rows.values():
        connect(row, horizontal=True)
    for column in columns.values():
        connect(column, horizontal=False)
    return neighbors


def _route_excursion(route: list[Point], source: Rect, target: Rect) -> float:
    bounds = Rect(
        min(source.left, target.left),
        min(source.top, target.top),
        max(source.right, target.right) - min(source.left, target.left),
        max(source.bottom, target.bottom) - min(source.top, target.top),
    )
    return max(
        (
            max(
                0.0,
                bounds.left - point.x,
                point.x - bounds.right,
                bounds.top - point.y,
                point.y - bounds.bottom,
            )
            for point in route
        ),
        default=0.0,
    )


def _point_blockers(point: Point, obstacles: dict[str, Rect]) -> list[str]:
    return [
        obstacle_id
        for obstacle_id, rect in obstacles.items()
        if rect.left <= point.x <= rect.right and rect.top <= point.y <= rect.bottom
    ]


def _terminal_escape_blockers(
    terminal: Rect,
    obstacles: dict[str, Rect],
    distance: float,
) -> list[str] | None:
    directions = {
        "left": Point(-distance, 0),
        "right": Point(distance, 0),
        "top": Point(0, -distance),
        "bottom": Point(0, distance),
    }
    all_blockers: set[str] = set()
    for side, delta in directions.items():
        port = _port(terminal, side)
        escape = Point(port.x + delta.x, port.y + delta.y)
        blockers = set(_route_collisions([port, escape], obstacles))
        if not blockers:
            return None
        all_blockers.update(blockers)
    return sorted(all_blockers)


def _unroutable_issue(
    *,
    edge_id: str,
    source_id: str,
    target_id: str,
    source: Rect,
    target: Rect,
    obstacles: dict[str, Rect],
    escape_distance: float,
) -> dict[str, object]:
    source_blockers = _terminal_escape_blockers(source, obstacles, escape_distance)
    target_blockers = _terminal_escape_blockers(target, obstacles, escape_distance)
    if source_blockers is not None:
        cause = "source_terminal_trapped"
        terminal_id = source_id
        blockers = source_blockers
    elif target_blockers is not None:
        cause = "target_terminal_trapped"
        terminal_id = target_id
        blockers = target_blockers
    else:
        cause = "no_safe_orthogonal_corridor"
        terminal_id = ""
        direct = _straight_route(source, target)
        blockers = _route_collisions(direct, obstacles)
        if not blockers:
            blockers = sorted(
                obstacles, key=lambda item: _rect_distance(obstacles[item], source.center)
            )[:8]
    blockers = _public_blocker_ids(blockers)

    issue: dict[str, object] = {
        "code": "unroutable_edge",
        "cause": cause,
        "edge_id": edge_id,
        "source_id": source_id,
        "target_id": target_id,
        "blocking_node_ids": blockers,
        "attempted_directions": ["above", "below", "left", "right", "multi_channel"],
        "failure_fingerprint": f"{edge_id}:{cause}:{','.join(blockers)}",
    }
    if terminal_id:
        issue.update(
            {
                "repair_actions": [
                    {
                        "action": "relayout_terminal",
                        "cell_id": terminal_id,
                        "avoid_cell_ids": blockers,
                    }
                ],
                "retry_strategy": "move_terminal_then_regenerate_edges",
                "message": (
                    f"连线 {edge_id} 的端点 {terminal_id} 被节点包围；请先移动该端点，"
                    "再重新生成相关连线，不要仅重复提交原 XML 或只添加折点"
                ),
            }
        )
    else:
        issue.update(
            {
                "repair_actions": [
                    {
                        "action": "regenerate_local_layout",
                        "cell_ids": [source_id, target_id],
                        "avoid_cell_ids": blockers,
                    }
                ],
                "retry_strategy": "regenerate_local_layout_then_edges",
                "message": (
                    f"连线 {edge_id} 不存在安全正交通道；请扩大端点附近间距或调整局部节点布局，"
                    "再重新生成相关连线"
                ),
            }
        )
    return issue


def _rect_distance(rect: Rect, point: Point) -> float:
    delta_x = max(rect.left - point.x, 0.0, point.x - rect.right)
    delta_y = max(rect.top - point.y, 0.0, point.y - rect.bottom)
    return delta_x + delta_y


def _public_blocker_ids(blockers: Iterable[str]) -> list[str]:
    return sorted({blocker.removesuffix("#header") for blocker in blockers})


def _channel_values(
    start: float,
    end: float,
    lower_boundaries: Iterable[float],
    upper_boundaries: Iterable[float],
    step: float,
    maximum: float,
) -> list[float]:
    values = {start, end}
    interval_start, interval_end = sorted((start, end))
    boundary_values = [
        *(value - 1 for value in lower_boundaries),
        *(value + 1 for value in upper_boundaries),
    ]
    values.update(
        value
        for value in boundary_values
        if interval_start - maximum <= value <= interval_end + maximum
    )
    count = max(1, int(maximum // step))
    for index in range(1, count + 1):
        delta = step * index
        values.update({start - delta, start + delta, end - delta, end + delta})
    return sorted(values, key=lambda value: (abs(value - start) + abs(value - end), value))


def _route_from_existing_points(
    source: Rect,
    target: Rect,
    points: list[Point],
    style: _Style | None = None,
) -> tuple[list[Point], tuple[str, str]]:
    source_side = _side_toward(source, points[0])
    target_side = _side_toward(target, points[-1])
    source_port = _port(source, source_side)
    target_port = _port(target, target_side)
    if style is not None:
        source_port = _constrained_port(source, style, "exit", source_port)
        target_port = _constrained_port(target, style, "entry", target_port)
    return _normalize_route([source_port, *points, target_port]), (source_side, target_side)


def _constrained_port(rect: Rect, style: _Style, prefix: str, fallback: Point) -> Point:
    raw_x = style.values.get(f"{prefix}X")
    raw_y = style.values.get(f"{prefix}Y")
    if raw_x is None or raw_y is None:
        return fallback
    return Point(
        rect.x + _number(raw_x) * rect.width + _number(style.values.get(f"{prefix}Dx")),
        rect.y + _number(raw_y) * rect.height + _number(style.values.get(f"{prefix}Dy")),
    )


def _side_toward(rect: Rect, point: Point) -> str:
    distances = {
        "left": abs(point.x - rect.left),
        "right": abs(point.x - rect.right),
        "top": abs(point.y - rect.top),
        "bottom": abs(point.y - rect.bottom),
    }
    return min(distances, key=distances.get)


def _port(rect: Rect, side: str) -> Point:
    if side == "left":
        return Point(rect.left, rect.center.y)
    if side == "right":
        return Point(rect.right, rect.center.y)
    if side == "top":
        return Point(rect.center.x, rect.top)
    return Point(rect.center.x, rect.bottom)


def _ports_respected(route: list[Point], ports: tuple[str, str]) -> bool:
    if len(route) < 2:
        return False

    def points_outward(port: Point, neighbor: Point, side: str) -> bool:
        if side == "left":
            return math.isclose(port.y, neighbor.y) and neighbor.x < port.x
        if side == "right":
            return math.isclose(port.y, neighbor.y) and neighbor.x > port.x
        if side == "top":
            return math.isclose(port.x, neighbor.x) and neighbor.y < port.y
        return math.isclose(port.x, neighbor.x) and neighbor.y > port.y

    return points_outward(route[0], route[1], ports[0]) and points_outward(
        route[-1], route[-2], ports[1]
    )


def _route_avoids_terminal_interiors(route: list[Point], source: Rect, target: Rect) -> bool:
    return not any(
        _segment_enters_rect_interior(start, end, terminal)
        for start, end in zip(route, route[1:], strict=False)
        for terminal in (source, target)
    )


def _segment_enters_rect_interior(start: Point, end: Point, rect: Rect) -> bool:
    if math.isclose(start.x, end.x):
        return (
            rect.left < start.x < rect.right
            and max(start.y, end.y) > rect.top
            and min(start.y, end.y) < rect.bottom
        )
    if math.isclose(start.y, end.y):
        return (
            rect.top < start.y < rect.bottom
            and max(start.x, end.x) > rect.left
            and min(start.x, end.x) < rect.right
        )
    # Generated routes are orthogonal. Treat a diagonal as unsafe if it touches
    # the slightly shrunken interior.
    epsilon = 1e-6
    if rect.width <= epsilon * 2 or rect.height <= epsilon * 2:
        return False
    return _segment_intersects_rect(
        start,
        end,
        Rect(
            rect.x + epsilon,
            rect.y + epsilon,
            rect.width - epsilon * 2,
            rect.height - epsilon * 2,
        ),
    )


def _straight_route(source: Rect, target: Rect) -> list[Point]:
    delta_x = target.center.x - source.center.x
    delta_y = target.center.y - source.center.y
    if abs(delta_x) >= abs(delta_y):
        if delta_x >= 0:
            return [_port(source, "right"), _port(target, "left")]
        return [_port(source, "left"), _port(target, "right")]
    if delta_y >= 0:
        return [_port(source, "bottom"), _port(target, "top")]
    return [_port(source, "top"), _port(target, "bottom")]


def _write_route(
    edge: ET.Element,
    route: list[Point],
    ports: tuple[str, str],
    cells: dict[str, ET.Element],
) -> None:
    style = _style_map(edge.attrib.get("style", ""))
    style.values["edgeStyle"] = "segmentEdgeStyle"
    style.values.pop("curved", None)
    source_x, source_y = _side_constraint(ports[0])
    target_x, target_y = _side_constraint(ports[1])
    style.values.update(
        {
            "exitX": source_x,
            "exitY": source_y,
            "exitDx": "0",
            "exitDy": "0",
            "exitPerimeter": "1",
            "entryX": target_x,
            "entryY": target_y,
            "entryDx": "0",
            "entryDy": "0",
            "entryPerimeter": "1",
        }
    )
    edge.set("style", style.serialize())
    geometry = edge.find("mxGeometry")
    if geometry is None:
        geometry = ET.SubElement(edge, "mxGeometry", {"relative": "1", "as": "geometry"})
    for array in list(geometry.findall("Array")):
        if array.attrib.get("as") == "points":
            geometry.remove(array)
    waypoints = route[1:-1]
    if waypoints:
        parent_origin = _parent_origin(edge, cells)
        array = ET.SubElement(geometry, "Array", {"as": "points"})
        for point in waypoints:
            ET.SubElement(
                array,
                "mxPoint",
                {
                    "x": _format_number(point.x - parent_origin.x),
                    "y": _format_number(point.y - parent_origin.y),
                },
            )


def _parent_origin(edge: ET.Element, cells: dict[str, ET.Element]) -> Point:
    parent_id = edge.attrib.get("parent", "")
    rects = _absolute_vertex_rects(cells)
    parent = rects.get(parent_id)
    return Point(parent.x, parent.y) if parent is not None else Point(0, 0)


def _side_constraint(side: str) -> tuple[str, str]:
    return {
        "left": ("0", "0.5"),
        "right": ("1", "0.5"),
        "top": ("0.5", "0"),
        "bottom": ("0.5", "1"),
    }[side]


def _geometry_points(edge: ET.Element, cells: dict[str, ET.Element]) -> list[Point]:
    geometry = edge.find("mxGeometry")
    array = geometry.find("Array[@as='points']") if geometry is not None else None
    if array is None:
        return []
    parent_origin = _parent_origin(edge, cells)
    return [
        Point(
            _number(point.attrib.get("x")) + parent_origin.x,
            _number(point.attrib.get("y")) + parent_origin.y,
        )
        for point in array.findall("mxPoint")
    ]


def _serialized_route_maps(
    cells: dict[str, ET.Element],
    vertex_rects: dict[str, Rect],
) -> tuple[dict[str, list[Point]], dict[str, frozenset[str]]]:
    routes: dict[str, list[Point]] = {}
    terminals: dict[str, frozenset[str]] = {}
    for edge in (cell for cell in cells.values() if cell.attrib.get("edge") == "1"):
        source_id = edge.attrib.get("source", "")
        target_id = edge.attrib.get("target", "")
        edge_id = edge.attrib.get("id", "")
        if source_id not in vertex_rects or target_id not in vertex_rects:
            continue
        style = _style_map(edge.attrib.get("style", ""))
        points = _geometry_points(edge, cells)
        if points:
            route, _ = _route_from_existing_points(
                vertex_rects[source_id],
                vertex_rects[target_id],
                points,
                style,
            )
        else:
            route = _straight_route(vertex_rects[source_id], vertex_rects[target_id])
            route = [
                _constrained_port(vertex_rects[source_id], style, "exit", route[0]),
                _constrained_port(vertex_rects[target_id], style, "entry", route[-1]),
            ]
        routes[edge_id] = route
        terminals[edge_id] = frozenset({source_id, target_id})
    return routes, terminals


def _route_map_intersections(
    routes: dict[str, list[Point]],
    terminals: dict[str, frozenset[str]],
    obstacles: dict[str, Rect],
    *,
    cells: dict[str, ET.Element] | None = None,
    vertex_rects: dict[str, Rect] | None = None,
) -> list[tuple[str, str]]:
    collisions: list[tuple[str, str]] = []
    for edge_id, route in routes.items():
        endpoint_ids = terminals.get(edge_id, frozenset())
        blocked = {
            obstacle_id: rect
            for obstacle_id, rect in obstacles.items()
            if not _belongs_to_terminal(obstacle_id, endpoint_ids)
            and not (
                cells is not None
                and vertex_rects is not None
                and _belongs_inside_non_obstacle_terminal(
                    obstacle_id,
                    endpoint_ids,
                    cells,
                    vertex_rects,
                )
            )
        }
        collisions.extend((edge_id, blocker_id) for blocker_id in _route_collisions(route, blocked))
    return collisions


def _count_edge_crossings(
    routes: dict[str, list[Point]],
    terminals: dict[str, frozenset[str]],
) -> int:
    edge_ids = list(routes)
    count = 0
    for index, left_id in enumerate(edge_ids):
        for right_id in edge_ids[index + 1 :]:
            if terminals.get(left_id, frozenset()) & terminals.get(right_id, frozenset()):
                continue
            if _routes_cross(routes[left_id], routes[right_id]):
                count += 1
    return count


def _routes_cross(left: list[Point], right: list[Point]) -> bool:
    return any(
        _segments_intersect(left_start, left_end, right_start, right_end)
        for left_start, left_end in zip(left, left[1:], strict=False)
        for right_start, right_end in zip(right, right[1:], strict=False)
    )


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    def orientation(first: Point, second: Point, third: Point) -> float:
        return (second.x - first.x) * (third.y - first.y) - (second.y - first.y) * (
            third.x - first.x
        )

    def contains(first: Point, second: Point, point: Point) -> bool:
        return min(first.x, second.x) <= point.x <= max(first.x, second.x) and min(
            first.y, second.y
        ) <= point.y <= max(first.y, second.y)

    values = (
        orientation(a, b, c),
        orientation(a, b, d),
        orientation(c, d, a),
        orientation(c, d, b),
    )
    if values[0] * values[1] < 0 and values[2] * values[3] < 0:
        return True
    return any(
        math.isclose(value, 0.0) and contains(start, end, point)
        for value, start, end, point in (
            (values[0], a, b, c),
            (values[1], a, b, d),
            (values[2], c, d, a),
            (values[3], c, d, b),
        )
    )


def _route_collisions(route: list[Point], obstacles: dict[str, Rect]) -> list[str]:
    result: list[str] = []
    for obstacle_id, rect in obstacles.items():
        if any(
            _segment_intersects_rect(start, end, rect)
            for start, end in zip(route, route[1:], strict=False)
        ):
            result.append(obstacle_id)
    return result


def _segment_intersects_rect(start: Point, end: Point, rect: Rect) -> bool:
    if math.isclose(start.x, end.x):
        return (
            rect.left <= start.x <= rect.right
            and max(start.y, end.y) >= rect.top
            and min(start.y, end.y) <= rect.bottom
        )
    if math.isclose(start.y, end.y):
        return (
            rect.top <= start.y <= rect.bottom
            and max(start.x, end.x) >= rect.left
            and min(start.x, end.x) <= rect.right
        )
    delta_x = end.x - start.x
    delta_y = end.y - start.y
    minimum = 0.0
    maximum = 1.0
    for direction, distance in (
        (-delta_x, start.x - rect.left),
        (delta_x, rect.right - start.x),
        (-delta_y, start.y - rect.top),
        (delta_y, rect.bottom - start.y),
    ):
        if math.isclose(direction, 0.0):
            if distance < 0:
                return False
            continue
        ratio = distance / direction
        if direction < 0:
            minimum = max(minimum, ratio)
        else:
            maximum = min(maximum, ratio)
        if minimum > maximum:
            return False
    return True


def _is_orthogonal(route: list[Point]) -> bool:
    return all(
        math.isclose(start.x, end.x) or math.isclose(start.y, end.y)
        for start, end in zip(route, route[1:], strict=False)
    )


def _normalize_route(points: list[Point]) -> list[Point]:
    deduplicated: list[Point] = []
    for point in points:
        if not deduplicated or point != deduplicated[-1]:
            deduplicated.append(point)
    index = 1
    while index < len(deduplicated) - 1:
        previous, current, following = deduplicated[index - 1 : index + 2]
        if (
            math.isclose(previous.x, current.x, abs_tol=1e-9)
            and math.isclose(current.x, following.x, abs_tol=1e-9)
        ) or (
            math.isclose(previous.y, current.y, abs_tol=1e-9)
            and math.isclose(current.y, following.y, abs_tol=1e-9)
        ):
            deduplicated.pop(index)
        else:
            index += 1
    return deduplicated


def _route_length(route: list[Point]) -> float:
    return sum(
        abs(start.x - end.x) + abs(start.y - end.y)
        for start, end in zip(route, route[1:], strict=False)
    )


def _number(value: object) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.4f}".rstrip("0").rstrip(".")


def _clean_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else round(value, 4)


__all__ = ["DrawioRoutingError", "RoutingResult", "route_drawio_candidate"]
