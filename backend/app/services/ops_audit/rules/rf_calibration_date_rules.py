"""RF calibration date validity checks for operations work order audits."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from app.services.ops_audit.config import load_yaml_config
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


RULE_ID = "RF_CALIBRATION_DATE_EXPIRED"
INTERVAL_RULE_ID = "RF_CALIBRATION_INTERVAL_TOO_LONG"
SHOULD_BE_EMPTY_RULE_ID = "RF_CALIBRATION_DATE_SHOULD_BE_EMPTY"
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
            if _is_o3_multipoint_no_cylinder_pair(table, form, pair, next_field):
                if _has_value(form.get(next_field)):
                    _add_o3_no_cylinder_date_should_be_empty_issue(order, table, form, pair, next_field, issues)
                continue
            if prev_field and next_field and prev_time and next_time and prev_time > next_time:
                violations.append(_violation(pair, prev_field, next_field, prev_time, next_time, reference_time, "prev_after_next"))
                continue
            if prev_field and next_field and prev_time and next_time:
                max_next_time = _calendar_years_after(prev_time, 2)
                if next_time > max_next_time:
                    _add_interval_too_long_issue(
                        order,
                        table,
                        pair,
                        prev_field,
                        next_field,
                        prev_time,
                        next_time,
                        max_next_time,
                        reference_time,
                        issues,
                    )
            if pair.get("prev_must_not_after_reference") and prev_field and prev_time and prev_time > reference_time:
                violations.append(_violation(pair, prev_field, next_field, prev_time, next_time, reference_time, "prev_after_reference"))
                continue
            # 校准有效期字段按自然日记录；截止日当天仍有效，不能因为截止日期
            # 被解析为 00:00:00 而把当天稍后的检查误判为过期。
            if next_field and next_time and next_time.date() < reference_time.date():
                violations.append(_violation(pair, prev_field, next_field, prev_time, next_time, reference_time, "not_after_reference"))
        if not violations:
            continue

        for violation in violations[:20]:
            evidence = {
                "working_order_code": order.get("WORKINGORDERCODE"),
                "rf_table": table,
                "reference_time": _format_time(reference_time),
                "violation": violation,
                "violations": [violation],
            }
            add_issue(
                issues,
                RULE_ID,
                "时间合理性",
                "高",
                f"rf.{table}.{violation.get('next_field') or violation.get('prev_field')}",
                f"RF表单校准有效期异常: {violation.get('description') or violation.get('label')}",
                json.dumps(evidence, ensure_ascii=False, default=str),
            )


def _is_o3_multipoint_no_cylinder_pair(
    table: str,
    form: dict[str, Any],
    pair: dict[str, Any],
    next_field: str | None,
) -> bool:
    if table != "RF_Q_GASEOUSMULTIPOINT_O3":
        return False
    if str(pair.get("label") or "") != "标气有效期" or next_field != "PPMCODEDATE":
        return False
    remark = _calibration_remark_text(form)
    return _mentions_no_o3_gas_cylinder(remark) or _o3_gas_cylinder_fields_are_placeholders(form)


def _add_o3_no_cylinder_date_should_be_empty_issue(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    pair: dict[str, Any],
    next_field: str | None,
    issues: list[Issue],
) -> None:
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "field": next_field,
        "label": pair.get("label"),
        "value": form.get(next_field) if next_field else None,
        "expected": "臭氧多点无标气瓶时，标气有效期字段应不填。",
    }
    add_issue(
        issues,
        SHOULD_BE_EMPTY_RULE_ID,
        "表单填写规范",
        "高",
        f"rf.{table}.{next_field or 'PPMCODEDATE'}",
        "臭氧多点校准无标气瓶，标气有效期应不填。",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _has_value(value: Any) -> bool:
    return str(value or "").strip() not in {"", "/", "-", "无", "无标气瓶", "无臭氧标气"}


def _add_interval_too_long_issue(
    order: dict[str, Any],
    table: str,
    pair: dict[str, Any],
    prev_field: str,
    next_field: str,
    prev_time: datetime,
    next_time: datetime,
    max_next_time: datetime,
    reference_time: datetime,
    issues: list[Issue],
) -> None:
    violation = _violation(
        pair,
        prev_field,
        next_field,
        prev_time,
        next_time,
        reference_time,
        "interval_over_two_years",
    )
    violation["max_next_time"] = _format_time(max_next_time)
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "reference_time": _format_time(reference_time),
        "violations": [violation],
    }
    add_issue(
        issues,
        INTERVAL_RULE_ID,
        "时间合理性",
        "高",
        f"rf.{table}.{next_field}",
        f"RF表单下次校准日期距上次校准日期超过两年: {pair.get('label')}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _calendar_years_after(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def _violation(
    pair: dict[str, Any],
    prev_field: str | None,
    next_field: str | None,
    prev_time: datetime | None,
    next_time: datetime | None,
    reference_time: datetime,
    reason: str,
) -> dict[str, Any]:
    label = str(pair.get("label") or "校准有效期")
    return {
        "label": pair.get("label"),
        "prev_field": prev_field,
        "next_field": next_field,
        "prev_time": _format_time(prev_time),
        "next_time": _format_time(next_time),
        "reference_time": _format_time(reference_time),
        "reason": reason,
        "description": _violation_description(label, prev_time, next_time, reference_time, reason),
    }


def _violation_description(
    label: str,
    prev_time: datetime | None,
    next_time: datetime | None,
    reference_time: datetime,
    reason: str,
) -> str:
    prev_text = _format_time(prev_time)
    next_text = _format_time(next_time)
    reference_text = _format_time(reference_time)
    if reason == "not_after_reference":
        return f"{label}至{next_text}，本次检查时间为{reference_text}"
    if reason == "prev_after_reference":
        return f"{label}的上次校准时间为{prev_text}，晚于本次检查时间{reference_text}"
    if reason == "prev_after_next":
        return f"{label}的上次校准时间为{prev_text}，晚于有效期截止时间{next_text}"
    if reason == "interval_over_two_years":
        return f"{label}从{prev_text}至{next_text}，有效期超过两年"
    return label


def _first_time(record: dict[str, Any], fields: list[str]) -> datetime | None:
    for field in fields:
        parsed = _parse_time(record.get(field))
        if parsed:
            return parsed
    return None


def _calibration_remark_text(form: dict[str, Any]) -> str:
    return "\n".join(
        str(form.get(field) or "").strip()
        for field in ("REMARK", "REMARKS", "CHECKREMARK", "DESCRIPTION")
        if str(form.get(field) or "").strip()
    )


def _mentions_no_o3_gas_cylinder(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    return bool(compact) and (
        "无标气瓶" in compact
        or "没有标气瓶" in compact
        or "无臭氧标气" in compact
        or "臭氧无标气" in compact
    )


def _o3_gas_cylinder_fields_are_placeholders(form: dict[str, Any]) -> bool:
    ppm = str(form.get("PPM") or "").strip()
    ppm_code = str(form.get("PPMCODE") or "").strip()
    placeholders = {"", "/", "-", "无", "无标气瓶", "无臭氧标气"}
    return ppm in placeholders and ppm_code in placeholders


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
