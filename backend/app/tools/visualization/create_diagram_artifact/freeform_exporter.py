from __future__ import annotations

import base64
import html
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .drawio_writer import build_drawio_xml
from .freeform_models import FreeformDiagram, FreeformShape


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
    needs_svg = "drawio_svg" in output_formats
    exporter = _find_drawio_exporter()
    exporter_ok = False

    if exporter is not None:
        exporter_ok = True
        if needs_png:
            exporter_ok = _run_drawio_export(exporter, drawio_path, preview_png_path, "png")
        if needs_svg:
            exporter_ok = (
                _run_drawio_export(exporter, drawio_path, preview_svg_path, "svg")
                and exporter_ok
            )

    if exporter is None or not exporter_ok:
        warnings.append("exporter_unavailable")

    if needs_svg and not preview_svg_path.exists():
        _write_fallback_svg(diagram, preview_svg_path)

    if needs_png and not preview_png_path.exists():
        _write_fallback_png(diagram, preview_png_path, warnings)

    if needs_png and not preview_svg_path.exists() and (exporter is None or not exporter_ok):
        _write_fallback_svg(diagram, preview_svg_path)

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
        subprocess.run(command, check=True, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return output_path.exists() and output_path.stat().st_size > 0


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
    ]

    for group in diagram.groups:
        x = _number(group.x, 0)
        y = _number(group.y, 0)
        group_width = _number(group.width, 240)
        group_height = _number(group.height, 160)
        parts.append(
            (
                f'<g data-group-id="{html.escape(group.id, quote=True)}">'
                f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(group_width)}" '
                f'height="{_fmt(group_height)}" rx="8" fill="none" '
                f'stroke="#8a8f98" stroke-dasharray="6 4"/>'
                f'<text x="{_fmt(x + 10)}" y="{_fmt(y + 22)}" font-size="14" '
                f'font-family="Arial, sans-serif" fill="#424852">'
                f"{html.escape(group.label or group.id)}</text></g>"
            )
        )

    shape_by_id = {shape.id: shape for shape in diagram.shapes}
    for connector in diagram.connectors:
        source = shape_by_id.get(connector.source_id)
        target = shape_by_id.get(connector.target_id)
        if source is None or target is None:
            continue
        x1 = source.x + source.width / 2
        y1 = source.y + source.height / 2
        x2 = target.x + target.width / 2
        y2 = target.y + target.height / 2
        parts.append(
            (
                f'<line data-connector-id="{html.escape(connector.id, quote=True)}" '
                f'x1="{_fmt(x1)}" y1="{_fmt(y1)}" x2="{_fmt(x2)}" y2="{_fmt(y2)}" '
                'stroke="#4b5563" stroke-width="2"/>'
            )
        )

    for shape in diagram.shapes:
        parts.append(_shape_svg(shape))

    parts.append("</svg>")
    output_path.write_text("\n".join(parts), encoding="utf-8")


def _shape_svg(shape: FreeformShape) -> str:
    x = shape.x
    y = shape.y
    width = shape.width
    height = shape.height
    escaped_id = html.escape(shape.id, quote=True)
    escaped_label = html.escape(shape.label or shape.id)
    text = (
        f'<text x="{_fmt(x + width / 2)}" y="{_fmt(y + height / 2 + 5)}" '
        f'text-anchor="middle" font-size="14" font-family="Arial, sans-serif" '
        f'fill="#1f2937">{escaped_label}</text>'
    )

    if shape.type in {"circle", "ellipse"}:
        body = (
            f'<ellipse cx="{_fmt(x + width / 2)}" cy="{_fmt(y + height / 2)}" '
            f'rx="{_fmt(width / 2)}" ry="{_fmt(height / 2)}" '
            'fill="#eef6ff" stroke="#2563eb" stroke-width="2"/>'
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
            f'<polygon points="{point_text}" fill="#fff7ed" '
            'stroke="#ea580c" stroke-width="2"/>'
        )
    elif shape.type == "text":
        body = ""
    else:
        rx = 10 if shape.type in {"rounded_rect", "stadium"} else 0
        body = (
            f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(width)}" '
            f'height="{_fmt(height)}" rx="{rx}" fill="#f8fafc" '
            f'stroke="#2563eb" stroke-width="2"/>'
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

    for group in diagram.groups:
        x = _number(group.x, 0)
        y = _number(group.y, 0)
        group_width = _number(group.width, 240)
        group_height = _number(group.height, 160)
        draw.rectangle(
            [x, y, x + group_width, y + group_height],
            outline="#8a8f98",
            width=2,
        )
        draw.text((x + 10, y + 8), group.label or group.id, fill="#424852")

    shape_by_id = {shape.id: shape for shape in diagram.shapes}
    for connector in diagram.connectors:
        source = shape_by_id.get(connector.source_id)
        target = shape_by_id.get(connector.target_id)
        if source is None or target is None:
            continue
        draw.line(
            [
                (source.x + source.width / 2, source.y + source.height / 2),
                (target.x + target.width / 2, target.y + target.height / 2),
            ],
            fill="#4b5563",
            width=2,
        )

    for shape in diagram.shapes:
        box = [shape.x, shape.y, shape.x + shape.width, shape.y + shape.height]
        if shape.type in {"circle", "ellipse"}:
            draw.ellipse(box, fill="#eef6ff", outline="#2563eb", width=2)
        elif shape.type == "diamond":
            draw.polygon(
                [
                    (shape.x + shape.width / 2, shape.y),
                    (shape.x + shape.width, shape.y + shape.height / 2),
                    (shape.x + shape.width / 2, shape.y + shape.height),
                    (shape.x, shape.y + shape.height / 2),
                ],
                fill="#fff7ed",
                outline="#ea580c",
            )
        elif shape.type != "text":
            draw.rounded_rectangle(box, radius=10, fill="#f8fafc", outline="#2563eb", width=2)
        draw.text((shape.x + 8, shape.y + 8), shape.label or shape.id, fill="#1f2937")

    image.save(output_path, format="PNG")


def _number(value: float | None, default: float) -> float:
    return default if value is None else value


def _fmt(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:.2f}".rstrip("0").rstrip(".")


__all__ = ["FreeformExportResult", "export_freeform_diagram"]
