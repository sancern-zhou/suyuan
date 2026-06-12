from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any

from .freeform_models import (
    FreeformCanvas,
    FreeformConnector,
    FreeformDiagram,
    FreeformGroup,
    FreeformShape,
)
from .rich_text import DEFAULT_DIAGRAM_DRAWIO_FONT_FAMILY


DEFAULT_STYLE_PACK = "business_clean"
DEFAULT_GRID_SIZE = 10
CANVAS_MARGIN = 40
OVERLAP_RATIO_THRESHOLD = 0.28
HIGH_FAN_IN_THRESHOLD = 4
LONG_LABEL_LENGTH = 16
MAX_AUTO_LABEL_WIDTH = 320.0
MAX_LABEL_WIDTH_GROWTH_FACTOR = 2.6
A4_FONT_SCALE = 1.5
GROUP_FONT_SCALE_BASE = 21.0
SHAPE_FONT_SCALE_BASE = 18.0
CONNECTOR_FONT_SCALE_BASE = 15.0
GROUP_CHILD_SPACING = DEFAULT_GRID_SIZE * 2
GROUP_CHILD_PADDING = DEFAULT_GRID_SIZE * 4


@dataclass(frozen=True)
class PostprocessOptions:
    enabled: bool = True
    snap_to_grid: bool = True
    expand_canvas: bool = True
    apply_style_pack: bool = True
    center_group_children: bool = False
    fit_shape_labels: bool = True
    scale_font_sizes: bool = True
    warn_only: bool = False


@dataclass(frozen=True)
class PostprocessResult:
    diagram: FreeformDiagram
    quality_warnings: list[str]
    actions: list[dict[str, Any]]
    style_pack: str | None


STYLE_PACKS: dict[str, dict[str, dict[str, str]]] = {
    "business_clean": {
        "group": {
            "fillColor": "#EEF6FF",
            "strokeColor": "#2F6F9F",
            "strokeWidth": "2",
            "fontColor": "#123047",
            "fontSize": "21",
            "fontFamily": DEFAULT_DIAGRAM_DRAWIO_FONT_FAMILY,
        },
        "shape": {
            "fillColor": "#FFFFFF",
            "strokeColor": "#2F6F9F",
            "strokeWidth": "2",
            "fontColor": "#1F2937",
            "fontSize": "18",
            "fontFamily": DEFAULT_DIAGRAM_DRAWIO_FONT_FAMILY,
        },
        "connector": {
            "strokeColor": "#5B6B82",
            "strokeWidth": "2",
            "endArrow": "block",
            "fontSize": "15",
            "fontFamily": DEFAULT_DIAGRAM_DRAWIO_FONT_FAMILY,
        },
    },
}


def postprocess_freeform_diagram(
    diagram: FreeformDiagram,
    *,
    style_pack: str | None = None,
    options: PostprocessOptions | dict[str, Any] | None = None,
) -> PostprocessResult:
    normalized_options = _normalise_options(options)
    normalized_style_pack = _normalise_style_pack(style_pack)
    warnings: list[str] = []
    actions: list[dict[str, Any]] = []

    if not normalized_options.enabled:
        return PostprocessResult(
            diagram=diagram,
            quality_warnings=_quality_warnings(diagram),
            actions=[],
            style_pack=None,
        )

    next_diagram = diagram
    if normalized_options.snap_to_grid and not normalized_options.warn_only:
        next_diagram, changed = _snap_diagram_to_grid(next_diagram)
        if changed:
            actions.append({"action": "snap_to_grid", "grid": DEFAULT_GRID_SIZE})

    if normalized_style_pack and normalized_options.apply_style_pack and not normalized_options.warn_only:
        next_diagram, changed = _apply_style_pack(next_diagram, normalized_style_pack)
        if changed:
            actions.append({"action": "apply_style_pack", "style_pack": normalized_style_pack})
            warnings.append("style_pack_applied")

    if normalized_options.scale_font_sizes and not normalized_options.warn_only:
        next_diagram, changed = _scale_font_sizes_for_a4(next_diagram)
        if changed:
            actions.append({"action": "scale_font_sizes", "scale": A4_FONT_SCALE})

    if normalized_options.fit_shape_labels and not normalized_options.warn_only:
        next_diagram, changed = _fit_shape_labels(next_diagram)
        if changed:
            actions.append({"action": "fit_shape_labels"})

    if normalized_options.center_group_children and not normalized_options.warn_only:
        next_diagram, changed = _center_group_children(next_diagram)
        if changed:
            actions.append({"action": "center_group_children"})

    if not normalized_options.warn_only:
        next_diagram, changed = _layout_group_children(next_diagram)
        if changed:
            actions.append({"action": "layout_group_children"})

    if normalized_options.expand_canvas and not normalized_options.warn_only:
        next_diagram, changed = _expand_canvas(next_diagram)
        if changed:
            actions.append({
                "action": "expand_canvas",
                "width": next_diagram.canvas.width,
                "height": next_diagram.canvas.height,
            })
            warnings.append("canvas_expanded")

    warnings.extend(_quality_warnings(next_diagram))
    return PostprocessResult(
        diagram=next_diagram,
        quality_warnings=_dedupe(warnings),
        actions=actions,
        style_pack=normalized_style_pack,
    )


