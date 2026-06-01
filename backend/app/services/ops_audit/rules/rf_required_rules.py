"""RF form required field and low-value rules for operations work order audits."""

from __future__ import annotations

import json
from typing import Any

from app.services.ops_audit.config import (
    load_low_value_remarks,
    load_rf_field_profiles,
)
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue

LOW_VALUE_REMARKS = load_low_value_remarks()
RF_FIELD_PROFILES = load_rf_field_profiles()


def check_rf_required_fields(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Check RF form required fields for empty or low-value content.

    This rule identifies:
    - RF_REQUIRED_FIELD_LOW_VALUE: Key fields (personnel, vehicle, remarks) are empty or contain low-value content like "/", "-", "正常", "无"
    - RF_ENV_TEMP_HUMIDITY_EMPTY: Indoor temperature and humidity fields are empty

    The rule is configurable via rf_field_profiles.yaml and business_calibration.yaml.
    """

    has_order_env_temp_humidity = _has_complete_env_temp_humidity(forms)
    for table, form in forms:
        if form.get("_query_error"):
            continue

        _check_low_value_fields(order, table, form, issues)
        _check_inspection_person_vehicle(order, table, form, issues)
        _check_pm_tape_usage(order, table, form, issues)
        _check_env_temp_humidity(order, table, form, issues, has_order_env_temp_humidity)


def _check_low_value_fields(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    issues: list[Issue],
) -> None:
    """Check for low-value content in key fields."""

    low_value_groups = RF_FIELD_PROFILES.get("low_value_field_groups", {})
    if not low_value_groups:
        return

    empty_fields = []
    low_value_fields = []

    for group_name, field_candidates in low_value_groups.items():
        for field in field_candidates:
            if field not in form:
                continue

            value = form.get(field)
            if value is None or str(value).strip() == "":
                empty_fields.append(f"{group_name}.{field}")
                continue

            value_str = str(value).strip()
            if value_str in LOW_VALUE_REMARKS:
                low_value_fields.append(f"{group_name}.{field}={value_str}")

    if not (empty_fields or low_value_fields):
        return

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "empty_fields": empty_fields,
        "low_value_fields": low_value_fields,
        "sample_form_data": {k: v for k, v in list(form.items())[:10] if v is not None},
    }

    message_parts = []
    if empty_fields:
        message_parts.append(f"字段为空: {', '.join(empty_fields[:3])}")
    if low_value_fields:
        message_parts.append(f"低价值填报: {', '.join(low_value_fields[:3])}")

    add_issue(
        issues,
        "RF_REQUIRED_FIELD_LOW_VALUE",
        "表单完整性",
        "中",
        f"rf.{table}.required_fields",
        f"RF表单关键字段{'; '.join(message_parts)}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _check_inspection_person_vehicle(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    issues: list[Issue],
) -> None:
    if table != "RF_W_INSPECTIONSUMMARY":
        return

    violations = []
    person = _text(form.get("Users") or form.get("PATROLMAN"))
    vehicle = _text(form.get("Car") or form.get("VEHICLE"))
    if not _looks_like_person_name(person):
        violations.append({"field": "Users/PATROLMAN", "value": person, "reason": "巡检人员应填写姓名"})
    if not _looks_like_vehicle(vehicle):
        violations.append({"field": "Car/VEHICLE", "value": vehicle, "reason": "车辆应填写车牌号或交通工具"})
    if not violations:
        return

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "violations": violations,
    }
    add_issue(
        issues,
        "RF_PERSONNEL_VEHICLE_FORMAT_LOW_VALUE",
        "规范性问题",
        "中",
        f"rf.{table}.person_vehicle",
        f"每周巡检汇总表人员/车辆填写不规范: {violations[0]['field']}={violations[0]['value']}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _check_pm_tape_usage(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    issues: list[Issue],
) -> None:
    if table != "RF_W_PMCHECK":
        return
    device_model = _text(form.get("DEVICEMODEL"))
    pollutant_type = _text(form.get("POLLUTANTTYPE"))
    is_teom = "1405" in device_model
    field = "TEOMMEMBRANEDISPOSAL" if is_teom else "TAPEUSAGEDISPOSAL"
    if field not in form:
        return
    value = _text(form.get(field))
    is_placeholder = value in {"", "/"}
    expected_label = "TEOM滤膜负载及处置情况" if is_teom else "纸带使用量及处置情况"
    instrument_type = "teom_filter" if is_teom else "paper_tape"

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "pollutant_type": pollutant_type,
        "device_model": device_model,
        "instrument_type": instrument_type,
        "field": field,
        "field_label": expected_label,
        "value": value,
        "needs_semantic_review": not is_placeholder,
        "expected": (
            "DEVICEMODEL包含1405时应填写TEOM滤膜负载及处置情况；"
            "其他颗粒物仪器应填写纸带使用量及处置情况。"
            "空值或/为明确不规范；其他内容交由语义复核判断。"
        ),
    }
    add_issue(
        issues,
        "RF_PM_TAPE_USAGE_INVALID",
        "规范性问题",
        "中",
        f"rf.{table}.{field}",
        f"颗粒物周检{expected_label}需复核: {value or '<空>'}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _check_env_temp_humidity(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    issues: list[Issue],
    has_order_env_temp_humidity: bool = False,
) -> None:
    """Check for missing indoor temperature and humidity fields."""

    if has_order_env_temp_humidity:
        return
    if _form_indicates_not_applicable_device(form):
        return

    temp_fields = RF_FIELD_PROFILES.get("temperature_fields", [])
    humidity_fields = RF_FIELD_PROFILES.get("humidity_fields", [])

    if not temp_fields and not humidity_fields:
        return

    missing_temp = []
    missing_humidity = []

    for field in temp_fields:
        actual_field, value = _form_value_case_insensitive(form, field)
        if actual_field:
            if value is None or str(value).strip() in {"", "/", "-", "0"}:
                missing_temp.append(actual_field)

    for field in humidity_fields:
        actual_field, value = _form_value_case_insensitive(form, field)
        if actual_field:
            if value is None or str(value).strip() in {"", "/", "-", "0"}:
                missing_humidity.append(actual_field)

    if not missing_temp and not missing_humidity:
        return

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "missing_temperature": missing_temp,
        "missing_humidity": missing_humidity,
    }

    message_parts = []
    if missing_temp:
        message_parts.append(f"温度字段({', '.join(missing_temp[:2])})未填")
    if missing_humidity:
        message_parts.append(f"湿度字段({', '.join(missing_humidity[:2])})未填")

    add_issue(
        issues,
        "RF_ENV_TEMP_HUMIDITY_EMPTY",
        "表单完整性",
        "中",
        f"rf.{table}.env_temp_humidity",
        f"RF表单{'; '.join(message_parts)}",
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _has_complete_env_temp_humidity(forms: list[tuple[str, dict[str, Any]]]) -> bool:
    temp_fields = RF_FIELD_PROFILES.get("temperature_fields", [])
    humidity_fields = RF_FIELD_PROFILES.get("humidity_fields", [])
    for _table, form in forms:
        if form.get("_query_error"):
            continue
        has_temp = any(
            actual_field and _has_meaningful_env_value(value)
            for actual_field, value in (_form_value_case_insensitive(form, field) for field in temp_fields)
        )
        has_humidity = any(
            actual_field and _has_meaningful_env_value(value)
            for actual_field, value in (_form_value_case_insensitive(form, field) for field in humidity_fields)
        )
        if has_temp and has_humidity:
            return True
    return False


def _form_value_case_insensitive(form: dict[str, Any], field: str) -> tuple[str | None, Any]:
    if field in form:
        return field, form.get(field)
    target = str(field).lower()
    for actual_field, value in form.items():
        if str(actual_field).lower() == target:
            return str(actual_field), value
    return None, None


def _has_meaningful_env_value(value: Any) -> bool:
    return value is not None and str(value).strip() not in {"", "/", "-", "0"}


def _form_indicates_not_applicable_device(form: dict[str, Any]) -> bool:
    text = " ".join(
        _text(form.get(field))
        for field in (
            "REMARK",
            "Remark",
            "remark",
            "DESCRIPTION",
            "Description",
            "DESCRIPTIONTA",
            "SITUATION",
            "Situation",
        )
    )
    not_applicable_markers = (
        "无该设备",
        "无此设备",
        "无对应设备",
        "无设备",
        "未配置",
        "不适用",
        "无需",
        "无此项",
    )
    special_maintenance_markers = (
        "流动监测车",
        "监测车",
        "非常规",
        "不完全一样",
        "停运状态",
    )
    return any(marker in text for marker in not_applicable_markers + special_maintenance_markers)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _looks_like_person_name(value: str) -> bool:
    if not value or value in LOW_VALUE_REMARKS:
        return False
    if len(value) >= 24 and "-" in value:
        return False
    if any(token in value.lower() for token in {"null", "none", "userid"}):
        return False
    return bool(any("\u4e00" <= char <= "\u9fff" for char in value)) or 2 <= len(value) <= 20


def _looks_like_vehicle(value: str) -> bool:
    if not value or value in LOW_VALUE_REMARKS:
        return False
    transport_keywords = (
        "步行",
        "骑行",
        "电动车",
        "自行车",
        "公交",
        "公共交通",
        "地铁",
        "出租",
        "网约车",
        "交通工具",
        "未开车",
        "乘坐",
    )
    if any(keyword in value for keyword in transport_keywords):
        return True
    import re

    return bool(re.search(r"[\u4e00-\u9fff][A-Z][.\-\s·]?[A-Z0-9]{5,6}", value.upper()))


def _numeric_value(value: str) -> float | None:
    import re

    match = re.search(r"\d+(?:\.\d+)?", value)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None
