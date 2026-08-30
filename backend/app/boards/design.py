from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

BOARD_DIAGRAM_TYPES = {
    "general",
    "architecture",
    "process_flow",
    "data_flow",
    "decision_tree",
    "flowchart",
    "layered_system",
    "timeline",
    "gantt",
    "comparison_matrix",
    "sequence",
    "swimlane",
    "org_tree",
    "state_machine",
    "er_model",
    "nested",
}

BOARD_AUDIENCES = {"engineer", "mixed", "executive"}
BOARD_DETAIL_LEVELS = {"simplified", "balanced", "faithful"}
BOARD_CANVAS_PRESETS = {"auto", "board-wide", "board-tall", "slide-16x9", "document"}

DETAIL_BUDGETS = {
    "simplified": {"nodes": 7, "edges": 10},
    "balanced": {"nodes": 12, "edges": 16},
    "faithful": {"nodes": 20, "edges": 28},
}

DEFAULT_BOARD_THEME_TOKENS = {
    "canvas": "#F7F8FA",
    "surface": "#FFFFFF",
    "surface_muted": "#F2F4F7",
    "text_primary": "#1F2937",
    "text_secondary": "#667085",
    "border": "#98A2B3",
    "accent": "#1677FF",
    "accent_tint": "#EAF2FF",
    "danger": "#D92D20",
    "success": "#079455",
    "link": "#175CD3",
}

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_HTML_TAG = re.compile(r"<[^>]+>")
_BREAK_TAG = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)


def clean_drawio_label(value: Any) -> str:
    text = str(value or "")
    text = _BREAK_TAG.sub("\n", text)
    text = _HTML_TAG.sub("", text)
    text = html.unescape(text).replace("\xa0", " ")
    return " ".join(text.split())


def parse_drawio_style(style: Any) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in str(style or "").split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
            parsed[key] = value
        else:
            parsed[part] = "1"
    return parsed


def normalize_board_theme_tokens(value: Any = None) -> dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    normalized = dict(DEFAULT_BOARD_THEME_TOKENS)
    for key in normalized:
        candidate = str(raw.get(key) or "").strip()
        if _HEX_COLOR.fullmatch(candidate):
            normalized[key] = candidate.upper()
    return normalized


