from __future__ import annotations

import math
import textwrap
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from matplotlib.artist import Artist
from matplotlib.text import Annotation, Text
from matplotlib.transforms import Bbox

WORD_SOURCE_WIDTH_IN = 8.2
WORD_TARGET_WIDTH_IN = 5.8
DEFAULT_SPACING_PX = 3.0
BOUNDARY_PADDING_PX = 3.0
MAX_FONT_REDUCTION_PASSES = 10


@dataclass
class LayoutTextItem:
    artist: Text
    role: str
    domain: str
    priority: float = 0.0
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class LayoutIssue:
    kind: str
    domain: str
    items: list[LayoutTextItem]


@dataclass
class LayoutReport:
    items: list[LayoutTextItem]
    issues: list[LayoutIssue]

    @property
    def conflict_count(self) -> int:
        return len(self.issues)


class TextLayoutRegistry:
    """Register chart text whose semantic role Matplotlib cannot infer."""

    def __init__(self) -> None:
        self._items: list[LayoutTextItem] = []

    @property
    def items(self) -> list[LayoutTextItem]:
        return list(self._items)

    def register(
        self,
        artist: Text,
        *,
        role: str,
        domain: str,
        priority: float = 0.0,
        payload: dict[str, Any] | None = None,
    ) -> Text:
        self._items.append(
            LayoutTextItem(
                artist=artist,
                role=role,
                domain=domain,
                priority=float(priority),
                payload=dict(payload or {}),
            )
        )
        return artist


