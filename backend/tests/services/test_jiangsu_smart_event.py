import json

import pytest
from app.scheduled_tasks.default_tasks import build_jiangsu_smart_event_task
from app.scheduled_tasks.models import ExecutionStatus, StepExecution, TaskEvent, TaskExecution
from app.scheduled_tasks.service import EventDispatchResult
from app.services.jiangsu_smart_event import (
    JiangsuSmartEventService,
    normalize_alarm_event,
    persist_scheduled_task_result,
)


def test_normalize_alarm_keeps_pending_status_and_source_tag():
    event = normalize_alarm_event({
        "id": 12,
        "code": "5006A",
        "stationName": "海安监测站",
        "alarmtime": "2026-09-09 08:00:00",
        "content": "UPS 电源报警",
    })

    assert event["event_id"] == "alarm:12"
    assert event["event_status"] == "未研判"
    assert event["event_type"] == "待 AI 研判"
    assert event["clue_tags"][0]["tag_source"] == "子站报警"
    assert event["clue_tags"][0]["tag_name"] == "供电报警"
    assert event["event_trigger_type"] == "jiangsu.smart_event.alarm.power"
    assert "疑似" not in event["initial_event_name"]


def test_normalize_alarm_parses_operations_api_us_datetime_and_station_code():
    event = normalize_alarm_event({
        "id": 161345,
        "stacode": "3011A",
        "positionName": "沛县汉源宾馆",
        "alarmtime": "9/9/2026 1:20:01 PM",
        "ddalarmstateName": "未处理",
        "content": "数据偏差：PM2.5 浓度异常",
    })

    assert event["site_id"] == "3011A"
    assert event["event_start_time"].startswith("2026-09-09T13:20:01")
    assert event["source_alarm_state"] == "未处理"


def test_normalize_alarm_uses_rule_type_when_content_is_not_descriptive():
    event = normalize_alarm_event({
        "id": 2,
        "stacode": "3011A",
        "positionName": "示例站点",
        "alarmtime": "2026-09-09 12:00:00",
        "content": "平台检测到异常",
        "ddRuleType": "断数报警",
    })

    assert event["primary_clue_tag"] == "数采网络报警"


class FakeAlarmTool:
    async def execute(self, **kwargs):
        return {"success": True, "data": [{"id": 1, "code": "A", "content": "仪器报警"}], "metadata": {"x": 1}}


class CapturingAlarmTool(FakeAlarmTool):
    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return await super().execute(**kwargs)


class FailingAlarmTool:
    async def execute(self, **kwargs):
        return {"success": False, "summary": "平台暂不可用", "data": []}


class CapturingScheduledTaskService:
    def __init__(self):
        self.events = []

    async def publish_event(self, event, *, wait=False):
        self.events.append((event, wait))
        return EventDispatchResult(
            matched_task_ids=["jiangsu_smart_event_instrument_alarm"],
            accepted_task_ids=["jiangsu_smart_event_instrument_alarm"],
        )


@pytest.mark.asyncio
async def test_service_filters_normalized_events(tmp_path):
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    payload = await service.list_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
        keyword="仪器",
    )
    assert payload["total"] == 1
    assert payload["source"] == "alarm_adapter_store"
    assert payload["capabilities"]["platform_event_api"] is False


@pytest.mark.asyncio
async def test_sync_creates_one_pending_ai_task_per_new_event(tmp_path):
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    first = await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
    )
    second = await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
    )

    assert len(first["created_tasks"]) == 1
    assert second["created_tasks"] == []
    tasks = service.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["event_id"] == "alarm:1"
    assert tasks[0]["status"] == "待执行"
    assert tasks[0]["conversation_id"].startswith("conversation:")


@pytest.mark.asyncio
async def test_smart_event_sync_queries_all_provincial_stations_without_fixed_codes(tmp_path):
    alarm_tool = CapturingAlarmTool()
    service = JiangsuSmartEventService(alarm_tool, data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09 00:00:00",
        end_time="2026-09-09 23:59:59",
    )

    assert alarm_tool.calls[0]["station_codes"] is None
    assert alarm_tool.calls[0]["station_type"] == "省控"


@pytest.mark.asyncio
async def test_sync_publishes_event_to_matching_scheduled_task(monkeypatch, tmp_path):
    scheduled = CapturingScheduledTaskService()
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: scheduled)
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    result = await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
    )
    assert result["dispatches"][0]["accepted_task_ids"] == ["jiangsu_smart_event_instrument_alarm"]
    assert scheduled.events[0][0].event_type == "jiangsu.smart_event.alarm.instrument"
    assert scheduled.events[0][0].payload["smart_event"]["event_id"] == "alarm:1"