def normalize_board_design_spec(
    value: Any = None,
    *,
    structural_digest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    candidates = (structural_digest or {}).get("type_candidates") or []
    requested_type = str(raw.get("diagram_type") or raw.get("type") or "").strip().lower()
    diagram_type = requested_type if requested_type in BOARD_DIAGRAM_TYPES else ""
    if not diagram_type:
        diagram_type = next(
            (str(item) for item in candidates if str(item) in BOARD_DIAGRAM_TYPES),
            "general",
        )

    audience = str(raw.get("audience") or "mixed").strip().lower()
    if audience not in BOARD_AUDIENCES:
        audience = "mixed"
    detail_level = str(raw.get("detail_level") or raw.get("detail") or "balanced").strip().lower()
    if detail_level not in BOARD_DETAIL_LEVELS:
        detail_level = "balanced"
    canvas_preset = str(raw.get("canvas_preset") or raw.get("size") or "auto").strip().lower()
    if canvas_preset not in BOARD_CANVAS_PRESETS:
        canvas_preset = "auto"

    focal_ids = raw.get("focus_cell_ids") or raw.get("focal_cell_ids") or []
    if not isinstance(focal_ids, list):
        focal_ids = []
    split_plan = raw.get("split_plan") or []
    if not isinstance(split_plan, list):
        split_plan = []

    return {
        "diagram_type": diagram_type,
        "story": str(raw.get("story") or "").strip()[:500],
        "audience": audience,
        "detail_level": detail_level,
        "canvas_preset": canvas_preset,
        "theme_profile": str(raw.get("theme_profile") or "project-default").strip()[:80],
        "focus_cell_ids": [str(item).strip() for item in focal_ids if str(item).strip()][:8],
        "split_plan": split_plan[:12],
    }


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _geometry(cell: ET.Element) -> dict[str, float]:
    geometry = cell.find("mxGeometry")
    if geometry is None:
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    return {key: _number(geometry.attrib.get(key)) for key in ("x", "y", "width", "height")}


def _shape_name(style: dict[str, str]) -> str:
    raw = ";".join(f"{key}={value}" for key, value in style.items()).lower()
    shape = str(style.get("shape") or "").lower()
    if "swimlane" in style or "swimlane" in raw:
        return "swimlane"
    if "rhombus" in style or "rhombus" in raw:
        return "decision"
    if "cylinder" in shape or "datastore" in raw:
        return "store"
    if "lifeline" in raw:
        return "lifeline"
    if "table" in raw or "entityrelation" in raw or "er." in raw:
        return "table"
    if "ellipse" in style or "ellipse" in raw:
        return "state"
    if "cloud" in raw:
        return "external"
    if "actor" in raw:
        return "actor"
    if style.get("container") == "1" or "group" in style:
        return "container"
    if "text" in style and style.get("strokeColor") == "none" and style.get("fillColor") == "none":
        return "text"
    return "box"


def _has_cycle(node_ids: Iterable[str], edges: list[dict[str, Any]]) -> bool:
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source in adjacency and target in adjacency:
            adjacency[source].append(target)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for target in adjacency.get(node_id, []):
            if visit(target):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(visit(node_id) for node_id in adjacency if node_id not in visited)


def _node_depth(node_id: str, parents: dict[str, str], node_ids: set[str]) -> int:
    depth = 0
    seen = {node_id}
    parent = parents.get(node_id, "")
    while parent in node_ids and parent not in seen:
        depth += 1
        seen.add(parent)
        parent = parents.get(parent, "")
    return depth


def _type_candidates(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    has_cycle: bool,
    max_depth: int,
) -> list[str]:
    shapes = Counter(str(node.get("shape") or "box") for node in nodes)
    sources = {
        str(edge.get("source")) for edge in edges if edge.get("source") and edge.get("target")
    } - {str(edge.get("target")) for edge in edges if edge.get("source") and edge.get("target")}
    candidates: list[str] = []

    def add(name: str) -> None:
        if name not in candidates:
            candidates.append(name)

    if shapes["lifeline"]:
        add("sequence")
    if shapes["table"]:
        add("er_model")
    if shapes["swimlane"] >= 2:
        add("swimlane")
    if shapes["decision"]:
        add("decision_tree" if has_cycle or shapes["decision"] > 2 else "flowchart")
    if shapes["state"] >= 2 and has_cycle:
        add("state_machine")
    if max_depth >= 2 and shapes["container"] + shapes["swimlane"]:
        add("nested")
    if len(sources) == 1 and edges and not has_cycle:
        add("org_tree")
    if edges:
        add("architecture")
    if not candidates:
        add("general")
    return candidates


def build_board_structural_digest(
    xml: str,
    *,
    selected_cells: Any = None,
    max_nodes: int = 80,
    max_edges: int = 120,
) -> dict[str, Any]:
    try:
        root = ET.fromstring(str(xml or ""))
    except ET.ParseError as exc:
        return {
            "status": "invalid",
            "error": str(exc),
            "metrics": {"node_count": 0, "edge_count": 0, "container_count": 0, "max_depth": 0},
            "type_candidates": ["general"],
            "nodes": [],
            "edges": [],
            "selected_subgraph": {"node_ids": [], "edge_ids": []},
            "hubs": [],
            "collapsible_groups": [],
            "truncated": False,
        }

    cells = [cell for cell in root.iter("mxCell") if cell.attrib.get("id") not in {None, "0", "1"}]
    vertices = [cell for cell in cells if cell.attrib.get("vertex") == "1"]
    edge_cells = [cell for cell in cells if cell.attrib.get("edge") == "1"]
    node_ids = {str(cell.attrib["id"]) for cell in vertices}
    parents = {str(cell.attrib["id"]): str(cell.attrib.get("parent") or "") for cell in vertices}
    children: dict[str, list[str]] = defaultdict(list)
    for node_id, parent_id in parents.items():
        if parent_id in node_ids:
            children[parent_id].append(node_id)

    nodes: list[dict[str, Any]] = []
    for cell in vertices:
        cell_id = str(cell.attrib["id"])
        style = parse_drawio_style(cell.attrib.get("style"))
        geometry = _geometry(cell)
        nodes.append(
            {
                "id": cell_id,
                "label": clean_drawio_label(cell.attrib.get("value"))[:240],
                "parent": parents.get(cell_id) or None,
                "depth": _node_depth(cell_id, parents, node_ids),
                "shape": _shape_name(style),
                "geometry": geometry,
                "child_count": len(children.get(cell_id, [])),
            }
        )

    edges: list[dict[str, Any]] = []
    degree: Counter[str] = Counter()
    for cell in edge_cells:
        source = str(cell.attrib.get("source") or "")
        target = str(cell.attrib.get("target") or "")
        if source:
            degree[source] += 1
        if target:
            degree[target] += 1
        edges.append(
            {
                "id": str(cell.attrib["id"]),
                "source": source or None,
                "target": target or None,
                "label": clean_drawio_label(cell.attrib.get("value"))[:160],
            }
        )

    has_cycle = _has_cycle(node_ids, edges)
    max_depth = max((int(node["depth"]) for node in nodes), default=0)
    type_candidates = _type_candidates(nodes, edges, has_cycle=has_cycle, max_depth=max_depth)
    labels = {str(node["id"]): str(node.get("label") or "") for node in nodes}
    hubs = [
        {"id": node_id, "label": labels.get(node_id, ""), "degree": count}
        for node_id, count in degree.most_common(5)
        if node_id in node_ids
    ]
    collapsible_groups = []
    for parent_id, child_ids in children.items():
        if len(child_ids) < 2 or any(children.get(child_id) for child_id in child_ids):
            continue
        collapsible_groups.append(
            {
                "id": parent_id,
                "label": labels.get(parent_id, ""),
                "children": len(child_ids),
                "child_ids": child_ids[:12],
            }
        )
    collapsible_groups.sort(key=lambda item: int(item["children"]), reverse=True)

    selected_ids = {
        str(item.get("id"))
        for item in (selected_cells if isinstance(selected_cells, list) else [])
        if isinstance(item, dict) and item.get("id")
    }
    neighborhood = set(selected_ids)
    selected_edge_ids: list[str] = []
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source in selected_ids or target in selected_ids:
            neighborhood.update(item for item in (source, target) if item)
            selected_edge_ids.append(str(edge["id"]))

    container_count = sum(
        1
        for node in nodes
        if node.get("shape") in {"container", "swimlane"} or node.get("child_count")
    )
    return {
        "status": "ok",
        "metrics": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "container_count": container_count,
            "max_depth": max_depth,
            "has_cycle": has_cycle,
            "unlabeled_edge_count": sum(1 for edge in edges if not edge.get("label")),
        },
        "type_candidates": type_candidates,
        "nodes": nodes[:max_nodes],
        "edges": edges[:max_edges],
        "selected_subgraph": {
            "node_ids": sorted(neighborhood),
            "edge_ids": selected_edge_ids,
        },
        "hubs": hubs,
        "collapsible_groups": collapsible_groups[:8],
        "truncated": len(nodes) > max_nodes or len(edges) > max_edges,
    }


def compact_board_structural_digest(digest: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": digest.get("status"),
        "metrics": digest.get("metrics") or {},
        "type_candidates": digest.get("type_candidates") or [],
        "selected_subgraph": digest.get("selected_subgraph") or {},
        "hubs": digest.get("hubs") or [],
        "collapsible_groups": digest.get("collapsible_groups") or [],
        "truncated": bool(digest.get("truncated")),
    }


__all__ = [
    "BOARD_AUDIENCES",
    "BOARD_CANVAS_PRESETS",
    "BOARD_DETAIL_LEVELS",
    "BOARD_DIAGRAM_TYPES",
    "DEFAULT_BOARD_THEME_TOKENS",
    "DETAIL_BUDGETS",
    "build_board_structural_digest",
    "clean_drawio_label",
    "compact_board_structural_digest",
    "normalize_board_design_spec",
    "normalize_board_theme_tokens",
    "parse_drawio_style",
]
