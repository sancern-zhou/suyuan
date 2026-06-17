from __future__ import annotations

import base64
import html
import json
import math
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .drawio_writer import build_drawio_xml
from .freeform_models import FreeformConnector, FreeformDiagram, FreeformGroup, FreeformShape
from .rich_text import (
    DEFAULT_DIAGRAM_SVG_FONT_FAMILY,
    diagram_label_plain_text,
    diagram_label_tokens,
)


@dataclass(frozen=True)
class FreeformExportResult:
    drawio_path: Path
    source_json_path: Path
    preview_png_path: Path
    preview_svg_path: Path
    warnings: list[str] = field(default_factory=list)


def export_freeform_diagram(
    diagram: FreeformDiagram,
    artifact_dir: str | Path,
) -> FreeformExportResult:
    root_dir = Path(artifact_dir)
    assets_dir = root_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    drawio_path = assets_dir / "diagram.drawio"
    source_json_path = root_dir / "diagram.source.json"
    preview_png_path = assets_dir / "diagram.png"
    preview_svg_path = assets_dir / "diagram.drawio.svg"
    warnings: list[str] = []

    drawio_path.write_text(build_drawio_xml(diagram), encoding="utf-8")
    source_json_path.write_text(
        json.dumps(diagram.to_source_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    output_formats = set(diagram.output_formats)
    needs_png = True
    needs_svg = True
    exporter = _find_drawio_exporter()
    exporter_ok = False
    png_export_ok = False
    svg_export_ok = False

    if exporter is not None:
        exporter_ok = True
        if needs_svg:
            svg_export_ok = _run_drawio_export(exporter, drawio_path, preview_svg_path, "svg")
            exporter_ok = (
                svg_export_ok and exporter_ok
            )

    if exporter is None or not exporter_ok:
        warnings.append("exporter_unavailable")

    if needs_svg and (not svg_export_ok or not _is_usable_file(preview_svg_path)):
        _write_fallback_svg(diagram, preview_svg_path)

    if needs_png:
        _write_fallback_png(diagram, preview_png_path, warnings)

    return FreeformExportResult(
        drawio_path=drawio_path,
        source_json_path=source_json_path,
        preview_png_path=preview_png_path,
        preview_svg_path=preview_svg_path,
        warnings=warnings,
    )


def _find_drawio_exporter() -> str | None:
    return shutil.which("drawio") or shutil.which("diagrams.net")


def _run_drawio_export(
    exporter: str,
    drawio_path: Path,
    output_path: Path,
    output_format: str,
) -> bool:
    command = [
        exporter,
        "--export",
        "--format",
        output_format,
        "--output",
        str(output_path),
        str(drawio_path),
    ]
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return _is_usable_file(output_path)


def _is_usable_file(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _write_fallback_svg(diagram: FreeformDiagram, output_path: Path) -> None:
    width = max(1, int(diagram.canvas.width))
    height = max(1, int(diagram.canvas.height))
    background = html.escape(diagram.canvas.background or "#ffffff", quote=True)
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img">'
        ),
        f"<title>{html.escape(diagram.title)}</title>",
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="{background}"/>',
        _grid_pattern_svg(width, height),
    ]

    visible_groups = [item for item in diagram.groups if not _is_hidden(item.extras)]
    visible_shapes = _visible_render_shapes(diagram)
    parent_by_child = _parent_by_child(visible_groups, visible_shapes)
    group_styles = {group.id: _parse_source_style(group.extras) for group in visible_groups}
    shape_styles = _shape_styles(visible_shapes, parent_by_child, group_styles)
    endpoint_boxes = _endpoint_boxes(visible_groups, visible_shapes)

    for group in visible_groups:
        x = _number(group.x, 0)
        y = _number(group.y, 0)
        group_width = _number(group.width, 240)
        group_height = _number(group.height, 160)
        group_style = group_styles[group.id]
        parts.append(
            (
                f'<g data-group-id="{html.escape(group.id, quote=True)}">'
                f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(group_width)}" '
                f'height="{_fmt(group_height)}" rx="18" fill="{html.escape(group_style["fill"], quote=True)}" '
                f'stroke="{html.escape(group_style["stroke"], quote=True)}" stroke-width="{_fmt(group_style["stroke_width"])}" '
                f'stroke-dasharray="8 6" fill-opacity="0.72"/>'
                f'<text x="{_fmt(x + 10)}" y="{_fmt(y + 22)}" font-size="14" '
                f'font-family="{html.escape(DEFAULT_DIAGRAM_SVG_FONT_FAMILY, quote=True)}" fill="#424852">'
                f"{_svg_label_content(group.label or group.id)}</text></g>"
            )
        )

    endpoint_centers = _endpoint_centers(diagram, visible_shapes)
    bundled_connectors, individual_connectors = _bundle_high_fan_in_connectors(
        [item for item in diagram.connectors if not _is_hidden(item.extras)],
        endpoint_centers,
    )
    for target_id, connectors in bundled_connectors:
        parts.append(_connector_bundle_svg(target_id, connectors, endpoint_centers, parent_by_child, group_styles, shape_styles))

    for connector in individual_connectors:
        source = endpoint_boxes.get(connector.source_id)
        target = endpoint_boxes.get(connector.target_id)
        if source is None or target is None:
            continue
        points = _edge_route(source, target)
        parts.append(_connector_svg(connector, points, parent_by_child, group_styles, shape_styles))

    for shape in visible_shapes:
        parts.append(_shape_svg(shape, shape_styles[shape.id]))

    parts.append("</svg>")
    output_path.write_text("\n".join(parts), encoding="utf-8")


