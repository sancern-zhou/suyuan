from datetime import datetime, timedelta

from app.tools.jiangsu.work_order_dispatch import (
    compose_order_content,
    match_fault_contents,
    select_device,
    validate_edits,
)


def _draft(**overrides):
    draft = {
        "draft_id": "draft-token",
        "status": "pending",
        "order_type": "Fault",
        "created_at": "2026-08-19T09:00:00+08:00",
        "expires_at": "2026-08-21T09:00:00+08:00",
        "event_id": "jsfault_demo",
        "evidence_ref": "backend/backend_data_registry_jiangsu_ops/events/pack.json",
        "station": {"station_code": "5006A", "station_name": "示范站", "unique_code": "U1"},
        "devices": [
            {"device_id": 11, "label": "颗粒物分析仪 PM10-100", "device_type": "051"},
            {"device_id": 22, "label": "空调 HK-1", "device_type": "060"},
        ],
        "selected_device_id": 11,
        "fault_contents": {
            "11": [
                {"fault_content_id": "fc1", "name": "数据异常"},
                {"fault_content_id": "fc2", "name": "无法开机"},
            ],
            "22": [{"fault_content_id": "fc9", "name": "制冷异常"}],
        },
        "selected_fault_content_ids": ["fc1"],
        "order_title": "示范站 PM10 数据中断排查",
        "fault_description": "PM10 小时数据自 08:00 起中断",
        "remediation_plan": "现场检查采样系统与采集仪",
        "verification_standards": ["PM10 小时数据恢复连续 3 小时"],
        "order_content": "【故障描述】PM10 小时数据自 08:00 起中断",
        "urgency": "Middle",
        "plan_finish_time": "2026-08-20 09:00:00",
    }
    draft.update(overrides)
    return draft


def test_compose_order_content_uses_deterministic_template():
    content = compose_order_content(
        fault_description="PM10 断数",
        remediation_plan="现场排查采样系统",
        verification_standards=["数据恢复连续 3 小时", ""],
        event_id="jsfault_demo",
        evidence_ref="events/pack.json",
    )
    lines = content.split("\n")
    assert lines[0] == "【故障描述】PM10 断数"
    assert lines[1] == "【处置方案】现场排查采样系统"
    assert lines[2] == "【验证标准】"
    assert lines[3] == "- 数据恢复连续 3 小时"
    assert "事件 jsfault_demo" in lines[-1]
    assert "AI 草案经人工确认后创建" in lines[-1]


def test_select_device_matches_hint_and_falls_back_deterministically():
    devices = [
        {"device_id": 1, "label": "空调 HK-1"},
        {"device_id": 2, "label": "颗粒物分析仪 PM10-100"},
    ]
    assert select_device(devices, "pm10")["device_id"] == 2
    assert select_device(devices, "")["device_id"] == 1
    assert select_device([], "pm10") is None


def test_match_fault_contents_maps_keywords_onto_fixed_vocabulary():
    options = [
        {"fault_content_id": "fc1", "name": "数据异常"},
        {"fault_content_id": "fc2", "name": "无法开机"},
        {"fault_content_id": "other", "name": "其他"},
    ]
    assert match_fault_contents(options, ["数据中断", "浓度异常"]) == ["fc1"]
    assert match_fault_contents(options, ["不能开机"]) == ["fc2"]
    assert match_fault_contents(options, []) == []
    assert match_fault_contents(options, ["完全不匹配的词汇"]) == []


def test_validate_edits_accepts_panel_edits_and_recomposes_missing_content():
    final = validate_edits(_draft(), {
        "order_title": "示范站 PM10 断数处置",
        "fault_description": "PM10 数据中断 6 小时",
        "remediation_plan": "现场检查采集仪",
        "verification_standards": ["恢复后连续 3 小时有数"],
        "urgency": "Urgent",
        "device_id": 11,
        "fault_content_ids": ["fc1"],
        "plan_finish_time": "2026-08-20 12:00",
        "order_content": None,
    })
    assert final["order_title"] == "示范站 PM10 断数处置"
    assert final["urgency"] == "Urgent"
    assert final["plan_finish_time"] == "2026-08-20 12:00:00"
    assert final["order_content"].startswith("【故障描述】PM10 数据中断 6 小时")


def test_validate_edits_enforces_device_and_vocabulary_constraints():
    draft = _draft()
    for bad_edits, fragment in (
        ({"device_id": 99}, "设备台账"),
        ({"device_id": 22, "fault_content_ids": ["fc1"]}, "故障现象"),
        ({"fault_content_ids": []}, "故障现象"),
        ({"urgency": "Critical"}, "紧急程度"),
        ({"order_title": "  "}, "工单标题"),
        ({"plan_finish_time": "tomorrow"}, "建议完成时间"),
    ):
        try:
            validate_edits(draft, bad_edits)
        except ValueError as exc:
            assert fragment in str(exc)
        else:
            raise AssertionError(f"edits {bad_edits} must be rejected")


def test_validate_edits_rejects_overlong_title():
    try:
        validate_edits(_draft(), {"order_title": "长" * 101})
    except ValueError as exc:
        assert "100" in str(exc)
    else:
        raise AssertionError("overlong title must be rejected")


def test_platform_time_parsing_tolerates_common_layouts():
    from app.tools.jiangsu.work_order_dispatch import _parse_platform_time

    assert _parse_platform_time("2026-08-19 09:12:30") == datetime(2026, 8, 19, 9, 12, 30)
    assert _parse_platform_time("2026-08-19T09:12:30") == datetime(2026, 8, 19, 9, 12, 30)
    assert _parse_platform_time(None) is None
    assert _parse_platform_time("not-a-time") is None


def test_confirm_route_draft_flow(tmp_path, monkeypatch):
    """Draft files persist and reload through the shared registry directory."""
    from app.tools.jiangsu import work_order_dispatch as module

    monkeypatch.setattr(module, "get_data_registry", lambda: tmp_path)
    draft = _draft()
    module.save_draft(draft)
    loaded = module.load_draft(draft["draft_id"])
    assert loaded["order_title"] == draft["order_title"]
    loaded.update({"status": "confirmed", "result": {"work_order_code": "GD20260819001"}})
    module.save_draft(loaded)
    assert module.load_draft(draft["draft_id"])["result"]["work_order_code"] == "GD20260819001"
    assert module.load_draft("missing") is None


def test_draft_expiry_window_is_enforced_by_routes(monkeypatch):
    from app.api.jiangsu_work_order_routes import _parse_iso

    expired = datetime.now().astimezone() - timedelta(minutes=1)
    assert _parse_iso(expired.isoformat()) < datetime.now().astimezone()