def _normalise_options(options: PostprocessOptions | dict[str, Any] | None) -> PostprocessOptions:
    if options is None:
        return PostprocessOptions()
    if isinstance(options, PostprocessOptions):
        return options
    return PostprocessOptions(
        enabled=_bool_option(options, "enabled", True),
        snap_to_grid=_bool_option(options, "snap_to_grid", True),
        expand_canvas=_bool_option(options, "expand_canvas", True),
        apply_style_pack=_bool_option(options, "apply_style_pack", True),
        center_group_children=_bool_option(options, "center_group_children", False),
        fit_shape_labels=_bool_option(options, "fit_shape_labels", True),
        scale_font_sizes=_bool_option(options, "scale_font_sizes", True),
        warn_only=_bool_option(options, "warn_only", False),
    )


def _normalise_style_pack(style_pack: str | None) -> str | None:
    return DEFAULT_STYLE_PACK


def _bool_option(options: dict[str, Any], key: str, default: bool) -> bool:
    value = options.get(key, default)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _snap_diagram_to_grid(diagram: FreeformDiagram) -> tuple[FreeformDiagram, bool]:
    changed = False

    def snap(value: float) -> float:
        return round(value / DEFAULT_GRID_SIZE) * DEFAULT_GRID_SIZE

    shapes: list[FreeformShape] = []
    for shape in diagram.shapes:
        snapped = replace(
            shape,
            x=snap(shape.x),
            y=snap(shape.y),
            width=max(DEFAULT_GRID_SIZE, snap(shape.width)),
            height=max(DEFAULT_GRID_SIZE, snap(shape.height)),
        )
        changed = changed or snapped != shape
        shapes.append(snapped)

    groups: list[FreeformGroup] = []
    for group in diagram.groups:
        updates: dict[str, float] = {}
        for key in ("x", "y", "width", "height"):
            value = getattr(group, key)
            if value is not None:
                updates[key] = max(DEFAULT_GRID_SIZE, snap(value)) if key in {"width", "height"} else snap(value)
        snapped_group = replace(group, **updates)
        changed = changed or snapped_group != group
        groups.append(snapped_group)

    if not changed:
        return diagram, False
    return replace(diagram, shapes=shapes, groups=groups), True


def _apply_style_pack(diagram: FreeformDiagram, style_pack: str) -> tuple[FreeformDiagram, bool]:
    pack = STYLE_PACKS[style_pack]
    changed = False

    groups = []
    for group in diagram.groups:
        extras, extras_changed = _merge_defaults(group.extras, pack["group"])
        changed = changed or extras_changed
        groups.append(replace(group, extras=extras) if extras_changed else group)

    shapes = []
    for shape in diagram.shapes:
        defaults = pack["shape"]
        if shape.type in {"container", "swimlane"}:
            defaults = pack["group"]
        extras, extras_changed = _merge_defaults(shape.extras, defaults)
        changed = changed or extras_changed
        shapes.append(replace(shape, extras=extras) if extras_changed else shape)

    connectors = []
    for connector in diagram.connectors:
        extras, extras_changed = _merge_defaults(connector.extras, pack["connector"])
        changed = changed or extras_changed
        connectors.append(replace(connector, extras=extras) if extras_changed else connector)

    if not changed:
        return diagram, False
    return replace(diagram, groups=groups, shapes=shapes, connectors=connectors), True


