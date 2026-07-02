"""O3 transfer quality checks for operations work order audits."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


RULE_ID = "RF_O3_TRANSFER_RESULT_INVALID"
RF_TABLE = "RF_HY_O3VALUEPASS"
MIN_VALID_POINTS = 3
MAX_RELATIVE_DIFF_PERCENT = 2.0


def check_o3_transfer_quality_values(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Check O3 transfer point count and relative differences."""

    # Disabled until RF_HY_O3VALUEPASS field mapping is confirmed. Real June
    # records show DELIVER/WORKDENSITY fields are transposed template cells, so
    # comparing them as reference/work transfer points creates broad false
    # positives.
    return

    for table, form in forms:
        if form.get("_query_error") or table != RF_TABLE:
            continue
        points = _transfer_points(form)
        valid_points = [point for point in points if point.get("is_valid")]
        violations: list[dict[str, Any]] = []
        if len(valid_points) < MIN_VALID_POINTS:
            violations.append(
                {
                    "reason": "valid_point_count_below_minimum",
                    "valid_point_count": len(valid_points),
                    "minimum": MIN_VALID_POINTS,
                }
            )
        for point in valid_points:
            reference = point["reference_value"]
            if reference == 0:
                continue
            relative_diff = (point["work_value"] - reference) / reference * 100
            if abs(relative_diff) > MAX_RELATIVE_DIFF_PERCENT:
                violations.append(
                    {
                        "reason": "relative_difference_out_of_range",
                        "point": point["point"],
                        "field": point["work_field"],
                        "reference_field": point["reference_field"],
                        "reference_value": reference,
                        "work_value": point["work_value"],
                        "relative_diff_percent": round(relative_diff, 3),
                        "expected_abs_max_percent": MAX_RELATIVE_DIFF_PERCENT,
                    }
                )
        if not violations:
            continue
        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE") or form.get("WORKINGORDERCODE"),
            "rf_table": table,
            "valid_point_count": len(valid_points),
            "points": points,
            "violations": violations[:20],
        }
        add_issue(
            issues,
            RULE_ID,
            "表单结果合理性",
            "高",
            f"rf.{table}.transfer_result",
            _message(violations[0]),
            json.dumps(evidence, ensure_ascii=False, default=str),
        )


def _message(first: dict[str, Any]) -> str:
    if first.get("reason") == "valid_point_count_below_minimum":
        return f"O3量值传递有效传递点数量不足: {first.get('valid_point_count')} < {first.get('minimum')}"
    if first.get("reason") == "relative_difference_out_of_range":
        return (
            "O3量值传递传递点相对偏差超过±2%: "
            f"第{first.get('point')}点 {first.get('relative_diff_percent')}%"
        )
    return "O3量值传递结果不符合要求"


def _transfer_points(form: dict[str, Any]) -> list[dict[str, Any]]:
    points = []
    for point in range(1, 7):
        reference_field = f"DELIVER{point}VALUE"
        work_field = f"WORKDENSITY{point}VALUE"
        reference = _num(form.get(reference_field))
        work = _num(form.get(work_field))
        points.append(
            {
                "point": point,
                "reference_field": reference_field,
                "work_field": work_field,
                "reference_raw_value": form.get(reference_field),
                "work_raw_value": form.get(work_field),
                "reference_value": reference,
                "work_value": work,
                "is_valid": reference is not None and work is not None,
            }
        )
    return points


def _num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip()
    if text in {"", "/", "-", "无", "NA", "N/A", "nan", "NaN", "null"}:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    return float(match.group(0))
