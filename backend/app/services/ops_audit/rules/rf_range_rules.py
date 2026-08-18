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
RANGE_UNIT_MISMATCH_RULE_ID = "RF_RANGE_UNIT_MISMATCH"
MONTHLY_GASEOUS_FLOW_RANGE_MISSING_RULE_ID = "RF_M_GASEOUS_FLOW_RANGE_MISSING"


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
    structured_weekly_profiles.update(RANGE_PROFILES.get("co_weekly_check_profiles", {}))
    structured_weekly_profiles.update(RANGE_PROFILES.get("nox_weekly_check_profiles", {}))
    structured_weekly_profiles.update(RANGE_PROFILES.get("so2_weekly_check_profiles", {}))
    structured_weekly_profiles.update(RANGE_PROFILES.get("pm_weekly_check_profiles", {}))

    if not check_value_fields:
        return

    for table, form in forms:
        if form.get("_query_error"):
            continue

        if table == "RF_M_GASEOUSFLOWCHECK":
            _check_monthly_gaseous_flow_range_missing(order, table, form, issues)
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

    raw_brand = form.get(profile.get("brand_field") or "DEVICEBRAND") or form.get("BRAND")
    model_text = _profile_model_text(form)
    brand = _normalize_profile_brand(
        raw_brand,
        profile.get("brand_aliases", {}),
        model_text,
    )
    if not brand:
        return
    model_brand = _model_brand_hint(model_text)
    if model_brand and model_brand != brand:
        # A conflicting model is stronger evidence that the selected brand
        # range profile is not trustworthy. Do not turn a profile mismatch
        # into a business abnormal-value issue.
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
        spec = _structured_range_spec_for_field(form, field_name, field_config, brand)
        if not spec:
            continue
        comparison_result = _comparison_text_satisfies_spec(form.get(field_name), spec)
        if comparison_result is True:
            continue
        raw_unit = _extract_value_unit(form.get(field_name))
        unit_status = _unit_comparison_status(raw_unit, spec.get("unit"))
        if unit_status == "incompatible":
            _add_range_unit_mismatch_issue(
                order,
                table,
                profile,
                brand,
                field_config,
                field_name,
                form.get(field_name),
                raw_unit,
                spec,
                issues,
            )
            continue
        converted_value = _convert_structured_value_to_spec_unit(form, field_config, form.get(field_name), value, spec, brand)
        if converted_value is not None:
            value = converted_value
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
                "raw_unit": raw_unit,
                "unit_status": unit_status,
                "unit_source": "value" if raw_unit else "profile_default",
            }
        )

    for item in out_of_spec_values:
        handling_record_candidates = _handling_record_candidates(form, item.get("field"))
        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "rf_table": table,
            "brand": brand,
            "pollutant_type": form.get(pollutant_field),
            "field": item["field"],
            "field_label": item["label"],
            "observed_value": {
                "raw_value": item["raw_value"],
                "normalized_value": item["value"],
                "raw_unit": item["raw_unit"],
                "normalized_unit": item["unit"],
                "unit_conversion_applied": _unit_conversion_applied(item),
            },
            "expected_range": {
                "min": item["min"],
                "max": item["max"],
                "operator": item["operator"],
                "unit": item["unit"],
                "text": _range_spec_text(item),
            },
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
                f"{profile.get('display_name') or table}周检{item['label']}检查值"
                f"({_out_of_spec_value_text(item)})"
                f"超出{brand}品牌正常范围({_range_spec_text(item)})"
            ),
            json.dumps(evidence, ensure_ascii=False, default=str),
        )


