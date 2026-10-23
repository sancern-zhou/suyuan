"""Platform alarm work-order types used by smart-event dispatch.

江苏运维平台的「运维告警工单」使用独立类型枚举（人员闯入 / 雾炮 / 仪器故障），
与故障工单 ``Fault``、巡检/校准等业务工单类型是两套口径。派单写入平台时只能
使用平台定义值；中文名仅用于界面展示，不能作为请求参数。

平台列表页对告警工单使用多值绑定 ``orderTypes[i]``（见
``operation/WorkingOrder/GetMtcWorkingOrderPagedListAsync`` 的实际请求），而故障
工单沿用单值 ``OrderType``，两者查询参数不同，统一由本模块生成。
"""

from __future__ import annotations

import json
from typing import Any, Mapping

# 中文名严格取平台 OrderType 枚举的 [Description]，与平台页面显示一致。
ALARM_ORDER_TYPES: tuple[tuple[str, str], ...] = (
    ("PersonIntrusion", "人员入侵报警"),
    ("FogCannon", "雾炮喷淋报警"),
    ("InstrumentFault", "仪器故障报警"),
)
ALARM_ORDER_TYPE_LABELS: dict[str, str] = dict(ALARM_ORDER_TYPES)
DEFAULT_ALARM_ORDER_TYPE = "InstrumentFault"
# 兼容旧客户端/早期文案使用的短标签。
LEGACY_ORDER_TYPE_LABELS: dict[str, str] = {
    "人员闯入": "PersonIntrusion",
    "雾炮": "FogCannon",
    "仪器故障": "InstrumentFault",
}

# 事件类型 / 线索标签 / 平台报警规则 → 平台告警工单类型。
# 只做精确匹配：标签体系里「疑似站房环境影响」与「疑似外界环境影响」含义不同，
# 子串匹配会把两者混为一类。
_ORDER_TYPE_HINTS: tuple[tuple[str, frozenset[str]], ...] = (
    ("PersonIntrusion", frozenset({
        "疑似人员进入采样区干扰操作", "人员进入采样区", "人员闯入",
        "接触采样设施", "遮挡采样口",
    })),
    ("FogCannon", frozenset({
        "疑似雾炮喷淋", "雾炮喷淋", "洒水冲洗", "雾炮",
    })),
    # 仪器/供电/数采网络/站房环境在事件中心同属「仪器故障」类别
    # （见 SmartEventCenterPanel 的 instrument-fault 分类），平台侧统一归 InstrumentFault。
    ("InstrumentFault", frozenset({
        "疑似仪器故障", "仪器报警", "仪器参数超限", "单仪器断数",
        "供电报警", "供电断数", "数采网络报警", "公共系统报警",
        "站房环境报警", "站房环境", "疑似站房停电",
        "疑似公共系统异常", "疑似站房环境影响",
    })),
)


def platform_order_type_catalog() -> list[dict[str, str]]:
    """Platform-defined alarm order types, in display order."""
    return [{"value": code, "label": label} for code, label in ALARM_ORDER_TYPES]


def platform_order_type_label(code: str) -> str:
    value = str(code or "").strip()
    if value == "Fault":
        return "故障工单"
    return ALARM_ORDER_TYPE_LABELS.get(value, "")


def default_platform_order_type() -> str:
    """Deployment-configurable fallback for events without a direct mapping."""
    try:
        from config.settings import settings

        configured = str(
            getattr(settings, "jiangsu_platform_alarm_order_default_type", "") or ""
        ).strip()
    except Exception:  # pragma: no cover - settings import is guaranteed in runtime
        configured = ""
    return configured if configured in ALARM_ORDER_TYPE_LABELS else DEFAULT_ALARM_ORDER_TYPE


