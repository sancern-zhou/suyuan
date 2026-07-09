from __future__ import annotations

from collections import OrderedDict
from typing import Any


PROJECT_CATEGORIES: "OrderedDict[str, str]" = OrderedDict(
    [
        (
            "environment_monitoring",
            "环境监测与检测：水、气、土、声、地下水、污染源、机动车尾气、走航、在线监测、第三方检测等监测检测服务。",
        ),
        (
            "pollution_control",
            "污染治理与生态修复：污水、废气、VOCs、固废危废、土壤地下水、黑臭水体、农村生活污水、排污口整治、生态修复等治理工程或服务。",
        ),
        (
            "environment_consulting",
            "环境咨询、评估与技术服务：环保管家、排污许可、环境调查评估、方案编制、验收评估、绩效评估、环境影响评价相关采购服务。",
        ),
        (
            "law_enforcement_support",
            "执法监管支撑：生态环境执法辅助、非现场监管、监督性监测、污染源排查、企业帮扶检查、执法装备或执法技术服务。",
        ),
        (
            "digital_platform",
            "环境信息化与数据平台：智慧环保、智慧执法、环境数据平台、污染源管理系统、AI/大数据分析、信息系统建设或运维。",
        ),
        (
            "equipment_supplies",
            "环保设备、仪器与耗材：监测仪器、实验室设备、采样设备、试剂耗材、在线设备配件、标准物质等实物采购。",
        ),
        (
            "operation_maintenance",
            "环保设施或监测系统运维：空气站、水站、在线监测设备、实验室设备、污水处理设施、环境平台系统等运维服务。",
        ),
        (
            "emergency_response",
            "环境应急能力：环境应急物资、应急监测、突发环境事件应急服务、应急预案演练和应急能力建设。",
        ),
        (
            "ecology_conservation",
            "生态保护与调查评估：生态状况调查、生物多样性、自然保护地、生态保护红线、生态质量评估等采购服务。",
        ),
        (
            "other_environment_procurement",
            "其他环境业务采购：确认属于环境业务采购，但无法归入以上类别。",
        ),
    ]
)

PROJECT_CATEGORY_ALIASES = {
    "other": "other_environment_procurement",
    "environment_related": "other_environment_procurement",
    "environment_informatization": "digital_platform",
    "informatization": "digital_platform",
    "platform": "digital_platform",
    "equipment": "equipment_supplies",
    "supplies": "equipment_supplies",
    "emergency": "emergency_response",
    "ecology": "ecology_conservation",
}


def project_category_values() -> list[str]:
    return list(PROJECT_CATEGORIES)


def project_category_schema() -> str:
    return "|".join(PROJECT_CATEGORIES)


def project_category_options() -> list[dict[str, str]]:
    return [
        {"value": value, "description": description}
        for value, description in PROJECT_CATEGORIES.items()
    ]


def normalize_project_category(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or normalized.lower() in {"null", "none", "未知", "不详"}:
        return None
    normalized = normalized.lower()
    normalized = PROJECT_CATEGORY_ALIASES.get(normalized, normalized)
    if normalized in PROJECT_CATEGORIES:
        return normalized
    return "other_environment_procurement"