def _scale_font_sizes_for_a4(diagram: FreeformDiagram) -> tuple[FreeformDiagram, bool]:
    changed = False

    groups: list[FreeformGroup] = []
    for group in diagram.groups:
        extras, extras_changed = _scale_font_size_extras(group.extras, GROUP_FONT_SCALE_BASE)
        changed = changed or extras_changed
        groups.append(replace(group, extras=extras) if extras_changed else group)

    shapes: list[FreeformShape] = []
    for shape in diagram.shapes:
        base = GROUP_FONT_SCALE_BASE if shape.type in {"container", "swimlane"} else SHAPE_FONT_SCALE_BASE
        extras, extras_changed = _scale_font_size_extras(shape.extras, base)
        changed = changed or extras_changed
        shapes.append(replace(shape, extras=extras) if extras_changed else shape)

    connectors: list[FreeformConnector] = []
    for connector in diagram.connectors:
        extras, extras_changed = _scale_font_size_extras(connector.extras, CONNECTOR_FONT_SCALE_BASE)
        changed = changed or extras_changed
        connectors.append(replace(connector, extras=extras) if extras_changed else connector)

    if not changed:
        return diagram, False
    return replace(diagram, groups=groups, shapes=shapes, connectors=connectors), True


def _center_group_children(diagram: FreeformDiagram) -> tuple[FreeformDiagram, bool]:
    if not diagram.groups or not diagram.shapes:
        return diagram, False

    shape_by_id = {shape.id: shape for shape in diagram.shapes}
    inferred_children_by_group = _infer_children_by_group(diagram)
    updates_by_id: dict[str, FreeformShape] = {}

    for group in diagram.groups:
        if group.x is None or group.width is None:
            continue
        if group.children:
            children = [
                shape_by_id[child_id]
                for child_id in group.children
                if child_id in shape_by_id and _can_center_group_child(shape_by_id[child_id])
            ]
        else:
            children = inferred_children_by_group.get(group.id, [])
        if len(children) < 2:
            continue
        for row in _group_shapes_by_row(children):
            if len(row) < 2:
                continue
            row = sorted(row, key=lambda shape: shape.x)
            total_width = sum(shape.width for shape in row)
            spacing = DEFAULT_GRID_SIZE * 2
            total_width += spacing * (len(row) - 1)
            start_x = group.x + max(0.0, (group.width - total_width) / 2)
            current_x = start_x
            for shape in row:
                centered_shape = replace(shape, x=_snap_value(current_x))
                updates_by_id[shape.id] = centered_shape
                current_x += shape.width + spacing

    if not updates_by_id:
        return diagram, False

    shapes = [updates_by_id.get(shape.id, shape) for shape in diagram.shapes]
    changed = any(next_shape != shape for shape, next_shape in zip(diagram.shapes, shapes))
    if not changed:
        return diagram, False
    return replace(diagram, shapes=shapes), True


