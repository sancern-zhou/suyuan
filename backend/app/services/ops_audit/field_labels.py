"""Human-readable labels for RF remark and explanation fields."""

from __future__ import annotations

from typing import Any


REMARK_FIELD_LABELS = {
    "REMARK": "备注",
    "REMARKS": "备注",
    "CHECKREMARK": "检查备注",
    "BZ": "备注",
    "COMMENT": "说明",
    "DESCRIPTION": "说明",
    "EXCEPTIONHANDLINGRECORD": "异常时处理记录",
    "AIRTEMPEXCEPTION": "采样管温度异常说明",
    "AIRTEMPISNORMAL": "采样管温度状态",
    "WEATHERSITUATION": "气象设备运行情况",
    "VISIBILITYSITUATION": "能见度设备运行情况",
    "CITYCAMERASITUATION": "城市摄像设备运行情况",
    "DATAACQUISITIONSITUATION": "数据采集仪运行情况",
}


def remark_field_display_name(field: Any) -> str:
    raw = str(field or "").strip()
    upper = raw.upper()
    if upper in REMARK_FIELD_LABELS:
        return REMARK_FIELD_LABELS[upper]
    if upper.endswith("CHECKTEMP4VALUE"):
        return "温度校准情况"
    if upper.endswith("CHECKPRES4VALUE"):
        return "气压校准情况"
    if upper.endswith("CHECKROW"):
        return "检查项说明"
    if upper.endswith("SITUATION"):
        return "运行情况"
    if upper.endswith("EXCEPTION") or upper.endswith("ABNORMAL"):
        return "异常说明"
    if upper == "SEMANTIC_REVIEW_INPUT":
        return "语义审核读取的备注"
    return raw or "备注"
