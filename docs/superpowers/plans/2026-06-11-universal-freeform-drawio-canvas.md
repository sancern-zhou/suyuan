# Universal Freeform Draw.io Canvas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a universal `diagram_mode="freeform"` canvas to `create_diagram_artifact` that generates editable `.drawio` files plus previewable PNG/SVG/HTML artifacts for architecture diagrams, flowcharts, mind maps, topologies, and custom diagrams.

**Architecture:** Keep the existing template renderer intact. Add focused freeform modules for input normalization, draw.io XML writing, preview export/fallback rendering, then integrate them into `CreateDiagramArtifactTool.execute`. Persist a normalized `diagram.source.json` beside `diagram.drawio` so future Agent edits can operate on a simple source model instead of reverse-engineering draw.io XML.

**Tech Stack:** Python 3.11 in conda env `backend_py311`, existing FastAPI backend artifact services, PIL/Playwright already used by the diagram tool, optional diagrams.net/drawio CLI if present, Vue frontend artifact panel.

---

## Scope Check

This plan covers one vertical slice: backend freeform draw.io generation, preview artifacts, frontend downloads, and tests. It intentionally does not embed a browser-based diagrams.net editor or implement `.vsdx` generation.

## File Structure

- Create `backend/app/tools/visualization/create_diagram_artifact/freeform_models.py`
  - Dataclasses and normalization for `canvas`, `shapes`, `connectors`, `groups`, `output_formats`, and `diagram_intent`.
  - Validates IDs, connector endpoints, dimensions, and allowed/fallback shape behavior.
- Create `backend/app/tools/visualization/create_diagram_artifact/drawio_writer.py`
  - Converts normalized freeform models into draw.io XML.
  - Owns shape alias to draw.io style mapping and `drawio_shape` passthrough.
- Create `backend/app/tools/visualization/create_diagram_artifact/freeform_exporter.py`
  - Writes `assets/diagram.drawio`, `diagram.source.json`, and preview files.
  - Uses drawio CLI when available; falls back to simple SVG/PNG rendering.
- Modify `backend/app/tools/visualization/create_diagram_artifact/tool.py`
  - Extend function schema with freeform fields.
  - Route `diagram_mode="freeform"` to the new modules.
  - Attach multiple artifacts and refs.
- Modify `backend/app/tools/utility/present_artifact_tool.py`
  - Recognize `.drawio` as a downloadable artifact and prefer sibling preview files when present.
- Create `frontend/src/utils/artifactRelatedFiles.js`
  - Normalizes related file entries from `related_files`, `artifacts`, and `refs.artifacts`.
- Modify `frontend/src/components/VisualizationPanel.vue`
  - Surface related files from `artifact.related_files` or `refs.artifacts`.
- Add tests under `backend/tests/`:
  - `test_freeform_diagram_models.py`
  - `test_drawio_writer.py`
  - `test_freeform_diagram_tool.py`
  - Extend `test_present_artifact_tool.py` for `.drawio`.

## Task 1: Normalize Freeform Input

**Files:**
- Create: `backend/app/tools/visualization/create_diagram_artifact/freeform_models.py`
- Test: `backend/tests/test_freeform_diagram_models.py`

- [ ] **Step 1: Write failing tests for normalization and validation**

Create `backend/tests/test_freeform_diagram_models.py`:

