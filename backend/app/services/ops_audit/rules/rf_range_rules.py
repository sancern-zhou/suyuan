"""RF form range check rules for operations work order audits."""

from __future__ import annotations

import json
from typing import Any

from app.services.ops_audit.config import load_yaml_config
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue

RANGE_PROFILES = load_yaml_config("rf_range_profiles.yaml", {})


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

    if not check_value_fields:
        return

    for table, form in forms:
        if form.get("_query_error"):
            continue

        if table not in check_value_fields:
            continue

        value_fields = check_value_fields.get(table, [])
        if not value_fields:
            continue

        _check_missing_values(order, table, form, value_fields, issues)
        _check_gas_type_mismatch(order, table, form, gas_type_mapping, issues)
        _check_value_out_of_spec(order, table, form, brand_ranges, gas_type_mapping, issues)


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

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "brand": brand,
        "gas_type": gas_type,
        "unit": unit,
        "out_of_spec_values": out_of_spec_values,
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


def _parse_numeric(value: Any) -> float | None:
    """Parse numeric value from various formats."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None