def resolve_platform_order_type(
    event: Mapping[str, Any] | None,
    *,
    default: str | None = None,
) -> str:
    """Pick the platform alarm order type for one smart event."""
    if isinstance(event, Mapping):
        stored = str(event.get("platform_order_type") or "").strip()
        if stored in ALARM_ORDER_TYPE_LABELS:
            return stored
        texts = _event_texts(event)
        for code, hints in _ORDER_TYPE_HINTS:
            if any(text in hints for text in texts):
                return code
    return _normalise_default(default)


def normalise_platform_order_type(
    value: Any,
    *,
    event: Mapping[str, Any] | None = None,
    default: str | None = None,
) -> str:
    """Accept a platform code, a Chinese label, or a legacy event-type string.

    Older clients post the event's Chinese alarm type through ``order_type``;
    the value is mapped to the platform code rather than stored verbatim.
    """
    text = str(value or "").strip()
    if text in ALARM_ORDER_TYPE_LABELS:
        return text
    # 显式指定的故障工单类型保留兼容（历史事件与联调脚本仍走 Fault）。
    if text.casefold() == "fault":
        return "Fault"
    if text in LEGACY_ORDER_TYPE_LABELS:
        return LEGACY_ORDER_TYPE_LABELS[text]
    for code, label in ALARM_ORDER_TYPES:
        if text == label:
            return code
    if text:
        for code, hints in _ORDER_TYPE_HINTS:
            if text in hints:
                return code
    return resolve_platform_order_type(event, default=default)


def build_clue_json(event: Mapping[str, Any] | None, *, limit: int = 500) -> str:
    """Build the compact ``ClueJson`` accepted by ``AlarmOrder/CreateAsync``.

    The platform stores this string in a 1000-char column and re-serializes it
    with indentation, so the compact form is kept well below the limit.  Only
    alarm rows are populated; monitoring/maintenance/door arrays stay empty and
    can be filled by the platform's own evidence pipeline.
    """
    alarms: list[dict[str, Any]] = []
    evidence = event.get("evidence") if isinstance(event, Mapping) else None
    if isinstance(evidence, Mapping):
        raw = evidence.get("alarms")
        if not isinstance(raw, list):
            raw = [evidence.get("alarm")] if evidence.get("alarm") else []
        for row in raw[:2]:
            if not isinstance(row, Mapping):
                continue
            alarms.append({
                "alarmTime": row.get("alarmtime") or row.get("alarmTime") or row.get("timePoint"),
                "content": str(row.get("content") or row.get("alarmContent") or "")[:120],
                "alarmType": row.get("ddRuleType") or row.get("ruleType"),
                "object": str(row.get("deviceName") or row.get("objectName") or "")[:60],
            })
    payload: dict[str, Any] = {
        "alarms": alarms,
        "monitoringData": [],
        "maintenanceOrders": [],
        "doorRecords": [],
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    while len(text) > limit and payload["alarms"]:
        payload["alarms"].pop()
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return text


def platform_order_type_params(order_type: str) -> list[tuple[str, str]]:
    """List-query parameters for one order type.

    Alarm orders use the platform's multi-value ``orderTypes[i]`` binding;
    legacy fault queries keep the observed single ``OrderType`` filter.
    """
    code = str(order_type or "").strip()
    if not code:
        return []
    if code == "Fault":
        return [("OrderType", "Fault")]
    return [("orderTypes[0]", code)]


def _event_texts(event: Mapping[str, Any]) -> list[str]:
    texts = [
        str(event.get(key) or "").strip()
        for key in (
            "ai_event_type",
            "manual_final_event_type",
            "primary_clue_tag",
            "source_alarm_rule_type",
            "event_type",
        )
    ]
    tags = event.get("clue_tags")
    if isinstance(tags, list):
        texts.extend(
            str(tag.get("tag_name") or "").strip()
            for tag in tags
            if isinstance(tag, Mapping)
        )
    return [text for text in texts if text]


def _normalise_default(value: str | None) -> str:
    candidate = str(value or "").strip()
    if candidate in ALARM_ORDER_TYPE_LABELS:
        return candidate
    return default_platform_order_type()