def _shape_svg(shape: FreeformShape, shape_style: dict[str, str | float]) -> str:
    x = shape.x
    y = shape.y
    width = shape.width
    height = shape.height
    escaped_id = html.escape(shape.id, quote=True)
    label_content = _svg_label_content(shape.label or shape.id)
    if shape.type in {"container", "swimlane"}:
        text = (
            f'<text x="{_fmt(x + 8)}" y="{_fmt(y + 22)}" font-size="14" '
            f'font-family="{html.escape(DEFAULT_DIAGRAM_SVG_FONT_FAMILY, quote=True)}" '
            f'fill="#424852">{label_content}</text>'
        )
    else:
        text = (
            f'<text x="{_fmt(x + width / 2)}" y="{_fmt(y + height / 2 + 5)}" '
            f'text-anchor="middle" font-size="14" '
            f'font-family="{html.escape(DEFAULT_DIAGRAM_SVG_FONT_FAMILY, quote=True)}" '
            f'fill="#1f2937">{label_content}</text>'
        )

    if shape.type in {"database", "cylinder"}:
        top_h = min(18.0, height * 0.28)
        body = (
            f'<path d="M {_fmt(x)} {_fmt(y + top_h / 2)} '
            f'C {_fmt(x)} {_fmt(y - top_h / 6)}, {_fmt(x + width)} {_fmt(y - top_h / 6)}, {_fmt(x + width)} {_fmt(y + top_h / 2)} '
            f'L {_fmt(x + width)} {_fmt(y + height - top_h / 2)} '
            f'C {_fmt(x + width)} {_fmt(y + height + top_h / 6)}, {_fmt(x)} {_fmt(y + height + top_h / 6)}, {_fmt(x)} {_fmt(y + height - top_h / 2)} Z" '
            f'fill="{html.escape(shape_style["fill"], quote=True)}" '
            f'stroke="{html.escape(shape_style["stroke"], quote=True)}" '
            f'stroke-width="{_fmt(shape_style["stroke_width"])}"/>'
            f'<ellipse cx="{_fmt(x + width / 2)}" cy="{_fmt(y + top_h / 2)}" '
            f'rx="{_fmt(width / 2)}" ry="{_fmt(top_h / 2)}" fill="none" '
            f'stroke="{html.escape(shape_style["stroke"], quote=True)}" '
            f'stroke-width="{_fmt(shape_style["stroke_width"])}"/>'
        )
    elif shape.type in {"circle", "ellipse"}:
        body = (
            f'<ellipse cx="{_fmt(x + width / 2)}" cy="{_fmt(y + height / 2)}" '
            f'rx="{_fmt(width / 2)}" ry="{_fmt(height / 2)}" '
            f'fill="{html.escape(shape_style["fill"], quote=True)}" '
            f'stroke="{html.escape(shape_style["stroke"], quote=True)}" '
            f'stroke-width="{_fmt(shape_style["stroke_width"])}"/>'
        )
    elif shape.type == "diamond":
        points = [
            (x + width / 2, y),
            (x + width, y + height / 2),
            (x + width / 2, y + height),
            (x, y + height / 2),
        ]
        point_text = " ".join(f"{_fmt(px)},{_fmt(py)}" for px, py in points)
        body = (
            f'<polygon points="{point_text}" fill="{html.escape(shape_style["fill"], quote=True)}" '
            f'stroke="{html.escape(shape_style["stroke"], quote=True)}" '
            f'stroke-width="{_fmt(shape_style["stroke_width"])}"/>'
        )
    elif shape.type == "text":
        body = ""
    else:
        rx = 10 if shape.type in {"rectangle", "rect", "rounded_rect", "stadium"} else 0
        body = (
            f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(width)}" '
            f'height="{_fmt(height)}" rx="{rx}" fill="{html.escape(shape_style["fill"], quote=True)}" '
            f'stroke="{html.escape(shape_style["stroke"], quote=True)}" '
            f'stroke-width="{_fmt(shape_style["stroke_width"])}"/>'
        )
    return f'<g data-shape-id="{escaped_id}">{body}{text}</g>'


