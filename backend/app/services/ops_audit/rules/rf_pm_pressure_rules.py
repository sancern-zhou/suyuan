"""RF particulate pressure check rules."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


UNIT_RULE_ID = "RF_PM_PRESSURE_UNIT_MISMATCH"
ERROR_RULE_ID = "RF_PM_PRESSURE_ERROR_MISMATCH"
TABLE = "RF_Q_PMPRESSURE"
SKIP_VALUES = {"", "/", "-", "无", "不适用", "none", "null", "nan"}


def check_rf_pm_pressure_values(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Check quarterly particulate pressure values and error fields."""

    for table, form in forms:
        if form.get("_query_error") or table != TABLE:
            continue
        unit_violations = []
        error_violations = []
        for pollutant in ("PM10", "PM25"):
            standard = _num(form.get(f"{pollutant}CHECKPRES1VALUE"))
            measured = _num(form.get(f"{pollutant}CHECKPRES2VALUE"))
            actual_error = _num(form.get(f"{pollutant}CHECKPRES3VALUE"))
            for field, value in (
                (f"{pollutant}CHECKPRES1VALUE", standard),
                (f"{pollutant}CHECKPRES2VALUE", measured),
            ):
                if value is not None and not 800 <= value <= 1100:
                    unit_violations.append(
                        {
                            "pollutant": pollutant,
                            "field": field,
                            "raw_value": form.get(field),
                            "parsed_value": value,
                            "expected_unit": "hPa",
                            "expected_range": "800-1100",
                        }
                    )
            if standard is None or measured is None or actual_error is None:
                continue
            expected_error = standard - measured
            if abs(actual_error - expected_error) > 0.2:
                error_violations.append(
                    {
                        "pollutant": pollutant,
                        "field": f"{pollutant}CHECKPRES3VALUE",
                        "actual": actual_error,
                        "expected": round(expected_error, 6),
                        "delta": round(actual_error - expected_error, 6),
                        "inputs": {
                            f"{pollutant}CHECKPRES1VALUE": standard,
                            f"{pollutant}CHECKPRES2VALUE": measured,
                        },
                    }
                )

        if unit_violations:
            _add_issue(order, table, issues, UNIT_RULE_ID, "表单数值逻辑", "高", unit_violations, "颗粒物气压字段数值量级不符合 hPa 常见范围")
        if error_violations:
            _add_issue(order, table, issues, ERROR_RULE_ID, "表单数值逻辑", "高", error_violations, "颗粒物气压误差字段复算不一致")


def _add_issue(
    order: dict[str, Any],
    table: str,
    issues: list[Issue],
    rule_id: str,
    category: str,
    severity: str,
    violations: list[dict[str, Any]],
    message: str,
) -> None:
    first = violations[0]
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "violation_count": len(violations),
        "violations": violations[:20],
    }
    add_issue(
        issues,
        rule_id,
        category,
        severity,
        f"rf.{table}.{first['field']}",
        message,
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip().replace("％", "%").replace(",", "")
    if text.lower() in SKIP_VALUES:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None

