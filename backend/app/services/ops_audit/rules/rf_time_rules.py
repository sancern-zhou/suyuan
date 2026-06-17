"""RF form time range rules for operations work order audits."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from app.services.ops_audit.config import load_rf_field_profiles
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue

RF_FIELD_PROFILES = load_rf_field_profiles()
TIME_ONLY_WINDOW_TABLES = {"RF_TW_PmFlowCalibrate", "RF_TW_PmFlowCheck"}

def check_rf_time_ranges(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Check RF form time ranges for validity.

    This rule identifies:
    - RF_CHECK_TIME_OUTSIDE_RANGE: Check time is outside the start/end time range
    - LIFECYCLE_FINISH_NEAR_DEADLINE: Order completed near planned deadline

    The rule is configurable via rf_field_profiles.yaml.
    """

    for table, form in forms:
        if form.get("_query_error"):
            continue

        _check_time_outside_range(order, table, form, issues)

    _check_finish_near_deadline(order, forms, issues)


def _check_time_outside_range(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    issues: list[Issue],
) -> None:
    """Check if check time is within start and end time range."""

    check_time_fields = RF_FIELD_PROFILES.get("check_time_fields", [])
    start_time_fields = RF_FIELD_PROFILES.get("start_time_fields", [])
    end_time_fields = RF_FIELD_PROFILES.get("end_time_fields", [])

    if not check_time_fields or not start_time_fields or not end_time_fields:
        return

    if table in TIME_ONLY_WINDOW_TABLES:
        _check_time_only_window(order, table, form, issues)
        return

    check_time = _first_time_value(form, check_time_fields)
    start_time = _first_time_value(form, start_time_fields)
    end_time = _first_time_value(form, end_time_fields)

    if not check_time:
        return

    if start_time and end_time:
        if start_time <= check_time <= end_time:
            return

        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "rf_table": table,
            "check_time": _format_time(check_time),
            "start_time": _format_time(start_time),
            "end_time": _format_time(end_time),
            "time_range_hours": _hours_between(start_time, end_time),
        }

        direction = "早于" if check_time < start_time else "晚于"
        add_issue(
            issues,
            "RF_CHECK_TIME_OUTSIDE_RANGE",
            "时间合理性",
            "高",
            f"rf.{table}.check_time",
            f"RF表单检查时间{_format_time(check_time)}{direction}开始结束时间范围({_format_time(start_time)} 至 {_format_time(end_time)})",
            json.dumps(evidence, ensure_ascii=False, default=str),
        )
    elif start_time and check_time < start_time:
            evidence = {
                "working_order_code": order.get("WORKINGORDERCODE"),
                "rf_table": table,
                "check_time": _format_time(check_time),
                "start_time": _format_time(start_time),
                "end_time": None,
            }
            add_issue(
                issues,
                "RF_CHECK_TIME_OUTSIDE_RANGE",
                "时间合理性",
                "高",
                f"rf.{table}.check_time",
                f"RF表单检查时间{_format_time(check_time)}早于开始时间{_format_time(start_time)}",
                json.dumps(evidence, ensure_ascii=False, default=str),
            )
    elif end_time and check_time > end_time:
            evidence = {
                "working_order_code": order.get("WORKINGORDERCODE"),
                "rf_table": table,
                "check_time": _format_time(check_time),
                "start_time": None,
                "end_time": _format_time(end_time),
            }
            add_issue(
                issues,
                "RF_CHECK_TIME_OUTSIDE_RANGE",
                "时间合理性",
                "高",
                f"rf.{table}.check_time",
                f"RF表单检查时间{_format_time(check_time)}晚于结束时间{_format_time(end_time)}",
                json.dumps(evidence, ensure_ascii=False, default=str),
            )


def _check_time_only_window(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    issues: list[Issue],
) -> None:
    check_time = _parse_time(form.get("CHECKDATE"))
    start_time = _parse_time(form.get("CheckSdt"))
    end_time = _parse_time(form.get("CheckEdt"))
    if not check_time or not start_time or not end_time:
        return

    check_clock = check_time.time()
    start_clock = start_time.time()
    end_clock = end_time.time()
    if _clock_in_window(check_clock, start_clock, end_clock):
        return

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "check_time": _format_time(check_time),
        "start_time": _format_time(start_time),
        "end_time": _format_time(end_time),
        "check_clock": check_clock.strftime("%H:%M:%S"),
        "start_clock": start_clock.strftime("%H:%M:%S"),
        "end_clock": end_clock.strftime("%H:%M:%S"),
        "date_ignored": True,
    }
    add_issue(
        issues,
        "RF_CHECK_TIME_OUTSIDE_RANGE",
        "时间合理性",
        "高",
        f"rf.{table}.check_time",
        (
            f"RF表单检查时刻{check_clock.strftime('%H:%M:%S')}不在开始结束时段"
            f"({start_clock.strftime('%H:%M:%S')} 至 {end_clock.strftime('%H:%M:%S')})内"
        ),
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _clock_in_window(check_clock: Any, start_clock: Any, end_clock: Any) -> bool:
    if start_clock <= end_clock:
        return start_clock <= check_clock <= end_clock
    return check_clock >= start_clock or check_clock <= end_clock


def _check_finish_near_deadline(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Check if order was completed near the planned deadline."""

    near_deadline_hours = float(RF_FIELD_PROFILES.get("near_deadline_hours", 4) or 4)
    plan_finish = _parse_time(order.get("PLANFINISHTIME"))
    actual_finish = _parse_time(order.get("FINISHTIME"))
    create_time = _parse_time(order.get("CREATETIME"))

    if not plan_finish or not actual_finish:
        return

    time_to_deadline = _hours_between(actual_finish, plan_finish)

    if time_to_deadline is None or abs(time_to_deadline) > near_deadline_hours:
        return

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "create_time": _format_time(create_time),
        "plan_finish_time": _format_time(plan_finish),
        "actual_finish_time": _format_time(actual_finish),
        "hours_to_deadline": time_to_deadline,
        "near_deadline_hours": near_deadline_hours,
        "order_type": order.get("DDWORKINGORDERTYPE"),
        "maintenance_type": order.get("MAINTENANCETYPE"),
    }

    direction = "提前" if time_to_deadline >= 0 else "延后"
    add_issue(
        issues,
        "LIFECYCLE_FINISH_NEAR_DEADLINE",
        "生命周期闭环风险",
        "低",
        "working_order.finish_near_deadline",
        f"工单{direction}{abs(time_to_deadline):.1f}小时完成(计划{_format_time(plan_finish)},实际{_format_time(actual_finish)})",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _first_time_value(record: dict[str, Any], fields: list[str]) -> datetime | None:
    """Get the first valid datetime value from the record."""
    for field in fields:
        value = record.get(field)
        if value:
            parsed = _parse_time(value)
            if parsed:
                return parsed
    return None


def _parse_time(value: Any) -> datetime | None:
    """Parse time value to datetime."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S.%f%z",
        "%m %d %Y %I:%M%p",
        "%m %d %Y  %I:%M%p",
    ):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _format_time(value: datetime | None) -> str:
    """Format datetime for display."""
    if not value:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _hours_between(start: datetime | None, end: datetime | None) -> float | None:
    """Calculate hours between two datetimes."""
    if not start or not end:
        return None
    return (end - start).total_seconds() / 3600
