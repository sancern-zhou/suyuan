from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .freeform_models import (
    FreeformConnector,
    FreeformDiagram,
    FreeformGroup,
    FreeformShape,
)


_SAFE_ID_PATTERN = re.compile(r"[^A-Za-z0-9_.:-]+")
_SAFE_STYLE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_.:-]+")
_SAFE_STYLE_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_SAFE_STYLE_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9#.,_ ./:%()+-]{0,256}$")
_BLOCKED_STYLE_KEYS = {"image", "link", "src", "url"}
_DANGEROUS_TEXT_TOKENS = (
    "<script",
    "</script",
    "javascript:",
    "data:text/html",
    "onclick",
    "onerror",
    "onload",
)

_BASE_VERTEX_STYLE = "whiteSpace=wrap;html=1;"
_BASE_EDGE_STYLE = (
    "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;"
    "jettySize=auto;html=1;endArrow=block;endFill=1;"
)

_SHAPE_STYLES = {
    "rect": "rounded=0;",
    "rounded_rect": "rounded=1;arcSize=10;",
    "text": "text;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;",
    "container": "rounded=1;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#666666;",
    "swimlane": "swimlane;html=1;startSize=24;",
    "database": "shape=cylinder;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=15;",
    "cloud": "ellipse;shape=cloud;whiteSpace=wrap;html=1;",
    "queue": "shape=partialRectangle;whiteSpace=wrap;html=1;left=0;right=0;",
    "document": "shape=document;whiteSpace=wrap;html=1;boundedLbl=1;",
    "circle": "ellipse;aspect=fixed;",
    "ellipse": "ellipse;",
    "hexagon": "shape=hexagon;perimeter=hexagonPerimeter2;whiteSpace=wrap;html=1;",
    "diamond": "rhombus;whiteSpace=wrap;html=1;",
    "triangle": "triangle;whiteSpace=wrap;html=1;",
    "parallelogram": "shape=parallelogram;perimeter=parallelogramPerimeter;whiteSpace=wrap;html=1;",
    "cylinder": "shape=cylinder;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=15;",
    "actor": "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;",
    "note": "shape=note;whiteSpace=wrap;html=1;backgroundOutline=1;darkOpacity=0.05;",
    "callout": "shape=callout;whiteSpace=wrap;html=1;perimeter=calloutPerimeter;",
    "brace": "shape=curlyBracket;whiteSpace=wrap;html=1;rounded=1;",
    "bracket": "shape=curlyBracket;whiteSpace=wrap;html=1;rounded=0;",
    "line": "shape=line;strokeWidth=2;html=1;",
    "arrow": "shape=singleArrow;whiteSpace=wrap;html=1;arrowWidth=0.4;arrowSize=0.4;",
    "image": "shape=image;verticalLabelPosition=bottom;verticalAlign=top;html=1;",
}

_CONNECTOR_STYLES = {
    "orthogonal": _BASE_EDGE_STYLE,
    "straight": "edgeStyle=none;html=1;endArrow=block;endFill=1;",
    "curved": "edgeStyle=orthogonalEdgeStyle;curved=1;html=1;endArrow=block;endFill=1;",
    "dashed": f"{_BASE_EDGE_STYLE}dashed=1;",
}


def build_drawio_xml(diagram: FreeformDiagram) -> str:
    """Build Draw.io XML for a normalized freeform diagram."""
    id_map = _build_id_map(diagram)
    parent_by_child = _parent_by_child(diagram.groups, id_map)

    mxfile = ET.Element(
        "mxfile",
        {
            "host": "app.diagrams.net",
            "type": "device",
        },
    )
    diagram_el = ET.SubElement(
        mxfile,
        "diagram",
        {
            "id": _safe_identifier(diagram.artifact_id, "diagram"),
            "name": _safe_text(diagram.title),
        },
    )
    model = ET.SubElement(
        diagram_el,
        "mxGraphModel",
        {
            "dx": str(int(diagram.canvas.width)),
            "dy": str(int(diagram.canvas.height)),
            "grid": "1" if diagram.canvas.grid is not None else "0",
            "gridSize": _format_number(diagram.canvas.grid or 10),
            "guides": "1",
            "tooltips": "1",
            "connect": "1",
            "arrows": "1",
            "fold": "1",
            "page": "1",
            "pageScale": "1",
            "pageWidth": _format_number(diagram.canvas.width),
            "pageHeight": _format_number(diagram.canvas.height),
            "math": "0",
            "shadow": "0",
        },
    )
    if diagram.canvas.background:
        background = _safe_style_value(str(diagram.canvas.background))
        if background:
            model.set("background", background)

    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

    for group in diagram.groups:
        _append_group(root, group, id_map)

    for shape in diagram.shapes:
        _append_shape(root, shape, id_map, parent_by_child)

    for connector in diagram.connectors:
        _append_connector(root, connector, id_map)

    return ET.tostring(mxfile, encoding="unicode", short_empty_elements=True)