def _layout_group_children(diagram: FreeformDiagram) -> tuple[FreeformDiagram, bool]:
    if not diagram.shapes:
        return diagram, False

    shape_by_id = {shape.id: shape for shape in diagram.shapes}
    inferred_children_by_group = _infer_children_by_group(diagram)
    updates_by_id: dict[str, FreeformShape] = {}
    updates_by_group_id: dict[str, FreeformGroup] = {}

    for group in diagram.groups:
        if group.x is None or group.y is None or group.width is None or group.height is None:
            continue
        children = _group_layout_children(group, shape_by_id, inferred_children_by_group)
        if len(children) < 1:
            continue

        target_width, target_height, child_updates = _layout_children_in_region(
            x=group.x,
            y=group.y,
            width=group.width,
            height=group.height,
            children=children,
        )
        next_group = replace(group, width=target_width, height=target_height)
        if next_group != group:
            updates_by_group_id[group.id] = next_group
        updates_by_id.update(child_updates)

    shapes_after_group_layout = [updates_by_id.get(shape.id, shape) for shape in diagram.shapes]
    shape_by_id_after_groups = {shape.id: shape for shape in shapes_after_group_layout}
    inferred_children_by_container = _infer_children_by_container_shape(shapes_after_group_layout)
    for container in shapes_after_group_layout:
        if container.type not in {"container", "swimlane"} or _is_hidden(container.extras):
            continue
        children = _container_shape_layout_children(
            container,
            shape_by_id_after_groups,
            inferred_children_by_container,
        )
        if len(children) < 1:
            continue
        target_width, target_height, child_updates = _layout_children_in_region(
            x=container.x,
            y=container.y,
            width=container.width,
            height=container.height,
            children=children,
        )
        next_container = replace(container, width=target_width, height=target_height)
        if next_container != container:
            updates_by_id[container.id] = next_container
        updates_by_id.update(child_updates)

    if not updates_by_id and not updates_by_group_id:
        return diagram, False

    shapes = [updates_by_id.get(shape.id, shape) for shape in diagram.shapes]
    groups = [updates_by_group_id.get(group.id, group) for group in diagram.groups]
    changed = shapes != diagram.shapes or groups != diagram.groups
    if not changed:
        return diagram, False
    return replace(diagram, shapes=shapes, groups=groups), True


def _layout_children_in_region(
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    children: list[FreeformShape],
) -> tuple[float, float, dict[str, FreeformShape]]:
    rows = _group_shapes_by_row(children)
    if not rows:
        return width, height, {}

    row_widths = [_row_width(row, GROUP_CHILD_SPACING) for row in rows]
    row_heights = [max(shape.height for shape in row) for row in rows]
    content_width = max(row_widths, default=0.0)
    content_height = sum(row_heights) + GROUP_CHILD_SPACING * max(0, len(rows) - 1)
    target_width = max(width, _ceil_to_grid(content_width + GROUP_CHILD_PADDING * 2))
    target_height = max(height, _ceil_to_grid(content_height + GROUP_CHILD_PADDING * 2))
    updates_by_id: dict[str, FreeformShape] = {}

    start_y = y + max(0.0, (target_height - content_height) / 2)
    current_y = start_y
    for row, row_width, row_height in zip(rows, row_widths, row_heights):
        sorted_row = sorted(row, key=lambda shape: shape.x)
        recenter_x = (
            _row_has_overlap(sorted_row, GROUP_CHILD_SPACING)
            or _row_overflows_bounds(sorted_row, x, target_width)
            or target_width != width
        )
        current_x = x + max(0.0, (target_width - row_width) / 2)
        previous_right: float | None = None
        for shape in sorted_row:
            if recenter_x:
                target_x = _snap_value(current_x)
                if previous_right is not None and target_x < previous_right + GROUP_CHILD_SPACING:
                    target_x = _ceil_to_grid(previous_right + GROUP_CHILD_SPACING)
            else:
                target_x = shape.x
            target_y = current_y + max(0.0, (row_height - shape.height) / 2)
            next_shape = replace(shape, x=target_x, y=target_y)
            if next_shape != shape:
                updates_by_id[shape.id] = next_shape
            previous_right = target_x + shape.width
            current_x = previous_right + GROUP_CHILD_SPACING
        current_y += row_height + GROUP_CHILD_SPACING
    return target_width, target_height, updates_by_id


def _group_layout_children(
    group: FreeformGroup,
    shape_by_id: dict[str, FreeformShape],
    inferred_children_by_group: dict[str, list[FreeformShape]],
) -> list[FreeformShape]:
    if group.children:
        return [
            shape_by_id[child_id]
            for child_id in group.children
            if child_id in shape_by_id and _can_center_group_child(shape_by_id[child_id])
        ]
    return inferred_children_by_group.get(group.id, [])


def _container_shape_layout_children(
    container: FreeformShape,
    shape_by_id: dict[str, FreeformShape],
    inferred_children_by_container: dict[str, list[FreeformShape]],
) -> list[FreeformShape]:
    child_ids = container.extras.get("children")
    if isinstance(child_ids, list):
        return [
            shape_by_id[child_id]
            for child_id in child_ids
            if child_id in shape_by_id and _can_center_group_child(shape_by_id[child_id])
        ]
    return inferred_children_by_container.get(container.id, [])