def _write_fallback_png(
    diagram: FreeformDiagram,
    output_path: Path,
    warnings: list[str],
) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        warnings.append("png_fallback_unavailable")
        output_path.write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
                "z8BQDwAFgwJ/l8DfkAAAAABJRU5ErkJggg=="
            )
        )
        return

    width = max(1, int(diagram.canvas.width))
    height = max(1, int(diagram.canvas.height))
    try:
        image = Image.new("RGB", (width, height), diagram.canvas.background or "white")
    except ValueError:
        image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = _load_font(16)
    label_font = _load_font(14)
    _draw_grid(draw, width, height)

    visible_groups = [item for item in diagram.groups if not _is_hidden(item.extras)]
    visible_shapes = _visible_render_shapes(diagram)
    parent_by_child = _parent_by_child(visible_groups, visible_shapes)
    group_styles = {group.id: _parse_source_style(group.extras) for group in visible_groups}
    shape_styles = _shape_styles(visible_shapes, parent_by_child, group_styles)
    for style in [*group_styles.values(), *shape_styles.values()]:
        if str(style.get("fill", "")).lower() == "none":
            style["fill"] = "#ffffff"
    endpoint_boxes = _endpoint_boxes(visible_groups, visible_shapes)

    for group in visible_groups:
        x = _number(group.x, 0)
        y = _number(group.y, 0)
        group_width = _number(group.width, 240)
        group_height = _number(group.height, 160)
        group_style = group_styles[group.id]
        draw.rounded_rectangle(
            [x, y, x + group_width, y + group_height],
            radius=18,
            fill=group_style["fill"],
            outline=group_style["stroke"],
            width=int(group_style["stroke_width"]),
        )
        draw.text((x + 10, y + 8), diagram_label_plain_text(group.label or group.id), fill="#424852", font=title_font)

    endpoint_centers = _endpoint_centers(diagram, visible_shapes)
    bundled_connectors, individual_connectors = _bundle_high_fan_in_connectors(
        [item for item in diagram.connectors if not _is_hidden(item.extras)],
        endpoint_centers,
    )
    for target_id, connectors in bundled_connectors:
        _draw_connector_bundle(draw, target_id, connectors, endpoint_centers, parent_by_child, group_styles, shape_styles)

    for connector in individual_connectors:
        source = endpoint_boxes.get(connector.source_id)
        target = endpoint_boxes.get(connector.target_id)
        if source is None or target is None:
            continue
        points = _edge_route(source, target)
        connector_style = _connector_style(connector, parent_by_child, group_styles, shape_styles)
        _draw_polyline_arrow(
            draw,
            points,
            connector_style["stroke"],
            int(connector_style["stroke_width"]),
        )

    for shape in visible_shapes:
        box = [shape.x, shape.y, shape.x + shape.width, shape.y + shape.height]
        shape_style = shape_styles[shape.id]
        if shape.type in {"database", "cylinder"}:
            draw.rectangle(
                [shape.x, shape.y + 9, shape.x + shape.width, shape.y + shape.height - 9],
                fill=shape_style["fill"],
                outline=shape_style["stroke"],
                width=int(shape_style["stroke_width"]),
            )
            draw.ellipse(
                [shape.x, shape.y, shape.x + shape.width, shape.y + 18],
                fill=shape_style["fill"],
                outline=shape_style["stroke"],
                width=int(shape_style["stroke_width"]),
            )
            draw.arc(
                [shape.x, shape.y + shape.height - 18, shape.x + shape.width, shape.y + shape.height],
                start=0,
                end=180,
                fill=shape_style["stroke"],
                width=int(shape_style["stroke_width"]),
            )
        elif shape.type in {"circle", "ellipse"}:
            draw.ellipse(
                box,
                fill=shape_style["fill"],
                outline=shape_style["stroke"],
                width=int(shape_style["stroke_width"]),
            )
        elif shape.type == "diamond":
            draw.polygon(
                [
                    (shape.x + shape.width / 2, shape.y),
                    (shape.x + shape.width, shape.y + shape.height / 2),
                    (shape.x + shape.width / 2, shape.y + shape.height),
                    (shape.x, shape.y + shape.height / 2),
                ],
                fill=shape_style["fill"],
                outline=shape_style["stroke"],
            )
        elif shape.type != "text":
            radius = 10 if shape.type in {"rectangle", "rect", "rounded_rect", "stadium"} else 0
            draw.rounded_rectangle(
                box,
                radius=radius,
                fill=shape_style["fill"],
                outline=shape_style["stroke"],
                width=int(shape_style["stroke_width"]),
            )
        if shape.type in {"container", "swimlane"}:
            draw.text((shape.x + 8, shape.y + 8), diagram_label_plain_text(shape.label or shape.id), fill="#424852", font=title_font)
        else:
            _draw_centered_text(draw, box, diagram_label_plain_text(shape.label or shape.id), label_font)

    image.save(output_path, format="PNG")