```python
import pytest

from app.tools.visualization.create_diagram_artifact.freeform_models import (
    FreeformValidationError,
    normalize_freeform_diagram,
)


def test_normalize_freeform_diagram_accepts_basic_canvas():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo Diagram",
        canvas={"width": 1200, "height": 800, "grid": 20, "background": "#ffffff"},
        shapes=[
            {"id": "start", "type": "rounded_rect", "label": "开始", "x": 80, "y": 80, "width": 140, "height": 60},
            {"id": "decision", "type": "diamond", "label": "是否通过", "x": 320, "y": 70, "width": 120, "height": 90},
        ],
        connectors=[
            {"id": "edge_start_decision", "from": "start", "to": "decision", "label": "提交", "type": "orthogonal"}
        ],
        groups=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="process",
    )

    assert diagram.artifact_id == "demo"
    assert diagram.canvas.width == 1200
    assert [shape.id for shape in diagram.shapes] == ["start", "decision"]
    assert diagram.shapes[1].type == "diamond"
    assert diagram.connectors[0].source_id == "start"
    assert diagram.output_formats == ["drawio", "png", "drawio_svg"]
    assert diagram.diagram_intent == "process"


def test_duplicate_shape_ids_fail():
    with pytest.raises(FreeformValidationError, match="Duplicate shape id"):
        normalize_freeform_diagram(
            artifact_id="demo",
            title="Demo",
            canvas={},
            shapes=[
                {"id": "node", "label": "A", "x": 0, "y": 0},
                {"id": "node", "label": "B", "x": 100, "y": 0},
            ],
            connectors=[],
            groups=[],
            output_formats=[],
            diagram_intent=None,
        )


def test_connector_missing_endpoint_fails():
    with pytest.raises(FreeformValidationError, match="unknown target id missing"):
        normalize_freeform_diagram(
            artifact_id="demo",
            title="Demo",
            canvas={},
            shapes=[{"id": "node", "label": "A", "x": 0, "y": 0}],
            connectors=[{"id": "edge", "from": "node", "to": "missing"}],
            groups=[],
            output_formats=[],
            diagram_intent=None,
        )


def test_drawio_shape_passthrough_is_preserved():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={},
        shapes=[
            {
                "id": "aws_lambda",
                "type": "drawio_shape",
                "label": "函数",
                "x": 10,
                "y": 20,
                "width": 80,
                "height": 80,
                "drawio_shape_name": "mxgraph.aws4.lambda_function",
                "drawio_style": "sketch=0;aspect=fixed;",
            }
        ],
        connectors=[],
        groups=[],
        output_formats=[],
        diagram_intent="architecture",
    )

    shape = diagram.shapes[0]
    assert shape.type == "drawio_shape"
    assert shape.drawio_shape_name == "mxgraph.aws4.lambda_function"
    assert "aspect=fixed" in shape.drawio_style
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_freeform_diagram_models.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `freeform_models`.

- [ ] **Step 3: Implement normalization dataclasses**

Create `backend/app/tools/visualization/create_diagram_artifact/freeform_models.py`:

```python
"""Normalized source model for freeform draw.io canvas diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class FreeformValidationError(ValueError):
    """Raised when a freeform diagram cannot be safely generated."""


DEFAULT_OUTPUT_FORMATS = ["drawio", "png"]
ALLOWED_INTENTS = {"architecture", "process", "mind_map", "data_flow", "topology", "org_chart", "custom"}
KNOWN_SHAPE_TYPES = {
    "rect",
    "rounded_rect",
    "text",
    "container",
    "swimlane",
    "database",
    "cloud",
    "queue",
    "document",
    "circle",
    "ellipse",
    "hexagon",
    "diamond",
    "triangle",
    "parallelogram",
    "cylinder",
    "actor",
    "note",
    "callout",
    "brace",
    "bracket",
    "line",
    "arrow",
    "image",
    "drawio_shape",
}
KNOWN_CONNECTOR_TYPES = {"straight", "orthogonal", "curved"}
KNOWN_OUTPUT_FORMATS = {"drawio", "png", "drawio_svg", "svg"}


@dataclass(frozen=True)
class FreeformCanvas:
    width: int = 1600
    height: int = 1000
    grid: int = 20
    background: str = "#ffffff"


@dataclass(frozen=True)
class FreeformShape:
    id: str
    type: str
    label: str
    x: float
    y: float
    width: float
    height: float
    style: Dict[str, Any] = field(default_factory=dict)
    parent_id: Optional[str] = None
    drawio_shape_name: Optional[str] = None
    drawio_style: str = ""


@dataclass(frozen=True)
class FreeformConnector:
    id: str
    source_id: Optional[str]
    target_id: Optional[str]
    label: str = ""
    type: str = "orthogonal"
    style: Dict[str, Any] = field(default_factory=dict)
    waypoints: List[Dict[str, float]] = field(default_factory=list)


@dataclass(frozen=True)
class FreeformGroup:
    id: str
    label: str
    x: float
    y: float
    width: float
    height: float
    style: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FreeformDiagram:
    artifact_id: str
    title: str
    canvas: FreeformCanvas
    shapes: List[FreeformShape]
    connectors: List[FreeformConnector]
    groups: List[FreeformGroup]
    output_formats: List[str]
    diagram_intent: str

    def to_source_dict(self) -> Dict[str, Any]:
        return {
            "diagram_mode": "freeform",
            "artifact_id": self.artifact_id,
            "title": self.title,
            "diagram_intent": self.diagram_intent,
            "canvas": self.canvas.__dict__,
            "groups": [group.__dict__ for group in self.groups],
            "shapes": [shape.__dict__ for shape in self.shapes],
            "connectors": [connector.__dict__ for connector in self.connectors],
            "output_formats": self.output_formats,
        }


def normalize_freeform_diagram(
    *,
    artifact_id: str,
    title: str,
    canvas: Optional[Dict[str, Any]],
    shapes: Optional[List[Dict[str, Any]]],
    connectors: Optional[List[Dict[str, Any]]],
    groups: Optional[List[Dict[str, Any]]],
    output_formats: Optional[List[str]],
    diagram_intent: Optional[str],
) -> FreeformDiagram:
    safe_artifact_id = str(artifact_id or "").strip()
    safe_title = str(title or "").strip()
    if not safe_artifact_id:
        raise FreeformValidationError("artifact_id is required")
    if not safe_title:
        raise FreeformValidationError("title is required")

    normalized_canvas = _normalize_canvas(canvas or {})
    normalized_groups = [_normalize_group(item, index) for index, item in enumerate(groups or [])]
    normalized_shapes = [_normalize_shape(item, index) for index, item in enumerate(shapes or [])]
    if not normalized_shapes:
        raise FreeformValidationError("freeform diagram requires at least one shape")

    shape_ids = _ensure_unique_ids([shape.id for shape in normalized_shapes], "shape")
    group_ids = _ensure_unique_ids([group.id for group in normalized_groups], "group")
    known_ids = shape_ids | group_ids
    normalized_connectors = [
        _normalize_connector(item, index, known_ids) for index, item in enumerate(connectors or [])
    ]
    _ensure_unique_ids([connector.id for connector in normalized_connectors], "connector")

    return FreeformDiagram(
        artifact_id=safe_artifact_id,
        title=safe_title,
        canvas=normalized_canvas,
        shapes=normalized_shapes,
        connectors=normalized_connectors,
        groups=normalized_groups,
        output_formats=_normalize_output_formats(output_formats or DEFAULT_OUTPUT_FORMATS),
        diagram_intent=_normalize_intent(diagram_intent),
    )


def _normalize_canvas(raw: Dict[str, Any]) -> FreeformCanvas:
    return FreeformCanvas(
        width=_positive_int(raw.get("width"), 1600, "canvas.width"),
        height=_positive_int(raw.get("height"), 1000, "canvas.height"),
        grid=_positive_int(raw.get("grid"), 20, "canvas.grid"),
        background=str(raw.get("background") or "#ffffff"),
    )


def _normalize_shape(raw: Dict[str, Any], index: int) -> FreeformShape:
    shape_type = str(raw.get("type") or "rounded_rect").strip().lower()
    if shape_type not in KNOWN_SHAPE_TYPES:
        shape_type = "rounded_rect"
    return FreeformShape(
        id=_required_id(raw.get("id"), f"shape_{index + 1}"),
        type=shape_type,
        label=str(raw.get("label") or raw.get("text") or "").strip(),
        x=_number(raw.get("x"), 0, "shape.x"),
        y=_number(raw.get("y"), 0, "shape.y"),
        width=_positive_number(raw.get("width"), 160, "shape.width"),
        height=_positive_number(raw.get("height"), 72, "shape.height"),
        style=dict(raw.get("style") or {}),
        parent_id=str(raw.get("parent_id") or raw.get("parent") or "").strip() or None,
        drawio_shape_name=str(raw.get("drawio_shape_name") or "").strip() or None,
        drawio_style=str(raw.get("drawio_style") or ""),
    )


def _normalize_group(raw: Dict[str, Any], index: int) -> FreeformGroup:
    return FreeformGroup(
        id=_required_id(raw.get("id"), f"group_{index + 1}"),
        label=str(raw.get("label") or "").strip(),
        x=_number(raw.get("x"), 0, "group.x"),
        y=_number(raw.get("y"), 0, "group.y"),
        width=_positive_number(raw.get("width"), 320, "group.width"),
        height=_positive_number(raw.get("height"), 220, "group.height"),
        style=dict(raw.get("style") or {}),
    )


def _normalize_connector(raw: Dict[str, Any], index: int, known_ids: set[str]) -> FreeformConnector:
    source_id = str(raw.get("from") or raw.get("source_id") or "").strip() or None
    target_id = str(raw.get("to") or raw.get("target_id") or "").strip() or None
    if source_id and source_id not in known_ids:
        raise FreeformValidationError(f"Connector {raw.get('id') or index} references unknown source id {source_id}")
    if target_id and target_id not in known_ids:
        raise FreeformValidationError(f"Connector {raw.get('id') or index} references unknown target id {target_id}")
    connector_type = str(raw.get("type") or "orthogonal").strip().lower()
    if connector_type not in KNOWN_CONNECTOR_TYPES:
        connector_type = "orthogonal"
    return FreeformConnector(
        id=_required_id(raw.get("id"), f"connector_{index + 1}"),
        source_id=source_id,
        target_id=target_id,
        label=str(raw.get("label") or "").strip(),
        type=connector_type,
        style=dict(raw.get("style") or {}),
        waypoints=list(raw.get("waypoints") or []),
    )


def _normalize_output_formats(values: List[str]) -> List[str]:
    formats = []
    for value in values:
        normalized = str(value or "").strip().lower()
        if normalized == "drawio.svg":
            normalized = "drawio_svg"
        if normalized in KNOWN_OUTPUT_FORMATS and normalized not in formats:
            formats.append(normalized)
    return formats or list(DEFAULT_OUTPUT_FORMATS)


def _normalize_intent(value: Optional[str]) -> str:
    normalized = str(value or "custom").strip().lower()
    return normalized if normalized in ALLOWED_INTENTS else "custom"


def _ensure_unique_ids(values: List[str], kind: str) -> set[str]:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise FreeformValidationError(f"Duplicate {kind} id: {value}")
        seen.add(value)
    return seen


def _required_id(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip()
    if not text:
        raise FreeformValidationError("id cannot be empty")
    return text


def _positive_int(value: Any, fallback: int, field_name: str) -> int:
    return int(_positive_number(value, fallback, field_name))


def _positive_number(value: Any, fallback: float, field_name: str) -> float:
    result = _number(value, fallback, field_name)
    if result <= 0:
        raise FreeformValidationError(f"{field_name} must be positive")
    return result


def _number(value: Any, fallback: float, field_name: str) -> float:
    if value is None:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise FreeformValidationError(f"{field_name} must be numeric") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_freeform_diagram_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/visualization/create_diagram_artifact/freeform_models.py backend/tests/test_freeform_diagram_models.py
git commit -m "feat: add freeform diagram source model"
```

## Task 2: Generate Draw.io XML

**Files:**
- Create: `backend/app/tools/visualization/create_diagram_artifact/drawio_writer.py`
- Test: `backend/tests/test_drawio_writer.py`

- [ ] **Step 1: Write failing tests for draw.io XML generation**

Create `backend/tests/test_drawio_writer.py`:

```python
import xml.etree.ElementTree as ET

from app.tools.visualization.create_diagram_artifact.drawio_writer import build_drawio_xml
from app.tools.visualization.create_diagram_artifact.freeform_models import normalize_freeform_diagram


def test_build_drawio_xml_contains_shapes_and_edges():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={"width": 1000, "height": 700},
        shapes=[
            {"id": "a", "type": "rounded_rect", "label": "A", "x": 10, "y": 20, "width": 120, "height": 60},
            {"id": "b", "type": "database", "label": "数据库", "x": 260, "y": 20, "width": 120, "height": 80},
        ],
        connectors=[{"id": "edge_a_b", "from": "a", "to": "b", "label": "写入"}],
        groups=[],
        output_formats=["drawio"],
        diagram_intent="architecture",
    )

    xml_text = build_drawio_xml(diagram)
    root = ET.fromstring(xml_text)

    cells = {cell.attrib.get("id"): cell for cell in root.findall(".//mxCell")}
    assert "a" in cells
    assert "b" in cells
    assert "edge_a_b" in cells
    assert cells["edge_a_b"].attrib["source"] == "a"
    assert cells["edge_a_b"].attrib["target"] == "b"
    assert "shape=cylinder" in cells["b"].attrib["style"]


def test_drawio_shape_passthrough_style_is_used():
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={},
        shapes=[
            {
                "id": "native",
                "type": "drawio_shape",
                "label": "原生",
                "x": 0,
                "y": 0,
                "drawio_shape_name": "process",
                "drawio_style": "whiteSpace=wrap;html=1;",
            }
        ],
        connectors=[],
        groups=[],
        output_formats=["drawio"],
        diagram_intent="custom",
    )

    xml_text = build_drawio_xml(diagram)
    assert "shape=process" in xml_text
    assert "whiteSpace=wrap;html=1;" in xml_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_drawio_writer.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `drawio_writer`.

- [ ] **Step 3: Implement draw.io writer**

Create `backend/app/tools/visualization/create_diagram_artifact/drawio_writer.py`:

```python
"""Draw.io XML writer for freeform diagrams."""
from __future__ import annotations

import html
import xml.etree.ElementTree as ET
from typing import Dict, Iterable

from .freeform_models import FreeformConnector, FreeformDiagram, FreeformGroup, FreeformShape


SHAPE_STYLE_ALIASES: Dict[str, str] = {
    "rect": "rounded=0;whiteSpace=wrap;html=1;",
    "rounded_rect": "rounded=1;whiteSpace=wrap;html=1;",
    "text": "text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;",
    "container": "rounded=0;whiteSpace=wrap;html=1;container=1;recursiveResize=0;",
    "swimlane": "swimlane;whiteSpace=wrap;html=1;",
    "database": "shape=cylinder3d;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=15;",
    "cylinder": "shape=cylinder3d;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=15;",
    "cloud": "ellipse;shape=cloud;whiteSpace=wrap;html=1;",
    "queue": "shape=internalStorage;whiteSpace=wrap;html=1;",
    "document": "shape=document;whiteSpace=wrap;html=1;boundedLbl=1;",
    "circle": "ellipse;whiteSpace=wrap;html=1;aspect=fixed;",
    "ellipse": "ellipse;whiteSpace=wrap;html=1;",
    "hexagon": "shape=hexagon;perimeter=hexagonPerimeter2;whiteSpace=wrap;html=1;",
    "diamond": "rhombus;whiteSpace=wrap;html=1;",
    "triangle": "triangle;whiteSpace=wrap;html=1;",
    "parallelogram": "shape=parallelogram;whiteSpace=wrap;html=1;",
    "actor": "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;",
    "note": "shape=note;whiteSpace=wrap;html=1;backgroundOutline=1;darkOpacity=0.05;",
    "callout": "shape=callout;whiteSpace=wrap;html=1;",
    "brace": "shape=curlyBracket;whiteSpace=wrap;html=1;",
    "bracket": "shape=partialRectangle;whiteSpace=wrap;html=1;",
    "line": "shape=line;html=1;strokeWidth=2;",
    "arrow": "shape=singleArrow;whiteSpace=wrap;html=1;",
    "image": "shape=image;verticalLabelPosition=bottom;verticalAlign=top;html=1;",
}


def build_drawio_xml(diagram: FreeformDiagram) -> str:
    mxfile = ET.Element("mxfile", {"host": "app.diagrams.net", "type": "device"})
    diagram_el = ET.SubElement(mxfile, "diagram", {"id": diagram.artifact_id, "name": diagram.title})
    graph = ET.SubElement(
        diagram_el,
        "mxGraphModel",
        {
            "dx": str(diagram.canvas.width),
            "dy": str(diagram.canvas.height),
            "grid": "1",
            "gridSize": str(diagram.canvas.grid),
            "guides": "1",
            "tooltips": "1",
            "connect": "1",
            "arrows": "1",
            "fold": "1",
            "page": "1",
            "pageScale": "1",
            "pageWidth": str(diagram.canvas.width),
            "pageHeight": str(diagram.canvas.height),
            "math": "0",
            "shadow": "0",
        },
    )
    root = ET.SubElement(graph, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

    for group in diagram.groups:
        root.append(_group_cell(group))
    for shape in diagram.shapes:
        root.append(_shape_cell(shape))
    for connector in diagram.connectors:
        root.append(_connector_cell(connector))

    return ET.tostring(mxfile, encoding="unicode", short_empty_elements=False)


def _group_cell(group: FreeformGroup) -> ET.Element:
    cell = ET.Element(
        "mxCell",
        {
            "id": group.id,
            "value": html.escape(group.label),
            "style": _style("rounded=0;whiteSpace=wrap;html=1;container=1;recursiveResize=0;", group.style),
            "vertex": "1",
            "parent": "1",
        },
    )
    _geometry(cell, group.x, group.y, group.width, group.height)
    return cell


def _shape_cell(shape: FreeformShape) -> ET.Element:
    parent = shape.parent_id or "1"
    base_style = _base_style_for_shape(shape)
    cell = ET.Element(
        "mxCell",
        {
            "id": shape.id,
            "value": html.escape(shape.label),
            "style": _style(base_style, shape.style),
            "vertex": "1",
            "parent": parent,
        },
    )
    _geometry(cell, shape.x, shape.y, shape.width, shape.height)
    return cell


def _connector_cell(connector: FreeformConnector) -> ET.Element:
    attrs = {
        "id": connector.id,
        "value": html.escape(connector.label),
        "style": _style(_connector_style(connector), connector.style),
        "edge": "1",
        "parent": "1",
    }
    if connector.source_id:
        attrs["source"] = connector.source_id
    if connector.target_id:
        attrs["target"] = connector.target_id
    cell = ET.Element("mxCell", attrs)
    geometry = ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
    if connector.waypoints:
        points = ET.SubElement(geometry, "Array", {"as": "points"})
        for point in connector.waypoints:
            ET.SubElement(points, "mxPoint", {"x": str(point.get("x", 0)), "y": str(point.get("y", 0))})
    return cell


def _base_style_for_shape(shape: FreeformShape) -> str:
    if shape.type == "drawio_shape":
        native_shape = _safe_style_token(shape.drawio_shape_name or "rect")
        return f"shape={native_shape};{shape.drawio_style}"
    return SHAPE_STYLE_ALIASES.get(shape.type, SHAPE_STYLE_ALIASES["rounded_rect"])


def _connector_style(connector: FreeformConnector) -> str:
    edge_style = {
        "straight": "edgeStyle=none;",
        "orthogonal": "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;",
        "curved": "edgeStyle=entityRelationEdgeStyle;rounded=1;",
    }.get(connector.type, "edgeStyle=orthogonalEdgeStyle;rounded=0;")
    return f"{edge_style}html=1;endArrow=block;endFill=1;"


def _geometry(parent: ET.Element, x: float, y: float, width: float, height: float) -> None:
    ET.SubElement(
        parent,
        "mxGeometry",
        {"x": str(x), "y": str(y), "width": str(width), "height": str(height), "as": "geometry"},
    )


def _style(base: str, style: Dict[str, object]) -> str:
    parts = [base.rstrip(";")]
    mapping = {
        "fill": "fillColor",
        "stroke": "strokeColor",
        "font_color": "fontColor",
        "font_size": "fontSize",
        "stroke_width": "strokeWidth",
        "dashed": "dashed",
        "opacity": "opacity",
        "align": "align",
        "vertical_align": "verticalAlign",
        "start_arrow": "startArrow",
        "end_arrow": "endArrow",
    }
    for key, drawio_key in mapping.items():
        if key not in style:
            continue
        value = style[key]
        if isinstance(value, bool):
            value = "1" if value else "0"
        parts.append(f"{drawio_key}={_safe_style_token(value)}")
    return ";".join(part for part in parts if part) + ";"


def _safe_style_token(value: object) -> str:
    text = str(value or "")
    return text.replace(";", "").replace("<", "").replace(">", "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_drawio_writer.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/visualization/create_diagram_artifact/drawio_writer.py backend/tests/test_drawio_writer.py
git commit -m "feat: generate drawio xml for freeform diagrams"
```

## Task 3: Export Draw.io Files and Fallback Preview

**Files:**
- Create: `backend/app/tools/visualization/create_diagram_artifact/freeform_exporter.py`
- Test: `backend/tests/test_freeform_diagram_exporter.py`

- [ ] **Step 1: Write failing tests for file export**

Create `backend/tests/test_freeform_diagram_exporter.py`:

```python
import json

from app.tools.visualization.create_diagram_artifact.freeform_exporter import export_freeform_diagram
from app.tools.visualization.create_diagram_artifact.freeform_models import normalize_freeform_diagram


def test_export_freeform_diagram_writes_drawio_source_and_preview(tmp_path):
    diagram = normalize_freeform_diagram(
        artifact_id="demo",
        title="Demo",
        canvas={"width": 800, "height": 500},
        shapes=[{"id": "a", "type": "rounded_rect", "label": "A", "x": 20, "y": 30}],
        connectors=[],
        groups=[],
        output_formats=["drawio", "png", "drawio_svg"],
        diagram_intent="custom",
    )

    result = export_freeform_diagram(diagram, tmp_path)

    assert result.drawio_path.exists()
    assert result.source_json_path.exists()
    assert result.preview_png_path.exists()
    assert result.preview_svg_path.exists()
    source = json.loads(result.source_json_path.read_text(encoding="utf-8"))
    assert source["diagram_mode"] == "freeform"
    assert source["shapes"][0]["id"] == "a"
    assert result.preview_png_path.stat().st_size > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_freeform_diagram_exporter.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `freeform_exporter`.

- [ ] **Step 3: Implement exporter with fallback SVG/PNG**

Create `backend/app/tools/visualization/create_diagram_artifact/freeform_exporter.py`:

```python
"""File exporter for freeform draw.io diagrams."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from .drawio_writer import build_drawio_xml
from .freeform_models import FreeformDiagram, FreeformShape