def _infer_children_by_container_shape(shapes: list[FreeformShape]) -> dict[str, list[FreeformShape]]:
    containers = [
        shape
        for shape in shapes
        if shape.type in {"container", "swimlane"} and not _is_hidden(shape.extras)
    ]
    if not containers:
        return {}

    explicit_child_ids = {
        child_id
        for container in containers
        if isinstance(container.extras.get("children"), list)
        for child_id in container.extras["children"]
    }
    inferred: dict[str, list[FreeformShape]] = {container.id: [] for container in containers}
    for shape in shapes:
        if shape.id in explicit_child_ids or not _can_center_group_child(shape):
            continue
        containing = [container for container in containers if _shape_center_inside_container_shape(shape, container)]
        if not containing:
            continue
        smallest = min(containing, key=lambda container: container.width * container.height)
        inferred[smallest.id].append(shape)
    return inferred


def _shape_center_inside_container_shape(shape: FreeformShape, container: FreeformShape) -> bool:
    center_x = shape.x + shape.width / 2
    center_y = shape.y + shape.height / 2
    return (
        container.x <= center_x <= container.x + container.width
        and container.y <= center_y <= container.y + container.height
    )


def _row_width(row: list[FreeformShape], spacing: float) -> float:
    if not row:
        return 0.0
    return sum(shape.width for shape in row) + spacing * (len(row) - 1)


def _row_has_overlap(row: list[FreeformShape], min_spacing: float) -> bool:
    sorted_row = sorted(row, key=lambda shape: shape.x)
    for left, right in zip(sorted_row, sorted_row[1:]):
        if left.x + left.width + min_spacing > right.x:
            return True
    return False


def _row_overflows_bounds(row: list[FreeformShape], x: float, width: float) -> bool:
    left_bound = x
    right_bound = x + width
    return any(shape.x < left_bound or shape.x + shape.width > right_bound for shape in row)


def _fit_shape_labels(diagram: FreeformDiagram) -> tuple[FreeformDiagram, bool]:
    changed = False
    shapes: list[FreeformShape] = []
    for shape in diagram.shapes:
        next_shape = shape
        if _should_fit_shape_label(shape):
            required_width = _required_label_width(shape)
            max_width = max(shape.width, min(MAX_AUTO_LABEL_WIDTH, shape.width * MAX_LABEL_WIDTH_GROWTH_FACTOR))
            target_width = _ceil_to_grid(min(required_width, max_width))
            if target_width > shape.width:
                delta = target_width - shape.width
                target_x = max(0.0, _snap_value(shape.x - delta / 2))
                next_shape = replace(
                    next_shape,
                    x=target_x,
                    width=target_width,
                )
                changed = True

            required_height = _required_label_height(next_shape)
            if required_height > next_shape.height:
                next_shape = replace(next_shape, height=_ceil_to_grid(required_height))
                changed = True
        shapes.append(next_shape)

    if not changed:
        return diagram, False
    return replace(diagram, shapes=shapes), True


def _should_fit_shape_label(shape: FreeformShape) -> bool:
    if not shape.label:
        return False
    if shape.type in {"line", "arrow", "brace", "bracket", "image"}:
        return False
    if _is_hidden(shape.extras):
        return False
    if _bool_style_value(shape.extras, "overflow", default=False):
        return False
    return True


def _required_label_height(shape: FreeformShape) -> float:
    font_size = _font_size(shape.extras, default=12.0)
    horizontal_padding = max(12.0, font_size * 1.2)
    vertical_padding = max(12.0, font_size * 1.35)
    max_width = max(font_size, shape.width - horizontal_padding)
    lines = _estimated_wrapped_line_count(shape.label, max_width, font_size)
    line_height = max(14.0, font_size * 1.28)
    return lines * line_height + vertical_padding


