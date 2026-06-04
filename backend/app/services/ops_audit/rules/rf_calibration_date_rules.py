"""RF calibration date validity checks for operations work order audits."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.services.ops_audit.config import load_yaml_config
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


RULE_ID = "RF_CALIBRATION_DATE_EXPIRED"
PREV_MISMATCH_RULE_ID = "RF_CALIBRATION_PREV_DATE_MISMATCH"
PROFILES = load_yaml_config("rf_calibration_date_profiles.yaml", {})


def check_rf_calibration_dates(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
    *,
    all_orders: list[dict[str, Any]] | None = None,
    forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]] | None = None,
) -> None:
    """Check calibration validity periods against the RF reference time."""

    table_profiles = PROFILES.get("tables", {})
    if not table_profiles:
        return

    for table, form in forms:
        if form.get("_query_error") or table not in table_profiles:
            continue
        profile = table_profiles[table]
        reference_time = _first_time(form, profile.get("reference_time_fields", [])) or _parse_time(order.get("CREATETIME"))
        if not reference_time:
            continue

        violations = []
        for pair in profile.get("pairs", []):
            prev_field = pair.get("prev_field")
            next_field = pair.get("next_field")
            prev_time = _parse_time(form.get(prev_field)) if prev_field else None
            next_time = _parse_time(form.get(next_field)) if next_field else None
            if prev_field and next_field and prev_time and next_time and prev_time > next_time:
                violations.append(_violation(pair, prev_field, next_field, prev_time, next_time, reference_time, "prev_after_next"))
                continue
            if pair.get("prev_must_not_after_reference") and prev_field and prev_time and prev_time > reference_time:
                violations.append(_violation(pair, prev_field, next_field, prev_time, next_time, reference_time, "prev_after_reference"))
                continue
            if next_field and next_time and next_time <= reference_time:
                violations.append(_violation(pair, prev_field, next_field, prev_time, next_time, reference_time, "not_after_reference"))
            if pair.get("prev_must_match_actual_previous") and prev_field and prev_time:
                previous = _previous_same_station_table_reference(
                    order,
                    table,
                    form,
                    reference_time,
                    profile.get("reference_time_fields", []),
                    all_orders or [],
                    forms_by_code or {},
                )
                if previous and prev_time.date() != previous["reference_time"].date():
                    _add_previous_mismatch_issue(
                        order,
                        table,
                        pair,
                        prev_field,
                        prev_time,
                        previous,
                        issues,
                    )

        if not violations:
            continue

        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "rf_table": table,
            "reference_time": _format_time(reference_time),
            "violations": violations[:20],
        }
        first = violations[0]
        add_issue(
            issues,
            RULE_ID,
            "时间合理性",
            "高",
            f"rf.{table}.{first.get('next_field') or first.get('prev_field')}",
            f"RF表单校准有效期异常: {first.get('label')} {first.get('reason')}",
            json.dumps(evidence, ensure_ascii=False, default=str),
        )


def _add_previous_mismatch_issue(
    order: dict[str, Any],
    table: str,
    pair: dict[str, Any],
    prev_field: str,
    prev_time: datetime,
    previous: dict[str, Any],
    issues: list[Issue],
) -> None:
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "label": pair.get("label"),
        "prev_field": prev_field,
        "filled_previous_time": _format_time(prev_time),
        "actual_previous_time": _format_time(previous["reference_time"]),
        "previous_order_code": previous.get("working_order_code"),
        "previous_table": previous.get("table"),
        "reason": "prev_not_actual_previous_reference",
    }
    add_issue(
        issues,
        PREV_MISMATCH_RULE_ID,
        "时间合理性",
        "高",
        f"rf.{table}.{prev_field}",
        f"RF表单上一次校准日期与系统上一条同站点作业日期不一致: {pair.get('label')}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _previous_same_station_table_reference(
    current_order: dict[str, Any],
    current_table: str,
    current_form: dict[str, Any],
    current_reference_time: datetime,
    reference_fields: list[str],
    all_orders: list[dict[str, Any]],
    forms_by_code: dict[str, list[tuple[str, dict[str, Any]]]],
) -> dict[str, Any] | None:
    station_id = _station_id(current_order, current_form)
    current_code = str(current_order.get("WORKINGORDERCODE") or "")
    if not station_id or not current_code:
        return None

    orders_by_code = {
        str(order.get("WORKINGORDERCODE")): order
        for order in all_orders
        if order.get("WORKINGORDERCODE")
    }
    previous: dict[str, Any] | None = None
    for order_code, form_rows in forms_by_code.items():
        other_code = str(order_code or "")
        if not other_code or other_code == current_code:
            continue
        other_order = orders_by_code.get(other_code, {"WORKINGORDERCODE": other_code})
        for other_table, other_form in form_rows:
            if other_table != current_table or other_form.get("_query_error"):
                continue
            if _station_id(other_order, other_form) != station_id:
                continue
            other_reference_time = _first_time(other_form, reference_fields) or _parse_time(other_order.get("CREATETIME"))
            if not other_reference_time or other_reference_time >= current_reference_time:
                continue
            if previous is None or other_reference_time > previous["reference_time"]:
                previous = {
                    "working_order_code": other_code,
                    "table": other_table,
                    "reference_time": other_reference_time,
                }
    return previous


def _station_id(order: dict[str, Any], form: dict[str, Any]) -> str:
    return str(form.get("STATIONID") or order.get("STATIONID") or "").strip()


def _violation(
    pair: dict[str, Any],
    prev_field: str | None,
    next_field: str | None,
    prev_time: datetime | None,
    next_time: datetime | None,
    reference_time: datetime,
    reason: str,
) -> dict[str, Any]:
    return {
        "label": pair.get("label"),
        "prev_field": prev_field,
        "next_field": next_field,
        "prev_time": _format_time(prev_time),
        "next_time": _format_time(next_time),
        "reference_time": _format_time(reference_time),
        "reason": reason,
    }


def _first_time(record: dict[str, Any], fields: list[str]) -> datetime | None:
    for field in fields:
        parsed = _parse_time(record.get(field))
        if parsed:
            return parsed
    return None


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
        "%Y/%m/%d",
        "%Y/%m/%d %H:%M:%S",
        "%m %d %Y %I:%M%p",
        "%m %d %Y  %I:%M%p",
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
