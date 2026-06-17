from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .freeform_models import (
    FreeformConnector,
    FreeformDiagram,
    FreeformGroup,
    FreeformShape,
)
from .rich_text import diagram_label_html


_SAFE_ID_PATTERN = re.compile(r"[^A-Za-z0-9_.:-]+")
_SAFE_STYLE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_.:-]+")
_SAFE_STYLE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_SAFE_STYLE_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9#.,_ ./:%()+\-\[\]]{0,256}$")
_HTML_TAG_PATTERN = re.compile(r"<[^>]*>")
_EVENT_HANDLER_PATTERN = re.compile(r"\bon[a-z]+\s*=", re.IGNORECASE)
_BLOCKED_STYLE_KEYS = {"image", "link", "src", "url", "href"}
_BLOCKED_VALUE_TOKENS = ("javascript:", "data:", "vbscript:")
_DANGEROUS_TEXT_TOKENS = (
    "<script",
    "</script",
    "javascript:",
    "data:text/html",
    "onclick",
    "onerror",
    "onload",
)

_BASE_VERTEX_STYLE = "whiteSpace=wrap;html=1;align=center;verticalAlign=middle;"
_BASE_EDGE_STYLE = (
    "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;"
    "jettySize=auto;html=1;endArrow=block;endFill=1;"
)

_SHAPE_STYLES = {
    "rect": "rounded=1;arcSize=10;",
    "rectangle": "rounded=1;arcSize=10;",
    "rounded_rect": "rounded=1;arcSize=10;",
    "stadium": "rounded=1;absoluteArcSize=1;arcSize=60;",
    "text": "text;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;",
    "container": "rounded=1;arcSize=10;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#666666;",
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
    "arrow": _BASE_EDGE_STYLE,
}

_STYLE_KEY_ALIASES = {
    "fill": "fillColor",
    "stroke": "strokeColor",
    "stroke-width": "strokeWidth",
    "stroke_width": "strokeWidth",
    "end-arrow": "endArrow",
    "end_arrow": "endArrow",
    "start-arrow": "startArrow",
    "start_arrow": "startArrow",
    "font-color": "fontColor",
    "font_color": "fontColor",
    "font-size": "fontSize",
    "font_size": "fontSize",
    "font-family": "fontFamily",
    "font_family": "fontFamily",
}

_DIRECT_STYLE_KEYS = {
    "fillColor",
    "strokeColor",
    "strokeWidth",
    "fontColor",
    "fontSize",
    "fontFamily",
    "fontStyle",
    "dashed",
    "dashPattern",
    "endArrow",
    "endFill",
    "startArrow",
    "startFill",
    "opacity",
    "fillOpacity",
    "strokeOpacity",
}


def build_drawio_xml(diagram: FreeformDiagram) -> str:
    """Build Draw.io XML for a normalized freeform diagram."""
    visible_groups = [group for group in diagram.groups if not _is_hidden(group.extras)]
    visible_shapes = [shape for shape in diagram.shapes if not _is_hidden(shape.extras)]
    visible_ids = {group.id for group in visible_groups}
    visible_ids.update(shape.id for shape in visible_shapes)
    visible_connectors = [
        connector
        for connector in diagram.connectors
        if not _is_hidden(connector.extras)
        and connector.source_id in visible_ids
        and connector.target_id in visible_ids
    ]
    id_map = _build_id_map(visible_groups, visible_shapes, visible_connectors)
    group_by_id = {group.id: group for group in visible_groups}
    parent_by_child = _parent_by_child(visible_groups, visible_shapes, group_by_id)

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

    for group in visible_groups:
        _append_group(root, group, id_map)

    for shape in visible_shapes:
        _append_shape(root, shape, id_map, parent_by_child, group_by_id)

    for connector in visible_connectors:
        _append_connector(root, connector, id_map, parent_by_child, group_by_id)

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
            "value": _safe_label_html(group.label),
            "style": _merge_styles(
                (
                    f"group;rounded=1;arcSize=10;dashed=1;dashPattern=8 6;"
                    f"{_BASE_VERTEX_STYLE}container=1;collapsible=0;"
                ),
                _style_from_extras(group.extras),
            ),
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
    group_by_id: dict[str, FreeformGroup],
) -> None:
    shape_id = id_map[shape.id]
    parent_id = parent_by_child.get(shape.id)
    parent = id_map[parent_id] if parent_id else "1"
    x = shape.x
    y = shape.y
    if parent_id:
        parent_group = group_by_id.get(parent_id)
        if parent_group is not None:
            x -= parent_group.x or 0
            y -= parent_group.y or 0

    cell = ET.SubElement(
        root,
        "mxCell",
        {
            "id": shape_id,
            "value": _safe_label_html(shape.label),
            "style": _shape_style(shape, group_by_id.get(parent_id or "")),
            "vertex": "1",
            "parent": parent,
        },
    )
    ET.SubElement(
        cell,
        "mxGeometry",
        {
            "x": _format_number(x),
            "y": _format_number(y),
            "width": _format_number(shape.width),
            "height": _format_number(shape.height),
            "as": "geometry",
        },
    )