def _required_label_width(shape: FreeformShape) -> float:
    font_size = _font_size(shape.extras, default=12.0)
    horizontal_padding = max(12.0, font_size * 1.2)
    max_line_width = max(
        (_estimated_text_width(line, font_size) for line in str(shape.label).splitlines()),
        default=0.0,
    )
    return max(shape.width, max_line_width + horizontal_padding)


def _estimated_wrapped_line_count(label: str, max_width: float, font_size: float) -> int:
    explicit_lines = str(label).splitlines() or [""]
    return max(1, sum(_estimated_line_count(line, max_width, font_size) for line in explicit_lines))


def _estimated_line_count(text: str, max_width: float, font_size: float) -> int:
    if not text:
        return 1
    lines = 1
    current_width = 0.0
    for char in text:
        char_width = _estimated_char_width(char, font_size)
        if current_width > 0 and current_width + char_width > max_width:
            lines += 1
            current_width = char_width
        else:
            current_width += char_width
    return lines


def _estimated_char_width(char: str, font_size: float) -> float:
    if char.isspace():
        return font_size * 0.35
    if ord(char) < 128:
        return font_size * 0.56
    return font_size


def _estimated_text_width(text: str, font_size: float) -> float:
    return sum(_estimated_char_width(char, font_size) for char in text)


def _font_size(extras: dict[str, Any], default: float) -> float:
    for key in ("fontSize", "font_size", "font-size"):
        value = extras.get(key)
        if value is None:
            continue
        try:
            return max(8.0, min(float(value), 40.0))
        except (TypeError, ValueError):
            continue
    style = extras.get("style")
    if isinstance(style, str):
        for part in style.split(";"):
            if "=" not in part and ":" not in part:
                continue
            separator = "=" if "=" in part else ":"
            key, value = part.split(separator, 1)
            if key.strip().lower().replace("-", "").replace("_", "") == "fontsize":
                try:
                    return max(8.0, min(float(value.strip()), 40.0))
                except (TypeError, ValueError):
                    continue
    return default


def _bool_style_value(extras: dict[str, Any], key: str, default: bool) -> bool:
    value = extras.get(key)
    if value is None:
        style = extras.get("style")
        if isinstance(style, str):
            normalized_key = key.strip().lower()
            for part in style.split(";"):
                if "=" not in part and ":" not in part:
                    continue
                separator = "=" if "=" in part else ":"
                raw_key, raw_value = part.split(separator, 1)
                if raw_key.strip().lower() == normalized_key:
                    value = raw_value
                    break
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "visible"}


def _infer_children_by_group(diagram: FreeformDiagram) -> dict[str, list[FreeformShape]]:
    groups = [
        group
        for group in diagram.groups
        if group.x is not None and group.y is not None and group.width is not None and group.height is not None
    ]
    if not groups:
        return {}

    explicit_child_ids = {
        child_id
        for group in diagram.groups
        if group.children
        for child_id in group.children
    }
    inferred: dict[str, list[FreeformShape]] = {group.id: [] for group in groups}
    for shape in diagram.shapes:
        if shape.id in explicit_child_ids or not _can_center_group_child(shape):
            continue
        containing = [group for group in groups if _shape_center_inside_group(shape, group)]
        if not containing:
            continue
        smallest = min(containing, key=lambda group: (group.width or 0) * (group.height or 0))
        inferred[smallest.id].append(shape)
    return inferred


def _shape_center_inside_group(shape: FreeformShape, group: FreeformGroup) -> bool:
    if group.x is None or group.y is None or group.width is None or group.height is None:
        return False
    center_x = shape.x + shape.width / 2
    center_y = shape.y + shape.height / 2
    return group.x <= center_x <= group.x + group.width and group.y <= center_y <= group.y + group.height


def _can_center_group_child(shape: FreeformShape) -> bool:
    if shape.type in {"container", "swimlane"}:
        return False
    if _is_hidden(shape.extras):
        return False
    if _bool_extra(shape.extras, "layoutLocked"):
        return False
    return True