def _append_group(
    root: ET.Element,
    group: FreeformGroup,
    id_map: dict[str, str],
) -> None:
    group_id = id_map[group.id]
    cell = ET.SubElement(
        root,
        "mxCell",
        {
            "id": group_id,
            "value": _safe_text(group.label),
            "style": f"group;{_BASE_VERTEX_STYLE}container=1;collapsible=0;",
            "vertex": "1",
            "connectable": "0",
            "parent": "1",
        },
    )
    ET.SubElement(
        cell,
        "mxGeometry",
        {
            "x": _format_number(group.x or 0),
            "y": _format_number(group.y or 0),
            "width": _format_number(group.width or 240),
            "height": _format_number(group.height or 160),
            "as": "geometry",
        },
    )


def _append_shape(
    root: ET.Element,
    shape: FreeformShape,
    id_map: dict[str, str],
    parent_by_child: dict[str, str],
) -> None:
    shape_id = id_map[shape.id]
    cell = ET.SubElement(
        root,
        "mxCell",
        {
            "id": shape_id,
            "value": _safe_text(shape.label),
            "style": _shape_style(shape),
            "vertex": "1",
            "parent": parent_by_child.get(shape.id, "1"),
        },
    )
    ET.SubElement(
        cell,
        "mxGeometry",
        {
            "x": _format_number(shape.x),
            "y": _format_number(shape.y),
            "width": _format_number(shape.width),
            "height": _format_number(shape.height),
            "as": "geometry",
        },
    )


def _append_connector(
    root: ET.Element,
    connector: FreeformConnector,
    id_map: dict[str, str],
) -> None:
    attrs = {
        "id": id_map[connector.id],
        "value": _safe_text(connector.label),
        "style": _CONNECTOR_STYLES.get(connector.type, _BASE_EDGE_STYLE),
        "edge": "1",
        "parent": "1",
    }
    source = id_map.get(connector.source_id)
    target = id_map.get(connector.target_id)
    if source:
        attrs["source"] = source
    if target:
        attrs["target"] = target

    cell = ET.SubElement(root, "mxCell", attrs)
    ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})


def _shape_style(shape: FreeformShape) -> str:
    if shape.type == "drawio_shape":
        shape_name = _safe_style_name(shape.drawio_shape_name or "process")
        native_style = _filter_drawio_style(shape.drawio_style or "")
        return f"shape={shape_name};{native_style}"

    style = _SHAPE_STYLES.get(shape.type, _SHAPE_STYLES["rounded_rect"])
    if "whiteSpace=" in style or style.startswith("text;"):
        return style
    return f"{_BASE_VERTEX_STYLE}{style}"


def _build_id_map(diagram: FreeformDiagram) -> dict[str, str]:
    id_map: dict[str, str] = {}
    used = {"0", "1"}
    for raw_id in [
        *(group.id for group in diagram.groups),
        *(shape.id for shape in diagram.shapes),
        *(connector.id for connector in diagram.connectors),
    ]:
        safe_id = _safe_identifier(raw_id, "cell")
        candidate = safe_id
        suffix = 2
        while candidate in used:
            candidate = f"{safe_id}_{suffix}"
            suffix += 1
        used.add(candidate)
        id_map[raw_id] = candidate
    return id_map


def _parent_by_child(groups: list[FreeformGroup], id_map: dict[str, str]) -> dict[str, str]:
    parents: dict[str, str] = {}
    for group in groups:
        for child_id in group.children:
            if child_id not in parents and group.id in id_map:
                parents[child_id] = id_map[group.id]
    return parents


def _filter_drawio_style(style: str) -> str:
    safe_parts: list[str] = []
    for raw_part in style.split(";"):
        part = raw_part.strip()
        if not part:
            continue
        if "=" not in part:
            key = part
            value = ""
        else:
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
        if not _SAFE_STYLE_KEY_PATTERN.fullmatch(key):
            continue
        if key.lower() in _BLOCKED_STYLE_KEYS:
            continue
        if value and not _SAFE_STYLE_VALUE_PATTERN.fullmatch(value):
            continue
        safe_parts.append(f"{key}={value}" if value else key)
    return ";".join(safe_parts) + (";" if safe_parts else "")


def _safe_identifier(value: str, fallback: str) -> str:
    cleaned = str(value)
    for token in _DANGEROUS_TEXT_TOKENS:
        cleaned = cleaned.replace(token, "")
    cleaned = _SAFE_ID_PATTERN.sub("_", cleaned).strip("_.:-")
    if not cleaned:
        cleaned = fallback
    if cleaned[0].isdigit():
        cleaned = f"{fallback}_{cleaned}"
    return cleaned[:128]


def _safe_style_name(value: str) -> str:
    cleaned = _SAFE_STYLE_NAME_PATTERN.sub("", str(value))
    return cleaned[:96] or "process"


def _safe_style_value(value: str) -> str:
    value = value.strip()
    if _SAFE_STYLE_VALUE_PATTERN.fullmatch(value):
        return value
    return ""


def _safe_text(value: str) -> str:
    text = str(value)
    for token in _DANGEROUS_TEXT_TOKENS:
        text = text.replace(token, "")
    return text[:1000]


def _format_number(value: float | int) -> str:
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.6f}".rstrip("0").rstrip(".")


__all__ = ["build_drawio_xml"]
