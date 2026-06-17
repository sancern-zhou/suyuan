"""RF form enum and boolean value rules for operations work order audits."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.ops_audit.config import load_rf_enum_profiles
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue

RF_ENUM_PROFILES = load_rf_enum_profiles()

_RANGE_LIKE_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:-|~|至|到)\s*\d+(?:\.\d+)?")


def check_rf_enum_values(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Check configured enum/boolean fields for values outside allowed domains."""

    profiles = RF_ENUM_PROFILES.get("profiles", [])
    if not profiles:
        return

    for table, form in forms:
        if form.get("_query_error"):
            continue

        _check_pollutant_type(order, table, form, issues)

        for profile in profiles:
            if not _table_matches(table, profile.get("tables", [])):
                continue
            _check_profile(order, table, form, profile, issues)


def _check_profile(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    profile: dict[str, Any],
    issues: list[Issue],
) -> None:
    for field_profile in profile.get("fields", []):
        field = field_profile.get("name")
        if not field or field not in form:
            continue

        value = form.get(field)
        if value is None or str(value).strip() == "":
            continue

        value_text = _normalize(value)
        allowed_values = {_normalize(item) for item in field_profile.get("allowed_values", [])}
        range_like = bool(field_profile.get("disallow_range_like", True) and _RANGE_LIKE_RE.search(value_text))
        outside_allowed = bool(allowed_values and value_text not in allowed_values)

        if not range_like and not outside_allowed:
            continue

        reason = "range_text_in_enum_field" if range_like else "outside_allowed_values"
        severity = str(field_profile.get("severity") or ("高" if range_like else "中"))
        label = str(field_profile.get("label") or field)
        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "rf_table": table,
            "field": field,
            "label": label,
            "value": str(value).strip(),
            "allowed_values": list(field_profile.get("allowed_values", [])),
            "reason": reason,
        }

        add_issue(
            issues,
            "RF_ENUM_VALUE_INVALID",
            "表单填报一致性",
            severity,
            f"rf.{table}.{field}",
            f"RF表单枚举字段取值异常: {label}={str(value).strip()}",
            json.dumps(evidence, ensure_ascii=False, default=str),
        )


def _table_matches(table: str, patterns: list[Any]) -> bool:
    if not patterns:
        return False
    for pattern in patterns:
        pattern_text = str(pattern)
        if pattern_text == table:
            return True
        if pattern_text.endswith("*") and table.startswith(pattern_text[:-1]):
            return True
    return False


def _check_pollutant_type(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    issues: list[Issue],
) -> None:
    for profile in RF_ENUM_PROFILES.get("pollutant_type_profiles", []):
        if str(profile.get("table")) != table:
            continue

        expected = _normalize_pollutant(profile.get("expected"))
        if not expected:
            continue

        for field in profile.get("fields", []):
            if field not in form:
                continue
            value = form.get(field)
            if value is None or str(value).strip() == "":
                continue
            actual = _normalize_pollutant(value)
            if actual == expected:
                continue

            evidence = {
                "working_order_code": order.get("WORKINGORDERCODE"),
                "rf_table": table,
                "field": field,
                "expected": expected,
                "actual": str(value).strip(),
            }
            add_issue(
                issues,
                "RF_POLLUTANT_TYPE_MISMATCH",
                "表单填报一致性",
                str(profile.get("severity") or "高"),
                f"rf.{table}.{field}",
                f"RF表单污染物类型与表名不一致: {field}={str(value).strip()}, expected={expected}",
                json.dumps(evidence, ensure_ascii=False, default=str),
            )


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper().replace("－", "-").replace("—", "-").replace("～", "~")


def _normalize_pollutant(value: Any) -> str:
    text = str(value).strip().upper().replace(".", "")
    aliases = {
        "PM25": "PM2.5",
        "PM2_5": "PM2.5",
        "NOX": "NOX",
        "NO": "NO",
        "NO2": "NO2",
        "SO2": "SO2",
        "O3": "O3",
        "CO": "CO",
    }
    return aliases.get(text, text)
