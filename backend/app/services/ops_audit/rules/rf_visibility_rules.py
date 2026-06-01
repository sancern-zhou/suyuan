"""RF visibility calibration consistency checks."""

from __future__ import annotations

import json
from typing import Any

from app.services.ops_audit.models import Issue
from app.services.ops_audit.rules.base import add_issue


RULE_ID = "RF_VISIBILITY_NO_DEVICE_FIELD_CONFLICT"
VISIBILITY_TABLES = {
    "RF_HY_VISIBILITYCALI",
    "Sup_RF_NepheloMeterCalibration",
    "Sup_RF_MonthNepheloMeterCheck",
}
NO_DEVICE_KEYWORDS = ("无能见度设备", "无能见度仪", "无设备", "未配置", "无须见度设备")
DEVICE_FIELDS = ("DEVICEMODEL", "DEVICECODE", "DEMODEL", "DEBQDD", "DEXISHU")
SKIP_VALUES = {"", "/", "-", "无", "不适用", "none", "null", "nan"}
NON_VISIBILITY_MODELS = ("49i", "49ips", "48i", "43i", "42i")


def check_rf_visibility_values(
    order: dict[str, Any],
    forms: list[tuple[str, dict[str, Any]]],
    issues: list[Issue],
) -> None:
    """Check no-device visibility records do not carry unrelated instrument identity."""

    for table, form in forms:
        if form.get("_query_error") or table not in VISIBILITY_TABLES:
            continue
        text = " ".join(str(form.get(field) or "") for field in ("REMARK", "JIAOZHUNRESULT", "OTHERVALUE"))
        if not any(keyword in text for keyword in NO_DEVICE_KEYWORDS):
            continue

        conflicts = []
        for field in DEVICE_FIELDS:
            raw_value = form.get(field)
            value = _normalized_value(raw_value)
            if not value:
                continue
            conflicts.append(
                {
                    "field": field,
                    "value": raw_value,
                    "conflict_type": _conflict_type(value),
                }
            )

        if not conflicts:
            continue

        evidence = {
            "working_order_code": order.get("WORKINGORDERCODE"),
            "rf_table": table,
            "remark": form.get("REMARK"),
            "conflicts": conflicts,
        }
        first = conflicts[0]
        add_issue(
            issues,
            RULE_ID,
            "一致性",
            "高" if first["conflict_type"] == "non_visibility_model" else "中",
            f"rf.{table}.{first['field']}",
            f"能见度记录说明无设备，但仍填写设备字段 {first['field']}={first['value']}",
            json.dumps(evidence, ensure_ascii=False, default=str),
        )


def _normalized_value(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in SKIP_VALUES:
        return ""
    return text


def _conflict_type(value: str) -> str:
    normalized = value.lower().replace(" ", "")
    if any(model in normalized for model in NON_VISIBILITY_MODELS):
        return "non_visibility_model"
    return "field_filled_when_no_device"