def _number(value: float | None, default: float) -> float:
    return default if value is None else value


def _svg_label_content(value: str) -> str:
    pieces: list[str] = []
    for role, text in diagram_label_tokens(value):
        escaped = html.escape(text)
        if role == "sub":
            pieces.append(f'<tspan baseline-shift="sub" font-size="70%">{escaped}</tspan>')
        elif role == "sup":
            pieces.append(f'<tspan baseline-shift="super" font-size="70%">{escaped}</tspan>')
        else:
            pieces.append(f"<tspan>{escaped}</tspan>")
    return "".join(pieces)


def _grid_pattern_svg(width: int, height: int) -> str:
    return (
        '<defs>'
        '<marker id="arrowhead" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
        '<path d="M 0 0 L 8 4 L 0 8 z" fill="context-stroke" stroke="context-stroke"/>'
        '</marker>'
        '<pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">'
        '<path d="M 20 0 L 0 0 0 20" fill="none" stroke="#eef2f7" stroke-width="1"/>'
        '</pattern>'
        '</defs>'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="url(#grid)" opacity="0.75"/>'
    )


def _visible_render_shapes(diagram: FreeformDiagram) -> list[FreeformShape]:
    visible: list[FreeformShape] = []
    visible_boxes: list[tuple[float, float, float, float]] = []
    for shape in diagram.shapes:
        if _is_hidden(shape.extras):
            continue
        if shape.type not in {"container", "swimlane"}:
            box = (shape.x, shape.y, shape.x + shape.width, shape.y + shape.height)
            if any(_overlap_ratio(box, existing) >= 0.72 for existing in visible_boxes):
                continue
            visible_boxes.append(box)
        visible.append(shape)
    return visible


def _parent_by_child(
    groups: list[FreeformGroup],
    shapes: list[FreeformShape],
) -> dict[str, str]:
    parents: dict[str, str] = {}
    group_by_id = {group.id: group for group in groups}
    for shape in shapes:
        parent_id = str(shape.extras.get("parent_id") or shape.extras.get("parent") or "")
        if parent_id in group_by_id:
            parents[shape.id] = parent_id

    for group in groups:
        for child_id in group.children:
            parents.setdefault(child_id, group.id)

    for shape in shapes:
        if shape.id in parents:
            continue
        center_x = shape.x + shape.width / 2
        center_y = shape.y + shape.height / 2
        containing = [
            group
            for group in groups
            if _number(group.x, 0) <= center_x <= _number(group.x, 0) + _number(group.width, 240)
            and _number(group.y, 0) <= center_y <= _number(group.y, 0) + _number(group.height, 160)
        ]
        if containing:
            smallest = min(
                containing,
                key=lambda group: _number(group.width, 240) * _number(group.height, 160),
            )
            parents[shape.id] = smallest.id
    return parents


