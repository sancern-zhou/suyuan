"""平台告警工单类型目录与智能事件映射单元测试。"""
from __future__ import annotations

import json

from app.tools.jiangsu.alarm_order_types import (
    ALARM_ORDER_TYPE_LABELS,
    build_clue_json,
    platform_order_type_catalog,
    platform_order_type_params,
    normalise_platform_order_type,
    resolve_platform_order_type,
)


def test_catalog_uses_platform_defined_codes():
    catalog = platform_order_type_catalog()
    assert [item["value"] for item in catalog] == [
        "PersonIntrusion", "FogCannon", "InstrumentFault",
    ]
    assert ALARM_ORDER_TYPE_LABELS["FogCannon"] == "雾炮喷淋报警"


def test_resolve_from_ai_event_type():
    assert resolve_platform_order_type({"ai_event_type": "疑似人员进入采样区干扰操作"}) == "PersonIntrusion"
    assert resolve_platform_order_type({"ai_event_type": "疑似雾炮喷淋"}) == "FogCannon"
    assert resolve_platform_order_type({"ai_event_type": "疑似仪器故障"}) == "InstrumentFault"


def test_resolve_from_alarm_rule_and_tags():
    assert resolve_platform_order_type({"source_alarm_rule_type": "供电报警"}) == "InstrumentFault"
    assert resolve_platform_order_type({
        "clue_tags": [{"tag_name": "人员进入采样区"}],
    }) == "PersonIntrusion"
    assert resolve_platform_order_type({
        "primary_clue_tag": "雾炮喷淋",
    }) == "FogCannon"


def test_resolve_external_environment_has_no_direct_mapping_falls_back():
    # 「疑似外界环境影响」与「疑似站房环境影响」含义不同，不能被模糊匹配成仪器故障。
    assert resolve_platform_order_type(
        {"ai_event_type": "疑似外界环境影响"}, default="InstrumentFault") == "InstrumentFault"
    assert resolve_platform_order_type(
        {"ai_event_type": "疑似外界环境影响"}, default="FogCannon") == "FogCannon"


def test_stored_platform_type_wins():
    assert resolve_platform_order_type({
        "platform_order_type": "FogCannon",
        "ai_event_type": "疑似仪器故障",
    }) == "FogCannon"


def test_normalise_accepts_code_label_and_legacy_event_type():
    assert normalise_platform_order_type("FogCannon") == "FogCannon"
    assert normalise_platform_order_type("雾炮喷淋报警") == "FogCannon"
    assert normalise_platform_order_type("人员闯入") == "PersonIntrusion"
    assert normalise_platform_order_type("疑似雾炮喷淋") == "FogCannon"
    # 无法识别时用事件推断，再退到默认值。
    assert normalise_platform_order_type("未知类型", event={"ai_event_type": "疑似仪器故障"}) == "InstrumentFault"
    assert normalise_platform_order_type("未知类型", default="FogCannon") == "FogCannon"
    # 显式 Fault 保留兼容（历史事件/联调脚本）。
    assert normalise_platform_order_type("Fault") == "Fault"


def test_build_clue_json_matches_platform_default_shape():
    text = build_clue_json({"evidence": {"alarms": [{
        "alarmtime": "2026-10-23 08:00:00",
        "content": "PM10 数据中断",
        "ddRuleType": "仪器报警",
        "deviceName": "PM10 分析仪",
    }]}})
    payload = json.loads(text)
    assert set(payload) == {"alarms", "monitoringData", "maintenanceOrders", "doorRecords"}
    assert payload["alarms"][0]["alarmType"] == "仪器报警"
    assert payload["alarms"][0]["content"] == "PM10 数据中断"
    assert payload["monitoringData"] == []
    assert len(text) <= 500


def test_build_clue_json_stays_within_platform_column_limit():
    alarms = [{
        "alarmtime": "2026-10-23 08:00:00",
        "content": "长" * 500,
        "ddRuleType": "仪器报警",
        "deviceName": "设备" * 100,
    } for _ in range(2)]
    text = build_clue_json({"evidence": {"alarms": alarms}}, limit=300)
    assert len(text) <= 300
    assert json.loads(text)["alarms"] == []


def test_list_query_params_match_platform_binding():
    assert platform_order_type_params("FogCannon") == [("orderTypes[0]", "FogCannon")]
    # 故障工单沿用平台实际生效的单值过滤。
    assert platform_order_type_params("Fault") == [("OrderType", "Fault")]
    assert platform_order_type_params("") == []
