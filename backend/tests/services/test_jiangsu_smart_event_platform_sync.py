"""智能事件平台派单闭环（创建工单 + 状态回流）单元测试：全部走假数据，不打真实平台。"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

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


def test_dispatch_order_maps_chinese_alarm_type_to_platform_code(service):
    event = _seed_event(service)
    updated = service.dispatch_order(event["event_id"], title="派单", order_type="雾炮")
    assert updated["platform_order_type"] == "FogCannon"
    details = updated["operation_records"][-1]["details"]
    assert details["order_type"] == "FogCannon"
    assert details["requested_alarm_type"] == "雾炮"


def test_record_platform_dispatch_linked_stores_code_and_type(service):
    event = _seed_event(service)
    service.dispatch_order(event["event_id"], title="派单", order_type="FogCannon")
    result = service.record_platform_dispatch(
        event["event_id"],
        {"status": "linked", "work_order_code": "YJ2601", "order_type": "FogCannon"},
    )
    assert result["platform_order_code"] == "YJ2601"
    assert result["platform_order_type"] == "FogCannon"
    assert "已关联平台在办告警工单" in result["operation_records"][-1]["summary"]


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
                            fail_create=False, settings_enabled=True, create_result=True):
    from config.settings import settings
    from app.tools.jiangsu import platform_workflow as module

    monkeypatch.setattr(settings, "jiangsu_platform_writeback_enabled", settings_enabled)
    posts: list[tuple[str, dict]] = []

    class FakeApi:
        async def get(self, path, params):
            return {"result": {"items": []}}

        async def post(self, path, payload):
            posts.append((path, payload))
            if fail_create:
                raise RuntimeError("平台接口不可达")
            return {"result": create_result}

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

    async def resolve_created_alarm_order_code(**_kwargs):
        return order_code

    monkeypatch.setattr(module, "_JiangsuAuthenticatedApi", lambda source: FakeApi())
    monkeypatch.setattr("app.tools.jiangsu.fault_diagnosis._resolve_station_rows",
                        resolve_station_rows)
    monkeypatch.setattr("app.tools.jiangsu.work_order_dispatch._fetch_station_devices",
                        fetch_station_devices)
    monkeypatch.setattr("app.tools.jiangsu.work_order_dispatch.resolve_created_order_code",
                        resolve_created_order_code)
    monkeypatch.setattr(module, "resolve_created_alarm_order_code",
                        resolve_created_alarm_order_code)
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
        order_type="PersonIntrusion",
    ))
    assert result["status"] == "synced"
    assert result["work_order_code"] == "FA2601"
    assert result["order_type"] == "PersonIntrusion"
    create_path, payload = posts[0]
    # 告警工单必须走 AlarmOrderAppService，不能复用 FaultOrder/CreateAsync。
    assert create_path == "operation/AlarmOrder/CreateAsync"
    assert payload["orderType"] == "PersonIntrusion"
    assert payload["urgencyType"] == "Urgent"
    assert payload["stationCode"] == "3203A"
    assert "deviceId" not in payload
    assert payload["issuedType"] == ["App"]
    assert "智能事件 evt-1" in payload["orderContent"]


def test_create_smart_event_dispatch_order_instrument_fault_payload(service, tmp_path, monkeypatch):
    from app.tools.jiangsu import platform_workflow as module

    monkeypatch.setattr(module, "get_data_registry", lambda: tmp_path)
    posts = _patch_platform_helpers(
        monkeypatch,
        station={"station_code": "3203A", "station_name": "示范站", "unique_code": "320382004"},
        devices=[{"device_id": 11, "label": "颗粒物分析仪"}],
        order_code="IF2601",
    )
    clue = '{"alarms":[],"monitoringData":[],"maintenanceOrders":[],"doorRecords":[]}'
    result = asyncio.run(module.create_smart_event_dispatch_order(
        event_id="evt-1", site_id="320382004", site_name="示范站",
        title="示范站仪器故障处置", description="PM10 数据中断",
        order_type="InstrumentFault", clue_json=clue,
    ))
    assert result["status"] == "synced"
    _, payload = posts[0]
    assert payload["orderType"] == "InstrumentFault"
    assert payload["stationCode"] == "3203A"
    assert payload["deviceId"] == 11
    assert payload["faultPhenomenon"] == "PM10 数据中断"
    assert payload["otherContent"] == "PM10 数据中断"
    assert payload["checkTask"] == ["other"]
    assert payload["clueJson"] == clue


def test_create_smart_event_dispatch_order_links_existing_alarm_order(service, tmp_path, monkeypatch):
    from app.tools.jiangsu import platform_workflow as module

    monkeypatch.setattr(module, "get_data_registry", lambda: tmp_path)
    _patch_platform_helpers(
        monkeypatch,
        station={"station_code": "3203A", "station_name": "示范站", "unique_code": "320382004"},
        devices=[{"device_id": 11, "label": "颗粒物分析仪"}],
    )
    gets: list[tuple[str, list[tuple[str, str]]]] = []

    class LinkApi:
        async def get(self, path, params):
            gets.append((path, list(params)))
            created = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            return {"result": {"items": [{
                "id": 901, "workingOrderCode": "YJ2601", "orderType": "FogCannon",
                "orderStatus": "Doing", "workFlowStatus": "Doing", "createTime": created,
            }]}}

        async def post(self, path, payload):
            raise AssertionError("命中在办告警工单时不得重复建单")

    monkeypatch.setattr(module, "_JiangsuAuthenticatedApi", lambda source: LinkApi())
    result = asyncio.run(module.create_smart_event_dispatch_order(
        event_id="evt-1", site_id="320382004", site_name="示范站",
        title="示范站雾炮干扰处置", order_type="FogCannon",
        event_start_time=datetime.now().astimezone().isoformat(),
    ))
    assert result["status"] == "linked"
    assert result["work_order_code"] == "YJ2601"
    assert result["order_type"] == "FogCannon"
    assert ("orderTypes[0]", "FogCannon") in gets[0][1]
    assert ("StationCode", "3203A") in gets[0][1]


def test_create_smart_event_dispatch_order_maps_chinese_event_type(service, tmp_path, monkeypatch):
    from app.tools.jiangsu import platform_workflow as module

    monkeypatch.setattr(module, "get_data_registry", lambda: tmp_path)
    posts = _patch_platform_helpers(
        monkeypatch,
        station={"station_code": "3203A", "station_name": "示范站", "unique_code": "320382004"},
        devices=[{"device_id": 11, "label": "颗粒物分析仪"}],
        order_code="YJ2602",
    )
    result = asyncio.run(module.create_smart_event_dispatch_order(
        event_id="evt-1", site_id="320382004", site_name="示范站",
        title="示范站雾炮干扰处置", order_type="疑似雾炮喷淋",
    ))
    assert result["status"] == "synced"
    assert result["order_type"] == "FogCannon"
    assert posts[0][0] == "operation/AlarmOrder/CreateAsync"
    assert posts[0][1]["orderType"] == "FogCannon"


def test_create_smart_event_dispatch_order_false_response_is_failed(service, tmp_path, monkeypatch):
    """CreateAsync 以裸 true/false 返回；false 不能被当成建单成功。"""
    from app.tools.jiangsu import platform_workflow as module

    monkeypatch.setattr(module, "get_data_registry", lambda: tmp_path)
    _patch_platform_helpers(
        monkeypatch,
        station={"station_code": "3203A", "station_name": "示范站", "unique_code": "320382004"},
        devices=[{"device_id": 11, "label": "颗粒物分析仪"}],
        create_result=False,
    )
    result = asyncio.run(module.create_smart_event_dispatch_order(
        event_id="evt-1", site_id="320382004", site_name="示范站",
        title="示范站人员入侵处置", order_type="PersonIntrusion",
    ))
    assert result["status"] == "failed"
    assert "CreateAsync 返回 false" in result["detail"]


def test_create_smart_event_dispatch_order_failure_is_reported(service, tmp_path, monkeypatch):
    from app.tools.jiangsu import platform_workflow as module

    monkeypatch.setattr(module, "get_data_registry", lambda: tmp_path)
    _patch_platform_helpers(monkeypatch, station=None)
    result = asyncio.run(module.create_smart_event_dispatch_order(
        event_id="evt-1", site_id="未知站", title="派单"))
    assert result["status"] == "failed"
    assert "平台工单创建失败" in result["detail"]


def test_create_smart_event_dispatch_order_resolves_code_with_platform_naive_time(
        service, tmp_path, monkeypatch):
    """回归：建单后按平台返回的 naive createTime 回查工单号，不得因 aware/naive 比较抛错。"""
    from app.tools.jiangsu import platform_workflow as module
    import app.tools.jiangsu.work_order_dispatch as dispatch_module

    real_resolve = dispatch_module.resolve_created_order_code
    monkeypatch.setattr(module, "get_data_registry", lambda: tmp_path)
    _patch_platform_helpers(
        monkeypatch,
        station={"station_code": "3203A", "station_name": "示范站", "unique_code": "320382004"},
        devices=[{"device_id": 11, "label": "颗粒物分析仪"}],
        order_code=None,
    )
    # 覆盖默认打桩：回查工单号这一步走真实 resolve_created_order_code
    monkeypatch.setattr("app.tools.jiangsu.work_order_dispatch.resolve_created_order_code",
                        real_resolve)

    class RecentOrdersApi:
        async def get(self, path, params):
            created = (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
            return {"result": [{"wo": {
                "orderTitle": "示范站仪器故障处置",
                "createTime": created,
                "workingOrderCode": "FA2601",
            }}]}

        async def post(self, path, payload):
            return {"result": True}

    monkeypatch.setattr("app.tools.jiangsu.work_order_dispatch._JiangsuAuthenticatedApi",
                        lambda source: RecentOrdersApi())

    result = asyncio.run(module.create_smart_event_dispatch_order(
        event_id="evt-1", site_id="320382004", site_name="示范站",
        title="示范站仪器故障处置", order_type="Fault"))
    assert result["order_type"] == "Fault"
    assert result["status"] == "synced"
    assert result["work_order_code"] == "FA2601"


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
        def __init__(self):
            self.gets: list[tuple[str, list[tuple[str, str]]]] = []

        async def get(self, path, params):
            self.gets.append((path, list(params)))
            if "WflWorkFlow" in path:
                return {"result": {"stepList": [
                    {"guid": "step-2", "taskName": "故障处理"}]}}
            return {"result": {"items": [
                {"workingOrderCode": "FA2601", "orderStatus": "Doing",
                 "currentPoint": "step-2", "updateTime": "2026-10-23 09:00:00"}]}}

    api = FakeApi()
    monkeypatch.setattr(fetcher_module, "_JiangsuAuthenticatedApi", lambda source: api)

    fetcher = fetcher_module.JiangsuSmartEventPlatformSyncFetcher()
    first = asyncio.run(fetcher.fetch_and_store())
    assert first["synced_events"] == 1
    second = asyncio.run(fetcher.fetch_and_store())
    assert second["synced_events"] == 0
    state = json.loads((tmp_path / "jiangsu_smart_event_platform_sync" / "state.json")
                       .read_text(encoding="utf-8"))
    assert state["FA2601"]["signature"] == "Doing|故障处理"
    # 事件由「仪器报警」映射为 InstrumentFault：清单与流程节点都必须按该类型查询。
    assert any(("orderTypes[0]", "InstrumentFault") in params
               for path, params in api.gets if "WflWorkFlow" not in path)
    assert any(("Type", "InstrumentFault") in params
               for path, params in api.gets if "WflWorkFlow" in path)
