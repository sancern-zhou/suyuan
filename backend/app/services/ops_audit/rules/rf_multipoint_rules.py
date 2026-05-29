"""RF multipoint calibration checks for operations work order audits."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from app.services.ops_audit.config import load_yaml_config
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


RULE_ID = "RF_MULTIPOINT_RANGE_INVALID"
PROFILES = load_yaml_config("rf_multipoint_profiles.yaml", {})
SKIP_TOKENS = {"", "/", "-", "nan", "none", "null", "无", "无该项指标", "不适用", "未填写"}


def check_rf_multipoint_values(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Check multipoint calibration range fields against pollutant-specific limits."""

    table_profiles = PROFILES.get("tables", {})
    if not table_profiles:
        return

    for table, form in forms:
        if form.get("_query_error") or table not in table_profiles:
            continue

        profile = table_profiles[table]
        expected = _to_float(profile.get("expected_range"))
        tolerance = float(profile.get("tolerance", 1) or 1)
        if expected is None:
            continue

        violations = []
        for field in profile.get("range_fields", []):
            if field not in form:
                continue
            raw_value = form.get(field)
            value = _range_number(raw_value)
            if value is None:
                continue
            if abs(value - expected) <= tolerance:
                continue
            violations.append(
                {
                    "rf_table": table,
                    "pollutant": profile.get("pollutant"),
                    "field": field,
                    "raw_value": raw_value,
                    "parsed_range": value,
                    "expected_range": expected,
                    "tolerance": tolerance,
                }
            )

        if not violations:
            continue

        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "rf_table": table,
            "pollutant": profile.get("pollutant"),
            "expected_range": expected,
            "violations": violations[:20],
        }
        first = violations[0]
        add_issue(
            issues,
            RULE_ID,
            "表单数值逻辑",
            "高",
            f"rf.{table}.{first['field']}",
            f"多点校准量程填写错误: {profile.get('pollutant')} 量程 {first['parsed_range']}，应为 {expected:g}",
            json.dumps(evidence, ensure_ascii=False, default=str),
        )


def _range_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in SKIP_TOKENS:
        return None
    normalized = re.sub(r"(?<=\d)\s*(?:~|～|-|—|－|至)\s*(?=\d)", " ", text.replace(",", ""))
    numbers = [_to_float(match) for match in re.findall(r"[-+]?\d+(?:\.\d+)?", normalized)]
    numbers = [number for number in numbers if number is not None]
    if not numbers:
        return None
    # For values like "0-500" or "0~20000", the upper bound is the configured range.
    return max(numbers)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