def _group_shapes_by_row(shapes: list[FreeformShape]) -> list[list[FreeformShape]]:
    rows: list[list[FreeformShape]] = []
    tolerance = DEFAULT_GRID_SIZE * 2
    for shape in sorted(shapes, key=lambda item: (item.y, item.x)):
        center_y = shape.y + shape.height / 2
        matched = False
        for row in rows:
            row_center = sum(item.y + item.height / 2 for item in row) / len(row)
            if abs(center_y - row_center) <= tolerance:
                row.append(shape)
                matched = True
                break
        if not matched:
            rows.append([shape])
    return rows


def _snap_value(value: float) -> float:
    return round(value / DEFAULT_GRID_SIZE) * DEFAULT_GRID_SIZE


def _merge_defaults(extras: dict[str, Any], defaults: dict[str, str]) -> tuple[dict[str, Any], bool]:
    merged = dict(extras)
    changed = False
    for key, value in defaults.items():
        if _has_style_key(merged, key):
            continue
        merged[key] = value
        changed = True
    return merged, changed


def _scale_font_size_extras(extras: dict[str, Any], base_limit: float) -> tuple[dict[str, Any], bool]:
    current = _explicit_font_size(extras)
    if current is None or current > base_limit:
        return extras, False
    scaled = max(current + 1, math.ceil(current * A4_FONT_SCALE))
    return _set_font_size(extras, scaled)


def _explicit_font_size(extras: dict[str, Any]) -> float | None:
    aliases = _style_aliases("fontSize")
    for raw_key, raw_value in extras.items():
        if str(raw_key).strip().lower().replace("-", "_") not in aliases:
            continue
        parsed = _parse_float(raw_value)
        if parsed is not None:
            return parsed

    raw_style = extras.get("style")
    if raw_style is None:
        return None
    for part in str(raw_style).split(";"):
        if not part.strip():
            continue
        separator = "=" if "=" in part else ":" if ":" in part else None
        if separator is None:
            continue
        raw_key, raw_value = part.split(separator, 1)
        if raw_key.strip().lower().replace("-", "_") not in aliases:
            continue
        parsed = _parse_float(raw_value)
        if parsed is not None:
            return parsed
    return None


def _set_font_size(extras: dict[str, Any], font_size: int) -> tuple[dict[str, Any], bool]:
    aliases = _style_aliases("fontSize")
    merged = dict(extras)
    font_size_text = str(font_size)

    for raw_key in list(merged.keys()):
        if str(raw_key).strip().lower().replace("-", "_") in aliases:
            if str(merged[raw_key]) == font_size_text:
                return extras, False
            merged[raw_key] = font_size_text
            return merged, True

    raw_style = merged.get("style")
    if raw_style is not None:
        updated_style, changed = _set_font_size_in_style(str(raw_style), font_size_text)
        if changed:
            merged["style"] = updated_style
            return merged, True

    merged["fontSize"] = font_size_text
    return merged, True


def _set_font_size_in_style(style: str, font_size_text: str) -> tuple[str, bool]:
    aliases = _style_aliases("fontSize")
    parts = style.split(";")
    changed = False
    for index, part in enumerate(parts):
        if not part.strip():
            continue
        separator = "=" if "=" in part else ":" if ":" in part else None
        if separator is None:
            continue
        raw_key, raw_value = part.split(separator, 1)
        if raw_key.strip().lower().replace("-", "_") not in aliases:
            continue
        if raw_value.strip() == font_size_text:
            return style, False
        parts[index] = f"{raw_key}{separator}{font_size_text}"
        changed = True
        break
    return ";".join(parts), changed


def _parse_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _has_style_key(extras: dict[str, Any], key: str) -> bool:
    aliases = _style_aliases(key)
    for raw_key in extras.keys():
        if str(raw_key).strip().lower().replace("-", "_") in aliases:
            return True
    raw_style = extras.get("style")
    if raw_style is None:
        return False
    for part in str(raw_style).split(";"):
        if not part.strip():
            continue
        if "=" in part:
            raw_part_key = part.split("=", 1)[0]
        elif ":" in part:
            raw_part_key = part.split(":", 1)[0]
        else:
            raw_part_key = part
        if raw_part_key.strip().lower().replace("-", "_") in aliases:
            return True
    return False