@dataclass(frozen=True)
class FreeformExportResult:
    drawio_path: Path
    source_json_path: Path
    preview_png_path: Path
    preview_svg_path: Optional[Path]
    warnings: List[str]


def export_freeform_diagram(diagram: FreeformDiagram, artifact_dir: Path) -> FreeformExportResult:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = artifact_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    drawio_path = assets_dir / "diagram.drawio"
    source_json_path = artifact_dir / "diagram.source.json"
    preview_png_path = assets_dir / "diagram.png"
    preview_svg_path = assets_dir / "diagram.drawio.svg"
    warnings: List[str] = []

    drawio_path.write_text(build_drawio_xml(diagram), encoding="utf-8")
    source_json_path.write_text(
        json.dumps(diagram.to_source_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    exported = _try_drawio_cli_export(drawio_path, preview_png_path, preview_svg_path, diagram.output_formats)
    if not exported:
        warnings.append("exporter_unavailable")
        _write_fallback_svg(diagram, preview_svg_path)
        _write_fallback_png(diagram, preview_png_path)

    return FreeformExportResult(
        drawio_path=drawio_path,
        source_json_path=source_json_path,
        preview_png_path=preview_png_path,
        preview_svg_path=preview_svg_path if preview_svg_path.exists() else None,
        warnings=warnings,
    )


def _try_drawio_cli_export(
    drawio_path: Path,
    png_path: Path,
    svg_path: Path,
    output_formats: List[str],
) -> bool:
    executable = shutil.which("drawio") or shutil.which("diagrams.net")
    if not executable:
        return False
    try:
        if "png" in output_formats:
            subprocess.run(
                [executable, "--export", "--format", "png", "--output", str(png_path), str(drawio_path)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
        if "drawio_svg" in output_formats or "svg" in output_formats:
            subprocess.run(
                [executable, "--export", "--format", "svg", "--output", str(svg_path), str(drawio_path)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
        return png_path.exists()
    except Exception:
        return False


def _write_fallback_svg(diagram: FreeformDiagram, output_path: Path) -> None:
    body = []
    for group in diagram.groups:
        body.append(
            f'<rect x="{group.x}" y="{group.y}" width="{group.width}" height="{group.height}" '
            f'fill="{group.style.get("fill", "#f7f8fb")}" stroke="{group.style.get("stroke", "#9aa9c3")}" '
            f'stroke-dasharray="6 4"/>'
        )
        if group.label:
            body.append(f'<text x="{group.x + 12}" y="{group.y + 24}" font-size="18">{_escape(group.label)}</text>')
    for shape in diagram.shapes:
        body.append(_shape_svg(shape))
    output_path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{diagram.canvas.width}" height="{diagram.canvas.height}" '
        f'viewBox="0 0 {diagram.canvas.width} {diagram.canvas.height}">{"".join(body)}</svg>',
        encoding="utf-8",
    )


def _shape_svg(shape: FreeformShape) -> str:
    fill = shape.style.get("fill", "#ffffff")
    stroke = shape.style.get("stroke", "#5f6368")
    label_y = shape.y + shape.height / 2 + 6
    if shape.type in {"circle", "ellipse"}:
        primitive = (
            f'<ellipse cx="{shape.x + shape.width / 2}" cy="{shape.y + shape.height / 2}" '
            f'rx="{shape.width / 2}" ry="{shape.height / 2}" fill="{fill}" stroke="{stroke}"/>'
        )
    else:
        rx = "10" if shape.type == "rounded_rect" else "0"
        primitive = f'<rect x="{shape.x}" y="{shape.y}" width="{shape.width}" height="{shape.height}" rx="{rx}" fill="{fill}" stroke="{stroke}"/>'
    return (
        primitive
        + f'<text x="{shape.x + shape.width / 2}" y="{label_y}" font-size="{shape.style.get("font_size", 16)}" '
        + f'text-anchor="middle">{_escape(shape.label)}</text>'
    )


def _write_fallback_png(diagram: FreeformDiagram, output_path: Path) -> None:
    image = Image.new("RGB", (diagram.canvas.width, diagram.canvas.height), diagram.canvas.background)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for group in diagram.groups:
        draw.rectangle(
            [group.x, group.y, group.x + group.width, group.y + group.height],
            outline=str(group.style.get("stroke", "#9aa9c3")),
            fill=str(group.style.get("fill", "#f7f8fb")),
        )
        if group.label:
            draw.text((group.x + 12, group.y + 10), group.label, fill="#111827", font=font)
    for shape in diagram.shapes:
        box = [shape.x, shape.y, shape.x + shape.width, shape.y + shape.height]
        draw.rectangle(box, outline=str(shape.style.get("stroke", "#5f6368")), fill=str(shape.style.get("fill", "#ffffff")))
        draw.text((shape.x + 8, shape.y + 8), shape.label, fill="#111827", font=font)
    image.save(output_path, format="PNG")


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_freeform_diagram_exporter.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/visualization/create_diagram_artifact/freeform_exporter.py backend/tests/test_freeform_diagram_exporter.py
git commit -m "feat: export freeform diagrams"
```

## Task 4: Integrate Freeform Mode Into `create_diagram_artifact`

**Files:**
- Modify: `backend/app/tools/visualization/create_diagram_artifact/tool.py`
- Test: `backend/tests/test_freeform_diagram_tool.py`

- [ ] **Step 1: Write failing integration tests**

Create `backend/tests/test_freeform_diagram_tool.py`:

```python
from pathlib import Path

import pytest

from app.tools.visualization.create_diagram_artifact.tool import CreateDiagramArtifactTool


@pytest.mark.asyncio
async def test_create_diagram_artifact_freeform_returns_editable_files():
    tool = CreateDiagramArtifactTool()

    result = await tool.execute(
        artifact_id="test_freeform_canvas",
        title="自由画布测试",
        diagram_mode="freeform",
        diagram_intent="process",
        canvas={"width": 900, "height": 500},
        shapes=[
            {"id": "start", "type": "rounded_rect", "label": "开始", "x": 80, "y": 100},
            {"id": "judge", "type": "diamond", "label": "判断", "x": 320, "y": 90, "width": 120, "height": 100},
        ],
        connectors=[{"id": "edge_start_judge", "from": "start", "to": "judge", "label": "进入"}],
        output_formats=["drawio", "png", "drawio_svg"],
    )

    assert result["success"] is True
    data = result["data"]
    assert Path(data["drawio_path"]).exists()
    assert Path(data["source_json_path"]).exists()
    assert Path(data["static_image_path"]).exists()
    assert data["metadata"]["diagram_mode"] == "freeform"
    formats = {artifact["format"] for artifact in data["artifacts"]}
    assert {"drawio", "png"}.issubset(formats)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_freeform_diagram_tool.py -q
```

Expected: FAIL because `diagram_mode` is ignored or unsupported.

- [ ] **Step 3: Extend tool schema**

Modify `CreateDiagramArtifactTool.__init__` in `backend/app/tools/visualization/create_diagram_artifact/tool.py`:

```python
# Add to parameters.properties
"diagram_mode": {
    "type": "string",
    "enum": ["template", "freeform"],
    "description": "template uses existing structured renderers; freeform uses universal draw.io canvas elements.",
},
"diagram_intent": {
    "type": "string",
    "enum": ["architecture", "process", "mind_map", "data_flow", "topology", "org_chart", "custom"],
},
"canvas": {
    "type": "object",
    "additionalProperties": True,
},
"shapes": {
    "type": "array",
    "items": {"type": "object", "additionalProperties": True},
},
"connectors": {
    "type": "array",
    "items": {"type": "object", "additionalProperties": True},
},
"groups": {
    "type": "array",
    "items": {"type": "object", "additionalProperties": True},
},
"output_formats": {
    "type": "array",
    "items": {"type": "string", "enum": ["drawio", "png", "drawio_svg", "svg", "html"]},
},
```

- [ ] **Step 4: Add imports and execute parameters**

At the top of `tool.py`, add:

```python
from app.tools.artifact_utils import build_document_artifact
from app.tools.resource_refs import build_artifact_ref, build_file_ref, build_visual_ref, merge_refs
from app.tools.visualization.create_diagram_artifact.freeform_exporter import export_freeform_diagram
from app.tools.visualization.create_diagram_artifact.freeform_models import (
    FreeformValidationError,
    normalize_freeform_diagram,
)
```

Extend `execute` signature:

```python
diagram_mode: str = "template",
diagram_intent: Optional[str] = None,
canvas: Optional[Dict[str, Any]] = None,
shapes: Optional[List[Dict[str, Any]]] = None,
connectors: Optional[List[Dict[str, Any]]] = None,
groups: Optional[List[Dict[str, Any]]] = None,
output_formats: Optional[List[str]] = None,
```

- [ ] **Step 5: Add a freeform branch before template rendering**

Inside `execute`, after required `artifact_id/title` validation and before normalizing `diagram_type`, add:

```python
if str(diagram_mode or "template").strip().lower() == "freeform":
    try:
        freeform_diagram = normalize_freeform_diagram(
            artifact_id=artifact_id,
            title=title,
            canvas=canvas,
            shapes=shapes,
            connectors=connectors,
            groups=groups,
            output_formats=output_formats,
            diagram_intent=diagram_intent,
        )
    except FreeformValidationError as exc:
        return {
            "status": "failed",
            "success": False,
            "data": None,
            "metadata": {
                "generator": self.name,
                "schema_version": "diagram_html.v3",
                "diagram_mode": "freeform",
            },
            "summary": f"自由画布图生成失败: {exc}",
        }

    preview_html = self._build_freeform_preview_html(title, freeform_diagram)
    data = html_artifact_service.create_artifact(
        artifact_id,
        preview_html,
        title=title,
        metadata={
            "artifact_kind": "diagram",
            "diagram_mode": "freeform",
            "diagram_intent": freeform_diagram.diagram_intent,
            "output_targets": freeform_diagram.output_formats,
            "generated_at": datetime.now().isoformat(),
            **(metadata or {}),
        },
    )
    export_result = export_freeform_diagram(freeform_diagram, Path(data["artifact_dir"]))
    drawio_relative = str(export_result.drawio_path.relative_to(Path(data["artifact_dir"])))
    drawio_url = f"/api/html-artifacts/{data.get('artifact_id')}/{drawio_relative}"
    png_relative = str(export_result.preview_png_path.relative_to(Path(data["artifact_dir"])))
    png_url = f"/api/html-artifacts/{data.get('artifact_id')}/{png_relative}"
    data.update(
        {
            "drawio_path": str(export_result.drawio_path),
            "drawio_url": drawio_url,
            "source_json_path": str(export_result.source_json_path),
            "static_image_path": str(export_result.preview_png_path),
            "static_image_url": png_url,
            "metadata": {
                "diagram_mode": "freeform",
                "diagram_intent": freeform_diagram.diagram_intent,
                "layout_warnings": export_result.warnings,
            },
        }
    )
    data["visuals"] = [
        build_visual_ref(
            id=f"{data.get('artifact_id')}_preview",
            type="image",
            title=title,
            image_url=png_url,
            local_path=str(export_result.preview_png_path),
            output_target="preview",
        )
    ]
    related_artifacts = [
        build_document_artifact(export_result.preview_png_path, kind="image", format="png", title=f"{title} 预览图", generator=self.name),
        build_document_artifact(
            export_result.drawio_path,
            kind="editable_diagram",
            format="drawio",
            title=f"{title} 可编辑源文件",
            generator=self.name,
            metadata={"download_url": drawio_url},
        ),
    ]
    if export_result.preview_svg_path:
        related_artifacts.append(
            build_document_artifact(export_result.preview_svg_path, kind="editable_diagram", format="drawio.svg", title=f"{title} 可编辑 SVG", generator=self.name)
        )
    data["artifact"] = related_artifacts[0]
    data["artifacts"] = related_artifacts
    data["related_files"] = related_artifacts
    data["refs"] = merge_refs(
        data.get("refs"),
        {
            "files": [
                build_file_ref(export_result.preview_png_path, type="image", format="png", usage="preview"),
                build_file_ref(
                    export_result.drawio_path,
                    type="document",
                    format="drawio",
                    usage="editable_source",
                    download_url=drawio_url,
                ),
            ],
            "artifacts": [build_artifact_ref(artifact) for artifact in related_artifacts],
            "visuals": data["visuals"],
        },
    )
    return {
        "status": "success",
        "success": True,
        "data": data,
        "refs": data.get("refs", {}),
        "visuals": data["visuals"],
        "html_preview": data.get("html_preview"),
        "file_path": data.get("file_path"),
        "file_type": data.get("file_type", "html_artifact"),
        "artifact": data.get("artifact"),
        "artifacts": data.get("artifacts", []),
        "metadata": {
            "generator": self.name,
            "schema_version": "diagram_html.v3",
            "diagram_mode": "freeform",
            "diagram_intent": freeform_diagram.diagram_intent,
            "static_image_path": str(export_result.preview_png_path),
            "drawio_path": str(export_result.drawio_path),
            "layout_warnings": export_result.warnings,
        },
        "summary": f"自由画布图已生成：{data['artifact_id']}。可下载 .drawio 并预览 PNG。",
    }
```

Also add this helper method to `CreateDiagramArtifactTool`:

```python
def _build_freeform_preview_html(self, title: str, diagram: Any) -> str:
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    body {{ margin: 0; font-family: {diagram_css_font_stack()}; background: #f7f8fb; color: #202124; }}
    .wrap {{ width: min(100%, {diagram.canvas.width}px); margin: 0 auto; padding: 16px; }}
    h1 {{ margin: 0 0 12px; font-size: 24px; }}
    img {{ display: block; width: 100%; height: auto; border: 1px solid #d6dbe3; background: #fff; }}
    .downloads {{ margin-top: 12px; display: flex; gap: 10px; flex-wrap: wrap; }}
    .downloads span {{ border: 1px solid #c9cdd3; padding: 6px 10px; background: #fff; }}
  </style>
</head>
<body>
  <main class="wrap">
    <h1>{safe_title}</h1>
    <img src="assets/diagram.png" alt="{safe_title}" />
    <div class="downloads"><span>assets/diagram.drawio</span><span>assets/diagram.png</span><span>assets/diagram.drawio.svg</span></div>
  </main>
</body>
</html>"""
```

- [ ] **Step 6: Run integration test**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_freeform_diagram_tool.py -q
```

Expected: PASS.

- [ ] **Step 7: Run existing diagram regressions**

Run:

```bash
conda run -n backend_py311 pytest backend/tests/test_create_diagram_artifact_semantics.py backend/tests/test_flowchart_artifact_tool.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/tools/visualization/create_diagram_artifact/tool.py backend/tests/test_freeform_diagram_tool.py
git commit -m "feat: add freeform mode to diagram artifact tool"
```

## Task 5: Support Presenting `.drawio` Artifacts

**Files:**
- Modify: `backend/app/tools/utility/present_artifact_tool.py`
- Test: `backend/app/tools/utility/present_artifact_tool_test.py`

- [ ] **Step 1: Add failing test for `.drawio`**

Append to `backend/app/tools/utility/present_artifact_tool_test.py`:

```python
import pytest

from app.tools.utility.present_artifact_tool import PresentArtifactTool


@pytest.mark.asyncio
async def test_present_drawio_file_as_downloadable_artifact(tmp_path):
    drawio_path = tmp_path / "diagram.drawio"
    drawio_path.write_text("<mxfile></mxfile>", encoding="utf-8")

    tool = PresentArtifactTool()
    tool.allowed_dirs.append(tmp_path.resolve())

    result = await tool.execute(str(drawio_path))

    assert result["success"] is True
    assert result["data"]["file_type"] == "editable_diagram"
    assert result["artifact"]["format"] == "drawio"
    assert result["artifact"]["preview_panel"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n backend_py311 pytest backend/app/tools/utility/present_artifact_tool_test.py -q
```

Expected: FAIL with unsupported file type `.drawio`.

- [ ] **Step 3: Add drawio extension handling**

Modify `backend/app/tools/utility/present_artifact_tool.py`:

```python
DRAWIO_EXTENSIONS = {".drawio"}
```

Update `_resolve_artifact_type` to return `editable_diagram`:

```python
if suffix in DRAWIO_EXTENSIONS:
    return "editable_diagram"
```

Inside `execute`, before unsupported preview handling:

```python
elif resolved_type == "editable_diagram":
    data["download_only"] = True
```

When building `artifact`, add preview panel false for drawio:

```python
if resolved_type == "editable_diagram":
    artifact["preview_panel"] = False
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n backend_py311 pytest backend/app/tools/utility/present_artifact_tool_test.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tools/utility/present_artifact_tool.py backend/app/tools/utility/present_artifact_tool_test.py
git commit -m "feat: allow drawio artifact presentation"
```

## Task 6: Frontend Related File Downloads

**Files:**
- Create: `frontend/src/utils/artifactRelatedFiles.js`
- Test: `frontend/src/utils/__tests__/artifactRelatedFiles.test.mjs`
- Modify: `frontend/src/components/VisualizationPanel.vue`

- [ ] **Step 1: Write failing related-files utility test**

Create `frontend/src/utils/__tests__/artifactRelatedFiles.test.mjs`:

```javascript
import assert from 'node:assert/strict'
import { normalizeRelatedArtifactFiles } from '../artifactRelatedFiles.js'

const artifact = {
  title: '自由画布测试',
  related_files: [
    { title: '自由画布测试 预览图', format: 'png', file_path: '/tmp/diagram.png' },
    { title: '自由画布测试 可编辑源文件', format: 'drawio', file_path: '/tmp/diagram.drawio' },
    { title: '自由画布测试 可编辑 SVG', format: 'drawio.svg', file_path: '/tmp/diagram.drawio.svg' }
  ]
}

const files = normalizeRelatedArtifactFiles({ artifact })

assert.equal(files.length, 3)
assert.deepEqual(files.map(file => file.format), ['png', 'drawio', 'drawio.svg'])
assert.equal(files[1].downloadLabel, '自由画布测试 可编辑源文件')

const refsOnly = normalizeRelatedArtifactFiles({
  refs: {
    artifacts: [
      { title: '源文件', format: 'drawio', file_path: '/tmp/source.drawio' }
    ]
  }
})

assert.equal(refsOnly.length, 1)
assert.equal(refsOnly[0].format, 'drawio')
```

- [ ] **Step 2: Run frontend test to verify failure**

Run:

```bash
cd frontend && node src/utils/__tests__/artifactRelatedFiles.test.mjs
```

Expected: FAIL because `artifactRelatedFiles.js` does not exist.

- [ ] **Step 3: Implement related-files utility**

Create `frontend/src/utils/artifactRelatedFiles.js`:

```javascript
export function normalizeRelatedArtifactFiles({ artifact = {}, refs = {} } = {}) {
  const direct = artifact.related_files || artifact.relatedFiles || artifact.artifacts || []
  const refArtifacts = refs.artifacts || []
  const merged = [...direct, ...refArtifacts]
  const seen = new Set()

  return merged
    .filter(Boolean)
    .map((file) => {
      const format = file.format || file.file_type || 'file'
      const path = file.file_path || file.path || ''
      const title = file.title || file.file_name || format
      return {
        ...file,
        format,
        file_path: path,
        downloadLabel: title,
        key: `${format}:${path}:${title}`
      }
    })
    .filter((file) => {
      if (seen.has(file.key)) return false
      seen.add(file.key)
      return true
    })
}
```

- [ ] **Step 4: Add related files rendering**

In `frontend/src/components/VisualizationPanel.vue`, add a computed helper near existing artifact computed values:

```javascript
import { normalizeRelatedArtifactFiles } from '../utils/artifactRelatedFiles'

const relatedFiles = computed(() => {
  const artifact = selectedArtifact.value || currentArtifact.value || {}
  return normalizeRelatedArtifactFiles({ artifact, refs: artifact.refs || {} })
})
```

Add template markup near the existing download/preview controls:

```vue
<div v-if="relatedFiles.length" class="related-files">
  <button
    v-for="file in relatedFiles"
    :key="file.file_path || file.file_name || file.title"
    type="button"
    class="related-file-button"
    @click="downloadArtifact(file)"
  >
    {{ file.downloadLabel }}
  </button>
</div>
```

Add scoped styles:

```css
.related-files {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.related-file-button {
  border: 1px solid #c9cdd3;
  background: #fff;
  color: #1f2937;
  padding: 6px 10px;
  border-radius: 4px;
  cursor: pointer;
}
```

- [ ] **Step 5: Run frontend test**

Run:

```bash
cd frontend && node src/utils/__tests__/artifactRelatedFiles.test.mjs
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/VisualizationPanel.vue frontend/src/utils/artifactRelatedFiles.js frontend/src/utils/__tests__/artifactRelatedFiles.test.mjs
git commit -m "feat: show related diagram downloads"
```

## Task 7: End-to-End Regression and Prompt Guidance

**Files:**
- Modify: `backend/app/agent/prompts/assistant_prompt.py`
- Modify: `backend/app/agent/prompts/tool_registry.py` if tool examples are listed there
- Test: existing prompt/tool registry tests

- [ ] **Step 1: Add prompt guidance**

In `backend/app/agent/prompts/assistant_prompt.py`, update the diagram guidance block to include:

```python
"- 当用户要求可编辑图、类似 Visio/draw.io、自由布局、复杂拓扑、思维导图或不希望受模板限制时，使用 `create_diagram_artifact` 的 `diagram_mode=\"freeform\"`。freeform 是通用 draw.io 画布，不限定架构图，可用 `canvas/shapes/connectors/groups` 自由组合，并输出 `.drawio` 主编辑源和 PNG/SVG 预览。\n",
"- 规范分层架构图、流程图、决策树仍可使用 `diagram_mode=\"template\"` 和对应模板；不要把 freeform 再强行压成 `layers/groups/items`。\n",
```

- [ ] **Step 2: Run prompt tests**

Run:

```bash
conda run -n backend_py311 pytest backend/app/agent/prompts/task_tool_registry_test.py backend/tests/test_assistant_ppt_tool_exposure.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full backend freeform test set**

Run:

```bash
conda run -n backend_py311 pytest \
  backend/tests/test_freeform_diagram_models.py \
  backend/tests/test_drawio_writer.py \
  backend/tests/test_freeform_diagram_exporter.py \
  backend/tests/test_freeform_diagram_tool.py \
  backend/app/tools/utility/present_artifact_tool_test.py \
  -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/prompts/assistant_prompt.py backend/app/agent/prompts/tool_registry.py
git commit -m "docs: guide agents to use freeform diagram canvas"
```

## Task 8: Manual Verification

**Files:**
- No code changes expected

- [ ] **Step 1: Run a direct smoke script**

Run:

```bash
cd backend && conda run -n backend_py311 python - <<'PY'
import asyncio
from pathlib import Path
from app.tools.visualization.create_diagram_artifact.tool import CreateDiagramArtifactTool

async def main():
    tool = CreateDiagramArtifactTool()
    result = await tool.execute(
        artifact_id="manual_freeform_smoke",
        title="通用自由画布冒烟测试",
        diagram_mode="freeform",
        diagram_intent="mind_map",
        canvas={"width": 1000, "height": 700},
        shapes=[
            {"id": "center", "type": "ellipse", "label": "中心主题", "x": 420, "y": 280, "width": 160, "height": 80},
            {"id": "branch_a", "type": "rounded_rect", "label": "分支 A", "x": 160, "y": 180},
            {"id": "branch_b", "type": "diamond", "label": "判断节点", "x": 680, "y": 180},
        ],
        connectors=[
            {"id": "edge_center_a", "from": "center", "to": "branch_a", "type": "curved"},
            {"id": "edge_center_b", "from": "center", "to": "branch_b", "type": "curved"},
        ],
        output_formats=["drawio", "png", "drawio_svg"],
    )
    print(result["success"])
    print(result["metadata"]["drawio_path"])
    print(result["metadata"]["static_image_path"])
    assert result["success"]
    assert Path(result["metadata"]["drawio_path"]).exists()
    assert Path(result["metadata"]["static_image_path"]).exists()

asyncio.run(main())
PY
```

Expected: prints `True` and existing `.drawio` / `.png` paths.

- [ ] **Step 2: Inspect generated files**

Run:

```bash
find backend/backend_data_registry/html_artifacts/manual_freeform_smoke -maxdepth 2 -type f
```

Expected files include:

```text
index.html
diagram.source.json
assets/diagram.drawio
assets/diagram.png
assets/diagram.drawio.svg
meta.json
```

- [ ] **Step 3: Final regression command**

Run:

```bash
conda run -n backend_py311 pytest \
  backend/tests/test_freeform_diagram_models.py \
  backend/tests/test_drawio_writer.py \
  backend/tests/test_freeform_diagram_exporter.py \
  backend/tests/test_freeform_diagram_tool.py \
  backend/app/tools/utility/present_artifact_tool_test.py \
  -q
```

Expected: PASS.

- [ ] **Step 4: Confirm no manual-fix diff remains**

Run:

```bash
git diff -- backend/app/tools/visualization/create_diagram_artifact backend/tests/test_freeform_diagram_models.py backend/tests/test_drawio_writer.py backend/tests/test_freeform_diagram_exporter.py backend/tests/test_freeform_diagram_tool.py
```

Expected: no output. If this command prints a diff, inspect the changed files, rerun the relevant tests above, then commit the specific fix with a message that names the failing behavior.

## Self-Review Notes

- Spec coverage: the plan covers universal freeform canvas, `.drawio` source, PNG/SVG preview, source JSON for future Agent edits, `.drawio` presentation, frontend related downloads, prompt guidance, and tests.
- Known tradeoff: first implementation includes a fallback renderer that is intentionally simple. It preserves preview availability but does not attempt full draw.io visual parity when the drawio CLI is unavailable.
- No `.vsdx` generation is planned; diagrams.net export remains the recommended path for Visio compatibility.