def _add_range_unit_mismatch_issue(
    order: dict[str, Any],
    table: str,
    profile: dict[str, Any],
    brand: str,
    field_config: dict[str, Any],
    field_name: str,
    raw_value: Any,
    raw_unit: str,
    spec: dict[str, Any],
    issues: list[Issue],
) -> None:
    label = str(field_config.get("label") or field_name)
    spec_unit = str(spec.get("unit") or "").strip()
    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "brand": brand,
        "field": field_name,
        "label": label,
        "raw_value": raw_value,
        "raw_unit": raw_unit,
        "expected_unit": spec_unit,
        "expected_range": _range_spec_text(
            {
                "min": spec.get("min"),
                "max": spec.get("max"),
                "operator": spec.get("operator"),
                "unit": spec_unit,
            }
        ),
        "report_classification": "technical_diagnostic",
        "counts_as_work_order_issue": False,
    }
    add_issue(
        issues,
        RANGE_UNIT_MISMATCH_RULE_ID,
        "一致性",
        "中",
        f"rf.{table}.{field_name}",
        (
            f"{profile.get('display_name') or table}周检{label}检查值({raw_value})单位为{raw_unit}，"
            f"但{brand}品牌正常范围单位为{spec_unit}，单位不一致，无法进行范围比对"
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
            comparison_value = _normalize_monthly_flow_value_to_range_unit(value, unit, min_value, max_value)
            if comparison_value < min_value or comparison_value > max_value:
                out_of_spec_value = {
                    "gas_type": gas_type,
                    "range_field": range_field,
                    "raw_range": form.get(range_field),
                    "field": field,
                    "value": comparison_value,
                    "min": min_value,
                    "max": max_value,
                    "unit": unit,
                }
                if comparison_value != value:
                    out_of_spec_value["raw_value"] = value
                out_of_spec_values.append(
                    out_of_spec_value
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


def _check_monthly_gaseous_flow_range_missing(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    issues: list[Issue],
) -> None:
    missing = []
    for gas_type, range_field, _value_fields in MONTHLY_GASEOUS_FLOW_FIELDS:
        if range_field not in form:
            continue
        value = str(form.get(range_field) or "").strip()
        if value in {"", "/", "-", "无", "无此参数", "不适用"}:
            missing.append({"gas_type": gas_type, "field": range_field, "value": value})
    if not missing:
        return

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "missing_ranges": missing,
    }
    gases = "、".join(item["gas_type"] for item in missing)
    fields = "、".join(item["field"] for item in missing)
    add_issue(
        issues,
        MONTHLY_GASEOUS_FLOW_RANGE_MISSING_RULE_ID,
        "表单完整性",
        "高",
        f"rf.{table}.flow_range",
        f"月度气体流量检查{gases}流量范围未填写或无效: {fields}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _normalize_monthly_flow_value_to_range_unit(
    value: float,
    range_unit: str,
    min_value: float,
    max_value: float,
) -> float:
    canonical_unit = _canonical_unit(range_unit)
    if canonical_unit == "ml/min" and max_value >= 50 and 0 < value < 10:
        return value * 1000
    if canonical_unit == "l/min" and max_value <= 10 and value >= 50:
        return value / 1000
    return value


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


def _normalize_profile_brand(brand: Any, aliases: dict[str, Any], model: Any = None) -> str | None:
    if not brand:
        return None
    brand_text = str(brand).strip()
    if not brand_text:
        return None
    brand_upper = brand_text.upper()
    if brand_upper == "TH":
        return "TH" if _is_tianhong_200xh_model(model) else "THERMO"
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


def _profile_model_text(form: dict[str, Any]) -> str:
    fields = (
        "DEVICEMODEL",
        "DEVICE_MODEL",
        "MODEL",
        "DEIVCEMODEL",
        "DEMODEL",
        "DEVICEMODELO3",
        "DEVICEMODELNO2",
        "DEVICEMODELSO2",
        "DEVICEMODELCO",
    )
    return " ".join(str(form.get(field) or "") for field in fields).strip()


def _model_brand_hint(model: Any) -> str | None:
    normalized = re.sub(r"[^A-Z0-9]+", "", str(model or "").upper())
    if not normalized:
        return None
    if re.search(r"(?:^|THERMO|TE)(?:42|43|48|49)I(?:PS)?$", normalized) or any(
        token in normalized for token in ("SHARP5030", "5014I")
    ):
        return "THERMO"
    if re.fullmatch(r"T(?:100|200|300|400|500)(?:U)?", normalized):
        return "API"
    if normalized.startswith("AQMS"):
        return "FPI"
    if re.fullmatch(r"200[1-4]H", normalized):
        return "TH"
    return None


def _is_tianhong_200xh_model(model: Any) -> bool:
    model_text = str(model or "").upper()
    return any(marker in model_text for marker in ("2001H", "2002H", "2003H", "2004H"))


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


def _convert_value_to_spec_unit(raw_value: Any, numeric: float, spec: dict[str, Any]) -> float | None:
    return _convert_unit(numeric, _extract_value_unit(raw_value), spec.get("unit"))


def _structured_range_spec_for_field(
    form: dict[str, Any],
    field_name: str,
    field_config: dict[str, Any],
    brand: str,
) -> dict[str, Any] | None:
    spec = (
        _inline_range_spec_for_field(form, field_name)
        or _inline_range_spec_for_label(form, field_config.get("label") or field_name)
        or (field_config.get("ranges") or {}).get(brand)
    )
    if not spec:
        return None
    spec = dict(spec)
    if (
        brand == "ESA"
        and str(field_config.get("key") or "") in {"reaction_pressure", "sample_pressure"}
        and _canonical_unit(_extract_value_unit(form.get(field_name))) == "hpa"
        and _canonical_unit(spec.get("unit")) == "mv"
    ):
        return None
    if (
        field_name == "AIRTEMPVALUE"
        and str(field_config.get("key") or "") == "air_temperature"
        and "SHARP5030" in _profile_model_text(form).upper()
    ):
        spec["max"] = 60
        spec["operator"] = "<="
        spec["unit"] = spec.get("unit") or "℃"
    return spec


def _convert_structured_value_to_spec_unit(
    form: dict[str, Any],
    field_config: dict[str, Any],
    raw_value: Any,
    numeric: float,
    spec: dict[str, Any],
    brand: str,
) -> float | None:
    converted = _convert_value_to_spec_unit(raw_value, numeric, spec)
    if converted is not None:
        return converted
    raw_unit = _extract_value_unit(raw_value)
    key = str(field_config.get("key") or "")
    target_unit = _canonical_unit(spec.get("unit"))
    if not raw_unit and key == "ozone_flow" and target_unit == "ml/min" and 0 < numeric < 1:
        return numeric * 1000.0
    if not raw_unit and key == "sample_pressure" and brand == "XH" and target_unit == "kpa" and 20 <= numeric <= 35:
        return _convert_unit(numeric, "inHg", "kPa")
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
    converted_threshold = _convert_unit(threshold, _extract_value_unit(text), spec.get("unit"))
    if converted_threshold is not None:
        threshold = converted_threshold

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


def _extract_value_unit(value: Any) -> str:
    if value is None or isinstance(value, (int, float)):
        return ""
    text = str(value)
    match = re.search(
        r"(In-Hg-A|inHgA|inHg|in-Hg|hPa|HPA|KPa|kPa|mmHg|TORR|torr|PSIA|psia|"
        r"ml/min|mL/min|l/min|L/min|sccm|SCCM|scc|SLPM|mV|V|%)",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _unit_comparison_status(source_unit: Any, target_unit: Any) -> str:
    source = _canonical_unit(source_unit)
    target = _canonical_unit(target_unit)
    if not source or not target:
        return "unknown"
    if source == target or _convert_unit(1.0, source, target) is not None:
        return "compatible"
    return "incompatible"


def _convert_unit(value: float, source_unit: Any, target_unit: Any) -> float | None:
    source = _canonical_unit(source_unit)
    target = _canonical_unit(target_unit)
    if not source or not target or source == target:
        return value if source and target and source == target else None
    pressure_to_kpa = {
        "kpa": 1.0,
        "hpa": 0.1,
        "mmhg": 0.133322368,
        "torr": 0.133322368,
        "inhg": 3.38638867,
        "psia": 6.89475729,
    }
    if source in pressure_to_kpa and target in pressure_to_kpa:
        return value * pressure_to_kpa[source] / pressure_to_kpa[target]
    factors = {
        "l/min": {"ml/min": 1000.0},
        "ml/min": {"l/min": 0.001},
        "v": {"mv": 1000.0},
        "mv": {"v": 0.001},
    }
    factor = factors.get(source, {}).get(target)
    if factor is None:
        return None
    return value * factor


def _canonical_unit(unit: Any) -> str:
    text = str(unit or "").strip()
    if not text:
        return ""
    normalized = text.replace("／", "/").replace("升", "L").replace("毫升", "mL")
    lower = normalized.lower()
    if lower in {"l/min", "lpm", "slpm"}:
        return "l/min"
    if lower in {"ml/min", "mlpm", "sccm", "scc"}:
        return "ml/min"
    if lower == "v":
        return "v"
    if lower == "mv":
        return "mv"
    if lower == "kpa":
        return "kpa"
    if lower == "hpa":
        return "hpa"
    if lower in {"mmhg"}:
        return "mmhg"
    if lower == "torr":
        return "torr"
    if lower in {"in-hg-a", "inhga", "inhg", "in-hg"}:
        return "inhg"
    if lower == "psia":
        return "psia"
    return lower


def _inline_range_spec_for_field(form: dict[str, Any], field_name: str) -> dict[str, Any] | None:
    row_field = _row_field_for_value_field(field_name)
    if not row_field:
        return None
    return _parse_inline_range_spec(form.get(row_field))


def _inline_range_spec_for_label(form: dict[str, Any], label: Any) -> dict[str, Any] | None:
    label_text = str(label or "").strip()
    if not label_text:
        return None
    for field in ("REMARK", "REMARKS", "CHECKREMARK", "DESCRIPTION"):
        text = str(form.get(field) or "").strip()
        if not text or label_text not in text:
            continue
        for segment in re.split(r"[;；。,\n\r]+", text):
            if label_text not in segment:
                continue
            spec = _parse_inline_range_spec(segment)
            if spec:
                return spec
    return None


def _row_field_for_value_field(field_name: str) -> str | None:
    if not field_name.endswith("VALUE"):
        return None
    return f"{field_name[:-5]}ROW"


def _parse_inline_range_spec(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or "范围" not in text:
        return None
    unit_match = re.search(
        r"(In-Hg-A|inHgA|inHg|in-Hg|hPa|HPA|KPa|kPa|PSIA|psia|mmHg|TORR|torr|"
        r"sccm|SCCM|ml/min|mL/min|L/min|SLPM|mV|V|%)",
        text,
    )
    unit = unit_match.group(1) if unit_match else ""

    range_match = re.search(
        r"([-+]?\d+(?:\.\d+)?)\s*(?:~|～|-|－|—|至|到)\s*([-+]?\d+(?:\.\d+)?)",
        text,
    )
    if range_match:
        left = float(range_match.group(1))
        right = float(range_match.group(2))
        return {"min": min(left, right), "max": max(left, right), "unit": unit, "source": "inline_row"}

    plus_minus_match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*(?:±|\+/-)\s*([-+]?\d+(?:\.\d+)?)", text)
    if plus_minus_match:
        center = float(plus_minus_match.group(1))
        delta = float(plus_minus_match.group(2))
        return {"min": center - delta, "max": center + delta, "unit": unit, "source": "inline_row"}

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


def _unit_conversion_applied(item: dict[str, Any]) -> bool:
    raw_unit = _canonical_unit(item.get("raw_unit"))
    normalized_unit = _canonical_unit(item.get("unit"))
    return bool(raw_unit and normalized_unit and raw_unit != normalized_unit)


def _out_of_spec_value_text(item: dict[str, Any]) -> str:
    raw_value = item.get("raw_value")
    if not _unit_conversion_applied(item):
        return str(raw_value)
    normalized_value = item.get("value")
    if isinstance(normalized_value, float):
        normalized_text = f"{normalized_value:g}"
    else:
        normalized_text = str(normalized_value)
    normalized_unit = str(item.get("unit") or "").strip()
    converted = f"{normalized_text} {normalized_unit}".strip()
    return f"{raw_value}，换算为{converted}"


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


def _handling_record_candidates(form: dict[str, Any], value_field: Any = None) -> dict[str, Any]:
    candidates: dict[str, Any] = {}
    for field, value in form.items():
        if str(field).upper() == "PROCESSTYPE":
            continue
        if _is_handling_record_field(field):
            candidates[str(field)] = value
    for field in _field_specific_remark_fields(value_field):
        if field in form and field not in candidates:
            candidates[field] = form.get(field)
    return candidates


def _field_specific_remark_fields(value_field: Any) -> list[str]:
    field = str(value_field or "").strip()
    if not field:
        return []
    upper = field.upper()
    candidates = []
    if upper.endswith("BCHECKVALUE"):
        candidates.append(field[: -len("BCHECKVALUE")] + "CHECKROW")
    if upper.endswith("VALUE"):
        candidates.append(field[: -len("VALUE")] + "ROW")
    if upper.endswith("CHECKVALUE"):
        candidates.append(field[: -len("CHECKVALUE")] + "CHECKROW")
    candidates.append(f"{field}ROW")
    deduped = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


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
