"""RF calibration date validity checks for operations work order audits."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.services.ops_audit.config import load_yaml_config
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


RULE_ID = "RF_CALIBRATION_DATE_EXPIRED"
PROFILES = load_yaml_config("rf_calibration_date_profiles.yaml", {})


def check_rf_calibration_dates(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
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
            if next_field and next_time and next_time < reference_time:
                violations.append(_violation(pair, prev_field, next_field, prev_time, next_time, reference_time, "expired_before_reference"))

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
