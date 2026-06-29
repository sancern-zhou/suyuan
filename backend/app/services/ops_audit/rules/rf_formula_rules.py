"""RF form formula checks for operations work order audits."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue

RULE_ID = "RF_VALUE_FORMULA_MISMATCH"
PRESSURE_TRUE_VALUE_RULE_ID = "RF_Q_GASEOUSFLOWCHECK_PRESSURE_TRUE_VALUE_MISMATCH"
MONTHLY_GAS_FLOW_ERROR_RANGE_RULE_ID = "RF_M_GASEOUSFLOWCHECK_ERROR_OUT_OF_RANGE"
PM_MEMBRANE_ERROR_MISMATCH_RULE_ID = "RF_PM_MEMBRANE_ERROR_MISMATCH"
PM_MEMBRANE_ERROR_RANGE_RULE_ID = "RF_PM_MEMBRANE_ERROR_OUT_OF_RANGE"
QUARTER_GAS_FLOW_TARGET_POINT_RULE_ID = "RF_Q_GASEOUS_FLOW_TARGET_POINT_MISMATCH"
SKIP_TOKENS = {"", "/", "-", "nan", "none", "null", "无", "无该项指标", "不适用", "未填写"}


def check_rf_formula_values(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Check formulas that can be recomputed from RF form fields."""

    for table, form in forms:
        if form.get("_query_error"):
            continue

        violations: list[dict[str, Any]] = []
        if table in {
            "RF_W_GASEOUSCHECK_CO",
            "RF_W_GASEOUSCHECK_NOX",
            "RF_W_GASEOUSCHECK_O3",
            "RF_W_GASEOUSCHECK_SO2",
        }:
            violations.extend(_check_weekly_gas_true_values(table, form))
        elif table == "RF_M_GASEOUSFLOWCHECK":
            monthly_error_range_violations = _check_monthly_gas_flow_error_range(table, form)
            if monthly_error_range_violations:
                _add_monthly_gas_flow_error_range_issue(order, table, monthly_error_range_violations, issues)
            violations.extend(_check_monthly_gas_flow(table, form))
        elif table == "RF_Q_GaseousFlowCheck":
            target_point_violations = _check_quarter_gas_flow_target_points(table, form)
            if target_point_violations:
                _add_quarter_gas_flow_target_point_issue(order, table, target_point_violations, issues)
            pressure_violations = _check_quarter_pressure_true_value(table, form)
            if pressure_violations:
                _add_pressure_true_value_issue(order, table, pressure_violations, issues)
            violations.extend(_check_quarter_gas_flow(table, form))
        elif table == "RF_TW_PmFlowCheck":
            violations.extend(_check_tw_pm_flow_check(table, form))
        elif table == "RF_TW_PmFlowCalibrate":
            violations.extend(_check_tw_pm_flow_calibrate(table, form))
        elif table in {"RF_Q_PM10RUNSTATUSCHECK", "RF_Q_PM25RUNSTATUSCHECK"}:
            pm_membrane_violations = _check_pm_membrane_error(table, form)
            mismatch_violations = [item for item in pm_membrane_violations if item.get("violation_type") == "mismatch"]
            range_violations = [item for item in pm_membrane_violations if item.get("violation_type") == "out_of_range"]
            if mismatch_violations:
                _add_pm_membrane_error_issue(order, table, mismatch_violations, issues)
            if range_violations:
                _add_pm_membrane_error_range_issue(order, table, range_violations, issues)

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
            "高",
            f"rf.{table}.formula",
            f"RF表单公式计算结果不一致: {first.get('formula_id')} {first.get('actual')} != {first.get('expected')}",
            json.dumps(evidence, ensure_ascii=False, default=str),
        )