def _style_aliases(key: str) -> set[str]:
    normalized = key.strip().lower().replace("-", "_")
    aliases = {normalized}
    if normalized == "fillcolor":
        aliases.update({"fill", "fill_color"})
    elif normalized == "strokecolor":
        aliases.update({"stroke", "stroke_color"})
    elif normalized == "strokewidth":
        aliases.update({"stroke_width"})
    elif normalized == "fontcolor":
        aliases.update({"font_color"})
    elif normalized == "fontsize":
        aliases.update({"font_size"})
    elif normalized == "fontfamily":
        aliases.update({"font_family"})
    elif normalized == "endarrow":
        aliases.update({"end_arrow"})
    elif normalized == "endfill":
        aliases.update({"end_fill"})
    return aliases


def _expand_canvas(diagram: FreeformDiagram) -> tuple[FreeformDiagram, bool]:
    visible_shapes = [shape for shape in diagram.shapes if not _is_hidden(shape.extras)]
    visible_groups = [group for group in diagram.groups if not _is_hidden(group.extras)]
    max_x = diagram.canvas.width
    max_y = diagram.canvas.height
    for shape in visible_shapes:
        max_x = max(max_x, shape.x + shape.width + CANVAS_MARGIN)
        max_y = max(max_y, shape.y + shape.height + CANVAS_MARGIN)
    for group in visible_groups:
        if group.x is not None and group.width is not None:
            max_x = max(max_x, group.x + group.width + CANVAS_MARGIN)
        if group.y is not None and group.height is not None:
            max_y = max(max_y, group.y + group.height + CANVAS_MARGIN)

    width = _ceil_to_grid(max_x)
    height = _ceil_to_grid(max_y)
    if width == diagram.canvas.width and height == diagram.canvas.height:
        return diagram, False
    return replace(diagram, canvas=replace(diagram.canvas, width=width, height=height)), True


def _quality_warnings(diagram: FreeformDiagram) -> list[str]:
    warnings: list[str] = []
    visible_shapes = [shape for shape in diagram.shapes if not _is_hidden(shape.extras)]
    if _has_overlap(visible_shapes):
        warnings.append("overlap_detected")
    if _has_high_fan_in(diagram.connectors):
        warnings.append("high_fan_in")
    if any(len(shape.label) > LONG_LABEL_LENGTH for shape in visible_shapes):
        warnings.append("label_too_long")
    if _is_sparse_canvas(diagram.canvas, visible_shapes):
        warnings.append("canvas_sparse")
    return warnings


def _has_overlap(shapes: list[FreeformShape]) -> bool:
    for index, left in enumerate(shapes):
        for right in shapes[index + 1:]:
            overlap_width = max(0.0, min(left.x + left.width, right.x + right.width) - max(left.x, right.x))
            overlap_height = max(0.0, min(left.y + left.height, right.y + right.height) - max(left.y, right.y))
            overlap_area = overlap_width * overlap_height
            if overlap_area <= 0:
                continue
            smaller_area = min(left.width * left.height, right.width * right.height)
            if smaller_area > 0 and overlap_area / smaller_area >= OVERLAP_RATIO_THRESHOLD:
                return True
    return False


def _has_high_fan_in(connectors: list[FreeformConnector]) -> bool:
    counts: dict[str, int] = {}
    for connector in connectors:
        if _is_hidden(connector.extras):
            continue
        counts[connector.target_id] = counts.get(connector.target_id, 0) + 1
    return any(count >= HIGH_FAN_IN_THRESHOLD for count in counts.values())


def _is_sparse_canvas(canvas: FreeformCanvas, shapes: list[FreeformShape]) -> bool:
    if len(shapes) < 2:
        return False
    used_area = sum(shape.width * shape.height for shape in shapes)
    canvas_area = max(1.0, canvas.width * canvas.height)
    return canvas_area > 1_000_000 and used_area / canvas_area < 0.04


def _is_hidden(extras: dict[str, Any]) -> bool:
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


def _bool_extra(extras: dict[str, Any], key: str) -> bool:
    value = extras.get(key)
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _ceil_to_grid(value: float) -> float:
    return ((int(value) + DEFAULT_GRID_SIZE - 1) // DEFAULT_GRID_SIZE) * DEFAULT_GRID_SIZE


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
