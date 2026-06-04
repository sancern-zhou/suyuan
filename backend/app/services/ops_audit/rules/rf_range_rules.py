"""RF form range check rules for operations work order audits."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.ops_audit.config import load_yaml_config
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue

RANGE_PROFILES = load_yaml_config("rf_range_profiles.yaml", {})
MONTHLY_GASEOUS_FLOW_FIELDS = [
    ("SO2", "FLOWRANGSO2", ["DISPLAYVALUESO2", "MEASUREDVALUESO2"]),
    ("NO2", "FLOWRANGNO2", ["DISPLAYVALUENO2", "MEASUREDVALUENO2"]),
    ("CO", "FLOWRANGCO", ["DISPLAYVALUECO", "MEASUREDVALUECO"]),
    ("O3", "FLOWRANGO3", ["DISPLAYVALUEO3", "MEASUREDVALUEO3"]),
]


def check_rf_range_values(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Check RF form range values for completeness and validity.

    This rule identifies:
    - RF_RANGE_VALUE_MISSING: Expected check value is missing
    - RF_RANGE_OUT_OF_SPEC: Check value exceeds brand normal range
    - RF_RANGE_BY_GAS_TYPE_MISMATCH: Gas type doesn't match range

    The rule is configurable via rf_range_profiles.yaml.
    """

    check_value_fields = RANGE_PROFILES.get("check_value_fields", {})
    brand_ranges = RANGE_PROFILES.get("brand_ranges", {})
    gas_type_mapping = RANGE_PROFILES.get("gas_type_mapping", {})
    structured_weekly_profiles = {}
    structured_weekly_profiles.update(RANGE_PROFILES.get("o3_weekly_check_profiles", {}))
    structured_weekly_profiles.update(RANGE_PROFILES.get("nox_weekly_check_profiles", {}))
    structured_weekly_profiles.update(RANGE_PROFILES.get("so2_weekly_check_profiles", {}))
    structured_weekly_profiles.update(RANGE_PROFILES.get("pm_weekly_check_profiles", {}))

    if not check_value_fields:
        return

    for table, form in forms:
        if form.get("_query_error"):
            continue

        if table == "RF_M_GASEOUSFLOWCHECK":
            _check_monthly_gaseous_flow_range_text(order, table, form, issues)

        _check_weekly_structured_ranges(order, table, form, structured_weekly_profiles, issues)

        if table not in check_value_fields:
            continue

        value_fields = check_value_fields.get(table, [])
        if not value_fields:
            continue

        _check_missing_values(order, table, form, value_fields, issues)
        _check_gas_type_mismatch(order, table, form, gas_type_mapping, issues)
        _check_value_out_of_spec(order, table, form, brand_ranges, gas_type_mapping, issues)


def _check_weekly_structured_ranges(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    profiles: dict[str, Any],
    issues: list[Issue],
) -> None:
    profile = profiles.get(table)
    if not profile:
        return

    pollutant_field = str(profile.get("pollutant_field") or "")
    allowed_pollutants = {
        str(item).strip().upper()
        for item in profile.get("pollutant_values", [])
        if str(item).strip()
    }
    pollutant = str(form.get(pollutant_field) or "").strip().upper()
    if allowed_pollutants and pollutant and pollutant not in allowed_pollutants:
        return

    brand = _normalize_profile_brand(
        form.get(profile.get("brand_field") or "DEVICEBRAND") or form.get("BRAND"),
        profile.get("brand_aliases", {}),
    )
    if not brand:
        return

    out_of_spec_values = []
    for field_config in profile.get("fields", []):
        field_name = str(field_config.get("field") or "")
        if not field_name or field_name not in form:
            continue
        value = _parse_numeric(form.get(field_name))
        if value is None:
            if field_config.get("semantic_required_when_blank"):
                _add_blank_structured_value_semantic_candidate(order, table, form, field_config, issues)
            continue
        spec = (field_config.get("ranges") or {}).get(brand)
        if not spec:
            continue
        comparison_result = _comparison_text_satisfies_spec(form.get(field_name), spec)
        if comparison_result is True:
            continue
        if _is_value_in_spec(value, spec):
            continue
        out_of_spec_values.append(
            {
                "field": field_name,
                "label": field_config.get("label") or field_name,
                "value": value,
                "raw_value": form.get(field_name),
                "min": spec.get("min"),
                "max": spec.get("max"),
                "operator": spec.get("operator"),
                "unit": spec.get("unit", ""),
            }
        )

    for item in out_of_spec_values:
        handling_record_candidates = _handling_record_candidates(form)
        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "rf_table": table,
            "brand": brand,
            "pollutant_type": form.get(pollutant_field),
            "out_of_spec_values": [item],
            "handling_record_candidates": handling_record_candidates,
            "needs_semantic_review": True,
        }
        add_issue(
            issues,
            "RF_RANGE_OUT_OF_SPEC",
            "表单结果合理性",
            "高",
            f"rf.{table}.{item['field']}",
            (
                f"{profile.get('display_name') or table}周检{item['label']}检查值({item['raw_value']})"
                f"超出{brand}品牌正常范围({_range_spec_text(item)})"
            ),
            json.dumps(evidence, ensure_ascii=False, default=str),
        )


