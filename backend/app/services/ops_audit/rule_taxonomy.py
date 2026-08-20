"""Rule taxonomy helpers for operations work order audits."""

from __future__ import annotations

from typing import Any


ISSUE_CATEGORIES = {
    "完整性问题",
    "规范性问题",
    "时间合理性问题",
    "数值逻辑问题",
    "一致性问题",
    "异常说明问题",
    "附件质量问题",
}

EXCLUDED_RULE_IDS = {
    "FLOW_MISSING",
    "FLOW_NO_CREATE",
    "FLOW_NO_CHECK",
    "FLOW_NO_REVIEW",
    "FLOW_END_EMPTY",
    "FLOW_TIME_ORDER",
    "FLOW_SEQUENCE",
    "FLOW_REMARK_LOW_VALUE",
    "LIFECYCLE_FINISH_NEAR_DEADLINE",
    "LIFECYCLE_FINISH_WITHOUT_EFFECTIVE_CLOSURE",
    "RF_AUDITOR_EMPTY",
    "RF_REVIEW_EMPTY",
    "RF_VALUE_FORMULA_MISMATCH",
}

EXCLUDED_RULE_PREFIXES = ("FLOW_", "LIFECYCLE_")


def is_excluded_rule(rule_id: str | None) -> bool:
    """Return whether a rule should be hidden from audit results."""

    rule = str(rule_id or "")
    return rule in EXCLUDED_RULE_IDS or rule.startswith(EXCLUDED_RULE_PREFIXES)


def issue_category(rule_id: str | None, category: str | None = None) -> str:
    """Normalize rule categories to a single problem-nature taxonomy."""

    rule = str(rule_id or "")
    current = str(category or "")
    if current in ISSUE_CATEGORIES:
        return current

    if is_excluded_rule(rule):
        return "规范性问题"
    if rule.startswith("ATTACHMENT_") or rule.startswith("REPORT_"):
        if rule.endswith("_VALUE_MISMATCH"):
            return "一致性问题"
        return "附件质量问题"
    if rule in {
        "RF_STATION_MISMATCH",
        "RF_RANGE_BY_GAS_TYPE_MISMATCH",
        "RF_POLLUTANT_TYPE_MISMATCH",
        "RF_DEVICE_IDENTITY_INCONSISTENT",
        "RF_ENUM_VALUE_INVALID",
        "RF_VISIBILITY_NO_DEVICE_FIELD_CONFLICT",
        "RF_RANGE_UNIT_MISMATCH",
    }:
        return "一致性问题"
    if rule in {
        "RF_CHECK_TIME_OUTSIDE_RANGE",
        "RF_CALIBRATION_DATE_EXPIRED",
        "RF_CALIBRATION_INTERVAL_TOO_LONG",
        "RF_REFERENCE_FLOWMETER_CERT_DATE_MISMATCH",
        "RF_HY_ENV_HUMIDITY_CALIBRATION_DATE_INVALID",
    }:
        return "时间合理性问题"
    if rule in {
        "RF_UNIT_MISMATCH",
        "RF_VALUE_FORMULA_MISMATCH",
        "RF_Q_GASEOUSFLOWCHECK_PRESSURE_TRUE_VALUE_MISMATCH",
        "RF_M_GASEOUSFLOWCHECK_ERROR_OUT_OF_RANGE",
        "RF_PM_MEMBRANE_ERROR_OUT_OF_RANGE",
        "RF_PM_PRESSURE_ERROR_MISMATCH",
        "RF_PM_TEMP_ERROR_MISMATCH",
        "RF_PM_TEMP_ERROR_OUT_OF_RANGE",
        "RF_PM_SAMPLE_TUBE_TEMP_ABNORMAL",
        "RF_ABNORMAL_RESULT_FIELD",
        "RF_PM_PRESSURE_ERROR_OUT_OF_RANGE",
        "RF_PM_PRESSURE_UNIT_MISMATCH",
        "RF_FIELD_POSITION_SUSPECT",
        "RF_MULTIPOINT_RANGE_INVALID",
        "RF_RANGE_OUT_OF_SPEC",
        "RF_Q_GASEOUS_FLOW_ENV_HUMIDITY_OUT_OF_RANGE",
        "RF_M_GASEOUS_CALIDEVICE_ENV_HUMIDITY_OUT_OF_RANGE",
        "RF_O3_VALUE_PASS_FIELD_POSITION_SUSPECT",
        "RF_O3_TRANSFER_RESULT_INVALID",
    }:
        return "数值逻辑问题"
    if rule in {"RF_O3_VALUE_PASS_FLOW_VALUE_MISSING"}:
        return "完整性问题"
    if rule in {"RF_PM_TEMP_PRESSURE_ERROR_UNRECALCULABLE"}:
        return "表单完整性问题"
    if rule in {"RF_CALIBRATION_DATE_SHOULD_BE_EMPTY"}:
        return "规范性问题"
    if rule in {
        "RF_ABNORMAL_VALUE_NO_REMARK",
        "RF_Q_PENDING_NO_REMARK",
        "RF_NO_DEVICE_WITHOUT_REMARK",
    }:
        return "异常说明问题"
    if rule in {
        "RF_TW_REMARK_LOW_VALUE",
        "REMARK_SEMANTIC_INCOMPLETE",
        "RF_PERSONNEL_VEHICLE_FORMAT_LOW_VALUE",
        "RF_PM_TAPE_USAGE_INVALID",
        "RF_PM_PAPER_TAPE_NOT_APPLICABLE_FILLED",
        "RF_HY_ENV_HUMIDITY_BEFORE_AFTER_UNCHANGED_SUSPECT",
    }:
        return "规范性问题"
    if rule in {"RF_HY_ENV_HUMIDITY_SENSOR_VALUE_MISSING"}:
        return "完整性问题"
    if "一致性" in current:
        return "一致性问题"
    if "时间" in current or "有效期" in current:
        return "时间合理性问题"
    if "数值" in current or "量程" in current or "结果合理性" in current:
        return "数值逻辑问题"
    if "附件" in current or "报告" in current:
        return "附件质量问题"
    if "规范" in current or "语义" in current:
        return "规范性问题"
    return "完整性问题"


def normalize_catalog_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Return a catalog rule with normalized problem-nature category metadata."""

    normalized = dict(rule)
    original = normalized.get("category")
    normalized["original_category"] = original
    normalized["category"] = issue_category(normalized.get("rule_id"), str(original or ""))
    normalized["display_status"] = "excluded" if is_excluded_rule(normalized.get("rule_id")) else "active"
    return normalized