def _shape_styles(
    shapes: list[FreeformShape],
    parent_by_child: dict[str, str],
    group_styles: dict[str, dict[str, str | float]],
) -> dict[str, dict[str, str | float]]:
    styles: dict[str, dict[str, str | float]] = {}
    for shape in shapes:
        parent_style = group_styles.get(parent_by_child.get(shape.id, ""))
        default_stroke = str(parent_style["stroke"]) if parent_style else "#6b7280"
        styles[shape.id] = _parse_source_style(
            shape.extras,
            default_fill="#ffffff",
            default_stroke=default_stroke,
            default_stroke_width=2.0,
        )
    return styles


def _endpoint_boxes(
    groups: list[FreeformGroup],
    shapes: list[FreeformShape],
) -> dict[str, tuple[float, float, float, float]]:
    boxes = {
        shape.id: (shape.x, shape.y, shape.x + shape.width, shape.y + shape.height)
        for shape in shapes
    }
    boxes.update(
        {
            group.id: (
                _number(group.x, 0),
                _number(group.y, 0),
                _number(group.x, 0) + _number(group.width, 240),
                _number(group.y, 0) + _number(group.height, 160),
            )
            for group in groups
        }
    )
    return boxes


def _bundle_high_fan_in_connectors(
    connectors: list[FreeformConnector],
    centers: dict[str, tuple[float, float]],
) -> tuple[list[tuple[str, list[FreeformConnector]]], list[FreeformConnector]]:
    by_target: dict[str, list[FreeformConnector]] = {}
    individual: list[FreeformConnector] = []
    for connector in connectors:
        if connector.source_id not in centers or connector.target_id not in centers:
            individual.append(connector)
            continue
        by_target.setdefault(connector.target_id, []).append(connector)

    bundled: list[tuple[str, list[FreeformConnector]]] = []
    for target_id, target_connectors in by_target.items():
        if len(target_connectors) >= 4:
            bundled.append((target_id, target_connectors))
        else:
            individual.extend(target_connectors)
    return bundled, individual


def _connector_bundle_svg(
    target_id: str,
    connectors: list[FreeformConnector],
    centers: dict[str, tuple[float, float]],
    parent_by_child: dict[str, str],
    group_styles: dict[str, dict[str, str | float]],
    shape_styles: dict[str, dict[str, str | float]],
) -> str:
    target = centers[target_id]
    sources = [centers[connector.source_id] for connector in connectors]
    style = _connector_style(connectors[0], parent_by_child, group_styles, shape_styles)
    stroke = html.escape(str(style["stroke"]), quote=True)
    stroke_width = _fmt(float(style["stroke_width"]))
    target_x, target_y = target
    avg_source_y = sum(y for _, y in sources) / len(sources)
    bus_y = target_y + (avg_source_y - target_y) * 0.55
    min_x = min(x for x, _ in sources)
    max_x = max(x for x, _ in sources)
    pieces = [
        (
            f'<g data-connector-bundle="{html.escape(target_id, quote=True)}" '
            f'data-connector-count="{len(connectors)}">'
        ),
        (
            f'<line x1="{_fmt(min_x)}" y1="{_fmt(bus_y)}" x2="{_fmt(max_x)}" y2="{_fmt(bus_y)}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}" stroke-opacity="0.55"/>'
        ),
        (
            f'<line x1="{_fmt(target_x)}" y1="{_fmt(target_y)}" x2="{_fmt(target_x)}" y2="{_fmt(bus_y)}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}" stroke-opacity="0.55"/>'
        ),
    ]
    for source_x, source_y in sources:
        pieces.append(
            f'<line x1="{_fmt(source_x)}" y1="{_fmt(source_y)}" x2="{_fmt(source_x)}" y2="{_fmt(bus_y)}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}" stroke-opacity="0.45"/>'
        )
    pieces.append("</g>")
    return "".join(pieces)


def _connector_svg(
    connector: FreeformConnector,
    points: list[tuple[float, float]],
    parent_by_child: dict[str, str],
    group_styles: dict[str, dict[str, str | float]],
    shape_styles: dict[str, dict[str, str | float]],
) -> str:
    style = _connector_style(connector, parent_by_child, group_styles, shape_styles)
    stroke = html.escape(str(style["stroke"]), quote=True)
    stroke_width = _fmt(float(style["stroke_width"]))
    escaped_id = html.escape(connector.id, quote=True)
    if len(points) == 2:
        (x1, y1), (x2, y2) = points
        return (
            f'<line data-connector-id="{escaped_id}" '
            f'x1="{_fmt(x1)}" y1="{_fmt(y1)}" x2="{_fmt(x2)}" y2="{_fmt(y2)}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}" stroke-opacity="0.45" marker-end="url(#arrowhead)"/>'
        )
    point_text = " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in points)
    return (
        f'<polyline data-connector-id="{escaped_id}" points="{point_text}" fill="none" '
        f'stroke="{stroke}" stroke-width="{stroke_width}" stroke-opacity="0.45" marker-end="url(#arrowhead)"/>'
    )


