"""RF multipoint calibration checks for operations work order audits."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from typing import Any

from app.services.ops_audit.config import load_yaml_config
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


RULE_ID = "RF_MULTIPOINT_RANGE_INVALID"
TIME_RULE_ID = "RF_Q_MULTIPOINT_STEP_TIME_INVALID"
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

        time_violations = _check_step_times(table, form)
        if time_violations:
            evidence = {
                "working_order_code": order.get("WORKINGORDERCODE"),
                "rf_table": table,
                "violations": time_violations[:20],
            }
            first = time_violations[0]
            add_issue(
                issues,
                TIME_RULE_ID,
                "时间合理性",
                "高",
                f"rf.{table}.{first.get('field')}",
                f"多点校准时间异常: {first.get('label')} {first.get('reason')}",
                json.dumps(evidence, ensure_ascii=False, default=str),
            )

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


def _check_step_times(table: str, form: dict[str, Any]) -> list[dict[str, Any]]:
    if not table.startswith("RF_Q_GASEOUSMULTIPOINT_"):
        return []

    steps = _available_steps(form)

    violations = []
    for step_id, label, start_field, end_field in steps:
        start = _parse_time(form.get(start_field))
        end = _parse_time(form.get(end_field))
        if not start and not end:
            continue
        if start and end:
            if end < start:
                violations.append(
                    _time_violation(label, end_field, start, end, "结束时间早于开始时间")
                )
            hours = (end - start).total_seconds() / 3600
            if hours > 6:
                violations.append(
                    _time_violation(label, end_field, start, end, "单点持续时间异常过长")
                )
    order_violation = _sequence_violation(steps, form)
    if order_violation:
        violations.append(order_violation)
    return violations


def _available_steps(form: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    step_defs = [("zero", "零点", "LINGDIANSDTDATE", "LINGDIANEDTDATE")]
    step_defs.extend(
        (point, f"{point}%点", f"MCLSDTDATE{point}", f"MCLEDTDATE{point}")
        for point in ("10", "20", "40", "60", "80")
    )
    return [
        step
        for step in step_defs
        if _parse_time(form.get(step[2])) or _parse_time(form.get(step[3]))
    ]


def _sequence_violation(
    steps: list[tuple[str, str, str, str]],
    form: dict[str, Any],
) -> dict[str, Any] | None:
    intervals = []
    for step_id, label, start_field, end_field in steps:
        start = _parse_time(form.get(start_field))
        end = _parse_time(form.get(end_field))
        if not start:
            continue
        intervals.append(
            {
                "step": step_id,
                "label": label,
                "field": start_field,
                "start": start,
                "end": end,
            }
        )
    if len(intervals) < 2:
        return None

    chronological = sorted(intervals, key=lambda item: item["start"])
    step_order = [item["step"] for item in chronological]
    allowed_orders = [
        ["zero", "10", "20", "40", "60", "80"],
        ["80", "60", "40", "20", "10", "zero"],
    ]
    compact_allowed = [
        [step for step in allowed if step in step_order]
        for allowed in allowed_orders
    ]
    if step_order in compact_allowed:
        return None

    return {
        "step": chronological[0]["step"],
        "label": chronological[0]["label"],
        "field": chronological[0]["field"],
        "observed_order": step_order,
        "allowed_orders": compact_allowed,
        "reason": "多点校准点位时间顺序既不符合升序也不符合降序作业",
    }


def _time_violation(
    label: str,
    field: str,
    start: datetime,
    end: datetime,
    reason: str,
) -> dict[str, Any]:
    return {
        "label": label,
        "field": field,
        "start_time": _format_time(start),
        "end_time": _format_time(end),
        "duration_hours": round((end - start).total_seconds() / 3600, 3),
        "reason": reason,
    }


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _format_time(value: datetime | None) -> str | None:
    if not value:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


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