def govern_text_layout(
    fig,
    registry: TextLayoutRegistry,
    *,
    output_context: str,
) -> tuple[list[str], dict[str, Any]]:
    """Measure, govern, and re-measure text for general report charts."""

    warnings: list[str] = []
    actions = {
        "font_reductions": 0,
        "wrapped_labels": 0,
        "thinned_ticks": 0,
        "omitted_annotations": 0,
        "omitted_reference_labels": 0,
        "omitted_legend_items": 0,
        "legend_reflows": 0,
    }
    omitted_items: list[dict[str, Any]] = []
    full_label_mapping: dict[str, str] = {}
    pie_slices = _serialize_pie_slices(registry, omitted_items)
    governance_passes = 1

    try:
        _draw(fig)
        initial_report = inspect_text_layout(fig, registry)
        if not initial_report.issues:
            return [], {
                "status": "resolved",
                "passes": 1,
                "initial_conflicts": 0,
                "final_conflicts": 0,
                "actions": actions,
                "omitted_items": [],
                "full_label_mapping": {},
                "pie_slices": pie_slices,
                "residual_issues": [],
            }

        pie_actions = _govern_pie_labels(fig, registry, output_context)
        governance_passes += 1
        _merge_action_counts(actions, pie_actions["actions"])
        omitted_items.extend(pie_actions["omitted_items"])
        full_label_mapping.update(pie_actions["full_label_mapping"])

        _draw(fig)
        for _ in range(MAX_FONT_REDUCTION_PASSES):
            report = inspect_text_layout(fig, registry)
            if not report.issues:
                break
            changed = _shrink_conflicting_domains(report, output_context)
            actions["font_reductions"] += changed
            if not changed:
                break
            _draw(fig)
            governance_passes += 1

        tick_actions = _thin_overlapping_ticks(fig, registry)
        governance_passes += 1
        _merge_action_counts(actions, tick_actions["actions"])
        omitted_items.extend(tick_actions["omitted_items"])

        legend_actions = _govern_legends(fig, registry, output_context)
        governance_passes += 1
        _merge_action_counts(actions, legend_actions["actions"])
        omitted_items.extend(legend_actions["omitted_items"])

        reference_actions = _govern_reference_labels(fig, registry)
        governance_passes += 1
        _merge_action_counts(actions, reference_actions["actions"])
        omitted_items.extend(reference_actions["omitted_items"])

        # Legend reflow can change the final renderer geometry. Re-run the
        # measured tick policy once so governance converges on the final set
        # of artists rather than the pre-reflow layout.
        final_tick_actions = _thin_overlapping_ticks(fig, registry)
        governance_passes += 1
        _merge_action_counts(actions, final_tick_actions["actions"])
        omitted_items.extend(final_tick_actions["omitted_items"])

        _draw(fig)
        final_report = inspect_text_layout(fig, registry)
        if omitted_items:
            warnings.append("text_items_omitted_for_layout")
        if actions["font_reductions"]:
            warnings.append("text_font_size_reduced")
        if actions["thinned_ticks"]:
            warnings.append("axis_tick_labels_thinned_for_layout")
        if final_report.issues:
            warnings.append("text_overlap_unresolved")
            status = "unresolved"
        elif omitted_items:
            status = "degraded"
        else:
            status = "resolved"

        metadata = {
            "status": status,
            "passes": governance_passes,
            "initial_conflicts": initial_report.conflict_count,
            "final_conflicts": final_report.conflict_count,
            "actions": actions,
            "omitted_items": omitted_items,
            "full_label_mapping": full_label_mapping,
            "pie_slices": _serialize_pie_slices(registry, omitted_items),
            "residual_issues": _serialize_issues(final_report.issues),
        }
        return _dedupe(warnings), metadata
    except Exception as exc:
        return ["text_layout_governance_failed"], {
            "status": "unresolved",
            "passes": 0,
            "initial_conflicts": None,
            "final_conflicts": None,
            "actions": actions,
            "omitted_items": omitted_items,
            "full_label_mapping": full_label_mapping,
            "pie_slices": _serialize_pie_slices(registry, omitted_items),
            "residual_issues": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def inspect_text_layout(fig, registry: TextLayoutRegistry) -> LayoutReport:
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    items = _collect_items(fig, registry)
    issues: list[LayoutIssue] = []

    grouped: dict[str, list[LayoutTextItem]] = {}
    for item in items:
        grouped.setdefault(item.domain, []).append(item)

    for domain, domain_items in grouped.items():
        visible = [item for item in domain_items if _is_visible_text(item.artist)]
        for left_index, left in enumerate(visible):
            left_box = _padded_bbox(_artist_bbox(left.artist, renderer), DEFAULT_SPACING_PX)
            for right in visible[left_index + 1 :]:
                right_box = _padded_bbox(_artist_bbox(right.artist, renderer), DEFAULT_SPACING_PX)
                if left_box.overlaps(right_box):
                    issues.append(LayoutIssue("overlap", domain, [left, right]))

    # Clipping is a hard canvas-boundary condition. Readability spacing is
    # handled by padded overlap checks; applying the same padding here would
    # incorrectly mark legitimate edge-aligned tick labels as clipped.
    figure_box = fig.bbox
    for item in items:
        if not _is_visible_text(item.artist):
            continue
        item_box = _artist_bbox(item.artist, renderer)
        if not _bbox_contains(figure_box, item_box):
            issues.append(LayoutIssue("clipped", item.domain, [item]))

    issues.extend(_cross_domain_issues(items, renderer))
    return LayoutReport(items=items, issues=_dedupe_issues(issues))


def _collect_items(fig, registry: TextLayoutRegistry) -> list[LayoutTextItem]:
    items = registry.items
    registered = {id(item.artist) for item in items}

    for axis_index, ax in enumerate(fig.axes):
        candidates = [
            (ax.title, "title", f"title:{axis_index}"),
            (ax.xaxis.label, "x_axis_label", f"x_structure:{axis_index}"),
            (ax.yaxis.label, "y_axis_label", f"y_structure:{axis_index}"),
        ]
        for artist, role, domain in candidates:
            if id(artist) not in registered and _is_visible_text(artist):
                items.append(LayoutTextItem(artist, role, domain, priority=100.0))
                registered.add(id(artist))

        for artist in _visible_axis_tick_labels(ax.xaxis):
            if id(artist) not in registered and _is_visible_text(artist):
                items.append(
                    LayoutTextItem(artist, "x_tick", f"x_ticks:{axis_index}", priority=60.0)
                )
                registered.add(id(artist))
        for artist in _visible_axis_tick_labels(ax.yaxis):
            if id(artist) not in registered and _is_visible_text(artist):
                items.append(
                    LayoutTextItem(artist, "y_tick", f"y_ticks:{axis_index}", priority=60.0)
                )
                registered.add(id(artist))

        legend = ax.get_legend()
        if legend is not None and legend.get_visible():
            for artist in legend.get_texts():
                if id(artist) not in registered and _is_visible_text(artist):
                    items.append(
                        LayoutTextItem(artist, "legend", f"legend:{axis_index}", priority=70.0)
                    )
                    registered.add(id(artist))

    return items


def _visible_axis_tick_labels(axis) -> list[Text]:
    labels = list(axis.get_ticklabels())
    locations = list(axis.get_majorticklocs())
    lower, upper = sorted(float(value) for value in axis.get_view_interval())
    tolerance = max(abs(upper - lower), 1.0) * 1e-9
    visible: list[Text] = []
    for location, label in zip(locations, labels, strict=False):
        try:
            numeric_location = float(location)
        except (TypeError, ValueError):
            continue
        if lower - tolerance <= numeric_location <= upper + tolerance and _is_visible_text(label):
            visible.append(label)
    return visible


def _cross_domain_issues(items: Sequence[LayoutTextItem], renderer) -> list[LayoutIssue]:
    issues: list[LayoutIssue] = []
    pairs = {
        frozenset({"title", "legend"}),
        frozenset({"x_axis_label", "x_tick"}),
        frozenset({"y_axis_label", "y_tick"}),
    }
    visible = [item for item in items if _is_visible_text(item.artist)]
    for index, left in enumerate(visible):
        for right in visible[index + 1 :]:
            role_pair = frozenset({left.role, right.role})
            reference_crossing = "reference_label" in role_pair and bool(
                role_pair
                & {
                    "title",
                    "legend",
                    "x_tick",
                    "y_tick",
                    "x_axis_label",
                    "y_axis_label",
                    "pie_label",
                }
            )
            if role_pair not in pairs and not reference_crossing:
                continue
            left_box = _padded_bbox(_artist_bbox(left.artist, renderer), DEFAULT_SPACING_PX)
            right_box = _padded_bbox(_artist_bbox(right.artist, renderer), DEFAULT_SPACING_PX)
            if left_box.overlaps(right_box):
                issues.append(LayoutIssue("overlap", "cross_domain", [left, right]))
    return issues


def _govern_pie_labels(fig, registry: TextLayoutRegistry, output_context: str) -> dict[str, Any]:
    all_items = [item for item in registry.items if item.role == "pie_label"]
    items = [item for item in all_items if item.payload.get("placement") == "outside"]
    actions = {"font_reductions": 0, "wrapped_labels": 0, "omitted_annotations": 0}
    omitted_items: list[dict[str, Any]] = []
    full_label_mapping: dict[str, str] = {}
    if not items:
        return {
            "actions": actions,
            "omitted_items": omitted_items,
            "full_label_mapping": full_label_mapping,
        }

    for index, item in enumerate(items):
        original = str(item.payload.get("label") or item.artist.get_text())
        full_label_mapping[f"pie_label:{index}"] = original
        wrapped = _wrap_label_with_suffix(original, item.payload.get("share"), width=12)
        if wrapped != item.artist.get_text():
            item.artist.set_text(wrapped)
            actions["wrapped_labels"] += 1

    min_font = _source_font(8.0, output_context)
    while not _arrange_pie_labels(fig, items):
        changed = False
        for item in items:
            if not item.artist.get_visible():
                continue
            current = float(item.artist.get_fontsize())
            reduced = max(min_font, current - _source_font(0.7, output_context))
            if reduced < current - 0.01:
                item.artist.set_fontsize(reduced)
                actions["font_reductions"] += 1
                changed = True
        if not changed:
            break
        _draw(fig)

    largest = max(items, key=lambda item: item.priority)
    while not _arrange_pie_labels(fig, items):
        candidates = [item for item in items if item.artist.get_visible() and item is not largest]
        if not candidates:
            break
        omitted = min(
            candidates, key=lambda item: (item.priority, int(item.payload.get("index", 0)))
        )
        omitted.artist.set_visible(False)
        arrow = getattr(omitted.artist, "arrow_patch", None)
        if isinstance(arrow, Artist):
            arrow.set_visible(False)
        actions["omitted_annotations"] += 1
        omitted_items.append(
            {
                "role": "pie_label",
                "index": omitted.payload.get("index"),
                "label": str(omitted.payload.get("label") or ""),
                "value": omitted.payload.get("value"),
                "share": omitted.payload.get("share"),
                "reason": "insufficient_safe_area",
            }
        )
        _draw(fig)

    _arrange_pie_labels(fig, items)
    return {
        "actions": actions,
        "omitted_items": omitted_items,
        "full_label_mapping": full_label_mapping,
    }


def _arrange_pie_labels(fig, items: Sequence[LayoutTextItem]) -> bool:
    visible = [item for item in items if item.artist.get_visible()]
    if not visible:
        return True
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    axes = visible[0].artist.axes
    if axes is None:
        return False

    success = True
    for side in (-1, 1):
        side_items = [item for item in visible if int(item.payload.get("side", 1)) == side]
        if not side_items:
            continue
        side_items.sort(
            key=lambda item: (
                float(item.payload.get("desired_y", 0.0)),
                int(item.payload.get("index", 0)),
            )
        )
        heights = [_artist_bbox(item.artist, renderer).height for item in side_items]
        figure_safe = _inset_bbox(fig.bbox, BOUNDARY_PADDING_PX + 3.0)
        lower = figure_safe.y0
        upper = figure_safe.y1
        title = axes.title
        if _is_visible_text(title):
            upper = min(upper, _artist_bbox(title, renderer).y0 - DEFAULT_SPACING_PX)
        required = sum(heights) + DEFAULT_SPACING_PX * max(0, len(heights) - 1)
        if required > upper - lower:
            success = False
            continue

        desired = [
            axes.transData.transform((side * 1.08, float(item.payload.get("desired_y", 0.0))))[1]
            for item in side_items
        ]
        centers: list[float] = []
        for index, (target, height) in enumerate(zip(desired, heights, strict=False)):
            minimum = lower + height / 2
            if centers:
                minimum = centers[-1] + heights[index - 1] / 2 + DEFAULT_SPACING_PX + height / 2
            centers.append(max(target, minimum))

        last_maximum = upper - heights[-1] / 2
        if centers[-1] > last_maximum:
            centers[-1] = last_maximum
            for index in range(len(centers) - 2, -1, -1):
                maximum = (
                    centers[index + 1]
                    - heights[index + 1] / 2
                    - DEFAULT_SPACING_PX
                    - heights[index] / 2
                )
                centers[index] = min(centers[index], maximum)
        if centers[0] < lower + heights[0] / 2 - 0.01:
            success = False
            continue

        inverse = axes.transData.inverted()
        for item, center in zip(side_items, centers, strict=False):
            y_data = float(inverse.transform((axes.bbox.x0, center))[1])
            item.artist.set_position((side * 1.08, y_data))

    _draw(fig)
    if not success:
        return False
    _nudge_pie_labels_inside_figure(fig, visible)
    _draw(fig)
    report = inspect_text_layout(fig, _registry_for(items))
    pie_issues = [
        issue for issue in report.issues if any(item.role == "pie_label" for item in issue.items)
    ]
    return not pie_issues


def _shrink_conflicting_domains(report: LayoutReport, output_context: str) -> int:
    conflicted_domains = {issue.domain for issue in report.issues}
    conflicted_roles = {item.role for issue in report.issues for item in issue.items}
    minimums = {
        "title": _source_font(12.0, output_context),
        "x_axis_label": _source_font(9.0, output_context),
        "y_axis_label": _source_font(9.0, output_context),
        "x_tick": _source_font(8.0, output_context),
        "y_tick": _source_font(8.0, output_context),
        "legend": _source_font(8.0, output_context),
        "reference_label": _source_font(8.0, output_context),
        "data_label": _source_font(8.0, output_context),
        "pie_label": _source_font(8.0, output_context),
    }
    changed = 0
    for item in report.items:
        if item.domain not in conflicted_domains and item.role not in conflicted_roles:
            continue
        minimum = minimums.get(item.role)
        if minimum is None:
            continue
        current = float(item.artist.get_fontsize())
        reduced = max(minimum, current * 0.9)
        if reduced < current - 0.01:
            item.artist.set_fontsize(reduced)
            changed += 1
    return changed


def _thin_overlapping_ticks(fig, registry: TextLayoutRegistry) -> dict[str, Any]:
    actions = {"thinned_ticks": 0}
    omitted_items: list[dict[str, Any]] = []
    for _ in range(5):
        report = inspect_text_layout(fig, registry)
        domains = {
            issue.domain
            for issue in report.issues
            if issue.kind in {"overlap", "clipped"}
            and (issue.domain.startswith("x_ticks:") or issue.domain.startswith("y_ticks:"))
        }
        if not domains:
            break
        changed = False
        for domain in sorted(domains):
            labels = [
                item for item in report.items if item.domain == domain and item.artist.get_visible()
            ]
            if len(labels) == 1:
                # A single label can still exceed the canvas after reaching
                # the font floor. Hide it rather than emit clipped text; its
                # complete value remains in omission metadata.
                item = labels[0]
                item.artist.set_visible(False)
                actions["thinned_ticks"] += 1
                omitted_items.append(
                    {
                        "role": item.role,
                        "label": item.artist.get_text(),
                        "reason": "clipped_tick_label",
                    }
                )
                changed = True
                continue
            if len(labels) == 2:
                # When two endpoint labels still collide at the readable font
                # floor, retain one scale marker instead of shipping two
                # illegible labels. Prefer the first X endpoint and the last Y
                # endpoint; omitted text remains recoverable in metadata.
                item = labels[0] if domain.startswith("y_ticks:") else labels[1]
                item.artist.set_visible(False)
                actions["thinned_ticks"] += 1
                omitted_items.append(
                    {
                        "role": item.role,
                        "label": item.artist.get_text(),
                        "reason": "overlapping_tick_labels",
                    }
                )
                changed = True
                continue
            keep = {0, len(labels) - 1}
            keep.update(range(0, len(labels), 2))
            for index, item in enumerate(labels):
                if index in keep:
                    continue
                item.artist.set_visible(False)
                actions["thinned_ticks"] += 1
                omitted_items.append(
                    {
                        "role": item.role,
                        "label": item.artist.get_text(),
                        "reason": "overlapping_tick_labels",
                    }
                )
                changed = True
        if not changed:
            break
        _draw(fig)
    return {"actions": actions, "omitted_items": omitted_items}


def _govern_legends(fig, registry: TextLayoutRegistry, output_context: str) -> dict[str, Any]:
    actions = {"legend_reflows": 0, "omitted_legend_items": 0}
    omitted_items: list[dict[str, Any]] = []
    for axis_index, ax in enumerate(fig.axes):
        legend = ax.get_legend()
        if legend is None or not legend.get_visible():
            continue
        texts = legend.get_texts()
        if len(texts) < 2:
            continue
        domain = f"legend:{axis_index}"
        report = inspect_text_layout(fig, registry)
        if not any(
            issue.domain in {domain, "cross_domain"}
            and any(item.role == "legend" for item in issue.items)
            for issue in report.issues
        ):
            continue
        best_columns = 1
        best_score = math.inf
        for columns in range(1, min(4, len(texts)) + 1):
            legend.set_ncols(columns)
            _draw(fig)
            candidate = inspect_text_layout(fig, registry)
            score = sum(
                1
                for issue in candidate.issues
                if issue.domain in {domain, "cross_domain"}
                and any(item.role == "legend" for item in issue.items)
            )
            if score < best_score:
                best_score = score
                best_columns = columns
        legend.set_ncols(best_columns)
        actions["legend_reflows"] += 1
        _draw(fig)

        if _legend_issue_count(fig, registry, axis_index) == 0:
            continue

        handles = list(legend.legend_handles)
        labels = [text.get_text() for text in legend.get_texts()]
        if not handles or len(handles) != len(labels):
            continue
        legend_options = {
            "loc": legend._loc,
            "frameon": legend.get_frame_on(),
            "fontsize": min(float(text.get_fontsize()) for text in legend.get_texts()),
        }
        title = legend.get_title().get_text()
        if title:
            legend_options["title"] = title

        low, high = 1, len(labels)
        best_keep = 1
        while low <= high:
            keep = (low + high) // 2
            legend = _rebuild_legend(
                ax,
                handles[:keep],
                labels[:keep],
                columns=min(best_columns, keep),
                options=legend_options,
            )
            _draw(fig)
            if _legend_issue_count(fig, registry, axis_index) == 0:
                best_keep = keep
                low = keep + 1
            else:
                high = keep - 1

        legend = _rebuild_legend(
            ax,
            handles[:best_keep],
            labels[:best_keep],
            columns=min(best_columns, best_keep),
            options=legend_options,
        )
        _draw(fig)
        for label in labels[best_keep:]:
            omitted_items.append(
                {
                    "role": "legend",
                    "label": label,
                    "reason": "insufficient_safe_area",
                }
            )
            actions["omitted_legend_items"] += 1
    return {"actions": actions, "omitted_items": omitted_items}


def _govern_reference_labels(fig, registry: TextLayoutRegistry) -> dict[str, Any]:
    items = [item for item in registry.items if item.role == "reference_label"]
    actions = {"omitted_reference_labels": 0}
    omitted_items: list[dict[str, Any]] = []
    if not items:
        return {"actions": actions, "omitted_items": omitted_items}

    stable_order = {id(item.artist): index for index, item in enumerate(items)}
    for _ in range(len(items)):
        report = inspect_text_layout(fig, registry)
        conflicting = {
            id(item.artist)
            for issue in report.issues
            for item in issue.items
            if item.role == "reference_label"
        }
        candidates = [
            item for item in items if item.artist.get_visible() and id(item.artist) in conflicting
        ]
        if not candidates:
            break
        # Preserve higher-priority and earlier declarations. With equal
        # priority, later labels are omitted first for deterministic output.
        omitted = min(
            candidates,
            key=lambda item: (item.priority, -stable_order[id(item.artist)]),
        )
        omitted.artist.set_visible(False)
        actions["omitted_reference_labels"] += 1
        omitted_items.append(
            {
                "role": "reference_label",
                "label": str(omitted.payload.get("label") or omitted.artist.get_text()),
                "axis": omitted.payload.get("axis"),
                "value": omitted.payload.get("value"),
                "reason": "overlapping_reference_labels",
            }
        )
        _draw(fig)

    return {"actions": actions, "omitted_items": omitted_items}


def _legend_issue_count(fig, registry: TextLayoutRegistry, axis_index: int) -> int:
    domain = f"legend:{axis_index}"
    report = inspect_text_layout(fig, registry)
    return sum(
        1
        for issue in report.issues
        if issue.domain in {domain, "cross_domain"}
        and any(item.role == "legend" for item in issue.items)
    )


def _rebuild_legend(ax, handles, labels, *, columns: int, options: dict[str, Any]):
    current = ax.get_legend()
    if current is not None:
        current.remove()
    return ax.legend(handles, labels, ncol=max(1, columns), **options)


def _registry_for(items: Sequence[LayoutTextItem]) -> TextLayoutRegistry:
    registry = TextLayoutRegistry()
    registry._items = list(items)
    return registry


def _serialize_pie_slices(
    registry: TextLayoutRegistry,
    omitted_items: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    reasons = {
        int(item["index"]): str(item.get("reason") or "layout_omission")
        for item in omitted_items
        if item.get("role") == "pie_label" and item.get("index") is not None
    }
    slices = []
    for item in registry.items:
        if item.role != "pie_label":
            continue
        index = int(item.payload.get("index", len(slices)))
        visible = bool(item.artist.get_visible())
        slices.append(
            {
                "index": index,
                "label": str(item.payload.get("label") or ""),
                "value": item.payload.get("value"),
                "share": item.payload.get("share"),
                "visible": visible,
                "omitted": not visible,
                "omission_reason": reasons.get(index),
            }
        )
    return sorted(slices, key=lambda item: item["index"])


def _wrap_label_with_suffix(label: str, share: Any, width: int) -> str:
    suffix = ""
    try:
        suffix = f" {float(share) * 100:.1f}%"
    except (TypeError, ValueError):
        pass
    combined = f"{label}{suffix}"
    lines = textwrap.wrap(combined, width=width, break_long_words=True) or [combined]
    return "\n".join(lines)


def _nudge_pie_labels_inside_figure(fig, items: Sequence[LayoutTextItem]) -> None:
    renderer = fig.canvas.get_renderer()
    safe_box = _inset_bbox(fig.bbox, BOUNDARY_PADDING_PX)
    for item in items:
        if not item.artist.get_visible() or item.artist.axes is None:
            continue
        box = _artist_bbox(item.artist, renderer)
        delta_x = 0.0
        if box.x0 < safe_box.x0:
            delta_x = safe_box.x0 - box.x0
        elif box.x1 > safe_box.x1:
            delta_x = safe_box.x1 - box.x1
        if not delta_x:
            continue
        axes = item.artist.axes
        current = axes.transData.transform(item.artist.get_position())
        adjusted = axes.transData.inverted().transform((current[0] + delta_x, current[1]))
        item.artist.set_position((float(adjusted[0]), float(adjusted[1])))


def _source_font(final_pt: float, output_context: str) -> float:
    if output_context == "word":
        return final_pt * WORD_SOURCE_WIDTH_IN / WORD_TARGET_WIDTH_IN
    return final_pt


def _draw(fig) -> None:
    fig.canvas.draw()


def _artist_bbox(artist: Text, renderer) -> Bbox:
    if isinstance(artist, Annotation):
        # Annotation.get_window_extent() also includes its leader line. Layout
        # governance concerns readable text boxes; intersecting leader-line
        # paths must not be mistaken for overlapping labels.
        return Text.get_window_extent(artist, renderer=renderer)
    return artist.get_window_extent(renderer=renderer)


def _padded_bbox(box: Bbox, padding: float) -> Bbox:
    return Bbox.from_extents(box.x0 - padding, box.y0 - padding, box.x1 + padding, box.y1 + padding)


def _inset_bbox(box: Bbox, padding: float) -> Bbox:
    return Bbox.from_extents(box.x0 + padding, box.y0 + padding, box.x1 - padding, box.y1 - padding)


def _bbox_contains(outer: Bbox, inner: Bbox) -> bool:
    return (
        inner.x0 >= outer.x0
        and inner.y0 >= outer.y0
        and inner.x1 <= outer.x1
        and inner.y1 <= outer.y1
    )


def _is_visible_text(artist: Text) -> bool:
    return bool(artist.get_visible() and str(artist.get_text()).strip())


def _merge_action_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = int(target.get(key, 0)) + int(value)


def _serialize_issues(issues: Iterable[LayoutIssue]) -> list[dict[str, Any]]:
    return [
        {
            "kind": issue.kind,
            "domain": issue.domain,
            "roles": [item.role for item in issue.items],
        }
        for issue in issues
    ]


def _dedupe_issues(issues: Sequence[LayoutIssue]) -> list[LayoutIssue]:
    seen = set()
    result = []
    for issue in issues:
        key = (issue.kind, issue.domain, tuple(sorted(id(item.artist) for item in issue.items)))
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