def _connector_style(
    connector: FreeformConnector,
    parent_by_child: dict[str, str],
    group_styles: dict[str, dict[str, str | float]],
    shape_styles: dict[str, dict[str, str | float]],
) -> dict[str, str | float]:
    source_group_style = group_styles.get(parent_by_child.get(connector.source_id, ""))
    target_group_style = group_styles.get(parent_by_child.get(connector.target_id, ""))
    source_shape_style = shape_styles.get(connector.source_id)
    target_shape_style = shape_styles.get(connector.target_id)
    inherited_stroke = (
        source_group_style
        or target_group_style
        or source_shape_style
        or target_shape_style
        or {"stroke": "#6b7280"}
    )["stroke"]
    return _parse_source_style(
        connector.extras,
        default_fill="none",
        default_stroke=str(inherited_stroke),
        default_stroke_width=2.0,
    )


def _edge_route(
    source_box: tuple[float, float, float, float],
    target_box: tuple[float, float, float, float],
) -> list[tuple[float, float]]:
    source = _edge_point(source_box, target_box)
    target = _edge_point(target_box, source_box)
    return _orthogonal_route(source, target)


def _edge_point(
    box: tuple[float, float, float, float],
    other: tuple[float, float, float, float],
) -> tuple[float, float]:
    left, top, right, bottom = box
    other_left, other_top, other_right, other_bottom = other
    cx = (left + right) / 2
    cy = (top + bottom) / 2
    other_cx = (other_left + other_right) / 2
    other_cy = (other_top + other_bottom) / 2
    dx = other_cx - cx
    dy = other_cy - cy
    if abs(dx) >= abs(dy):
        return (right if dx >= 0 else left, cy)
    return (cx, bottom if dy >= 0 else top)


def _orthogonal_route(
    source: tuple[float, float],
    target: tuple[float, float],
) -> list[tuple[float, float]]:
    x1, y1 = source
    x2, y2 = target
    if abs(x1 - x2) < 1 or abs(y1 - y2) < 1:
        return [source, target]
    mid_y = y1 + (y2 - y1) / 2
    return [source, (x1, mid_y), (x2, mid_y), target]


def _draw_connector_bundle(
    draw,
    target_id: str,
    connectors: list[FreeformConnector],
    centers: dict[str, tuple[float, float]],
    parent_by_child: dict[str, str],
    group_styles: dict[str, dict[str, str | float]],
    shape_styles: dict[str, dict[str, str | float]],
) -> None:
    target_x, target_y = centers[target_id]
    sources = [centers[connector.source_id] for connector in connectors]
    style = _connector_style(connectors[0], parent_by_child, group_styles, shape_styles)
    stroke = style["stroke"]
    width = int(style["stroke_width"])
    avg_source_y = sum(y for _, y in sources) / len(sources)
    bus_y = target_y + (avg_source_y - target_y) * 0.55
    min_x = min(x for x, _ in sources)
    max_x = max(x for x, _ in sources)
    draw.line([(min_x, bus_y), (max_x, bus_y)], fill=stroke, width=width)
    draw.line([(target_x, target_y), (target_x, bus_y)], fill=stroke, width=width)
    for source_x, source_y in sources:
        draw.line([(source_x, source_y), (source_x, bus_y)], fill=stroke, width=width)


def _draw_grid(draw, width: int, height: int) -> None:
    for x in range(0, width, 20):
        draw.line([(x, 0), (x, height)], fill="#eef2f7", width=1)
    for y in range(0, height, 20):
        draw.line([(0, y), (width, y)], fill="#eef2f7", width=1)


def _draw_polyline_arrow(
    draw,
    points: list[tuple[float, float]],
    fill: str,
    width: int,
) -> None:
    if len(points) < 2:
        return
    draw.line(points, fill=fill, width=width)
    start = points[-2]
    end = points[-1]
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    size = max(7, width * 4)
    left = (
        end[0] - size * math.cos(angle - math.pi / 6),
        end[1] - size * math.sin(angle - math.pi / 6),
    )
    right = (
        end[0] - size * math.cos(angle + math.pi / 6),
        end[1] - size * math.sin(angle + math.pi / 6),
    )
    draw.polygon([end, left, right], fill=fill)


