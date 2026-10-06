"""Shared environmental chart semantics; not a data-validity evaluator.

Tables: HJ 633 tables 1/3 and appendix A; GB 3095 table 1.
Only ambient-air basic pollutants are built in. Other standards must be
verified separately rather than inferred from these limits.
"""

import json
import math
from datetime import date, datetime
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_EVEN
from numbers import Integral

from app.utils.path_config import BACKEND_ROOT


_STANDARDS = json.loads(
    (BACKEND_ROOT / "config/environment_chart_standards.json").read_text(encoding="utf-8")
)
AQI_COLORS = tuple(_STANDARDS["aqi_colors"])
AQI_LABELS = ("优", "良", "轻度污染", "中度污染", "重度污染", "严重污染")
MISSING_COLOR = _STANDARDS["missing_color"]
_TIME_LABELS = {
    "1h": "1小时平均", "24h": "日平均", "8h": "8小时平均",
    "daily_max_8h": "日最大8小时平均", "annual": "年平均",
}


def _observation_date(observed_on):
    if isinstance(observed_on, datetime):
        return observed_on.date()
    if isinstance(observed_on, date):
        return observed_on
    return date.fromisoformat(str(observed_on))


def _observation_context(observed_on):
    day = _observation_date(observed_on)
    if day < date(2026, 3, 1):
        raise ValueError("仅内置 2026 版标准，自 2026-03-01 实施；该数据日期不适用。")
    return day


def _pollutant(pollutant, unit):
    pollutant = str(pollutant).upper().replace("_", ".")
    if pollutant not in _STANDARDS["limits_2026_transition"]:
        raise ValueError("未内置该污染物的环境空气标准，请核实适用标准。")
    expected = "mg/m3" if pollutant == "CO" else "ug/m3"
    normalized = str(unit).replace("μ", "u").replace("µ", "u").replace("³", "3").replace("^", "")
    if normalized != expected:
        raise ValueError(f"{pollutant} 要求单位 {expected}；请先转换数据单位。")
    return pollutant, "mg/m³" if pollutant == "CO" else "μg/m³"


def _concentration(value):
    if value is None:
        return None
    value = float(value)
    if math.isnan(value):
        return None
    if not math.isfinite(value) or value < 0:
        raise ValueError("浓度或 AQI 必须为有限非负数；缺失使用 None/NaN。")
    return value


def aqi_color(value):
    """Return the appendix-A RGB color; missing values remain distinct."""
    value = _concentration(value)
    if value is None:
        return MISSING_COLOR
    for index, upper in enumerate((50, 100, 150, 200, 300)):
        if value <= upper:
            return AQI_COLORS[index]
    return AQI_COLORS[-1]


def get_pollutant_scale(*, pollutant, average_time, observed_on, unit):
    """Return verified concentration/IAQI breakpoints for legends and heatmaps."""
    _observation_context(observed_on)
    pollutant, unit = _pollutant(pollutant, unit)
    periods = _STANDARDS["iaqi_2026"][pollutant]
    if average_time not in periods:
        raise ValueError("该污染物/平均时间没有可用的 IAQI 分级口径。")
    breaks = list(periods[average_time])
    return {"pollutant": pollutant, "average_time": average_time, "unit": unit,
            "concentration_breakpoints": breaks,
            "iaqi_breakpoints": list(_STANDARDS["iaqi_levels"][:len(breaks)]),
            "colors": list(AQI_COLORS), "labels": list(AQI_LABELS),
            "standard": "HJ 633-2026", "source": _STANDARDS["sources"]["HJ633-2026"]}


def pollutant_iaqi(value, *, pollutant, average_time, observed_on, unit):
    """Map a prepared concentration to IAQI for chart coloring.

    Input concentration is rounded per GB/T 8170; completeness, reference
    state and the upstream averaging calculation must be checked separately.
    """
    scale = get_pollutant_scale(pollutant=pollutant, average_time=average_time,
                               observed_on=observed_on, unit=unit)
    value = _concentration(value)
    if value is None:
        return None
    precision = Decimal("0.1") if scale["pollutant"] == "CO" else Decimal("1")
    concentration = Decimal(str(value)).quantize(precision, rounding=ROUND_HALF_EVEN)
    breaks = [Decimal(str(item)) for item in scale["concentration_breakpoints"]]
    levels = scale["iaqi_breakpoints"]
    if concentration > breaks[-1] and len(breaks) < 8:
        return levels[-1]
    for index in range(1, len(breaks)):
        if concentration <= breaks[index]:
            value = ((concentration - breaks[index - 1])
                     * (levels[index] - levels[index - 1])
                     / (breaks[index] - breaks[index - 1]) + levels[index - 1])
            return int(value.to_integral_value(rounding=ROUND_CEILING))
    return 500


