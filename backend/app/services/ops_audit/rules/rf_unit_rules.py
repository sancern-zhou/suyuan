"""RF form unit and value-scale checks for operations work order audits."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from app.services.ops_audit.config import load_yaml_config
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


RULE_ID = "RF_UNIT_MISMATCH"
UNIT_PROFILES = load_yaml_config("rf_unit_profiles.yaml", {})
SKIP_TOKENS = {"", "/", "-", "nan", "none", "null", "无", "无该项指标", "不适用", "未填写"}


def check_rf_unit_values(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Check whether RF units match the magnitude of related numeric values."""

    table_profiles = UNIT_PROFILES.get("tables", {})
    if not table_profiles:
        return

    for table, form in forms:
        if form.get("_query_error") or table not in table_profiles:
            continue

        violations = []
        for check in table_profiles.get(table, {}).get("checks", []):
            violations.extend(_check_unit_scale(table, form, check))

        if not violations:
            continue

        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "rf_table": table,
            "violation_count": len(violations),
            "violations": violations[:20],
        }
        first = violations[0]
        add_issue(
            issues,
            RULE_ID,
            "表单数值逻辑",
            "中",
            f"rf.{table}.unit",
            f"RF表单单位与数值量级不匹配: {first.get('label')} {first.get('field')}={first.get('value')} {first.get('unit')}",
            json.dumps(evidence, ensure_ascii=False, default=str),
        )


def _check_unit_scale(table: str, form: dict[str, Any], check: dict[str, Any]) -> list[dict[str, Any]]:
    unit_field = str(check.get("unit_field") or "")
    fixed_unit = _normalize_unit(check.get("fixed_unit"))
    if not fixed_unit and (not unit_field or unit_field not in form):
        return []

    unit_text = str(form.get(unit_field) or "") if unit_field else str(check.get("fixed_unit") or "")
    unit = fixed_unit or _extract_unit(unit_text)
    if not unit:
        return []

    allowed_units = {_normalize_unit(unit) for unit in check.get("allowed_units", []) if _normalize_unit(unit)}
    if allowed_units and unit not in allowed_units:
        return [
            {
                "rf_table": table,
                "check_id": check.get("id"),
                "label": check.get("label"),
                "field": unit_field,
                "raw_unit_text": unit_text,
                "unit": unit,
                "allowed_units": sorted(allowed_units),
                "reason": "unit_not_allowed",
            }
        ]

    scale = check.get("unit_scales", {}).get(unit)
    if not scale:
        return []

    min_value = _to_float(scale.get("min"))
    max_value = _to_float(scale.get("max"))
    violations = []
    for field in check.get("value_fields", []):
        if field not in form:
            continue
        value = _parse_number(form.get(field))
        if value is None:
            continue
        if min_value is not None and value < min_value:
            violations.append(_scale_violation(table, check, unit_field, unit_text, unit, field, value, min_value, max_value))
        elif max_value is not None and value > max_value:
            violations.append(_scale_violation(table, check, unit_field, unit_text, unit, field, value, min_value, max_value))
    return violations


def _scale_violation(
    table: str,
    check: dict[str, Any],
    unit_field: str,
    unit_text: str,
    unit: str,
    value_field: str,
    value: float,
    min_value: float | None,
    max_value: float | None,
) -> dict[str, Any]:
    return {
        "rf_table": table,
        "check_id": check.get("id"),
        "label": check.get("label"),
        "unit_field": unit_field,
        "raw_unit_text": unit_text,
        "unit": unit,
        "field": value_field,
        "value": value,
        "expected_min": min_value,
        "expected_max": max_value,
        "reason": "value_scale_outside_unit_range",
    }


def _extract_unit(text: str) -> str | None:
    normalized = text.replace("／", "/").replace("﹨", "/").replace("每", "/")
    normalized = re.sub(r"\s+", "", normalized)
    lower = normalized.lower()
    if re.search(r"(?:ml|毫升)/(?:min|分钟)|(?:ml|毫升)(?:/)?(?:min|分钟)", lower):
        return "ml/min"
    if re.search(r"(?:l|升)/(?:min|分钟)|(?:l|升)(?:/)?(?:min|分钟)", lower):
        return "L/min"
    return None


def _normalize_unit(unit: Any) -> str | None:
    text = str(unit or "").strip()
    if not text:
        return None
    lower = text.lower().replace(" ", "")
    if lower in {"ml/min", "mlmin", "毫升/分钟", "毫升每分钟"}:
        return "ml/min"
    if lower in {"l/min", "lmin", "升/分钟", "升每分钟"}:
        return "L/min"
    return text


def _parse_number(value: Any) -> float | None:
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


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