def _append_connector(
    root: ET.Element,
    connector: FreeformConnector,
    id_map: dict[str, str],
    parent_by_child: dict[str, str],
    group_by_id: dict[str, FreeformGroup],
) -> None:
    inherited_style = _connector_inherited_style(connector, parent_by_child, group_by_id)
    attrs = {
        "id": id_map[connector.id],
        "value": _safe_label_html(connector.label),
        "style": _merge_styles(
            _CONNECTOR_STYLES.get(connector.type, _BASE_EDGE_STYLE),
            _merge_styles(inherited_style, _style_from_extras(connector.extras)),
        ),
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


def _shape_style(shape: FreeformShape, parent_group: FreeformGroup | None = None) -> str:
    if shape.type == "drawio_shape":
        shape_name = _safe_style_name(shape.drawio_shape_name or "process")
        native_style = _filter_drawio_style(shape.drawio_style or "")
        return f"shape={shape_name};{native_style}"

    style = _SHAPE_STYLES.get(shape.type, _SHAPE_STYLES["rounded_rect"])
    if "whiteSpace=" in style or style.startswith("text;"):
        base_style = style
    else:
        base_style = f"{_BASE_VERTEX_STYLE}{style}"
    inherited_style = ""
    if parent_group is not None:
        group_stroke = _style_value_from_extras(parent_group.extras, "strokeColor")
        if group_stroke:
            inherited_style = f"fillColor=#ffffff;strokeColor={group_stroke};strokeWidth=2;"
    return _merge_styles(base_style, _merge_styles(inherited_style, _style_from_extras(shape.extras)))


def _connector_inherited_style(
    connector: FreeformConnector,
    parent_by_child: dict[str, str],
    group_by_id: dict[str, FreeformGroup],
) -> str:
    if _style_value_from_extras(connector.extras, "strokeColor"):
        return ""
    group_id = parent_by_child.get(connector.source_id) or parent_by_child.get(connector.target_id)
    group = group_by_id.get(group_id or "")
    stroke = _style_value_from_extras(group.extras, "strokeColor") if group is not None else ""
    if not stroke:
        return "strokeColor=#6b7280;strokeWidth=2;"
    return f"strokeColor={stroke};strokeWidth=2;"


def _build_id_map(
    groups: list[FreeformGroup],
    shapes: list[FreeformShape],
    connectors: list[FreeformConnector],
) -> dict[str, str]:
    id_map: dict[str, str] = {}
    used = {"0", "1"}
    for raw_id in [
        *(group.id for group in groups),
        *(shape.id for shape in shapes),
        *(connector.id for connector in connectors),
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


def _parent_by_child(
    groups: list[FreeformGroup],
    shapes: list[FreeformShape],
    group_by_id: dict[str, FreeformGroup],
) -> dict[str, str]:
    parents: dict[str, str] = {}
    for shape in shapes:
        parent_id = str(shape.extras.get("parent_id") or shape.extras.get("parent") or "")
        if parent_id in group_by_id:
            parents[shape.id] = parent_id

    for group in groups:
        for child_id in group.children:
            if child_id not in parents:
                parents[child_id] = group.id
    return parents


def _style_from_extras(extras: dict[str, object]) -> str:
    parts: list[str] = []
    style = extras.get("style")
    if style is not None:
        parts.append(_translate_style(str(style)))

    direct_parts: list[str] = []
    for raw_key, raw_value in extras.items():
        key = _STYLE_KEY_ALIASES.get(str(raw_key).lower(), str(raw_key))
        if key not in _DIRECT_STYLE_KEYS:
            continue
        if str(raw_key).lower() == "hidden":
            continue
        direct_parts.append(f"{key}={raw_value}")
        if key == "endArrow" and raw_value == "block":
            direct_parts.append("endFill=1")
    if direct_parts:
        parts.append(";".join(direct_parts))

    return _filter_drawio_style(";".join(part for part in parts if part))


def _style_value_from_extras(extras: dict[str, object], wanted_key: str) -> str:
    wanted_key = wanted_key.lower()
    style = extras.get("style")
    if style is not None:
        translated = _translate_style(str(style))
        for part in translated.split(";"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            if key.strip().lower() == wanted_key and _is_safe_style_value(value.strip()):
                return value.strip()

    for raw_key, raw_value in extras.items():
        key = _STYLE_KEY_ALIASES.get(str(raw_key).lower(), str(raw_key))
        value = str(raw_value).strip()
        if key.lower() == wanted_key and _is_safe_style_value(value):
            return value
    return ""


def _translate_style(style: str) -> str:
    translated: list[str] = []
    for raw_part in style.split(";"):
        part = raw_part.strip()
        if not part:
            continue
        if ":" in part and "=" not in part:
            key, value = part.split(":", 1)
        elif "=" in part:
            key, value = part.split("=", 1)
        else:
            translated.append(part)
            continue
        key = key.strip()
        value = value.strip()
        key = _STYLE_KEY_ALIASES.get(key.lower(), key)
        if key.lower() == "hidden":
            continue
        if key == "endArrow" and value == "block":
            translated.append("endFill=1")
        translated.append(f"{key}={value}")
    return ";".join(translated)


def _merge_styles(base_style: str, extra_style: str) -> str:
    if not base_style:
        return extra_style
    if not extra_style:
        return base_style
    return f"{base_style.rstrip(';')};{extra_style}"


def _is_hidden(extras: dict[str, object]) -> bool:
    hidden = extras.get("hidden")
    if isinstance(hidden, bool):
        return hidden
    if hidden is not None and str(hidden).strip().lower() in {"1", "true", "yes"}:
        return True
    style = extras.get("style")
    if style is None:
        return False
    for raw_part in str(style).split(";"):
        part = raw_part.strip()
        if not part:
            continue
        if ":" in part and "=" not in part:
            key, value = part.split(":", 1)
        elif "=" in part:
            key, value = part.split("=", 1)
        else:
            continue
        if key.strip().lower() == "hidden" and value.strip().lower() in {"1", "true", "yes"}:
            return True
    return False


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
        key_lower = key.lower()
        if not _SAFE_STYLE_KEY_PATTERN.fullmatch(key):
            continue
        if key_lower in _BLOCKED_STYLE_KEYS or key_lower.startswith("on"):
            continue
        if value and not _is_safe_style_value(value):
            continue
        safe_parts.append(f"{key}={value}" if value else key)
    return ";".join(safe_parts) + (";" if safe_parts else "")


def _safe_identifier(value: str, fallback: str) -> str:
    cleaned = str(value)
    cleaned = _strip_dangerous_text(cleaned)
    cleaned = _SAFE_ID_PATTERN.sub("_", cleaned).strip("_.:-")
    if not cleaned:
        cleaned = fallback
    if cleaned[0].isdigit():
        cleaned = f"{fallback}_{cleaned}"
    return cleaned[:128]


def _safe_style_name(value: str) -> str:
    cleaned = _strip_dangerous_text(str(value))
    cleaned = _SAFE_STYLE_NAME_PATTERN.sub("", cleaned)
    return cleaned[:96] or "process"


def _safe_style_value(value: str) -> str:
    value = value.strip()
    if _is_safe_style_value(value):
        return value
    return ""


def _safe_text(value: str) -> str:
    return _strip_dangerous_text(str(value))[:1000]


def _safe_label_html(value: str) -> str:
    return diagram_label_html(str(value)[:1000])


def _strip_dangerous_text(value: str) -> str:
    text = _HTML_TAG_PATTERN.sub("", value)
    text = _EVENT_HANDLER_PATTERN.sub("", text)
    for token in _DANGEROUS_TEXT_TOKENS:
        text = re.sub(re.escape(token), "", text, flags=re.IGNORECASE)
    return text


def _is_safe_style_value(value: str) -> bool:
    if not _SAFE_STYLE_VALUE_PATTERN.fullmatch(value):
        return False
    lowered = value.lower()
    if any(token in lowered for token in _BLOCKED_VALUE_TOKENS):
        return False
    if "://" in value or _EVENT_HANDLER_PATTERN.search(value):
        return False
    if any(char in value for char in ("<", ">", '"', "'", "&")):
        return False
    return True


def _format_number(value: float | int) -> str:
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.6f}".rstrip("0").rstrip(".")


__all__ = ["build_drawio_xml"]
