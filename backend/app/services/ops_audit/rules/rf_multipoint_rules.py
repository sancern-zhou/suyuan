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
PROFILES = load_yaml_config("rf_multipoint_profiles.yaml", {})
SKIP_TOKENS = {"", "/", "-", "nan", "none", "null", "无", "无该项指标", "不适用", "未填写"}


def check_rf_multipoint_values(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
    all_orders: list[dict[str, Any]] | None = None,
    forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]] | None = None,
) -> None:
    """Check multipoint calibration fields.

    Range consistency is checked against the previous same-station, same-table
    record instead of a fixed pollutant-specific range.
    """

    table_profiles = PROFILES.get("tables", {})
    if not table_profiles:
        return

    for table, form in forms:
        if form.get("_query_error") or table not in table_profiles:
            continue

        profile = table_profiles[table]
        comparison = _range_change_comparison(
            order,
            table,
            form,
            profile,
            all_orders or [],
            forms_by_code or {},
        )
        if comparison is None:
            continue

        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "current_order_code": order.get("WORKINGORDERCODE"),
            "rf_table": table,
            "pollutant": profile.get("pollutant"),
            **comparison,
        }
        add_issue(
            issues,
            RULE_ID,
            "表单数值逻辑",
            "高",
            f"rf.{table}.{comparison['current_field']}",
            (
                f"多点校准量程发生变化: {profile.get('pollutant')} 当前量程 "
                f"{comparison['current_range']:g}，上一条同站点同类表单量程 "
                f"{comparison['previous_range']:g}"
            ),
            json.dumps(evidence, ensure_ascii=False, default=str),
        )


def _range_change_comparison(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    profile: dict[str, Any],
    all_orders: list[dict[str, Any]],
    forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]],
) -> dict[str, Any] | None:
    if not all_orders or not forms_by_code:
        return None

    current_range = _first_range_value(form, profile.get("range_fields", []))
    if current_range is None:
        return None

    previous = _previous_same_station_same_table_record(order, table, form, all_orders, forms_by_code)
    if previous is None:
        return None

    previous_order, _, previous_form = previous
    previous_range = _first_range_value(previous_form, profile.get("range_fields", []))
    if previous_range is None:
        return None

    tolerance = float(profile.get("history_tolerance", profile.get("tolerance", 1)) or 1)
    if abs(current_range["value"] - previous_range["value"]) <= tolerance:
        return None

    return {
        "station_id": _form_station(order, form),
        "current_field": current_range["field"],
        "current_raw_value": current_range["raw_value"],
        "current_range": current_range["value"],
        "previous_order_code": previous_order.get("WORKINGORDERCODE"),
        "previous_reference_time": _format_time(_form_reference_time(previous_order, previous_form)),
        "previous_field": previous_range["field"],
        "previous_raw_value": previous_range["raw_value"],
        "previous_range": previous_range["value"],
        "tolerance": tolerance,
    }


def _first_range_value(form: dict[str, Any], fields: list[str]) -> dict[str, Any] | None:
    for field in fields:
        if field not in form:
            continue
        raw_value = form.get(field)
        value = _range_number(raw_value)
        if value is None:
            continue
        return {"field": field, "raw_value": raw_value, "value": value}
    return None


def _previous_same_station_same_table_record(
    current_order: dict[str, Any],
    current_table: str,
    current_form: dict[str, Any],
    all_orders: list[dict[str, Any]],
    forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]],
) -> tuple[dict[str, Any], str, dict[str, Any]] | None:
    station_id = _form_station(current_order, current_form)
    if not station_id:
        return None

    current_time = _form_reference_time(current_order, current_form)
    current_code = str(current_order.get("WORKINGORDERCODE") or current_form.get("WORKINGORDERCODE") or "")
    previous: tuple[datetime, dict[str, Any], str, dict[str, Any]] | None = None

    for other_order in all_orders:
        other_code = str(other_order.get("WORKINGORDERCODE") or "")
        if not other_code or other_code == current_code:
            continue
        for other_table, other_form in forms_by_code.get(other_code, []):
            if other_table != current_table or other_form.get("_query_error"):
                continue
            if _form_station(other_order, other_form) != station_id:
                continue
            other_time = _form_reference_time(other_order, other_form)
            if current_time and other_time and other_time >= current_time:
                continue
            if current_time and not other_time:
                continue
            candidate_time = other_time or datetime.min
            if previous is None or candidate_time > previous[0]:
                previous = (candidate_time, other_order, other_table, other_form)

    if previous is None:
        return None
    _, other_order, other_table, other_form = previous
    return other_order, other_table, other_form


def _form_station(order: dict[str, Any], form: dict[str, Any]) -> str:
    return str(form.get("STATIONID") or order.get("STATIONID") or "").strip()


def _form_reference_time(order: dict[str, Any], form: dict[str, Any]) -> datetime | None:
    for field in (
        "CALIBRATIONDATE",
        "CHECKTIME",
        "CHECKDATETIME",
        "CHECKDATE",
        "CREATEDATE",
        "STARTTIME",
        "StartTime",
        "SdtTime",
        "CheckSdt",
    ):
        parsed = _parse_time(form.get(field))
        if parsed:
            return parsed
    return _parse_time(order.get("CREATETIME"))


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