@pytest.mark.asyncio
async def test_event_center_refresh_stores_events_without_dispatching_ai(monkeypatch, tmp_path):
    scheduled = CapturingScheduledTaskService()
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: scheduled)
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)

    payload = await service.list_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
        refresh=True,
    )

    assert payload["total"] == 1
    assert scheduled.events == []
    assert service.list_tasks()[0]["status"] == "待执行"


def test_create_task_requires_a_stored_event(tmp_path):
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    with pytest.raises(KeyError):
        service.create_task("alarm:missing")


@pytest.mark.asyncio
async def test_judgment_confirmation_operation_and_archive_are_persisted(tmp_path):
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
    )
    actor = {"user_id": "u1", "username": "operator"}
    event = service.submit_ai_judgment(
        "alarm:1",
        {
            "event_type": "疑似仪器故障",
            "level": "P1",
            "diagnosis_note": "建议核查校准记录",
            "confirmed": True,
        },
        actor=actor,
    )
    assert event["event_status"] == "已确认"
    record = service.record_operation(
        "alarm:1", action="feedback", summary="已通知站点复核", actor=actor, details={"channel": "电话"}
    )
    archived = service.archive_event("alarm:1", actor=actor, comment="复核完成")
    assert record["action"] == "feedback"
    assert archived["archived"] is True
    assert archived["event_status"] == "已归档"
    assert len(archived["operation_records"]) == 3
    with pytest.raises(ValueError, match="smart_event_archived"):
        service.record_operation("alarm:1", action="note", summary="不可修改", actor=actor)


@pytest.mark.asyncio
async def test_archive_requires_confirmed_judgment(tmp_path):
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
    )
    with pytest.raises(ValueError, match="smart_event_judgment_not_confirmed"):
        service.archive_event("alarm:1", actor={"user_id": "u1", "username": "operator"})


@pytest.mark.asyncio
async def test_list_uses_stale_store_when_alarm_api_is_temporarily_unavailable(tmp_path):
    writer = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    await writer.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
    )
    reader = JiangsuSmartEventService(FailingAlarmTool(), data_root=tmp_path)
    payload = await reader.list_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
    )
    assert payload["source"] == "alarm_adapter_store_stale"
    assert payload["capabilities"]["upstream_available"] is False
    assert payload["events"][0]["event_id"] == "alarm:1"


def test_config_round_trip(tmp_path):
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    saved = service.save_config({"event_merge_window_minutes": 90})
    loaded = service.load_config()
    assert saved["event_merge_window_minutes"] == 90
    assert loaded["event_merge_window_minutes"] == 90
    assert json.loads(service.config_path.read_text(encoding="utf-8"))["version"] == 1


def test_smart_event_task_uses_event_trigger_and_history_learning():
    task = build_jiangsu_smart_event_task("供电报警")
    assert task.event_type == "jiangsu.smart_event.alarm.power"
    assert task.history_learning.enabled is True
    assert task.history_learning.active_retrieval_enabled is True
    assert task.history_learning.memory_char_budget == 8000


@pytest.mark.asyncio
async def test_scheduled_task_final_reply_is_persisted_to_event_detail(tmp_path, monkeypatch):
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
    )
    monkeypatch.setattr("app.services.jiangsu_smart_event.get_data_registry", lambda: tmp_path)
    task = build_jiangsu_smart_event_task("仪器报警")
    execution = TaskExecution(
        execution_id="exec:1",
        task_id=task.task_id,
        task_name=task.name,
        status=ExecutionStatus.SUCCESS,
        total_steps=1,
        event_id="alarm:1",
        event_type="jiangsu.smart_event.alarm.instrument",
        steps=[
            StepExecution(
                step_id="task",
                status=ExecutionStatus.SUCCESS,
                agent_prompt="prompt",
                agent_response="研判结论：建议核查仪器状态和校准记录。",
            )
        ],
    )
    await persist_scheduled_task_result(
        task,
        TaskEvent(event_id="alarm:1", event_type="jiangsu.smart_event.alarm.instrument"),
        execution,
    )
    event = service._load_store()["events"][0]
    assert event["event_status"] == "AI 已研判"
    assert event["ai_judgment"]["final_response"].startswith("研判结论")
    assert event["ai_diagnosis_note"] == event["ai_judgment"]["final_response"]
