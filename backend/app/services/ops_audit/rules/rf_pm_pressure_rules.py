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
TEMP_ERROR_RULE_ID = "RF_PM_TEMP_ERROR_MISMATCH"
TEMP_RANGE_RULE_ID = "RF_PM_TEMP_ERROR_OUT_OF_RANGE"
PRESSURE_RANGE_RULE_ID = "RF_PM_PRESSURE_ERROR_OUT_OF_RANGE"
UNRECALCULABLE_RULE_ID = "RF_PM_TEMP_PRESSURE_ERROR_UNRECALCULABLE"
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
        pressure_error_violations = []
        temp_error_violations = []
        temp_range_violations = []
        pressure_range_violations = []
        unrecalculable_violations = []
        for pollutant in ("PM10", "PM25"):
            temp_violations = _check_error_triplet(
                form,
                pollutant=pollutant,
                metric="temp",
                display_field=f"{pollutant}CHECKTEMP1VALUE",
                standard_field=f"{pollutant}CHECKTEMP2VALUE",
                error_field=f"{pollutant}CHECKTEMP3VALUE",
            )
            temp_error_violations.extend(temp_violations["mismatch"])
            temp_range_violations.extend(
                _range_violations(temp_violations["calculated"], threshold=2.0, unit="℃", rule_kind="temp")
            )
            unrecalculable_violations.extend(temp_violations["unrecalculable"])

            pressure_violations = _check_error_triplet(
                form,
                pollutant=pollutant,
                metric="pressure",
                display_field=f"{pollutant}CHECKPRES1VALUE",
                standard_field=f"{pollutant}CHECKPRES2VALUE",
                error_field=f"{pollutant}CHECKPRES3VALUE",
            )
            pressure_error_violations.extend(pressure_violations["mismatch"])
            pressure_range_violations.extend(_pressure_range_violations(pressure_violations["calculated"]))
            unrecalculable_violations.extend(pressure_violations["unrecalculable"])

            display = _num(form.get(f"{pollutant}CHECKPRES1VALUE"))
            standard = _num(form.get(f"{pollutant}CHECKPRES2VALUE"))
            for field, value in (
                (f"{pollutant}CHECKPRES1VALUE", display),
                (f"{pollutant}CHECKPRES2VALUE", standard),
            ):
                if value is not None and not _is_valid_pressure_scale(value):
                    unit_violations.append(
                        {
                            "pollutant": pollutant,
                            "field": field,
                            "raw_value": form.get(field),
                            "parsed_value": value,
                            "expected_unit": "kPa 或 hPa",
                            "expected_range": "80-110 kPa 或 800-1100 hPa",
                        }
                    )

        if unit_violations:
            _add_issue(order, table, issues, UNIT_RULE_ID, "表单数值逻辑", "高", unit_violations, "颗粒物气压字段数值量级不符合 kPa/hPa 常见范围")
        if pressure_error_violations:
            _add_issue(order, table, issues, ERROR_RULE_ID, "表单数值逻辑", "高", pressure_error_violations, "颗粒物气压误差字段复算不一致")
        if temp_error_violations:
            _add_issue(order, table, issues, TEMP_ERROR_RULE_ID, "表单数值逻辑", "高", temp_error_violations, "颗粒物温度误差字段复算不一致")
        if temp_range_violations:
            _add_issue(order, table, issues, TEMP_RANGE_RULE_ID, "表单结果合理性", "高", temp_range_violations, "颗粒物温度误差不满足小于±2℃要求")
        if pressure_range_violations:
            _add_issue(order, table, issues, PRESSURE_RANGE_RULE_ID, "表单结果合理性", "高", pressure_range_violations, "颗粒物气压误差不满足小于±1kPa要求")
        if unrecalculable_violations:
            _add_issue(order, table, issues, UNRECALCULABLE_RULE_ID, "表单完整性", "中", unrecalculable_violations, "颗粒物温度/气压误差缺少可复算字段")


def _check_error_triplet(
    form: dict[str, Any],
    *,
    pollutant: str,
    metric: str,
    display_field: str,
    standard_field: str,
    error_field: str,
) -> dict[str, list[dict[str, Any]]]:
    display_raw = form.get(display_field)
    standard_raw = form.get(standard_field)
    actual_raw = form.get(error_field)
    display = _num(display_raw)
    standard = _num(standard_raw)
    actual_error = _num(actual_raw)
    if not any(_has_value(value) for value in (display_raw, standard_raw, actual_raw)):
        return {"mismatch": [], "unrecalculable": [], "calculated": []}
    if display is None or standard is None or actual_error is None:
        return {
            "mismatch": [],
            "unrecalculable": [
                {
                    "pollutant": pollutant,
                    "metric": metric,
                    "field": error_field,
                    "inputs": {
                        display_field: display_raw,
                        standard_field: standard_raw,
                        error_field: actual_raw,
                    },
                    "missing_or_invalid_fields": [
                        field
                        for field, value in (
                            (display_field, display),
                            (standard_field, standard),
                            (error_field, actual_error),
                        )
                        if value is None
                    ],
                }
            ],
            "calculated": [],
        }

    expected_error = display - standard
    rounded_expected = round(expected_error, 1)
    calculated = [
        {
            "pollutant": pollutant,
            "metric": metric,
            "field": error_field,
            "actual": actual_error,
            "expected": rounded_expected,
            "raw_expected": round(expected_error, 6),
            "delta": round(actual_error - rounded_expected, 6),
            "display": display,
            "standard": standard,
            "inputs": {
                display_field: display,
                standard_field: standard,
            },
        }
    ]
    if abs(actual_error - rounded_expected) <= 0.11:
        return {"mismatch": [], "unrecalculable": [], "calculated": calculated}
    return {"mismatch": calculated, "unrecalculable": [], "calculated": calculated}


def _range_violations(
    calculated: list[dict[str, Any]],
    *,
    threshold: float,
    unit: str,
    rule_kind: str,
) -> list[dict[str, Any]]:
    violations = []
    for item in calculated:
        expected = float(item["raw_expected"])
        if abs(expected) >= threshold:
            violation = dict(item)
            violation.update(
                {
                    "rule_kind": rule_kind,
                    "threshold": f"< ±{threshold:g}{unit}",
                    "calculated_error": round(expected, 6),
                }
            )
            violations.append(violation)
    return violations


def _pressure_range_violations(calculated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    violations = []
    for item in calculated:
        threshold = 10.0 if _pressure_triplet_looks_hpa(item) else 1.0
        unit = "hPa" if threshold == 10.0 else "kPa"
        violations.extend(_range_violations([item], threshold=threshold, unit=unit, rule_kind="pressure"))
    return violations


def _pressure_triplet_looks_hpa(item: dict[str, Any]) -> bool:
    return max(abs(float(item["display"])), abs(float(item["standard"]))) > 200


def _is_valid_pressure_scale(value: float) -> bool:
    return 80 <= value <= 110 or 800 <= value <= 1100


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() not in SKIP_VALUES


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