def _add_blank_structured_value_semantic_candidate(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    field_config: dict[str, Any],
    issues: list[Issue],
) -> None:
    field_name = str(field_config.get("field") or "")
    label = str(field_config.get("label") or field_name)
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "reason_rule_id": "RF_RANGE_VALUE_MISSING",
        "abnormal_field": f"rf.{table}.{field_name}",
        "abnormal_message": f"{label}检查值为空，需要结合备注判断是否有合理免填依据。",
        "remark_candidates": {
            key: form.get(key)
            for key in ("REMARK", "REMARKS", "CHECKREMARK")
            if key in form
        },
        "needs_semantic_review": True,
    }
    add_issue(
        issues,
        "RF_ABNORMAL_VALUE_NO_REMARK",
        "结果合理性",
        "高",
        f"rf.{table}.remark",
        f"RF表单{label}检查值为空，需语义判断备注是否说明免填依据",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _check_missing_values(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    value_fields: list[str],
    issues: list[Issue],
) -> None:
    """Check if expected check values are missing."""

    missing_fields = []
    for field in value_fields:
        if field in form:
            value = form.get(field)
            if value is None or str(value).strip() in {"", "/", "-", "0"}:
                missing_fields.append(field)

    if not missing_fields:
        return

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "missing_fields": missing_fields,
        "all_value_fields": value_fields,
    }

    add_issue(
        issues,
        "RF_RANGE_VALUE_MISSING",
        "表单完整性",
        "高",
        f"rf.{table}.range_values",
        f"RF表单应检项目检查值为空: {', '.join(missing_fields[:3])}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _check_value_out_of_spec(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    brand_ranges: dict[str, Any],
    gas_type_mapping: dict[str, Any],
    issues: list[Issue],
) -> None:
    """Check if check value exceeds brand normal range."""

    brand = _normalize_brand(form.get("DEVICEBRAND") or form.get("BRAND"))
    if not brand or brand not in brand_ranges:
        return

    gas_type_info = gas_type_mapping.get(table, {})
    if not gas_type_info:
        return

    gas_type = gas_type_info.get("gas_type")
    if not gas_type:
        return

    range_config = brand_ranges.get(brand, {}).get(gas_type)
    if not range_config:
        return

    min_value = range_config.get("min")
    max_value = range_config.get("max")
    unit = range_config.get("unit", "")

    if min_value is None or max_value is None:
        return

    value_candidates = ["DISPLAYVALUE", "MEASUREVALUE", "SENSORVALUE",
                        "PMDISPLAYVALUE", "PMMEASUREVALUE", "PMSENSORVALUE"]

    out_of_spec_values = []
    for field in value_candidates:
        if field in form:
            value = _parse_numeric(form.get(field))
            if value is not None and (value < min_value or value > max_value):
                out_of_spec_values.append({
                    "field": field,
                    "value": value,
                    "min": min_value,
                    "max": max_value,
                })

    if not out_of_spec_values:
        return

    handling_record_candidates = _handling_record_candidates(form)
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "brand": brand,
        "gas_type": gas_type,
        "unit": unit,
        "out_of_spec_values": out_of_spec_values,
        "handling_record_candidates": handling_record_candidates,
        "needs_semantic_review": True,
    }

    sample = out_of_spec_values[0]
    add_issue(
        issues,
        "RF_RANGE_OUT_OF_SPEC",
        "表单结果合理性",
        "高",
        f"rf.{table}.value_out_of_spec",
        f"RF表单检查值({sample['value']})超出{brand}品牌{gas_type}正常范围({min_value}-{max_value} {unit})",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _check_monthly_gaseous_flow_range_text(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    issues: list[Issue],
) -> None:
    """Check monthly gas flow display/measured values against range text."""

    out_of_spec_values = []
    for gas_type, range_field, value_fields in MONTHLY_GASEOUS_FLOW_FIELDS:
        parsed_range = _parse_flow_range_text(form.get(range_field))
        if not parsed_range:
            continue
        min_value, max_value, unit = parsed_range
        for field in value_fields:
            value = _parse_numeric(form.get(field))
            if value is None:
                continue
            if value < min_value or value > max_value:
                out_of_spec_values.append(
                    {
                        "gas_type": gas_type,
                        "range_field": range_field,
                        "raw_range": form.get(range_field),
                        "field": field,
                        "value": value,
                        "min": min_value,
                        "max": max_value,
                        "unit": unit,
                    }
                )

    if not out_of_spec_values:
        return

    handling_record_candidates = _handling_record_candidates(form)
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "out_of_spec_values": out_of_spec_values,
        "handling_record_candidates": handling_record_candidates,
        "needs_semantic_review": True,
    }
    sample = out_of_spec_values[0]
    add_issue(
        issues,
        "RF_RANGE_OUT_OF_SPEC",
        "表单结果合理性",
        "高",
        f"rf.{table}.{sample['field']}",
        (
            f"月度气体流量检查{sample['gas_type']} {sample['field']}={sample['value']}"
            f"超出流量范围({sample['min']}-{sample['max']} {sample['unit']})"
        ),
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _check_gas_type_mismatch(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    gas_type_mapping: dict[str, Any],
    issues: list[Issue],
) -> None:
    """Check configured gas or pollutant type fields against the RF table profile."""

    gas_type_info = gas_type_mapping.get(table, {})
    expected_gas_type = str(gas_type_info.get("gas_type") or "").strip().upper()
    gas_type_field = gas_type_info.get("field")
    if not expected_gas_type or not gas_type_field:
        return

    actual_value = form.get(str(gas_type_field))
    if actual_value is None or str(actual_value).strip() == "":
        return

    actual_gas_type = str(actual_value).strip().upper()
    aliases = {
        str(alias).strip().upper()
        for alias in gas_type_info.get("aliases", [])
        if str(alias).strip()
    }
    allowed_values = aliases | {expected_gas_type}
    if actual_gas_type in allowed_values:
        return

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "field": gas_type_field,
        "actual_gas_type": actual_value,
        "expected_gas_type": expected_gas_type,
        "allowed_values": sorted(allowed_values),
    }
    add_issue(
        issues,
        "RF_RANGE_BY_GAS_TYPE_MISMATCH",
        "一致性",
        "高",
        f"rf.{table}.{gas_type_field}",
        f"RF表单气体类型{actual_value}与{table}配置量程{expected_gas_type}不匹配",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _normalize_brand(brand: Any) -> str | None:
    """Normalize brand name for range lookup."""
    if not brand:
        return None
    brand_str = str(brand).strip().upper()
    if "THERMO" in brand_str or brand_str in {"TE", "热电"}:
        return "THERMO"
    if "API" in brand_str:
        return "API"
    return brand_str


def _normalize_profile_brand(brand: Any, aliases: dict[str, Any]) -> str | None:
    if not brand:
        return None
    brand_text = str(brand).strip()
    if not brand_text:
        return None
    brand_upper = brand_text.upper()
    for normalized, values in aliases.items():
        candidates = {str(value).strip().upper() for value in values if str(value).strip()}
        candidates.add(str(normalized).strip().upper())
        if brand_upper in candidates:
            return str(normalized)
    if "THERMO" in brand_upper or brand_upper in {"TE", "热电"}:
        return "THERMO"
    if "API" in brand_upper:
        return "API"
    return brand_upper


def _parse_numeric(value: Any) -> float | None:
    """Parse numeric value from various formats."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text in {"", "/", "-", "无", "无该项指标", "无此参数"}:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except (ValueError, TypeError):
        return None


def _comparison_text_satisfies_spec(value: Any, spec: dict[str, Any]) -> bool | None:
    if value is None or isinstance(value, (int, float)):
        return None
    text = str(value).strip()
    if not text:
        return None

    match = re.match(r"^\s*(>=|<=|＞=|＜=|≥|≤|＞|＜|>|<)\s*([-+]?\d+(?:\.\d+)?)", text)
    if not match:
        return None

    raw_operator = _normalize_comparison_operator(match.group(1))
    try:
        threshold = float(match.group(2))
    except (ValueError, TypeError):
        return None

    spec_operator = str(spec.get("operator") or "").strip()
    min_value = spec.get("min")
    max_value = spec.get("max")

    if raw_operator in {">", ">="} and min_value is not None:
        spec_min = float(min_value)
        if spec_operator == ">":
            if raw_operator == ">" and threshold >= spec_min:
                return True
            if raw_operator == ">=" and threshold > spec_min:
                return True
        if spec_operator == ">=" and threshold >= spec_min:
            return True

    if raw_operator in {"<", "<="} and max_value is not None:
        spec_max = float(max_value)
        if spec_operator == "<":
            if raw_operator == "<" and threshold <= spec_max:
                return True
            if raw_operator == "<=" and threshold < spec_max:
                return True
        if spec_operator == "<=" and threshold <= spec_max:
            return True

    return None


def _normalize_comparison_operator(operator: str) -> str:
    return (
        operator.replace("＞=", ">=")
        .replace("＜=", "<=")
        .replace("≥", ">=")
        .replace("≤", "<=")
        .replace("＞", ">")
        .replace("＜", "<")
    )


def _is_value_in_spec(value: float, spec: dict[str, Any]) -> bool:
    operator = str(spec.get("operator") or "").strip()
    min_value = spec.get("min")
    max_value = spec.get("max")
    if operator == ">":
        return min_value is None or value > float(min_value)
    if operator == ">=":
        return min_value is None or value >= float(min_value)
    if operator == "<":
        return max_value is None or value < float(max_value)
    if operator == "<=":
        return max_value is None or value <= float(max_value)
    if min_value is not None and value < float(min_value):
        return False
    if max_value is not None and value > float(max_value):
        return False
    return True


def _range_spec_text(spec: dict[str, Any]) -> str:
    operator = spec.get("operator")
    min_value = spec.get("min")
    max_value = spec.get("max")
    unit = spec.get("unit", "")
    if operator in {">", ">="} and min_value is not None and max_value is None:
        return f"{operator}{min_value} {unit}".strip()
    if operator in {"<", "<="} and max_value is not None and min_value is None:
        return f"{operator}{max_value} {unit}".strip()
    if min_value is not None and max_value is not None:
        return f"{min_value}-{max_value} {unit}".strip()
    if min_value is not None:
        return f">={min_value} {unit}".strip()
    if max_value is not None:
        return f"<={max_value} {unit}".strip()
    return str(unit or "未配置")


def _parse_flow_range_text(value: Any) -> tuple[float, float, str] | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    normalized = (
        text.replace("％", "%")
        .replace("＋", "+")
        .replace("－", "-")
        .replace("—", "-")
        .replace("–", "-")
        .replace("~", "～")
        .replace("至", "～")
        .replace("／", "/")
    )
    normalized = re.sub(r"\s+", "", normalized)
    unit = _extract_flow_unit(normalized)

    plus_minus_match = re.search(
        r"([-+]?\d+(?:\.\d+)?)\s*(?:±|\+/-)\s*([-+]?\d+(?:\.\d+)?)(%)?",
        normalized,
        flags=re.IGNORECASE,
    )
    if plus_minus_match:
        center = float(plus_minus_match.group(1))
        tolerance = float(plus_minus_match.group(2))
        if plus_minus_match.group(3):
            delta = abs(center) * tolerance / 100
        else:
            delta = tolerance
        return center - delta, center + delta, unit

    range_match = re.search(
        r"([-+]?\d+(?:\.\d+)?)\s*(?:～|-)\s*([-+]?\d+(?:\.\d+)?)",
        normalized,
    )
    if not range_match:
        return None
    first = float(range_match.group(1))
    second = float(range_match.group(2))
    return min(first, second), max(first, second), unit


def _handling_record_candidates(form: dict[str, Any]) -> dict[str, Any]:
    candidates: dict[str, Any] = {}
    for field, value in form.items():
        if _is_handling_record_field(field):
            candidates[str(field)] = value
    return candidates


def _is_handling_record_field(field: Any) -> bool:
    upper = str(field or "").upper()
    tokens = (
        "EXCEPTION",
        "ABNORMAL",
        "HANDLE",
        "HANDLING",
        "PROCESS",
        "DISPOSAL",
        "TREAT",
        "RECORD",
        "REMARK",
        "CHECKREMARK",
        "DESCRIPTION",
        "异常",
        "处理",
        "处置",
        "记录",
        "备注",
        "说明",
    )
    return any(token in upper for token in tokens)


def _extract_flow_unit(text: str) -> str:
    lower = text.lower()
    if re.search(r"(?:ml|毫升)/(?:min|分钟)|(?:ml|毫升)(?:/)?(?:min|分钟)", lower):
        return "ml/min"
    if re.search(r"(?:l|升)/(?:min|分钟)|(?:l|升)(?:/)?(?:min|分钟)", lower):
        return "L/min"
    return ""
