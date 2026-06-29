"""RF form field-position heuristics for operations work order audits."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from app.services.ops_audit.config import load_yaml_config
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


RULE_ID = "RF_FIELD_POSITION_SUSPECT"
POSITION_PROFILES = load_yaml_config("rf_position_profiles.yaml", {})
SKIP_TOKENS = {"", "/", "-", "nan", "none", "null", "无", "无该项指标", "不适用", "未填写"}


def check_rf_field_positions(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Detect likely RF value fields filled with another field's content."""

    table_profiles = POSITION_PROFILES.get("tables", {})
    if not table_profiles:
        return

    for table, form in forms:
        if form.get("_query_error") or table not in table_profiles:
            continue

        profile = table_profiles.get(table, {})
        violations = []
        violations.extend(_check_range_text_in_value_fields(table, form, profile))
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
            f"rf.{table}.field_position",
            f"RF表单字段位置疑似错填: {first.get('suggested_check')}",
            json.dumps(evidence, ensure_ascii=False, default=str),
        )


def _check_range_text_in_value_fields(table: str, form: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    violations = []
    for field in profile.get("range_text_fields", []):
        if field not in form:
            continue
        raw = form.get(field)
        if not _looks_like_range_text(raw):
            continue
        violations.append(
            {
                "rf_table": table,
                "field": field,
                "raw_value": raw,
                "reason": "range_text_in_numeric_value_field",
                "suggested_check": f"{field} 数值字段疑似填入量程/范围文本",
            }
        )
    return violations


def _check_swapped_error_formula(table: str, form: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    violations = []
    for check in profile.get("swap_formula_checks", []):
        left_field = str(check.get("left_field") or "")
        right_field = str(check.get("right_field") or "")
        error_field = str(check.get("error_field") or "")
        tolerance = float(check.get("tolerance", 0.2) or 0.2)
        left = _num(form.get(left_field))
        right = _num(form.get(right_field))
        actual_error = _num(form.get(error_field))
        if left is None or right in (None, 0) or actual_error is None:
            continue

        original_expected = (left - right) / right * 100
        original_delta = abs(actual_error - original_expected)
        if left == 0:
            continue
        swapped_expected = (right - left) / left * 100
        swapped_delta = abs(actual_error - swapped_expected)
        if original_delta <= tolerance or swapped_delta > tolerance:
            continue

        violations.append(
            {
                "rf_table": table,
                "check_id": check.get("id"),
                "label": check.get("label"),
                "suspect_fields": [left_field, right_field],
                "error_field": error_field,
                "actual_error": round(actual_error, 6),
                "original_expected": round(original_expected, 6),
                "swapped_expected": round(swapped_expected, 6),
                "original_formula_delta": round(original_delta, 6),
                "swapped_formula_delta": round(swapped_delta, 6),
                "reason": "swapped_fields_match_error_formula",
                "suggested_check": f"{left_field} 和 {right_field} 疑似填反",
            }
        )
    return violations


def _looks_like_range_text(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if text.lower() in SKIP_TOKENS:
        return False
    if re.search(r"\d\s*(?:~|～|至|-|—|－)\s*\d", text):
        return True
    if re.search(r"\d\s*(?:±|\+/-)\s*\d", text):
        return True
    if re.search(r"[A-Za-z]\d+\s*(?:~|～|至|-|—|－)\s*[A-Za-z]?\d+", text):
        return True
    return False


def _num(value: Any) -> float | None:
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
