from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


class FreeformValidationError(ValueError):
    """Raised when a freeform diagram source model is invalid."""


KNOWN_SHAPE_TYPES = {
    "rect",
    "rectangle",
    "rounded_rect",
    "stadium",
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

DEFAULT_OUTPUT_FORMATS = ["drawio", "png"]
MAX_CANVAS_WIDTH = 10000
MAX_CANVAS_HEIGHT = 10000
MAX_CANVAS_PIXELS = 25_000_000
MAX_SHAPES = 500
MAX_CONNECTORS = 1000
MAX_GROUPS = 200

SHAPE_TYPE_ALIASES = {
    "box": "rectangle",
    "rounded": "rounded_rect",
    "rounded_rectangle": "rounded_rect",
    "rounded_rect": "rounded_rect",
    "roundrect": "rounded_rect",
    "round_rect": "rounded_rect",
    "data_store": "database",
    "datastore": "database",
    "db": "database",
    "text_box": "text",
    "textbox": "text",
    "terminator": "stadium",
}


@dataclass(frozen=True)
class FreeformCanvas:
    width: float = 1000
    height: float = 700
    grid: float | None = None
    background: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_source_dict(self) -> dict[str, Any]:
        source = {
            "width": self.width,
            "height": self.height,
            **self.extras,
        }
        if self.grid is not None:
            source["grid"] = self.grid
        if self.background is not None:
            source["background"] = self.background
        return _json_safe(source)


@dataclass(frozen=True)
class FreeformShape:
    id: str
    type: str = "rounded_rect"
    label: str = ""
    x: float = 0
    y: float = 0
    width: float = 120
    height: float = 60
    drawio_shape_name: str | None = None
    drawio_style: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_source_dict(self) -> dict[str, Any]:
        source = {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            **self.extras,
        }
        if self.drawio_shape_name is not None:
            source["drawio_shape_name"] = self.drawio_shape_name
        if self.drawio_style is not None:
            source["drawio_style"] = self.drawio_style
        return _json_safe(source)


@dataclass(frozen=True)
class FreeformConnector:
    id: str
    source_id: str
    target_id: str
    label: str = ""
    type: str = "orthogonal"
    extras: dict[str, Any] = field(default_factory=dict)

    def to_source_dict(self) -> dict[str, Any]:
        return _json_safe(
            {
                "id": self.id,
                "from": self.source_id,
                "to": self.target_id,
                "label": self.label,
                "type": self.type,
                **self.extras,
            }
        )


@dataclass(frozen=True)
class FreeformGroup:
    id: str
    label: str = ""
    children: list[str] = field(default_factory=list)
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_source_dict(self) -> dict[str, Any]:
        source = {
            "id": self.id,
            "label": self.label,
            "children": list(self.children),
            **self.extras,
        }
        for key in ("x", "y", "width", "height"):
            value = getattr(self, key)
            if value is not None:
                source[key] = value
        return _json_safe(source)


@dataclass(frozen=True)
class FreeformDiagram:
    artifact_id: str
    title: str
    canvas: FreeformCanvas
    shapes: list[FreeformShape]
    connectors: list[FreeformConnector]
    groups: list[FreeformGroup]
    output_formats: list[str]
    diagram_intent: str | None = None

    def to_source_dict(self) -> dict[str, Any]:
        return _json_safe(
            {
                "diagram_mode": "freeform",
                "artifact_id": self.artifact_id,
                "title": self.title,
                "canvas": self.canvas.to_source_dict(),
                "shapes": [shape.to_source_dict() for shape in self.shapes],
                "connectors": [connector.to_source_dict() for connector in self.connectors],
                "groups": [group.to_source_dict() for group in self.groups],
                "output_formats": list(self.output_formats),
                "diagram_intent": self.diagram_intent,
            }
        )


def normalize_freeform_diagram(
    *,
    artifact_id: str,
    title: str,
    canvas: dict[str, Any] | None,
    shapes: list[dict[str, Any]] | None,
    connectors: list[dict[str, Any]] | None,
    groups: list[dict[str, Any]] | None,
    output_formats: list[str] | None,
    diagram_intent: str | None,
) -> FreeformDiagram:
    normalized_canvas = _normalize_canvas(_optional_mapping(canvas, "canvas"))
    shape_sources = _optional_object_list(shapes, "shapes")
    connector_sources = _optional_object_list(connectors, "connectors")
    group_sources = _optional_object_list(groups, "groups")
    _validate_collection_size(shape_sources, MAX_SHAPES, "shapes")
    _validate_collection_size(connector_sources, MAX_CONNECTORS, "connectors")
    _validate_collection_size(group_sources, MAX_GROUPS, "groups")
    normalized_shapes = [
        _normalize_shape(_require_mapping(shape, "shape")) for shape in shape_sources
    ]
    if not normalized_shapes:
        raise FreeformValidationError("freeform diagram requires at least one shape")

    normalized_groups = [_normalize_group(_require_mapping(group, "group")) for group in group_sources]

    known_endpoint_ids = {shape.id for shape in normalized_shapes}
    known_endpoint_ids.update(group.id for group in normalized_groups)
    _validate_group_children(normalized_groups, known_endpoint_ids)
    normalized_connectors = [
        _normalize_connector(_require_mapping(connector, "connector"), known_endpoint_ids)
        for connector in connector_sources
    ]
    _validate_unique_ids(normalized_shapes, normalized_groups, normalized_connectors)

    return FreeformDiagram(
        artifact_id=str(artifact_id),
        title=str(title),
        canvas=normalized_canvas,
        shapes=normalized_shapes,
        connectors=normalized_connectors,
        groups=normalized_groups,
        output_formats=_normalize_output_formats(output_formats),
        diagram_intent=diagram_intent,
    )


def _normalize_canvas(source: dict[str, Any]) -> FreeformCanvas:
    known = {"width", "height", "grid", "background"}
    width = _bounded_positive_number(
        source.get("width", 1000), "canvas.width", MAX_CANVAS_WIDTH
    )
    height = _bounded_positive_number(
        source.get("height", 700), "canvas.height", MAX_CANVAS_HEIGHT
    )
    if width * height > MAX_CANVAS_PIXELS:
        raise FreeformValidationError(
            f"canvas area must be <= {MAX_CANVAS_PIXELS} pixels"
        )
    return FreeformCanvas(
        width=width,
        height=height,
        grid=_optional_positive_number(source.get("grid"), "canvas.grid"),
        background=_optional_str(source.get("background")),
        extras=_extras(source, known),
    )


def _normalize_shape(source: dict[str, Any]) -> FreeformShape:
    known = {
        "id",
        "type",
        "label",
        "text",
        "name",
        "title",
        "x",
        "y",
        "width",
        "height",
        "drawio_shape_name",
        "drawio_style",
    }
    shape_type = _normalize_shape_type(source.get("type") or "rounded_rect")
    if shape_type not in KNOWN_SHAPE_TYPES:
        shape_type = "rounded_rect"

    return FreeformShape(
        id=_required_str(source, "id", "shape"),
        type=shape_type,
        label=_first_text(source, ("label", "text", "name", "title")),
        x=_number(source.get("x", 0), "shape.x"),
        y=_number(source.get("y", 0), "shape.y"),
        width=_positive_number(source.get("width", 120), "shape.width"),
        height=_positive_number(source.get("height", 60), "shape.height"),
        drawio_shape_name=_optional_str(source.get("drawio_shape_name")),
        drawio_style=_optional_str(source.get("drawio_style")),
        extras=_extras(source, known),
    )


def _normalize_connector(
    source: dict[str, Any], known_endpoint_ids: set[str]
) -> FreeformConnector:
    known = {
        "id",
        "from",
        "to",
        "source",
        "target",
        "source_id",
        "target_id",
        "label",
        "text",
        "type",
        "style",
    }
    connector = FreeformConnector(
        id=_required_str(source, "id", "connector"),
        source_id=_first_required_str(
            source, ("from", "source", "source_id"), "connector source"
        ),
        target_id=_first_required_str(
            source, ("to", "target", "target_id"), "connector target"
        ),
        label=_first_text(source, ("label", "text")),
        type=str(source.get("type") or source.get("style") or "orthogonal"),
        extras=_extras(source, known),
    )

    if connector.source_id not in known_endpoint_ids:
        raise FreeformValidationError(
            f"Connector {connector.id} references unknown source id {connector.source_id}"
        )
    if connector.target_id not in known_endpoint_ids:
        raise FreeformValidationError(
            f"Connector {connector.id} references unknown target id {connector.target_id}"
        )
    return connector


def _normalize_group(source: dict[str, Any]) -> FreeformGroup:
    known = {"id", "label", "children", "x", "y", "width", "height"}
    children = source.get("children", [])
    if children is None:
        children = []
    if not isinstance(children, list):
        raise FreeformValidationError("group.children must be a list")

    return FreeformGroup(
        id=_required_str(source, "id", "group"),
        label=str(source.get("label", "")),
        children=[str(child) for child in children],
        x=_optional_number(source.get("x"), "group.x"),
        y=_optional_number(source.get("y"), "group.y"),
        width=_optional_positive_number(source.get("width"), "group.width"),
        height=_optional_positive_number(source.get("height"), "group.height"),
        extras=_extras(source, known),
    )


def _validate_unique_ids(
    shapes: list[FreeformShape],
    groups: list[FreeformGroup],
    connectors: list[FreeformConnector],
) -> None:
    seen: set[str] = set()
    for shape in shapes:
        if shape.id in seen:
            raise FreeformValidationError(f"Duplicate shape id {shape.id}")
        seen.add(shape.id)

    for group in groups:
        if group.id in seen:
            raise FreeformValidationError(f"Duplicate group id {group.id}")
        seen.add(group.id)

    for connector in connectors:
        if connector.id in seen:
            raise FreeformValidationError(f"Duplicate connector id {connector.id}")
        seen.add(connector.id)


def _validate_group_children(groups: list[FreeformGroup], known_ids: set[str]) -> None:
    for group in groups:
        for child_id in group.children:
            if child_id not in known_ids:
                raise FreeformValidationError(
                    f"Group {group.id} references unknown child id {child_id}"
                )


def _normalize_output_formats(output_formats: list[str] | None) -> list[str]:
    if not output_formats:
        return list(DEFAULT_OUTPUT_FORMATS)

    normalized: list[str] = []
    seen: set[str] = set()
    for output_format in output_formats:
        value = str(output_format).strip().lower().strip("._").replace(".", "_")
        if value in {"svg", "_svg", "drawio_svg"}:
            value = "drawio_svg"
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized or list(DEFAULT_OUTPUT_FORMATS)


def _validate_collection_size(source: list[Any], maximum: int, context: str) -> None:
    if len(source) > maximum:
        raise FreeformValidationError(f"{context} must contain <= {maximum} items")


def _normalize_shape_type(value: Any) -> str:
    normalized = (
        str(value)
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
        .replace(".", "_")
    )
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    normalized = normalized.strip("_")
    return SHAPE_TYPE_ALIASES.get(normalized, normalized)


def _optional_mapping(source: Any, context: str) -> dict[str, Any]:
    if source is None:
        return {}
    return _require_mapping(source, context)


def _optional_object_list(source: Any, context: str) -> list[Any]:
    if source is None:
        return []
    if not isinstance(source, list):
        raise FreeformValidationError(f"{context} must be a list")
    return source


def _require_mapping(source: Any, context: str) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        raise FreeformValidationError(f"{context} must be an object")
    return dict(source)


def _required_str(source: dict[str, Any], key: str, context: str) -> str:
    value = source.get(key)
    if value is None or str(value) == "":
        raise FreeformValidationError(f"Missing {context} {key}")
    return str(value)


def _first_required_str(
    source: dict[str, Any], keys: tuple[str, ...], context: str
) -> str:
    for key in keys:
        value = source.get(key)
        if value is not None and str(value) != "":
            return str(value)
    raise FreeformValidationError(f"Missing {context}")


def _first_text(source: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = source.get(key)
        if value is not None:
            return str(value)
    return ""


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _number(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FreeformValidationError(f"{field_name} must be a number") from exc
    if not math.isfinite(number):
        raise FreeformValidationError(f"{field_name} must be finite")
    return number


def _optional_number(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    return _number(value, field_name)


def _positive_number(value: Any, field_name: str) -> float:
    number = _number(value, field_name)
    if number <= 0:
        raise FreeformValidationError(f"{field_name} must be positive")
    return number


def _bounded_positive_number(value: Any, field_name: str, maximum: float) -> float:
    number = _positive_number(value, field_name)
    if number > maximum:
        raise FreeformValidationError(f"{field_name} must be <= {maximum:g}")
    return number


def _optional_positive_number(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    return _positive_number(value, field_name)


def _extras(source: dict[str, Any], known_keys: set[str]) -> dict[str, Any]:
    return _json_safe({key: value for key, value in source.items() if key not in known_keys})


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise FreeformValidationError("Freeform source model must be JSON-serializable") from exc


__all__ = [
    "FreeformValidationError",
    "FreeformCanvas",
    "FreeformShape",
    "FreeformConnector",
    "FreeformGroup",
    "FreeformDiagram",
    "normalize_freeform_diagram",
]
