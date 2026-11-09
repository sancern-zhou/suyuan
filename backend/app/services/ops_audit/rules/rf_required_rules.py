"""RF form required field and low-value rules for operations work order audits."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.ops_audit.config import (
    load_low_value_remarks,
    load_rf_field_profiles,
)
from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue

LOW_VALUE_REMARKS = load_low_value_remarks()
RF_FIELD_PROFILES = load_rf_field_profiles()

# 组分站表单（sup_rf_common 及 sup_rf_* 专用分表）的列语义按 ruleitemtag 在
# sup_form_profiles.yaml 里单独建档，不走主网字段档案。主网温湿度字段清单里的
# 通用列名（temperature/humidity）在 sup_rf_pm1monitorinspection 等分表上恰好
# 同名但恒为空列（源库全量 NULL），按主网口径判定会产生 100% 命中的结构性误报，
# 因此主网温湿度规则跳过 SUP_ 前缀表。
SUP_FORM_TABLE_PREFIX = "SUP_"


def check_rf_required_fields(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Check RF form required fields for empty or low-value content.

    This rule identifies:
    - RF_ENV_TEMP_HUMIDITY_EMPTY: Indoor temperature and humidity fields are empty

    The rule is configurable via rf_field_profiles.yaml and business_calibration.yaml.
    """

    has_order_env_temp_humidity = _has_complete_env_temp_humidity(forms)
    for table, form in forms:
        if form.get("_query_error"):
            continue

        _check_inspection_person_vehicle(order, table, form, issues)
        _check_pm_tape_usage(order, table, form, issues)
        _check_env_temp_humidity(order, table, form, issues, has_order_env_temp_humidity)


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
    if is_teom:
        _check_teom_paper_tape_not_applicable(order, table, form, device_model, issues)
    if is_teom:
        problem_reason = (
            f"DEVICEMODEL={device_model}按TEOM/振荡天平类设备审核，"
            f"应填写{expected_label}；当前{field}为空或为/，"
            "无法判断滤膜负载或处置状态。"
        )
        message = (
            f"颗粒物周检{expected_label}为空或为/，"
            f"DEVICEMODEL={device_model}应填写{expected_label}"
        ) if is_placeholder else f"颗粒物周检{expected_label}需语义复核: {value}"
    else:
        problem_reason = (
            f"DEVICEMODEL={device_model or '<空>'}按非1405颗粒物仪器审核，"
            f"应填写{expected_label}；当前{field}为空或为/，"
            "无法判断纸带剩余量或处置状态。"
        )
        message = (
            f"颗粒物周检{expected_label}为空或为/，"
            f"非1405颗粒物仪器应填写{expected_label}"
        ) if is_placeholder else f"颗粒物周检{expected_label}需语义复核: {value}"

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
        "problem_reason": problem_reason if is_placeholder else "",
        "expected": (
            "DEVICEMODEL包含1405时按TEOM/振荡天平类设备审核，"
            "应填写TEOM滤膜负载及处置情况；其他颗粒物仪器应填写纸带使用量及处置情况。"
            "目标字段为空或/为明确不规范；其他内容交由语义复核判断。"
        ),
    }
    add_issue(
        issues,
        "RF_PM_TAPE_USAGE_INVALID",
        "规范性问题",
        "中",
        f"rf.{table}.{field}",
        message,
        json.dumps(evidence, ensure_ascii=False, default=str),
    )


def _check_teom_paper_tape_not_applicable(
    order: dict[str, Any],
    table: str,
    form: dict[str, Any],
    device_model: str,
    issues: list[Issue],
) -> None:
    """1405/TEOM instruments do not use the paper-tape field.

    The TEOM filter field is audited separately above.  A substantive paper
    tape entry is therefore a distinct applicability error; placeholders such
    as ``/`` and ``无`` are treated as an explicit non-applicable marker.
    """

    if "TAPEUSAGEDISPOSAL" not in form:
        return
    value = _text(form.get("TAPEUSAGEDISPOSAL"))
    if value.lower() in {"", "/", "-", "无", "不适用", "无需", "无纸带"}:
        return
    if re.search(r"(?:无|不使用|未使用|无需使用)纸带[。；;，,\s]*$", value):
        if not re.search(r"(?:已更换|剩余|余量|用量|使用量|\d+\s*%)", value):
            return

    evidence = {
        "working_order_code": order.get("WORKINGORDERCODE"),
        "rf_table": table,
        "device_model": device_model,
        "field": "TAPEUSAGEDISPOSAL",
        "value": value,
        "expected": "1405/TEOM设备不使用纸带，纸带字段应为空、/或明确不适用。",
    }
    add_issue(
        issues,
        "RF_PM_PAPER_TAPE_NOT_APPLICABLE_FILLED",
        "规范性问题",
        "中",
        f"rf.{table}.TAPEUSAGEDISPOSAL",
        f"1405/TEOM设备不使用纸带，但纸带字段填写为: {value}",
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

    if table.startswith(SUP_FORM_TABLE_PREFIX):
        return
    if has_order_env_temp_humidity:
        return
    if table == "RF_HY_VISIBILITYCALI" and _form_indicates_not_applicable_device(form):
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

    remark_candidates = _remark_candidates(form)
    has_remark = any(str(value or "").strip() for value in remark_candidates.values())
    if missing_temp:
        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "rf_table": table,
            "missing_dimension": "temperature",
            "missing_fields": missing_temp,
            "missing_temperature": missing_temp,
            "missing_humidity": [],
            "remark_candidates": remark_candidates,
            "needs_semantic_review": has_remark,
        }
        add_issue(
            issues,
            "RF_ENV_TEMP_HUMIDITY_EMPTY",
            "表单完整性",
            "中",
            f"rf.{table}.{missing_temp[0]}",
            f"RF表单温度字段({', '.join(missing_temp[:2])})未填",
            json.dumps(evidence, ensure_ascii=False, default=str),
        )
    if missing_humidity:
        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "rf_table": table,
            "missing_dimension": "humidity",
            "missing_fields": missing_humidity,
            "missing_temperature": [],
            "missing_humidity": missing_humidity,
            "remark_candidates": remark_candidates,
            "needs_semantic_review": has_remark,
        }
        add_issue(
            issues,
            "RF_ENV_TEMP_HUMIDITY_EMPTY",
            "表单完整性",
            "中",
            f"rf.{table}.{missing_humidity[0]}",
            f"RF表单湿度字段({', '.join(missing_humidity[:2])})未填",
            json.dumps(evidence, ensure_ascii=False, default=str),
        )


def _remark_candidates(form: dict[str, Any]) -> dict[str, Any]:
    candidates = {}
    for field, value in form.items():
        upper = str(field or "").upper()
        if any(token in upper for token in ("REMARK", "REMARKS", "CHECKREMARK", "DESCRIPTION", "SITUATION", "COMMENT")):
            candidates[str(field)] = value
    return candidates


def _has_complete_env_temp_humidity(forms: list[tuple[str, dict[str, Any]]]) -> bool:
    temp_fields = RF_FIELD_PROFILES.get("temperature_fields", [])
    humidity_fields = RF_FIELD_PROFILES.get("humidity_fields", [])
    for table, form in forms:
        if form.get("_query_error") or table.startswith(SUP_FORM_TABLE_PREFIX):
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
        "无能见度分析仪",
        "无能见度仪",
        "未配置能见度",
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
