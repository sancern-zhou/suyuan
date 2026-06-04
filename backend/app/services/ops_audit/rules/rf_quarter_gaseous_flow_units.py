"""Unit helpers for quarterly gaseous flow RF values."""

from __future__ import annotations

import math
import re
from typing import Any


HIGH_FLOW_POINTS = {"85", "60", "35"}
LOW_FLOW_POINTS = {"80", "50", "20"}
QUARTER_GASEOUS_FLOW_PREFIXES = {"RF_Valuve", "RF_Qa", "RF_Qs"}
SKIP_TOKENS = {"", "/", "-", "nan", "none", "null", "无", "无该项指标", "不适用", "未填写"}


def normalize_quarter_gaseous_flow_to_l_min(field: str, value: Any) -> float | None:
    """Normalize quarterly gaseous flow fields to L/min for range/report checks.

    The RF form stores 85/60/35 flow points in ml/min, while 80/50/20 points are
    stored in L/min. Formula checks should still use original field units.
    """

    number = parse_quarter_gaseous_flow_number(value)
    if number is None:
        return None
    point = quarter_gaseous_flow_point(field)
    if point in HIGH_FLOW_POINTS:
        return round(number / 1000, 6)
    if point in LOW_FLOW_POINTS:
        return number
    return number


def quarter_gaseous_flow_point(field: str) -> str | None:
    text = str(field or "").strip()
    for prefix in QUARTER_GASEOUS_FLOW_PREFIXES:
        match = re.fullmatch(rf"{re.escape(prefix)}_(\d+)", text)
        if match:
            return match.group(1)
    return None


def parse_quarter_gaseous_flow_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip()
    if text.lower() in SKIP_TOKENS:
        return None
    text = text.replace("％", "%").replace("，", ",").replace(",", "")
    text = text.replace("＋", "+").replace("－", "-")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None