def _add_pressure_true_value_issue(
    order: dict[str, Any],
    table: str,
    violations: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "violation_count": len(violations),
        "violations": violations[:20],
    }
    first = violations[0]
    add_issue(
        issues,
        PRESSURE_TRUE_VALUE_RULE_ID,
        "表单数值逻辑",
        "高",
        f"rf.{table}.{first.get('actual_field')}",
        f"季度气体流量检查气压真实值复算不一致: {first.get('actual')} != {first.get('expected')}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _add_monthly_gas_flow_error_range_issue(
    order: dict[str, Any],
    table: str,
    violations: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "violation_count": len(violations),
        "violations": violations[:20],
    }
    first = violations[0]
    add_issue(
        issues,
        MONTHLY_GAS_FLOW_ERROR_RANGE_RULE_ID,
        "表单结果合理性",
        "高",
        f"rf.{table}.{first.get('error_field')}",
        f"月度气体流量检查{first.get('gas_type')}测量误差{first.get('expected_error')}%超出±10%",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _add_pm_membrane_error_issue(
    order: dict[str, Any],
    table: str,
    violations: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "violation_count": len(violations),
        "violations": violations[:20],
    }
    first = violations[0]
    add_issue(
        issues,
        PM_MEMBRANE_ERROR_MISMATCH_RULE_ID,
        "表单数值逻辑",
        "高",
        f"rf.{table}.{first.get('error_field')}",
        f"颗粒物校准膜误差复算不一致: {first.get('actual_error')} != {first.get('expected_error')}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _add_pm_membrane_error_range_issue(
    order: dict[str, Any],
    table: str,
    violations: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "violation_count": len(violations),
        "violations": violations[:20],
    }
    first = violations[0]
    add_issue(
        issues,
        PM_MEMBRANE_ERROR_RANGE_RULE_ID,
        "表单结果合理性",
        "高",
        f"rf.{table}.{first.get('error_field')}",
        f"颗粒物校准膜误差{first.get('expected_error')}%超出±2%",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _add_quarter_gas_flow_target_point_issue(
    order: dict[str, Any],
    table: str,
    violations: list[dict[str, Any]],
    issues: list[Issue],
) -> None:
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "violation_count": len(violations),
        "violations": violations[:20],
    }
    first = violations[0]
    add_issue(
        issues,
        QUARTER_GAS_FLOW_TARGET_POINT_RULE_ID,
        "表单数值逻辑",
        "高",
        f"rf.{table}.{first.get('field')}",
        (
            f"季度气体流量检查未按指定流量点检查: {first.get('field')}="
            f"{first.get('actual')}，应接近{first.get('expected_target')}({first.get('point')}点)"
        ),
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _check_weekly_gas_true_values(table: str, form: dict[str, Any]) -> list[dict[str, Any]]:
    violations = []
    profiles = [
        ("zero_true_value", "LDBIAODINGVALUE", "LDSHOWVALUE", ["LDPYPPB"]),
        ("span_true_value", "MCLBIAODINGVALUE", "MCLHOWVALUE", ["KDPY"]),
    ]
    for formula_id, true_field, display_field, correction_fields in profiles:
        actual = _num(form.get(true_field))
        display = _num(form.get(display_field))
        if actual is None or display is None:
            continue

        expected_values = []
        for correction_field in correction_fields:
            correction = _num(form.get(correction_field))
            if correction is not None:
                expected_values.append(
                    (
                        f"{formula_id}_display_plus_correction",
                        display + correction,
                        {display_field: display, correction_field: correction},
                    )
                )

        slope = _num(form.get("YLCHECKVALUE"))
        intercept = _num(form.get("JGCHECKVALUE"))
        if slope is not None and intercept is not None and 0.1 <= abs(slope) <= 5:
            expected_values.append(
                (
                    f"{formula_id}_display_times_slope_plus_intercept",
                    display * slope + intercept,
                    {display_field: display, "YLCHECKVALUE": slope, "JGCHECKVALUE": intercept},
                )
            )

        if not expected_values:
            continue
        if any(abs(actual - expected) <= 0.2 for _, expected, _ in expected_values):
            continue
        best_id, best_expected, best_inputs = min(expected_values, key=lambda item: abs(actual - item[1]))
        violations.extend(
            _compare(
                table,
                best_id,
                true_field,
                actual,
                best_expected,
                abs_tol=0.2,
                inputs=best_inputs,
            )
        )
    return violations


def _check_monthly_gas_flow(table: str, form: dict[str, Any]) -> list[dict[str, Any]]:
    violations = []
    for gas in ("SO2", "NO2", "CO", "O3"):
        display = _num(form.get(f"DISPLAYVALUE{gas}"))
        measured = _num(form.get(f"MEASUREDVALUE{gas}"))
        actual = _num(form.get(f"MEASUREDERROR{gas}"))
        if display is None or measured in (None, 0) or actual is None:
            continue
        expected = round((display - measured) / measured * 100, 2)
        violations.extend(
            _compare(
                table,
                f"monthly_gas_flow_error_{gas}",
                f"MEASUREDERROR{gas}",
                actual,
                expected,
                abs_tol=0.0101,
                inputs={
                    f"DISPLAYVALUE{gas}": display,
                    f"MEASUREDVALUE{gas}": measured,
                },
            )
        )
    return violations


def _check_monthly_gas_flow_error_range(table: str, form: dict[str, Any]) -> list[dict[str, Any]]:
    violations = []
    for gas in ("SO2", "NO2", "CO", "O3"):
        display = _num(form.get(f"DISPLAYVALUE{gas}"))
        measured = _num(form.get(f"MEASUREDVALUE{gas}"))
        if display is None or measured in (None, 0):
            continue
        expected = round((display - measured) / measured * 100, 2)
        if abs(expected) <= 10:
            continue
        violations.append(
            {
                "rf_table": table,
                "gas_type": gas,
                "display_field": f"DISPLAYVALUE{gas}",
                "measured_field": f"MEASUREDVALUE{gas}",
                "error_field": f"MEASUREDERROR{gas}",
                "display_value": display,
                "measured_value": measured,
                "expected_error": expected,
                "allowed_min": -10,
                "allowed_max": 10,
            }
        )
    return violations


def _check_pm_membrane_error(table: str, form: dict[str, Any]) -> list[dict[str, Any]]:
    if table == "RF_Q_PM25RUNSTATUSCHECK":
        pollutant = "PM2.5"
        original_field = "PM25CHECKTEMP1VALUE"
        check_field = "PM25CHECKTEMP2VALUE"
        error_field = "PM25CHECKTEMP3VALUE"
    elif table == "RF_Q_PM10RUNSTATUSCHECK":
        pollutant = "PM10"
        original_field = "PM10CHECKTEMP1VALUE"
        check_field = "PM10CHECKTEMP2VALUE"
        error_field = "PM10CHECKTEMP3VALUE"
    else:
        return []

    original = _num(form.get(original_field))
    check = _num(form.get(check_field))
    actual_error = _num(form.get(error_field))
    if original in (None, 0) or check is None:
        return []

    expected_error = round((original - check) / original * 100, 1)
    base = {
        "rf_table": table,
        "pollutant": pollutant,
        "original_field": original_field,
        "check_field": check_field,
        "error_field": error_field,
        "original_value": original,
        "check_value": check,
        "actual_error": actual_error,
        "expected_error": expected_error,
        "allowed_min": -2,
        "allowed_max": 2,
    }
    violations = []
    if actual_error is not None and abs(expected_error - actual_error) > 0.11:
        violations.append({**base, "violation_type": "mismatch"})
    if abs(expected_error) > 2:
        violations.append({**base, "violation_type": "out_of_range"})
    return violations


def _check_quarter_gas_flow(table: str, form: dict[str, Any]) -> list[dict[str, Any]]:
    violations = []

    for point in ("85", "60", "35"):
        violations.extend(
            _linear_formula(
                table,
                form,
                f"standard_gas_qm_{point}",
                f"DF_Qm_{point}",
                f"DF_Valuve_{point}",
                a_field="D_Ac1",
                b_field="D_Bc1",
                abs_tol=0.2,
            )
        )
        violations.extend(
            _linear_formula(
                table,
                form,
                f"sample_flow_qa_{point}",
                f"RF_Qa_{point}",
                f"RF_Valuve_{point}",
                a_field="F_As1",
                b_field="F_Bs1",
                abs_tol=0.2,
            )
        )
        violations.extend(_standard_flow_formula(table, form, point, abs_tol=0.2))
        violations.extend(_relative_flow_error_formula(table, form, point, abs_tol=0.2))
    for point in ("80", "50", "20"):
        violations.extend(
            _linear_formula(
                table,
                form,
                f"standard_gas_qm_{point}",
                f"DF_Qm_{point}",
                f"DF_Valuve_{point}",
                a_field="D_Ac2",
                b_field="D_Bc2",
                abs_tol=0.2,
            )
        )
        violations.extend(
            _linear_formula(
                table,
                form,
                f"sample_flow_qa_{point}",
                f"RF_Qa_{point}",
                f"RF_Valuve_{point}",
                a_field="F_As2",
                b_field="F_Bs2",
                abs_tol=0.2,
            )
        )
        violations.extend(_standard_flow_formula(table, form, point, abs_tol=0.2))
        violations.extend(_relative_flow_error_formula(table, form, point, abs_tol=0.2))
    return violations


def _check_quarter_gas_flow_target_points(table: str, form: dict[str, Any]) -> list[dict[str, Any]]:
    violations = []
    point_targets = {
        "85": 8500,
        "60": 6000,
        "35": 3500,
        "80": 80,
        "50": 50,
        "20": 20,
    }
    for point, expected in point_targets.items():
        field = f"DF_Valuve_{point}"
        if field not in form:
            continue
        actual = _num(form.get(field))
        if actual is None:
            continue
        tolerance = max(abs(expected) * 0.05, 0.5)
        if abs(actual - expected) <= tolerance:
            continue
        violations.append(
            {
                "rf_table": table,
                "field": field,
                "point": point,
                "actual": actual,
                "expected_target": expected,
                "allowed_tolerance": round(tolerance, 6),
                "violation_type": "target_point_mismatch",
            }
        )
    return violations


def _check_quarter_pressure_true_value(table: str, form: dict[str, Any]) -> list[dict[str, Any]]:
    measuring_value = _num(form.get("P_MeasuringValue"))
    slope = _num(form.get("P_As"))
    intercept = _num(form.get("P_Bs"))
    actual = _num(form.get("P_Pa"))
    if measuring_value is None or slope is None or intercept is None or actual is None:
        return []
    expected = measuring_value * slope + intercept
    return _compare(
        table,
        "quarter_gaseous_flow_pressure_true_value",
        "P_Pa",
        actual,
        expected,
        abs_tol=0.2,
        inputs={
            "P_MeasuringValue": measuring_value,
            "P_As": slope,
            "P_Bs": intercept,
        },
    )


def _check_tw_pm_flow_check(table: str, form: dict[str, Any]) -> list[dict[str, Any]]:
    violations = []
    for prefix, label in (("MainFlow", "main_flow"), ("ReferFlow", "refer_flow")):
        violations.extend(
            _linear_formula(
                table,
                form,
                f"{label}_fixed",
                f"{prefix}Fixed",
                f"{prefix}Refer",
                a_field="F_A",
                b_field="F_B",
                abs_tol=0.02,
            )
        )
        violations.extend(
            _linear_formula(
                table,
                form,
                f"{label}_real",
                f"{prefix}Real",
                f"{prefix}Refer",
                a_field="F_A",
                b_field="F_B",
                abs_tol=0.02,
            )
        )
        target = _num(form.get(f"{prefix}Target"))
        fixed = _num(form.get(f"{prefix}Fixed"))
        actual_error = _num(form.get(f"{prefix}Error"))
        if target in (None, 0) or fixed is None or actual_error is None:
            continue
        expected_error = abs((fixed - target) / target * 100)
        violations.extend(
            _compare(
                table,
                f"{label}_error",
                f"{prefix}Error",
                abs(actual_error),
                expected_error,
                abs_tol=0.2,
                inputs={f"{prefix}Target": target, f"{prefix}Fixed": fixed},
            )
        )
    return violations


def _check_tw_pm_flow_calibrate(table: str, form: dict[str, Any]) -> list[dict[str, Any]]:
    violations = []
    for prefix in ("Prev", "Next"):
        a_value = _num(form.get(f"{prefix}_A"))
        b_value = _num(form.get(f"{prefix}_B"))
        actual = _num(form.get(f"{prefix}_C"))
        if a_value is None or b_value in (None, 0) or actual is None:
            continue
        expected = (b_value - a_value) / b_value * 100
        violations.extend(
            _compare(
                table,
                f"{prefix.lower()}_flow_calibrate_error",
                f"{prefix}_C",
                actual,
                expected,
                abs_tol=0.2,
                inputs={f"{prefix}_A": a_value, f"{prefix}_B": b_value},
            )
        )
    return violations


def _linear_formula(
    table: str,
    form: dict[str, Any],
    formula_id: str,
    actual_field: str,
    value_field: str,
    *,
    a_field: str | None,
    b_field: str | None,
    abs_tol: float,
) -> list[dict[str, Any]]:
    value = _num(form.get(value_field))
    actual = _num(form.get(actual_field))
    a_value = 1.0 if a_field is None else _num(form.get(a_field))
    b_value = 0.0 if b_field is None else _num(form.get(b_field))
    if value is None or actual is None or a_value is None or b_value is None:
        return []
    expected = value * a_value + b_value
    inputs = {value_field: value}
    if a_field:
        inputs[a_field] = a_value
    if b_field:
        inputs[b_field] = b_value
    return _compare(table, formula_id, actual_field, actual, expected, abs_tol=abs_tol, inputs=inputs)


def _standard_flow_formula(table: str, form: dict[str, Any], point: str, *, abs_tol: float) -> list[dict[str, Any]]:
    qa_value = _num(form.get(f"RF_Qa_{point}"))
    actual = _num(form.get(f"RF_Qs_{point}"))
    pa_value = _num(form.get("P_Pa"))
    ta_value = _num(form.get("T_Ta"))
    if qa_value is None or actual is None:
        return []
    method = str(form.get("CalculationMethod") or "").strip().upper()
    if method == "SRC":
        expected = qa_value
        inputs = {f"RF_Qa_{point}": qa_value, "CalculationMethod": method}
    else:
        if pa_value is None or ta_value is None:
            return []
        denominator = ta_value + 273
        if denominator == 0:
            return []
        standard_temperature = 298 if method == "TE_25" else 273
        expected = qa_value * (pa_value / 760) * standard_temperature / denominator
        inputs = {
            f"RF_Qa_{point}": qa_value,
            "P_Pa": pa_value,
            "T_Ta": ta_value,
            "CalculationMethod": method,
            "standard_temperature": standard_temperature,
        }
    if expected is None:
        return []
    return _compare(
        table,
        f"standard_flow_qs_{point}",
        f"RF_Qs_{point}",
        actual,
        expected,
        abs_tol=abs_tol,
        inputs=inputs,
    )


def _relative_flow_error_formula(table: str, form: dict[str, Any], point: str, *, abs_tol: float) -> list[dict[str, Any]]:
    qm_value = _num(form.get(f"DF_Qm_{point}"))
    qs_value = _num(form.get(f"RF_Qs_{point}"))
    actual = _num(form.get(f"RF_D_{point}"))
    if qm_value is None or qs_value in (None, 0) or actual is None:
        return []
    expected = (qm_value - qs_value) / qs_value * 100
    return _compare(
        table,
        f"relative_flow_error_d_{point}",
        f"RF_D_{point}",
        actual,
        expected,
        abs_tol=abs_tol,
        inputs={
            f"DF_Qm_{point}": qm_value,
            f"RF_Qs_{point}": qs_value,
        },
    )


def _compare(
    table: str,
    formula_id: str,
    actual_field: str,
    actual: float | None,
    expected: float | None,
    *,
    abs_tol: float,
    inputs: dict[str, Any],
) -> list[dict[str, Any]]:
    if actual is None or expected is None:
        return []
    delta = actual - expected
    if abs(delta) <= abs_tol:
        return []
    return [
        {
            "rf_table": table,
            "formula_id": formula_id,
            "actual_field": actual_field,
            "actual": round(actual, 6),
            "expected": round(expected, 6),
            "delta": round(delta, 6),
            "tolerance": abs_tol,
            "inputs": inputs,
        }
    ]


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
