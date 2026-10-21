"""Shared matplotlib legend placement for report and evidence charts.

Every renderer that draws a matplotlib legend routes it through
``position_legends_below_plot`` so the legend always sits horizontally under
the x-axis instead of floating inside the plotting area.  The legend is
anchored in figure coordinates and its height is measured afterwards, so the
caller can reserve exactly the amount of bottom space it needs via
``fig.tight_layout(rect=(0, reserved_bottom_fraction, 1, 1))``.

Because the relocated legend is removed from the layout engine
(``set_in_layout(False)``), matplotlib drops it from the ``bbox_inches="tight"``
computation.  Exporting therefore has to pass ``visible_legends(fig)`` as
``bbox_extra_artists``, otherwise the legend is silently cropped away.
"""

from __future__ import annotations

from typing import Any

LEGEND_MAX_COLUMNS = 4
LEGEND_MAX_RESERVED_FRACTION = 0.26
LEGEND_BOTTOM_ANCHOR = 0.015
LEGEND_NOTES_BOTTOM_ANCHOR = 0.075
LEGEND_ROW_GAP = 0.012
LEGEND_BOTTOM_MARGIN = 0.015


def visible_legends(fig) -> list[Any]:
    """Return every visible legend on the figure, for ``bbox_extra_artists``."""
    return [
        legend
        for ax in fig.axes
        if (legend := ax.get_legend()) is not None and legend.get_visible()
    ]


def position_legends_below_plot(fig, *, notes_present: bool = False) -> dict[str, Any]:
    """Move axes legends into a measured band below the plotting area."""
    legends = []
    for axis_index, ax in enumerate(fig.axes):
        legend = ax.get_legend()
        if legend is None or not legend.get_visible() or not legend.get_texts():
            continue
        legends.append((axis_index, ax, legend))

    if not legends:
        return {
            "position": "none",
            "legend_count": 0,
            "reserved_bottom_fraction": 0.0,
            "items": [],
        }

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    # Keep the legend above the provenance note when both are present.
    next_anchor = LEGEND_NOTES_BOTTOM_ANCHOR if notes_present else LEGEND_BOTTOM_ANCHOR
    items = []
    for axis_index, ax, legend in legends:
        handles = list(legend.legend_handles)
        labels = [text.get_text() for text in legend.get_texts()]
        item_count = len(labels)
        columns = min(LEGEND_MAX_COLUMNS, item_count)
        legend_options = {
            "fontsize": min(float(text.get_fontsize()) for text in legend.get_texts()),
            "frameon": legend.get_frame_on(),
            "loc": "lower center",
            "bbox_to_anchor": (0.5, next_anchor),
            "bbox_transform": fig.transFigure,
            "borderaxespad": 0.0,
            "ncol": columns,
        }
        title = legend.get_title().get_text()
        if title:
            legend_options["title"] = title
        legend.remove()
        legend = ax.legend(handles, labels, **legend_options)
        legend.set_in_layout(False)
        fig.canvas.draw()

        bbox = legend.get_window_extent(renderer=renderer)
        height_fraction = bbox.height / max(float(fig.bbox.height), 1.0)
        next_anchor += height_fraction + LEGEND_ROW_GAP
        items.append(
            {
                "axis_index": axis_index,
                "item_count": item_count,
                "columns": columns,
            }
        )

    required_fraction = next_anchor + LEGEND_BOTTOM_MARGIN
    return {
        "position": "outside_bottom",
        "legend_count": len(legends),
        "reserved_bottom_fraction": min(
            LEGEND_MAX_RESERVED_FRACTION,
            required_fraction,
        ),
        "required_bottom_fraction": required_fraction,
        "items": items,
    }
