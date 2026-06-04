"""Configuration loading for operations work order audit."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from app.services.ops_audit.rule_taxonomy import normalize_catalog_rule


CONFIG_DIR = Path(__file__).resolve().parent / "configs"

DEFAULT_LOW_VALUE_REMARKS = {
    "/",
    "-",
    "正常",
    "无异常",
    "已完成",
    "完成",
    "无",
    "任务检查单",
    "计划任务单",
    "创建工单",
    "清洗",
    "检查",
    "合格",
}

DEFAULT_BRAND_ALIASES = {
    "API": {"API"},
    "THERMO": {"THERMO", "TE", "热电"},
}

DEFAULT_DEVICE_IDENTITY_PROFILES = {
    "history_days": 370,
    "history_limit": 5000,
    "short_history_days": 30,
    "previous_same_station_limit": 20,
    "enabled_order_types": ["Check", "SupCheck"],
    "enabled_maintenance_types": ["Week", "TwoWeek", "Month", "Quarter", "HalfYear", "Year"],
    "identity_fields": [
        {"key": "brand", "label": "品牌", "severity": "中"},
        {"key": "model", "label": "型号", "severity": "中"},
        {"key": "device_code", "label": "设备编号", "severity": "中"},
        {"key": "range", "label": "量程", "severity": "中"},
    ],
    "rf_identity_fields": {
        "brand": ["DEVICEBRAND", "BRAND"],
        "model": ["DEVICEMODEL", "MODEL"],
        "device_code": ["DEVICECODE", "DEVICECODEN", "DEVICECODE_NEW"],
        "range": ["RANGEVALUE", "RANGE", "MEASURERANGE", "FULLSCALE"],
    },
    "base_device_fields": {
        "brand": ["DEVICEBRAND"],
        "model": ["DEVICEMODEL"],
        "device_code": ["DEVICECODE"],
    },
    "replacement_tables": ["RF_Y_DEVICECHANGE", "RF_Y_DEVICEREPAIR"],
    "replacement_keywords": ["更换", "替换", "维修", "报废", "停用", "启用"],
}

DEFAULT_ATTACHMENT_REQUIREMENTS = {
    "global_keywords": {
        "report": ["报告", "记录", "检查单", "维护单", "report"],
        "certificate": ["证书", "检定", "校准证", "certificate", "cert"],
        "curve": ["曲线", "线性", "多点", "curve"],
        "photo": ["照片", "图片", "现场", "水印", "jpg", "jpeg", "png", "image", "photo"],
    },
    "photo_extensions": [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".heic"],
    "requirements": [
        {
            "id": "MONTH_FLOW_CHECK_REPORT",
            "name": "月流量检查报告",
            "enabled": True,
            "order_types": ["Check", "SupCheck"],
            "maintenance_types": ["Month"],
            "rf_tables": ["RF_M_GASEOUSFLOWCHECK", "RF_Q_GaseousFlowCheck"],
            "required_types": ["report"],
            "severity": "高",
            "suggestion": "补充月流量检查报告或可追溯记录附件。",
        },
        {
            "id": "TWOWEEK_PM_FLOW_CHECK_REPORT",
            "name": "两周颗粒物流量检查报告",
            "enabled": True,
            "order_types": ["Check", "SupCheck"],
            "maintenance_types": ["TwoWeek"],
            "rf_tables": ["RF_TW_PmFlowCheck", "RF_TW_PmFlowCalibrate"],
            "required_types": ["report"],
            "severity": "高",
            "suggestion": "补充颗粒物流量检查报告或校准记录附件。",
        },
        {
            "id": "MULTIPOINT_CALIBRATION_CURVE",
            "name": "多点校准曲线图",
            "enabled": True,
            "order_types": ["Check", "SupCheck"],
            "maintenance_types": ["Quarter", "HalfYear", "Year"],
            "rf_tables": [
                "RF_Q_GASEOUSMULTIPOINT_CO",
                "RF_Q_GASEOUSMULTIPOINT_NO2",
                "RF_Q_GASEOUSMULTIPOINT_O3",
                "RF_Q_GASEOUSMULTIPOINT_SO2",
            ],
            "required_types": ["report", "curve"],
            "severity": "高",
            "suggestion": "补充多点校准报告和曲线图附件。",
        },
        {
            "id": "PREVENTIVE_MAINTENANCE_REPORT",
            "name": "预防性维护报告",
            "enabled": True,
            "order_types": ["Maintain", "Check", "SupCheck"],
            "maintenance_types": ["Quarter", "HalfYear", "Year"],
            "rf_tables": ["RF_Y_PreventiveMaintenance"],
            "required_types": ["report", "photo"],
            "severity": "中",
            "suggestion": "补充预防性维护报告和现场照片附件。",
        },
    ],
}

DEFAULT_AUDIT_WINDOW = {
    "audit_window": {
        "anchor_weekday": "Wednesday",
        "created_start_offset_days": 14,
        "created_end_offset_days": 7,
        "order_statuses": ["Finish"],
        "timezone": "Asia/Shanghai",
        "include_auto_finish_risk": True,
    }
}

DEFAULT_RF_NUMERIC_PROFILES = {
    "unit_whitelist": ["ppm", "ug/m3", "mg/m3", "ml/min", "L/min", "mmHg", "%", "HZ", "℃"],
    "formula_definitions": [
        {
            "id": "RF_Q_GASEOUSMULTIPOINT_LINEARITY",
            "name": "多点校准线性指标",
            "fields": ["XL", "JU", "XGXS"],
            "description": "斜率、截距和相关系数应完整填报。",
        }
    ],
    "brand_ranges": {},
}

DEFAULT_SCORING_CONFIG = {
    "severity_penalty": {"高": 18, "中": 8, "低": 3},
    "common_pattern_min_affected_orders": 20,
    "common_pattern_order_ratio": 0.25,
    "common_pattern_eligible_rules": [
        "RF_AUDITOR_EMPTY",
        "FLOW_REMARK_LOW_VALUE",
        "FLOW_NO_REVIEW",
        "RF_REQUIRED_FIELD_LOW_VALUE",
        "RF_ENV_TEMP_HUMIDITY_EMPTY",
        "RF_PERSONNEL_VEHICLE_FORMAT_LOW_VALUE",
    ],
    "hard_error_rules": [
        "FLOW_MISSING",
        "FLOW_NO_CREATE",
        "FLOW_NO_CHECK",
        "FLOW_TIME_ORDER",
        "FLOW_SEQUENCE",
        "RF_MISSING",
        "RF_STATION_MISMATCH",
        "RF_TW_POLLUTANT_MISMATCH",
        "RF_Q_MULTIPOINT_METRIC_EMPTY",
        "RF_MULTIPOINT_RANGE_INVALID",
        "RF_CALIBRATION_DATE_EXPIRED",
        "RF_CALIBRATION_PREV_DATE_MISMATCH",
        "RF_REFERENCE_FLOWMETER_CERT_DATE_MISMATCH",
        "RF_ENUM_VALUE_INVALID",
        "RF_POLLUTANT_TYPE_MISMATCH",
        "RF_Q_PENDING_NO_REMARK",
        "RF_ABNORMAL_VALUE_NO_REMARK",
        "RF_RANGE_VALUE_MISSING",
        "RF_RANGE_BY_GAS_TYPE_MISMATCH",
        "RF_RANGE_OUT_OF_SPEC",
        "RF_UNIT_MISMATCH",
        "RF_VALUE_FORMULA_MISMATCH",
        "RF_FIELD_POSITION_SUSPECT",
        "ATTACHMENT_REQUIRED_MISSING",
        "ATTACHMENT_O3_VALUE_PASS_XLS_VALUE_MISMATCH",
    ],
    "critical_hard_error_rules": [
        "FLOW_MISSING",
        "FLOW_NO_CREATE",
        "FLOW_TIME_ORDER",
        "FLOW_SEQUENCE",
        "RF_STATION_MISMATCH",
        "RF_TW_POLLUTANT_MISMATCH",
        "RF_Q_MULTIPOINT_METRIC_EMPTY",
        "RF_MULTIPOINT_RANGE_INVALID",
        "RF_CALIBRATION_DATE_EXPIRED",
        "RF_CALIBRATION_PREV_DATE_MISMATCH",
        "RF_REFERENCE_FLOWMETER_CERT_DATE_MISMATCH",
        "RF_ENUM_VALUE_INVALID",
        "RF_POLLUTANT_TYPE_MISMATCH",
        "RF_Q_PENDING_NO_REMARK",
        "RF_ABNORMAL_VALUE_NO_REMARK",
        "RF_UNIT_MISMATCH",
        "RF_VALUE_FORMULA_MISMATCH",
        "RF_FIELD_POSITION_SUSPECT",
        "RF_RANGE_BY_GAS_TYPE_MISMATCH",
        "ATTACHMENT_REQUIRED_MISSING",
        "ATTACHMENT_O3_VALUE_PASS_XLS_VALUE_MISMATCH",
    ],
}

DEFAULT_RULE_CATALOG = [
    {
        "rule_id": "FLOW_MISSING",
        "name": "工单流程缺失",
        "category": "流程完整性",
        "default_severity": "高",
        "scope": "working_orders/working_order_details",
        "rationale": "缺少流程记录会影响审核追溯。",
    },
    {
        "rule_id": "FLOW_NO_CREATE",
        "name": "流程无创建步骤",
        "category": "流程完整性",
        "default_severity": "中",
        "scope": "working_orders/working_order_details",
        "rationale": "流程应包含工单创建或提交步骤。",
    },
    {
        "rule_id": "FLOW_NO_CHECK",
        "name": "流程无审核步骤",
        "category": "流程完整性",
        "default_severity": "高",
        "scope": "working_orders/working_order_details",
        "rationale": "流程应包含审核、复核或检查步骤以形成闭环。",
    },
    {
        "rule_id": "LIFECYCLE_FINISH_WITHOUT_EFFECTIVE_CLOSURE",
        "name": "已完成工单缺少有效闭环证据",
        "category": "生命周期闭环风险",
        "default_severity": "高",
        "scope": "working_orders/working_order_details",
        "rationale": "系统状态为完成不等于实质闭环，缺少处理节点或处理说明时应优先复核。",
    },
    {
        "rule_id": "RF_CHECK_TIME_OUTSIDE_RANGE",
        "name": "RF 表单检查时间不在开始结束时间内",
        "category": "时间合理性",
        "default_severity": "高",
        "scope": "RF_*",
        "rationale": "检查时间应落在表单记录的开始时间与结束时间之间。",
    },
    {
        "rule_id": "RF_RANGE_VALUE_MISSING",
        "name": "RF 表单应检项目检查值为空",
        "category": "表单完整性",
        "default_severity": "高",
        "scope": "RF_W_GASEOUSCHECK_CO/RF_W_GASEOUSCHECK_NOX/RF_W_GASEOUSCHECK_O3/RF_W_GASEOUSCHECK_SO2/RF_W_PMCHECK",
        "rationale": "当前品牌要求检查的项目缺少检查值，无法判断仪器运行状态。",
    },
    {
        "rule_id": "RF_RANGE_BY_GAS_TYPE_MISMATCH",
        "name": "RF 表单气体类型与量程不匹配",
        "category": "一致性",
        "default_severity": "高",
        "scope": "RF_W_GASEOUSCHECK_*",
        "rationale": "表单气体类型应与量程配置匹配，否则量程审核失真。",
    },
    {
        "rule_id": "RF_ABNORMAL_VALUE_NO_REMARK",
        "name": "RF 表单异常值无说明",
        "category": "结果合理性",
        "default_severity": "中",
        "scope": "RF_*",
        "rationale": "检查值超限或关键值漏填时，应说明原因、处置或免填依据。",
    },
    {
        "rule_id": "REMARK_SEMANTIC_INCOMPLETE",
        "name": "备注未说明原因/措施/结果",
        "category": "语义复核",
        "default_severity": "高",
        "scope": "working_orders/working_order_details/RF_*",
        "rationale": "备注需要具备原因、措施和结果，才能支持闭环判断。",
    },
    {
        "rule_id": "ATTACHMENT_CERT_INCOMPLETE",
        "name": "证书只附封面或不完整",
        "category": "附件内容质量",
        "default_severity": "中",
        "scope": "attachments",
        "rationale": "证书附件应能看到完整正文、编号和有效性信息。",
    },
    {
        "rule_id": "ATTACHMENT_WATERMARK_INCOMPLETE",
        "name": "照片水印时间缺日期",
        "category": "附件内容质量",
        "default_severity": "中",
        "scope": "attachments",
        "rationale": "现场照片应尽量带有包含日期的水印信息。",
    },
    {
        "rule_id": "ATTACHMENT_PM_TEMP_PRESSURE_VALUE_MISMATCH",
        "name": "颗粒物温度压力照片读数与表单值不一致",
        "category": "附件读数一致性",
        "default_severity": "高",
        "scope": "RF_Q_PMPRESSURE/温度压力校准照片",
        "rationale": "通过多模态识别读取颗粒物温度、压力校准照片中的仪器显示值和标准值，并与表单 PM10/PM25 温度、气压字段比对。",
    },
    {
        "rule_id": "ATTACHMENT_O3_VALUE_PASS_XLS_VALUE_MISMATCH",
        "name": "O3 量值传递 XLS 附件数据与表单不一致",
        "category": "附件读数一致性",
        "default_severity": "高",
        "scope": "RF_HY_O3VALUEPASS/WO_COMMONFILE",
        "rationale": "臭氧（O3）校准仪（工作标准）量值传递记录表的斜率、截距(ppb)、相对于前一次传递的改变(%)应分别与 XLS 附件第一个 sheet 的 G26、G27、G29 单元格一致。",
    },
    {
        "rule_id": "RF_PM_TEMP_ERROR_MISMATCH",
        "name": "颗粒物温度误差复算不一致",
        "category": "表单数值逻辑",
        "default_severity": "高",
        "scope": "RF_Q_PMPRESSURE",
        "rationale": "颗粒物温度误差字段应按仪器显示值减标准值复算得到，填报不一致说明读数或误差位置可能错误。",
    },
    {
        "rule_id": "RF_PM_PRESSURE_ERROR_OUT_OF_RANGE",
        "name": "颗粒物气压误差超出±1kPa",
        "category": "表单结果合理性",
        "default_severity": "高",
        "scope": "RF_Q_PMPRESSURE",
        "rationale": "颗粒物气压误差应小于±1kPa；表单按 hPa 填写时等价为小于±10hPa，超出范围时应复测、校准或补充异常处置说明。",
    },
    {
        "rule_id": "RF_PM_TEMP_ERROR_OUT_OF_RANGE",
        "name": "颗粒物温度误差超出±2℃",
        "category": "表单结果合理性",
        "default_severity": "高",
        "scope": "RF_Q_PMPRESSURE",
        "rationale": "颗粒物温度误差应小于±2℃，超出范围时应复测、校准或补充异常处置说明。",
    },
    {
        "rule_id": "RF_PM_TEMP_PRESSURE_ERROR_UNRECALCULABLE",
        "name": "颗粒物温度/气压误差无法复算",
        "category": "表单完整性",
        "default_severity": "中",
        "scope": "RF_Q_PMPRESSURE",
        "rationale": "仪器显示值、标准值或误差字段缺失/不可解析时，无法复核误差公式和阈值是否符合要求。",
    },
    {
        "rule_id": "REPORT_TOC_NOT_UPDATED",
        "name": "报告目录未更新",
        "category": "附件内容质量",
        "default_severity": "中",
        "scope": "attachments",
        "rationale": "报告目录应与正文页码保持一致。",
    },
    {
        "rule_id": "RF_RANGE_OUT_OF_SPEC",
        "name": "RF 表单检查值超出品牌正常范围",
        "category": "表单结果合理性",
        "default_severity": "高",
        "scope": "RF_W_GASEOUSCHECK_CO/RF_W_GASEOUSCHECK_NOX/RF_W_GASEOUSCHECK_O3/RF_W_GASEOUSCHECK_SO2/RF_W_PMCHECK",
        "rationale": "检查值超出对应品牌正常范围，需核对单位、复测或补充异常处理记录。",
    },
]

DEFAULT_RF_FIELD_PROFILES = {
    "low_value_field_groups": {
        "人员": ["PERSON", "PERSONNEL", "INSPECTOR", "CHECKUSER", "CHECKUSERID", "PATROLUSER", "PREPARERUSERID"],
        "车辆": ["CAR", "CARNUMBER", "VEHICLE", "VEHICLENO", "VEHICLEPLATE"],
        "备注": ["REMARK", "REMARKS", "CHECKREMARK", "CleaningRemark", "SUBMITREMARK"],
    },
    "temperature_fields": ["INDOORTEMPERATURE", "INDOORTEMP", "ROOMTEMPERATURE", "ROOMTEMP", "TEMPERATURE", "TEMP", "WD"],
    "humidity_fields": ["INDOORHUMIDITY", "INDOORHUMID", "ROOMHUMIDITY", "ROOMHUMID", "HUMIDITY", "HUMID", "SD"],
    "check_time_fields": ["CHECKTIME", "CHECKDATETIME", "CHECKDATE", "CALIBRATIONDATE"],
    "start_time_fields": ["STARTTIME", "STARTDATETIME", "BEGINTIME", "BEGIN_TIME"],
    "end_time_fields": ["ENDTIME", "ENDDATETIME", "FINISHTIME", "END_TIME"],
    "near_deadline_hours": 4,
}

DEFAULT_SEMANTIC_REVIEW_PROFILES = {
    "thresholds": {
        "remark_complete": 0.75,
        "attachment_complete": 0.8,
        "photo_watermark": 0.75,
        "value_consistency": 0.8,
    },
    "remark_keywords": {
        "cause": ["原因", "由于", "因", "因为", "受", "故障", "异常", "停机", "损坏", "缺失", "误差"],
        "action": ["已", "进行了", "采取", "更换", "修复", "调整", "处理", "整改", "复测", "清洗"],
        "result": ["恢复", "正常", "合格", "完成", "通过", "无异常", "达标", "有效"],
    },
    "attachment_keywords": {
        "certificate_cover": ["封面", "首页", "目录", "证书编号", "certificate"],
        "report_toc": ["目录", "contents", "目录页", "报告目录"],
        "watermark": ["水印", "拍摄时间", "时间", "日期", "现场"],
    },
    "date_patterns": [
        r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}(?:日)?",
        r"\d{4}-\d{2}-\d{2}",
        r"\d{4}/\d{2}/\d{2}",
    ],
    "value_tolerance": 0.05,
    "min_ocr_text_length": 8,
}

DEFAULT_RULE_REVIEW_STAGES = {
    "stages": {
        "semantic_remark": [
            "FLOW_REMARK_LOW_VALUE",
            "REMARK_SEMANTIC_INCOMPLETE",
            "RF_TW_REMARK_LOW_VALUE",
            "RF_Q_PENDING_NO_REMARK",
            "LIFECYCLE_FINISH_NEAR_DEADLINE",
            "LIFECYCLE_FINISH_WITHOUT_EFFECTIVE_CLOSURE",
            "RF_ABNORMAL_VALUE_NO_REMARK",
        ],
        "flow_visual": [
            "ATTACHMENT_PM_FLOW_CALIBRATION_VALUE_MISMATCH",
            "ATTACHMENT_GAS_FLOW_DISPLAY_VALUE_MISMATCH",
            "ATTACHMENT_GAS_FLOW_MEASURED_VALUE_MISMATCH",
            "ATTACHMENT_PM_MEMBRANE_VALUE_MISMATCH",
            "ATTACHMENT_PM_TEMP_PRESSURE_VALUE_MISMATCH",
        ],
        "future_ocr": [
            "ATTACHMENT_CERT_INCOMPLETE",
            "ATTACHMENT_CURVE_MISSING",
            "ATTACHMENT_WATERMARK_INCOMPLETE",
            "ATTACHMENT_VALUE_MISMATCH",
            "ATTACHMENT_REPORT_MISSING",
            "REPORT_TOC_NOT_UPDATED",
        ],
        "excluded": [
            "MAIN_REQUIRED",
            "MAIN_STATUS",
            "MAIN_WORKFLOW_STATUS",
            "MAIN_TIME_ORDER",
            "MAIN_CONTENT_EMPTY",
            "MAIN_GENERIC_TITLE",
            "MAIN_DEVICE_EMPTY",
            "RF_AUDITOR_EMPTY",
            "RF_REVIEW_EMPTY",
        ],
    },
    "default_stage": "deterministic",
}


def load_yaml_config(name: str, default: Any) -> Any:
    path = CONFIG_DIR / name
    if not path.exists():
        return deepcopy(default)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return deepcopy(default)
    return loaded


def _as_set_map(values: dict[str, list[str] | set[str]]) -> dict[str, set[str]]:
    return {str(key): {str(item) for item in items} for key, items in values.items()}


def load_low_value_remarks() -> set[str]:
    return {str(item) for item in load_yaml_config("business_calibration.yaml", {}).get("low_value_remarks", DEFAULT_LOW_VALUE_REMARKS)}


def load_brand_aliases() -> dict[str, set[str]]:
    loaded = load_yaml_config("device_identity_profiles.yaml", {}).get("brand_aliases", DEFAULT_BRAND_ALIASES)
    return _as_set_map(loaded)


def load_device_identity_profiles() -> dict[str, Any]:
    loaded = load_yaml_config("device_identity_profiles.yaml", {})
    profiles = deepcopy(DEFAULT_DEVICE_IDENTITY_PROFILES)
    profiles.update(loaded.get("device_identity", {}))
    return profiles


def load_attachment_requirements() -> dict[str, Any]:
    loaded = load_yaml_config("attachment_requirements.yaml", {})
    requirements = deepcopy(DEFAULT_ATTACHMENT_REQUIREMENTS)
    requirements.update(loaded or {})
    return requirements


def load_audit_window_config() -> dict[str, Any]:
    loaded = load_yaml_config("audit_window.yaml", DEFAULT_AUDIT_WINDOW)
    merged = deepcopy(DEFAULT_AUDIT_WINDOW)
    merged.update(loaded or {})
    return merged


def load_rule_catalog() -> list[dict[str, Any]]:
    loaded = load_yaml_config("rule_catalog.yaml", {"rules": DEFAULT_RULE_CATALOG})
    return [normalize_catalog_rule(rule) for rule in list(loaded.get("rules", DEFAULT_RULE_CATALOG))]


def load_scoring_config() -> dict[str, Any]:
    loaded = load_yaml_config("business_calibration.yaml", {})
    scoring = deepcopy(DEFAULT_SCORING_CONFIG)
    scoring.update(loaded.get("scoring", {}))
    return scoring


def load_rf_field_profiles() -> dict[str, Any]:
    loaded = load_yaml_config("rf_field_profiles.yaml", DEFAULT_RF_FIELD_PROFILES)
    return loaded or deepcopy(DEFAULT_RF_FIELD_PROFILES)


def load_rf_range_profiles() -> dict[str, Any]:
    """Load RF range check profiles for value validation."""
    return load_yaml_config("rf_range_profiles.yaml", {})


def load_rf_numeric_profiles() -> dict[str, Any]:
    """Load numeric range and formula profiles for RF checks."""
    loaded = load_yaml_config("rf_numeric_profiles.yaml", DEFAULT_RF_NUMERIC_PROFILES)
    merged = deepcopy(DEFAULT_RF_NUMERIC_PROFILES)
    merged.update(loaded or {})
    return merged


def load_rf_enum_profiles() -> dict[str, Any]:
    """Load RF enum and boolean value profiles."""
    return load_yaml_config("rf_enum_profiles.yaml", {"profiles": []})


def load_semantic_review_profiles() -> dict[str, Any]:
    """Load semantic and visual review configuration."""
    loaded = load_yaml_config("semantic_review.yaml", DEFAULT_SEMANTIC_REVIEW_PROFILES)
    merged = deepcopy(DEFAULT_SEMANTIC_REVIEW_PROFILES)
    merged.update(loaded or {})
    return merged


def load_semantic_review_config() -> dict[str, Any]:
    """Load semantic review configuration.

    Kept as a compatibility alias for callers that import the config-level name.
    """
    return load_semantic_review_profiles()


def load_rule_review_stages() -> dict[str, Any]:
    """Load rule-to-review-stage configuration."""
    loaded = load_yaml_config("rule_review_stages.yaml", DEFAULT_RULE_REVIEW_STAGES)
    merged = deepcopy(DEFAULT_RULE_REVIEW_STAGES)
    merged.update(loaded or {})
    stages = deepcopy(DEFAULT_RULE_REVIEW_STAGES["stages"])
    stages.update((loaded or {}).get("stages", {}))
    merged["stages"] = stages
    return merged


def rules_for_review_stage(stage: str) -> set[str]:
    """Return rules assigned to a review stage."""
    stages = load_rule_review_stages().get("stages", {})
    return {str(rule_id) for rule_id in stages.get(stage, [])}


def review_stage_for_rule(rule_id: str | None) -> str:
    """Return the configured review stage for a rule."""
    rule = str(rule_id or "")
    config = load_rule_review_stages()
    for stage, rules in config.get("stages", {}).items():
        if rule in {str(item) for item in rules}:
            return str(stage)
    return str(config.get("default_stage") or "deterministic")