def _overlap_ratio(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    area_a = max(1.0, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1.0, (b[2] - b[0]) * (b[3] - b[1]))
    return intersection / min(area_a, area_b)


def _endpoint_centers(
    diagram: FreeformDiagram,
    shapes: list[FreeformShape] | None = None,
) -> dict[str, tuple[float, float]]:
    render_shapes = shapes if shapes is not None else _visible_render_shapes(diagram)
    centers = {
        shape.id: (shape.x + shape.width / 2, shape.y + shape.height / 2)
        for shape in render_shapes
    }
    centers.update(
        {
            group.id: (
                _number(group.x, 0) + _number(group.width, 240) / 2,
                _number(group.y, 0) + _number(group.height, 160) / 2,
            )
            for group in diagram.groups
            if not _is_hidden(group.extras)
        }
    )
    return centers


def _parse_source_style(
    extras: dict[str, object],
    *,
    default_fill: str = "#f8fafc",
    default_stroke: str = "#6b7280",
    default_stroke_width: float = 2.0,
) -> dict[str, str | float]:
    style = {
        "fill": default_fill,
        "stroke": default_stroke,
        "stroke_width": default_stroke_width,
    }
    raw_style = extras.get("style")
    raw_parts = str(raw_style).split(";") if raw_style is not None else []
    for raw_part in raw_parts:
        part = raw_part.strip()
        if not part:
            continue
        if ":" in part and "=" not in part:
            key, value = part.split(":", 1)
        elif "=" in part:
            key, value = part.split("=", 1)
        else:
            continue
        key = key.strip().lower()
        value = value.strip()
        if key in {"fill", "fillcolor"} and _is_safe_color(value):
            style["fill"] = value
        elif key in {"stroke", "strokecolor"} and _is_safe_color(value):
            style["stroke"] = value
        elif key in {"stroke-width", "stroke_width", "strokewidth"}:
            try:
                style["stroke_width"] = max(1.0, min(float(value), 20.0))
            except ValueError:
                pass
    for raw_key, raw_value in extras.items():
        key = str(raw_key).strip().lower()
        value = str(raw_value).strip()
        if key in {"fill", "fillcolor"} and _is_safe_color(value):
            style["fill"] = value
        elif key in {"stroke", "strokecolor"} and _is_safe_color(value):
            style["stroke"] = value
        elif key in {"stroke-width", "stroke_width", "strokewidth"}:
            try:
                style["stroke_width"] = max(1.0, min(float(value), 20.0))
            except ValueError:
                pass
    return style


def _is_hidden(extras: dict[str, object]) -> bool:
    hidden = extras.get("hidden")
    if isinstance(hidden, bool):
        return hidden
    if hidden is not None and str(hidden).strip().lower() in {"1", "true", "yes"}:
        return True
    raw_style = extras.get("style")
    if raw_style is None:
        return False
    for raw_part in str(raw_style).split(";"):
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


def _is_safe_color(value: str) -> bool:
    if value == "none":
        return True
    if not value.startswith("#") or len(value) not in {4, 7, 9}:
        return False
    return all(char in "***REMOVED***ABCDEF" for char in value[1:])


def _load_font(size: int):
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    for font_path in (
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/google-droid-sans-fonts/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ):
        path = Path(font_path)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_centered_text(draw, box: list[float], text: str, font) -> None:
    left, top, right, bottom = box
    max_width = max(1, right - left - 12)
    lines = _wrap_text(draw, text, font, max_width)
    line_heights = []
    text_width = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = max(text_width, bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])
    text_height = sum(line_heights) + max(0, len(lines) - 1) * 4
    y = top + max(6, (bottom - top - text_height) / 2)
    for index, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        x = left + max(6, (right - left - line_width) / 2)
        draw.text((x, y), line, fill="#1f2937", font=font)
        y += line_heights[index] + 4


def _wrap_text(draw, text: str, font, max_width: float) -> list[str]:
    if not text:
        return [""]
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = f"{current}{char}"
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if current and bbox[2] - bbox[0] > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:3]


def _fmt(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:.2f}".rstrip("0").rstrip(".")


__all__ = ["FreeformExportResult", "export_freeform_diagram"]
