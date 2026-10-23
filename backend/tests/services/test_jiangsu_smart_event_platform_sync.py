"""智能事件平台派单闭环（创建工单 + 状态回流）单元测试：全部走假数据，不打真实平台。"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.services.jiangsu_smart_event import (
    JiangsuSmartEventService,
    normalize_alarm_event,
)


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.task_review.get_data_registry", lambda: tmp_path)
    return JiangsuSmartEventService(data_root=tmp_path, evidence_fetcher=object())


def _seed_event(service, *, event_id="evt-1", site="320382004"):
    store = service._load_store()
    event = normalize_alarm_event({
        "id": event_id, "code": site, "stationName": "示范站",
        "alarmtime": "2026-10-23 08:00:00", "ddRuleType": "仪器报警",
    })
    event["event_status"] = "待复核"
    store.setdefault("events", []).append(event)
    service._save_store(store)
    store = service._load_store()
    return next(item for item in store["events"] if item["site_id"] == site)


def test_record_platform_dispatch_synced_stores_order_code(service):
    event = _seed_event(service)
    service.dispatch_order(event["event_id"], title="示范站仪器故障处置")
    result = service.record_platform_dispatch(
        event["event_id"],
        {"status": "synced", "work_order_code": "FA2601", "detail": "平台工单已创建"},
    )
    assert result["platform_order_code"] == "FA2601"
    operations = [op["action"] for op in result["operation_records"]]
    assert operations[-2:] == ["dispatch_order", "platform_dispatch"]


def test_record_platform_dispatch_failed_keeps_retry_clue(service):
    event = _seed_event(service)
    service.dispatch_order(event["event_id"], title="示范站仪器故障处置")
    result = service.record_platform_dispatch(
        event["event_id"],
        {"status": "failed", "work_order_code": "", "detail": "平台工单创建失败：无设备台账"},
    )
    assert "platform_order_code" not in result
    assert "创建失败" in result["operation_records"][-1]["summary"]


def test_record_platform_order_sync_finish_routes_to_feedback(service):
    event = _seed_event(service)
    service.dispatch_order(event["event_id"], title="派单")
    event = service.record_platform_order_sync(
        event["event_id"], work_order_code="FA2601", order_status="Finish", node_name="省中心审核")
    assert event["event_status"] == "已反馈"
    cards = [task for task in service._load_store()["tasks"] if task["event_id"] == event["event_id"]]
    assert any(task["task_type"] == "ai_judgment" and task.get("continuity", {}).get("feedback", {})
               .get("source") == "platform_sync" for task in cards)


def test_record_platform_order_sync_progress_only_appends_operation(service):
    event = _seed_event(service)
    service.dispatch_order(event["event_id"], title="派单")
    event = service.record_platform_order_sync(
        event["event_id"], work_order_code="FA2601", order_status="Doing", node_name="故障处理")
    assert event["event_status"] == "待反馈"
    last = event["operation_records"][-1]
    assert last["action"] == "platform_order_sync"
    assert "故障处理" in last["summary"]
    assert last["details"]["order_status"] == "Doing"


def _patch_platform_helpers(monkeypatch, *, station=None, devices=None, order_code="FA2601",
                            fail_create=False, settings_enabled=True):
    from config.settings import settings
    from app.tools.jiangsu import platform_workflow as module

    monkeypatch.setattr(settings, "jiangsu_platform_writeback_enabled", settings_enabled)
    posts: list[tuple[str, dict]] = []

    class FakeApi:
        async def get(self, path, params):
            return {"result": []}

        async def post(self, path, payload):
            posts.append((path, payload))
            if fail_create:
                raise RuntimeError("平台接口不可达")
            return {"result": True}

    class FakeResolve:
        async def resolve(self, **kwargs):
            if station is None:
                raise ValueError("未在平台站点目录解析到站点")
            return [station]

    async def resolve_station_rows(*_args, **kwargs):
        if station is None:
            raise ValueError("未在平台站点目录解析到站点")
        return [station]

    async def fetch_station_devices(_api, _station_code):
        if devices is None:
            raise ValueError("平台无设备台账")
        return devices

    async def resolve_created_order_code(**_kwargs):
        return order_code

    monkeypatch.setattr(module, "_JiangsuAuthenticatedApi", lambda source: FakeApi())
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._resolve_station_rows",
                        resolve_station_rows)
    monkeypatch.setattr("app.tools.jiangsu.work_order_dispatch._fetch_station_devices",
                        fetch_station_devices)
    monkeypatch.setattr("app.tools.jiangsu.work_order_dispatch.resolve_created_order_code",
                        resolve_created_order_code)
    return posts


def test_create_smart_event_dispatch_order_disabled(service, tmp_path, monkeypatch):
    from app.tools.jiangsu import platform_workflow as module

    monkeypatch.setattr(module, "get_data_registry", lambda: tmp_path)
    _patch_platform_helpers(monkeypatch, settings_enabled=False)
    result = asyncio.run(module.create_smart_event_dispatch_order(
        event_id="evt-1", site_id="320382004", title="派单"))
    assert result["status"] == "disabled"


def test_create_smart_event_dispatch_order_success(service, tmp_path, monkeypatch):
    from app.tools.jiangsu import platform_workflow as module

    monkeypatch.setattr(module, "get_data_registry", lambda: tmp_path)
    posts = _patch_platform_helpers(
        monkeypatch,
        station={"station_code": "3203A", "station_name": "示范站", "unique_code": "320382004"},
        devices=[{"device_id": 11, "label": "颗粒物分析仪"}],
        order_code="FA2601",
    )
    result = asyncio.run(module.create_smart_event_dispatch_order(
        event_id="evt-1", site_id="320382004", site_name="示范站",
        title="示范站仪器故障处置", description="PM10 数据中断",
        urgency_type="Urgent", issued_types=["App"],
    ))
    assert result["status"] == "synced"
    assert result["work_order_code"] == "FA2601"
    create_path, payload = posts[0]
    assert create_path == "operation/FaultOrder/CreateAsync"
    assert payload["urgencyType"] == "Urgent"
    assert payload["deviceId"] == 11
    assert payload["stationCodes"] == ["3203A"]
    assert payload["issuedType"] == ["App"]
    assert "智能事件 evt-1" in payload["orderContent"]


def test_create_smart_event_dispatch_order_failure_is_reported(service, tmp_path, monkeypatch):
    from app.tools.jiangsu import platform_workflow as module

    monkeypatch.setattr(module, "get_data_registry", lambda: tmp_path)
    _patch_platform_helpers(monkeypatch, station=None)
    result = asyncio.run(module.create_smart_event_dispatch_order(
        event_id="evt-1", site_id="未知站", title="派单"))
    assert result["status"] == "failed"
    assert "平台工单创建失败" in result["detail"]


def test_platform_sync_fetcher_dedupes_by_signature(tmp_path, monkeypatch):
    from app.fetchers import jiangsu_smart_event_platform_sync as fetcher_module
    from app.tools.jiangsu import platform_workflow as module
    from config.settings import settings

    monkeypatch.setattr(settings, "jiangsu_platform_writeback_enabled", True)
    monkeypatch.setattr("app.utils.path_config.get_data_registry", lambda: tmp_path)
    monkeypatch.setattr(module, "get_data_registry", lambda: tmp_path)

    service = JiangsuSmartEventService(data_root=tmp_path, evidence_fetcher=object())
    event = _seed_event(service)
    service.dispatch_order(event["event_id"], title="派单")
    service.record_platform_dispatch(
        event["event_id"], {"status": "synced", "work_order_code": "FA2601"})

    monkeypatch.setattr("app.services.jiangsu_smart_event.JiangsuSmartEventService",
                        lambda **_kwargs: service)

    class FakeApi:
        async def get(self, path, params):
            if "WflWorkFlow" in path:
                return {"result": {"stepList": [
                    {"guid": "step-2", "taskName": "故障处理"}]}}
            return {"result": {"items": [
                {"workingOrderCode": "FA2601", "orderStatus": "Doing",
                 "currentPoint": "step-2", "updateTime": "2026-10-23 09:00:00"}]}}

    monkeypatch.setattr(fetcher_module, "_JiangsuAuthenticatedApi", lambda source: FakeApi())

    fetcher = fetcher_module.JiangsuSmartEventPlatformSyncFetcher()
    first = asyncio.run(fetcher.fetch_and_store())
    assert first["synced_events"] == 1
    second = asyncio.run(fetcher.fetch_and_store())
    assert second["synced_events"] == 0
    state = json.loads((tmp_path / "jiangsu_smart_event_platform_sync" / "state.json")
                       .read_text(encoding="utf-8"))
    assert state["FA2601"]["signature"] == "Doing|故障处理"