def pollutant_color(value, **context):
    """Color a pollutant concentration using its explicit IAQI context."""
    return aqi_color(pollutant_iaqi(value, **context))


def get_environment_limit(*, pollutant, average_time, grade, observed_on, unit):
    """Resolve GB 3095 basic-project limits, including the 2026 transition."""
    day = _observation_context(observed_on)
    pollutant, unit = _pollutant(pollutant, unit)
    if not isinstance(grade, Integral) or isinstance(grade, bool) or grade not in (1, 2):
        raise ValueError("grade 必须明确为 1（一级）或 2（二级）。")
    periods = dict(_STANDARDS["limits_2026_transition"][pollutant])
    phase = "过渡阶段"
    if day >= date(2031, 1, 1):
        periods.update(_STANDARDS["limits_2031_overrides"].get(pollutant, {}))
        phase = "2031年起"
    if average_time not in periods:
        raise ValueError("该污染物/平均时间没有内置的环境质量限值，不能推断标准线。")
    value = periods[average_time][grade - 1]
    standard = "GB 3095-2026"
    label = f"{standard} {phase} {'一级' if grade == 1 else '二级'} {_TIME_LABELS[average_time]}限值 {value:g} {unit}"
    return {"value": value, "unit": unit, "pollutant": pollutant,
            "average_time": average_time, "grade": grade, "standard": standard,
            "phase": phase, "observed_on": day.isoformat(), "label": label,
            "source": _STANDARDS["sources"]["GB3095-2026"]}


def add_standard_limit(ax, *, data_average_time, reference_only=False, **context):
    """Draw a labeled dashed line; reject mismatched comparison periods."""
    limit = get_environment_limit(**context)
    if data_average_time not in _TIME_LABELS:
        raise ValueError("data_average_time 必须明确为文档列出的统计口径。")
    if data_average_time != limit["average_time"] and not reference_only:
        raise ValueError("数据平均时间与限值不匹配；仅作参考时必须显式 reference_only=True。")
    label = limit["label"]
    if reference_only:
        label += "（仅供参考，不作该时段达标判定）"
    line = ax.axhline(limit["value"], color="#5F5E5A", linestyle="--", linewidth=1.2,
                      label=label)
    line.environment_standard = {**limit, "reference_only": reference_only}
    # Explicit y-limits must not silently hide the standard line.
    low, high = ax.get_ylim()
    inverted = low > high
    low, high = sorted((low, high))
    padding = max(high - low, abs(limit["value"]), 1) * 0.04
    low, high = min(low, limit["value"] - padding), max(high, limit["value"] + padding)
    ax.set_ylim((high, low) if inverted else (low, high))
    return line


def legend_below(ax, *other_axes, handles=None, labels=None, ncols=3):
    """Collect explicit labels (including twin axes) and place below x labels."""
    if not isinstance(ncols, int) or ncols < 1:
        raise ValueError("ncols 必须为正整数。")
    if handles is None and labels is None:
        handles, labels = [], []
        for source in (ax, *other_axes):
            source_handles, source_labels = source.get_legend_handles_labels()
            handles.extend(source_handles)
            labels.extend(source_labels)
    if handles is None or labels is None or len(handles) != len(labels):
        raise ValueError("handles 与 labels 必须配对。")
    entries = {label: handle for handle, label in zip(handles, labels)
               if label and not label.startswith("_")}
    if not entries:
        raise ValueError("请给数据系列设置 label，或提供等级色块；热力图可使用带单位的色标。")
    for source in (ax, *other_axes):
        previous = source.get_legend()
        if previous is not None:
            previous.remove()
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    decoration = ax.get_tightbbox(renderer)
    bottom = ax.transAxes.inverted().transform((decoration.x0, decoration.y0))[1]
    legend = ax.legend(list(entries.values()), list(entries), loc="upper center",
                       bbox_to_anchor=(0.5, min(bottom, 0) - 0.04),
                       ncols=min(ncols, len(entries)), frameon=False, borderaxespad=0)
    legend.set_in_layout(True)
    return legend
