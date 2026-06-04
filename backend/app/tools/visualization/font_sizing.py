"""Shared font sizing helpers for generated chart images."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Literal, Union


FontScale = Union[str, int, float, None]
OutputContext = Literal["word", "report", "print", "screen", "html"]

DEFAULT_WORD_IMAGE_WIDTH_IN = 5.8


@dataclass(frozen=True)
class ChartFontSizes:
    title: int
    axis_label: int
    tick_label: int
    legend: int
    annotation: int
    colorbar_label: int
    colorbar_tick: int


_SEMANTIC_FONT_SCALES = {
    "small": 0.9,
    "normal": 1.0,
    "large": 1.25,
    "xlarge": 1.45,
}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def resolve_font_scale(font_scale: FontScale = None) -> float:
    if isinstance(font_scale, str):
        scale = _SEMANTIC_FONT_SCALES.get(font_scale.strip().lower(), 1.0)
    elif isinstance(font_scale, (int, float)):
        scale = float(font_scale)
    else:
        scale = 1.0
    return _clamp(scale, 0.8, 1.6)


def _scaled_size(base_px: float, coefficient: float, lower: int, upper: int, scale: float) -> int:
    return int(round(_clamp(base_px * coefficient * scale, lower, upper)))


def resolve_font_sizes(
    *,
    width_px: int,
    height_px: int,
    font_scale: FontScale = None,
) -> ChartFontSizes:
    """Return readable font sizes for a raster chart output.

    The formula scales with the shorter image side, then clamps each text role.
    This keeps small report images readable while preventing poster-sized outputs
    from producing oversized labels that collide with chart geometry.
    """

    base_px = max(1, min(int(width_px), int(height_px)))
    scale = resolve_font_scale(font_scale)

    return ChartFontSizes(
        title=_scaled_size(base_px, 0.022, 16, 34, scale),
        axis_label=_scaled_size(base_px, 0.014, 11, 22, scale),
        tick_label=_scaled_size(base_px, 0.011, 9, 18, scale),
        legend=_scaled_size(base_px, 0.012, 10, 18, scale),
        annotation=_scaled_size(base_px, 0.011, 9, 18, scale),
        colorbar_label=_scaled_size(base_px, 0.013, 10, 20, scale),
        colorbar_tick=_scaled_size(base_px, 0.010, 9, 16, scale),
    )


def _scaled_point_size(base_scale: float, base_size: int, lower: int, upper: int) -> int:
    return int(round(_clamp(base_size * base_scale, lower, upper)))


def _word_source_point_size(
    *,
    desired_final_pt: float,
    width_in: float,
    target_width_in: float,
    scale: float,
    lower: int,
    upper: int,
) -> int:
    source_scale = max(1.0, float(width_in) / max(1.0, float(target_width_in)))
    return int(round(_clamp(desired_final_pt * source_scale * scale, lower, upper)))


def resolve_matplotlib_font_sizes(
    *,
    width_in: float,
    height_in: float,
    dpi: int | None = None,
    font_scale: FontScale = None,
    output_context: OutputContext = "word",
    target_width_in: float = DEFAULT_WORD_IMAGE_WIDTH_IN,
) -> ChartFontSizes:
    """Return Matplotlib point sizes for a figure.

    For Word/report outputs, images are commonly inserted at a fixed physical
    width on an A4 page. A large source figure is therefore scaled down in Word,
    so source font sizes must be back-calculated from the target printed size.

    For screen/html outputs, Matplotlib point sizes already become more pixels
    as DPI increases, so DPI is intentionally ignored and sizing scales only
    with physical figure size.
    """

    del dpi
    context = (output_context or "word").strip().lower()
    scale = resolve_font_scale(font_scale)
    width = max(1.0, float(width_in))

    if context in {"word", "report", "print"}:
        return ChartFontSizes(
            title=_word_source_point_size(
                desired_final_pt=14,
                width_in=width,
                target_width_in=target_width_in,
                scale=scale,
                lower=18,
                upper=64,
            ),
            axis_label=_word_source_point_size(
                desired_final_pt=11,
                width_in=width,
                target_width_in=target_width_in,
                scale=scale,
                lower=14,
                upper=52,
            ),
            tick_label=_word_source_point_size(
                desired_final_pt=9.5,
                width_in=width,
                target_width_in=target_width_in,
                scale=scale,
                lower=12,
                upper=44,
            ),
            legend=_word_source_point_size(
                desired_final_pt=9.5,
                width_in=width,
                target_width_in=target_width_in,
                scale=scale,
                lower=12,
                upper=44,
            ),
            annotation=_word_source_point_size(
                desired_final_pt=9.5,
                width_in=width,
                target_width_in=target_width_in,
                scale=scale,
                lower=12,
                upper=44,
            ),
            colorbar_label=_word_source_point_size(
                desired_final_pt=10.5,
                width_in=width,
                target_width_in=target_width_in,
                scale=scale,
                lower=13,
                upper=48,
            ),
            colorbar_tick=_word_source_point_size(
                desired_final_pt=9,
                width_in=width,
                target_width_in=target_width_in,
                scale=scale,
                lower=12,
                upper=42,
            ),
        )

    short_side_in = max(1.0, min(float(width_in), float(height_in)))
    size_scale = sqrt(short_side_in / 6.0) * scale

    return ChartFontSizes(
        title=_scaled_point_size(size_scale, 16, 16, 30),
        axis_label=_scaled_point_size(size_scale, 12, 11, 22),
        tick_label=_scaled_point_size(size_scale, 10, 9, 18),
        legend=_scaled_point_size(size_scale, 10, 10, 18),
        annotation=_scaled_point_size(size_scale, 10, 9, 18),
        colorbar_label=_scaled_point_size(size_scale, 11, 10, 20),
        colorbar_tick=_scaled_point_size(size_scale, 9, 9, 16),
    )
