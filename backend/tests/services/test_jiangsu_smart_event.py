import json

import pytest
from app.scheduled_tasks.default_tasks import build_jiangsu_smart_event_task
from app.scheduled_tasks.models import ExecutionStatus, StepExecution, TaskEvent, TaskExecution
from app.scheduled_tasks.service import EventDispatchResult
from app.services.jiangsu_smart_event import (
    JiangsuSmartEventService,
    _event_fingerprint,
    normalize_alarm_event,
    persist_scheduled_task_result,
    normalize_compliance_tag,
    detect_data_clue_tags,
    NAMING_LABELS,
    COMPLIANCE_TAG_RULES,
    DEFAULT_HOUR_LIMITS,
    _compact_tags,
    _primary_tag,
    _detection_tag,
)


@pytest.fixture(autouse=True)
def reset_background_sync_state():
    JiangsuSmartEventService._background_sync_task = None
    JiangsuSmartEventService._background_sync_started_at = None
    yield
    pending = JiangsuSmartEventService._background_sync_task
    if pending is not None and not pending.done():
        pending.cancel()
    JiangsuSmartEventService._background_sync_task = None
    JiangsuSmartEventService._background_sync_started_at = None


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
    assert event["event_trigger_type"] == "jiangsu.smart_event.alarm"
    assert event["clue_trigger_type"] == "jiangsu.smart_event.alarm.power"
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


def test_normalize_alarm_uses_v3_initial_naming_template():
    event = normalize_alarm_event({
        "id": 3,
        "code": "5006A",
        "stationName": "海安监测站",
        "alarmtime": "2026-09-09 08:00:00",
        "content": "UPS 电源报警",
    })

    assert event["initial_event_name"] == "海安监测站供电断数线索待研判事件"
    assert event["event_name"] == event["initial_event_name"]
    assert event["merged_alarm_ids"] == [event["event_id"]]
    assert len(event["evidence"]["alarms"]) == 1


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
            matched_task_ids=["jiangsu_smart_event_ai_judgment"],
            accepted_task_ids=["jiangsu_smart_event_ai_judgment"],
        )


@pytest.mark.asyncio
async def test_service_filters_normalized_events(tmp_path):
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
    )
    payload = await service.list_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
        keyword="仪器",
        refresh=False,
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
async def test_last_sync_records_new_event_count(tmp_path):
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
    )
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
    )
    last_sync = service._load_store()["last_sync"]
    assert last_sync["new_event_count"] == 0
    assert last_sync["new_event_ids"] == []


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
    assert result["dispatches"][0]["accepted_task_ids"] == ["jiangsu_smart_event_ai_judgment"]
    assert scheduled.events[0][0].event_type == "jiangsu.smart_event.alarm"
    assert scheduled.events[0][0].payload["smart_event"]["event_id"] == "alarm:1"


@pytest.mark.asyncio
async def test_event_center_refresh_returns_store_first_and_syncs_in_background(monkeypatch, tmp_path):
    scheduled = CapturingScheduledTaskService()
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: scheduled)
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)

    payload = await service.list_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
        refresh=True,
    )

    # The response renders the stored events immediately without waiting for
    # the upstream alarm API; the sync runs in the background task.
    assert payload["total"] == 0
    assert payload["source_metadata"]["sync"]["in_progress"] is True
    assert JiangsuSmartEventService._background_sync_task is not None
    await JiangsuSmartEventService._background_sync_task

    store = service._load_store()
    assert len(store["events"]) == 1
    assert scheduled.events == []
    assert service.list_tasks()[0]["status"] == "待执行"
    assert store["last_sync"]["new_event_count"] == 1
    assert store["last_sync"]["new_event_ids"] == ["alarm:1"]


@pytest.mark.asyncio
async def test_background_sync_deduplicates_concurrent_triggers(tmp_path):
    class SlowAlarmTool(FakeAlarmTool):
        def __init__(self):
            self.calls = 0

        async def execute(self, **kwargs):
            import asyncio

            self.calls += 1
            await asyncio.sleep(0.05)
            return await super().execute(**kwargs)

    alarm_tool = SlowAlarmTool()
    service = JiangsuSmartEventService(alarm_tool, data_root=tmp_path)
    window = {"start_time": "2026-09-09T00:00:00+08:00", "end_time": "2026-09-09T23:59:59+08:00"}

    first = service.start_background_sync(**window)
    second = service.start_background_sync(**window)

    assert first["triggered"] is True
    assert second["triggered"] is False
    assert second["in_progress"] is True
    await JiangsuSmartEventService._background_sync_task
    assert alarm_tool.calls == 1
    assert JiangsuSmartEventService.background_sync_status()["in_progress"] is False


@pytest.mark.asyncio
async def test_manual_ai_judgment_dispatches_only_selected_event_with_evidence(monkeypatch, tmp_path):
    scheduled = CapturingScheduledTaskService()
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: scheduled)
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
        dispatch_ai=False,
    )
    store = service._load_store()
    event = store["events"][0]
    event["evidence_package"] = {"sources": {"monitoring": {"status": "success", "data": []}}}
    event["evidence_fingerprint"] = _event_fingerprint(event)
    service._save_store(store)
    result = await service.run_ai_judgment(event["event_id"])

    assert result["task"]["event_id"] == event["event_id"]
    assert len(scheduled.events) == 1
    dispatched = scheduled.events[0][0]
    assert dispatched.payload["evidence_package"]["sources"]["monitoring"]["status"] == "success"
    assert service._load_store()["events"][0]["event_status"] == "AI 研判中"


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
    # 响应先返回已存储事件，不等待上游；后台同步失败后把错误写入 last_sync。
    assert payload["events"][0]["event_id"] == "alarm:1"
    assert payload["source"] == "alarm_adapter_store"
    assert JiangsuSmartEventService._background_sync_task is not None
    await JiangsuSmartEventService._background_sync_task

    stale = await reader.list_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
        refresh=False,
    )
    assert stale["source"] == "alarm_adapter_store_stale"
    assert stale["capabilities"]["upstream_available"] is False
    assert stale["source_metadata"]["upstream_error"] == "平台暂不可用"
    assert stale["events"][0]["event_id"] == "alarm:1"


def test_config_round_trip(tmp_path):
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    saved = service.save_config({"event_merge_window_minutes": 90})
    loaded = service.load_config()
    assert saved["event_merge_window_minutes"] == 90
    assert loaded["event_merge_window_minutes"] == 90
    assert json.loads(service.config_path.read_text(encoding="utf-8"))["version"] == 1


class SameDayAlarmsTool:
    """同站点同一天的两条告警。"""

    def __init__(self, rows=None):
        self.rows = rows or [
            {"id": 1, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 08:00:00", "content": "UPS 电源报警"},
            {"id": 2, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 15:00:00", "content": "SO2 分析仪故障报警"},
        ]

    async def execute(self, **kwargs):
        return {"success": True, "data": self.rows, "metadata": {}}


class FakeEvidenceFetcher:
    def __init__(self):
        self.fetched = []

    async def fetch(self, event, **kwargs):
        self.fetched.append(event.get("event_id"))
        return {
            "schema_version": "jiangsu_smart_event_evidence/v1",
            "status": "success",
            "sources": {},
            "gaps": [],
        }


def _finished_execution(response: str, *, execution_id: str = "exec:merge") -> TaskExecution:
    return TaskExecution(
        execution_id=execution_id,
        task_id="jiangsu_smart_event_ai_judgment",
        task_name="江苏智能事件AI研判",
        status=ExecutionStatus.SUCCESS,
        total_steps=1,
        event_id="unused",
        event_type="jiangsu.smart_event.alarm",
        steps=[
            StepExecution(
                step_id="task",
                status=ExecutionStatus.SUCCESS,
                agent_prompt="prompt",
                agent_response=response,
            )
        ],
    )


@pytest.mark.asyncio
async def test_same_site_same_day_alarms_merge_into_one_event(tmp_path):
    service = JiangsuSmartEventService(SameDayAlarmsTool(), data_root=tmp_path)
    result = await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-09T23:59:59+08:00",
        dispatch_ai=False,
    )

    assert result["stored_event_count"] == 1
    store = service._load_store()
    event = store["events"][0]
    assert event["event_id"] == "alarm:1"
    assert event["clue_count"] == 2
    assert event["merged_alarm_ids"] == ["alarm:1", "alarm:2"]
    assert event["event_start_time"].startswith("2026-09-09T08:00:00")
    assert event["event_end_time"].startswith("2026-09-09T15:00:00")
    assert event["primary_clue_tag"] == "供电报警"
    assert event["initial_event_name"] == "示例站供电断数线索待研判事件"
    assert len(event["evidence"]["alarms"]) == 2
    # 合并后仍只有一张待执行任务卡，等待触发研判时分析完整事件。
    assert len(service.list_tasks()) == 1
    assert service.list_tasks()[0]["event_id"] == "alarm:1"


@pytest.mark.asyncio
async def test_cross_day_and_cross_site_alarms_stay_separate(tmp_path):
    tool = SameDayAlarmsTool(rows=[
        {"id": 1, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 08:00:00", "content": "UPS 电源报警"},
        {"id": 2, "code": "B", "stationName": "邻站", "alarmtime": "2026-09-09 09:00:00", "content": "UPS 电源报警"},
        {"id": 3, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-10 08:00:00", "content": "UPS 电源报警"},
    ])
    service = JiangsuSmartEventService(tool, data_root=tmp_path)
    result = await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00",
        end_time="2026-09-10T23:59:59+08:00",
        dispatch_ai=False,
    )

    assert result["stored_event_count"] == 3
    assert len(service.list_tasks()) == 3


@pytest.mark.asyncio
async def test_unjudged_merge_reuses_single_task_card(tmp_path):
    service = JiangsuSmartEventService(SameDayAlarmsTool(rows=[
        {"id": 1, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 08:00:00", "content": "UPS 电源报警"},
    ]), data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    service.alarm_tool = SameDayAlarmsTool()
    second = await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )

    assert second["merged_event_count"] == 1
    store = service._load_store()
    assert len(store["events"]) == 1
    assert store["events"][0]["clue_count"] == 2
    # 未研判事件不新增任务卡，沿用原待执行卡。
    assert len(service.list_tasks()) == 1
    assert "pending_delta" not in store["events"][0]


@pytest.mark.asyncio
async def test_merged_clues_on_judged_event_create_incremental_task(tmp_path):
    tool = SameDayAlarmsTool(rows=[
        {"id": 1, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 08:00:00", "content": "UPS 电源报警"},
    ])
    service = JiangsuSmartEventService(tool, data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    service.apply_task_execution("alarm:1", build_jiangsu_smart_event_task(), _finished_execution("第一轮结论：疑似站房停电。"))

    tool.rows = tool.rows + [
        {"id": 3, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 15:00:00", "content": "SO2 分析仪故障报警"},
    ]
    result = await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )

    assert result["merged_event_count"] == 1
    store = service._load_store()
    event = store["events"][0]
    assert event["event_id"] == "alarm:1"
    assert event["clue_count"] == 2
    assert event["pending_delta"]["clue_ids"] == ["alarm:3:alarm"]
    tasks = service.list_tasks()
    assert len(tasks) == 2
    first, incremental = tasks[0], tasks[1]
    assert first["status"] == "已完成"
    assert incremental["status"] == "待执行"
    assert incremental["title"].startswith("AI增量研判：")
    assert incremental["continuity"]["mode"] == "incremental"
    assert incremental["continuity"]["base_task_id"] == first["task_id"]
    # 增量研判在之前的对话基础上继续。
    assert incremental["conversation_id"] == first["conversation_id"]


@pytest.mark.asyncio
async def test_incremental_dispatch_carries_continuity_context(tmp_path, monkeypatch):
    scheduled = CapturingScheduledTaskService()
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: scheduled)
    tool = SameDayAlarmsTool(rows=[
        {"id": 1, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 08:00:00", "content": "UPS 电源报警"},
    ])
    service = JiangsuSmartEventService(tool, data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    service.apply_task_execution("alarm:1", build_jiangsu_smart_event_task(), _finished_execution("第一轮结论。"))
    tool.rows = tool.rows + [
        {"id": 3, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 16:00:00", "content": "数采仪离线"},
    ]
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=True
    )

    assert len(scheduled.events) == 1
    dispatched = scheduled.events[0][0]
    context = dispatched.payload["continuity_context"]
    assert context["mode"] == "incremental"
    assert context["previous_final_response"] == "第一轮结论。"
    assert [tag["tag_name"] for tag in context["new_clue_tags"]] == ["数采网络报警"]
    assert "连续性判断" in context["instruction"]


@pytest.mark.asyncio
async def test_apply_task_execution_continuity_same_cause_updates_base_card(tmp_path):
    tool = SameDayAlarmsTool(rows=[
        {"id": 1, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 08:00:00", "content": "UPS 电源报警"},
    ])
    service = JiangsuSmartEventService(tool, data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    service.apply_task_execution("alarm:1", build_jiangsu_smart_event_task(), _finished_execution("第一轮结论。", execution_id="exec:1"))
    tool.rows = tool.rows + [
        {"id": 3, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 15:00:00", "content": "UPS 持续报警"},
    ]
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    service.apply_task_execution(
        "alarm:1", build_jiangsu_smart_event_task(),
        _finished_execution("连续性判断：同一原因延续\n第二轮结论：供电异常持续。", execution_id="exec:2"),
    )

    store = service._load_store()
    event = store["events"][0]
    assert event["event_status"] == "AI 已研判"
    assert event["last_continuity_result"] == "same_cause"
    assert event["judgment_history"][0]["final_response"] == "第一轮结论。"
    assert event["ai_judgment"]["final_response"].startswith("连续性判断")
    assert event["judged_clue_ids"] == ["alarm:1:alarm", "alarm:3:alarm"]
    assert "pending_delta" not in event
    base_card, incremental_card = store["tasks"][0], store["tasks"][1]
    assert incremental_card["continuity_result"] == "same_cause"
    # 同一原因延续：原待办任务卡片更新为最新结论。
    assert base_card["final_response"].startswith("连续性判断：同一原因延续")


@pytest.mark.asyncio
async def test_apply_task_execution_continuity_new_cause_keeps_base_card(tmp_path):
    tool = SameDayAlarmsTool(rows=[
        {"id": 1, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 08:00:00", "content": "UPS 电源报警"},
    ])
    service = JiangsuSmartEventService(tool, data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    service.apply_task_execution("alarm:1", build_jiangsu_smart_event_task(), _finished_execution("第一轮结论。", execution_id="exec:1"))
    tool.rows = tool.rows + [
        {"id": 3, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 15:00:00", "content": "SO2 分析仪故障报警"},
    ]
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    service.apply_task_execution(
        "alarm:1", build_jiangsu_smart_event_task(),
        _finished_execution("连续性判断：新事件\n第二轮结论：独立仪器故障。", execution_id="exec:2"),
    )

    store = service._load_store()
    event = store["events"][0]
    assert event["last_continuity_result"] == "new_cause"
    base_card, incremental_card = store["tasks"][0], store["tasks"][1]
    # 新事件：原任务卡片保留上一轮结论，增量卡为独立研判轮次。
    assert base_card["final_response"] == "第一轮结论。"
    assert incremental_card["continuity_result"] == "new_cause"
    assert incremental_card["final_response"].startswith("连续性判断：新事件")


@pytest.mark.asyncio
async def test_run_ai_judgment_refetches_stale_evidence_after_merge(tmp_path, monkeypatch):
    scheduled = CapturingScheduledTaskService()
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: scheduled)
    evidence = FakeEvidenceFetcher()
    tool = SameDayAlarmsTool(rows=[
        {"id": 1, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 08:00:00", "content": "UPS 电源报警"},
    ])
    service = JiangsuSmartEventService(tool, data_root=tmp_path, evidence_fetcher=evidence)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    await service.run_ai_judgment("alarm:1")
    assert len(evidence.fetched) == 1

    tool.rows = tool.rows + [
        {"id": 3, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 15:00:00", "content": "数采仪离线"},
    ]
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    await service.run_ai_judgment("alarm:1")

    # 合并后证据指纹失效：扩展时间窗口重新抓取，仍是同一个证据包文件。
    assert len(evidence.fetched) == 2
    event = service._load_store()["events"][0]
    assert event["evidence_fingerprint"] == _event_fingerprint(event)


STRUCTURED_RESPONSE = """研判结论：疑似 SO2 仪器故障，有数据影响，建议 P1。
关键证据：SO2 分析仪报警与恒值同时出现。
```json
{
  "event_type": "疑似仪器故障",
  "data_impact": "有数据影响",
  "suggested_level": "P1",
  "diagnosis_note": "SO2 分析仪报警与小时数据恒值同窗，其余因子正常，建议核查仪器状态与校准记录。",
  "manual_review_suggestion": "人工复核 SO2 分析仪流量与近期质控记录。",
  "disposal_suggestions": ["派单核查 SO2 分析仪", "复核校准记录"],
  "primary_evidence_tags": ["报警：仪器报警"],
  "supporting_evidence_tags": ["数据：SO2 恒值"],
  "compliance_explanation_result": "无合规记录",
  "data_analysis": {
    "station_series_analysis": "SO2 在事件窗口内持续恒值，其余因子正常波动。",
    "regional_comparison_analysis": "本站 SO2 明显低于周边站点。",
    "data_impact_assessment": "SO2 事件窗口内小时值建议标记无效。",
    "logic_direction_check": "仪器故障对应单污染物恒值，方向一致。"
  }
}
```"""


@pytest.mark.asyncio
async def test_apply_task_execution_parses_structured_judgment_json(tmp_path):
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    service.apply_task_execution("alarm:1", build_jiangsu_smart_event_task(), _finished_execution(STRUCTURED_RESPONSE))

    event = service._load_store()["events"][0]
    assert event["ai_event_type"] == "疑似仪器故障"
    assert event["ai_data_impact"] == "有数据影响"
    assert event["ai_suggested_level"] == "P1"
    # 未提供 event_name 时按 V3.0 模板生成：站点+类型+（数据影响）。
    assert event["ai_event_name"] == "A疑似仪器故障（有数据影响）"
    assert event["event_name"] == event["ai_event_name"]
    # ai_diagnosis_note 优先取结构化摘要而非整段回复。
    assert event["ai_diagnosis_note"].startswith("SO2 分析仪报警")
    structured = event["ai_structured_judgment"]
    assert structured["primary_evidence_tags"] == ["报警：仪器报警"]
    assert structured["compliance_explanation_result"] == "无合规记录"
    assert set(structured["data_analysis"]) == {
        "station_series_analysis", "regional_comparison_analysis",
        "data_impact_assessment", "logic_direction_check",
    }
    assert event["judged_clue_ids"] == ["alarm:1:alarm"]


@pytest.mark.asyncio
async def test_structured_judgment_ignores_unknown_enums(tmp_path):
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    response = """结论。
```json
{"event_type": "自造类型", "data_impact": "影响很大", "suggested_level": "P9", "diagnosis_note": "摘要保留"}
```"""
    service.apply_task_execution("alarm:1", build_jiangsu_smart_event_task(), _finished_execution(response))

    event = service._load_store()["events"][0]
    structured = event["ai_structured_judgment"]
    # 非法枚举剔除：类型/影响/等级不回写，名称不生成；合法字段保留。
    assert structured["event_type"] is None
    assert structured["data_impact"] is None
    assert structured["suggested_level"] is None
    assert structured["diagnosis_note"] == "摘要保留"
    assert event.get("ai_event_type") is None
    assert event.get("ai_event_name") is None
    assert event["event_name"] == event["initial_event_name"]
    assert event["ai_data_impact"] == "待确认"


@pytest.mark.asyncio
async def test_structured_continuity_json_overrides_text_marker(tmp_path):
    tool = SameDayAlarmsTool(rows=[
        {"id": 1, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 08:00:00", "content": "UPS 电源报警"},
    ])
    service = JiangsuSmartEventService(tool, data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    service.apply_task_execution("alarm:1", build_jiangsu_smart_event_task(), _finished_execution("第一轮结论。", execution_id="exec:1"))
    tool.rows = tool.rows + [
        {"id": 3, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 15:00:00", "content": "SO2 分析仪故障报警"},
    ]
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    # 文本标记行说同一原因，json 块说新事件：以结构化字段为准。
    response = """连续性判断：同一原因延续
第二轮说明。
```json
{"event_type": "疑似仪器故障", "continuity": {"same_cause": false}}
```"""
    service.apply_task_execution("alarm:1", build_jiangsu_smart_event_task(), _finished_execution(response, execution_id="exec:2"))

    event = service._load_store()["events"][0]
    assert event["last_continuity_result"] == "new_cause"
    assert event["ai_event_type"] == "疑似仪器故障"
    base_card = service._load_store()["tasks"][0]
    assert base_card["final_response"] == "第一轮结论。"


def test_legacy_store_merges_same_day_events_and_repoints_tasks(tmp_path):
    store_dir = tmp_path / "jiangsu_smart_events"
    store_dir.mkdir(parents=True)
    first = normalize_alarm_event({"id": 1, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 08:00:00", "content": "UPS 电源报警"})
    second = normalize_alarm_event({"id": 2, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 15:00:00", "content": "SO2 分析仪故障报警"})
    second_task = {"task_id": "task:second", "event_id": "alarm:2", "task_type": "ai_judgment", "status": "待执行"}
    (store_dir / "store.json").write_text(json.dumps({
        "schema_version": "jiangsu_smart_events/v1",
        "events": [first, second],
        "tasks": [second_task],
    }, ensure_ascii=False), encoding="utf-8")

    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    store = service._load_store()

    assert len(store["events"]) == 1
    event = store["events"][0]
    assert event["event_id"] == "alarm:1"
    assert event["clue_count"] == 2
    assert set(event["merged_alarm_ids"]) == {"alarm:1", "alarm:2"}
    assert event["initial_event_name"] == "示例站供电断数线索待研判事件"
    assert [card["event_id"] for card in store["tasks"]] == ["alarm:1"]


@pytest.mark.asyncio
async def test_dispatch_order_moves_event_to_dispatching_state(tmp_path):
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    actor = {"user_id": "u1", "username": "operator"}
    event = service.dispatch_order(
        "alarm:1",
        title="现场核查喷淋作业",
        order_type="现场核查",
        assignee="站点运维",
        description="核查喷淋位置与持续时间",
        actor=actor,
    )

    assert event["event_status"] == "派单处置中"
    operation = event["operation_records"][-1]
    assert operation["action"] == "dispatch_order"
    assert operation["details"]["assignee"] == "站点运维"
    service.archive_event(
        "alarm:1", actor=actor, confirmation={"event_type": "疑似仪器故障", "level": "P2"},
    )
    with pytest.raises(ValueError, match="smart_event_archived"):
        service.dispatch_order("alarm:1", title="归档后不可派单", actor=actor)


@pytest.mark.asyncio
async def test_feedback_starts_incremental_round_and_replaces_conclusion(tmp_path, monkeypatch):
    scheduled = CapturingScheduledTaskService()
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: scheduled)
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path, evidence_fetcher=FakeEvidenceFetcher())
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    first_card = service.list_tasks()[0]
    service.apply_task_execution("alarm:1", build_jiangsu_smart_event_task(), _finished_execution("第一轮结论。", execution_id="exec:1"))

    result = await service.submit_feedback(
        "alarm:1", feedback="现场确认喷淋作业，已停用并提交照片。", attachments=["现场照片.jpg"], actor={"user_id": "u1", "username": "operator"}
    )

    event = result["event"]
    assert event["event_status"] == "已反馈"
    assert event["operation_records"][-1]["action"] == "event_feedback"
    feedback_card = result["task"]
    # 反馈是增量对话：复用上一轮会话，标记反馈原因。
    assert feedback_card["continuity"]["reason"] == "feedback"
    assert feedback_card["conversation_id"] == first_card["conversation_id"]
    assert feedback_card["continuity"]["feedback"]["attachments"] == ["现场照片.jpg"]
    dispatched = scheduled.events[-1][0]
    context = dispatched.payload["continuity_context"]
    assert context["reason"] == "feedback"
    assert "现场确认喷淋" in context["feedback"]["feedback"]

    # 反馈增量研判完成后：上一轮结论进入历史，新结论替换，状态回到已反馈。
    service.apply_task_execution(
        "alarm:1", build_jiangsu_smart_event_task(),
        _finished_execution("反馈复核后的更新结论。", execution_id="exec:2"),
    )
    store = service._load_store()
    event = store["events"][0]
    assert event["event_status"] == "已反馈"
    assert event["ai_judgment"]["final_response"] == "反馈复核后的更新结论。"
    assert event["judgment_history"][0]["final_response"] == "第一轮结论。"


@pytest.mark.asyncio
async def test_manual_rerun_starts_fresh_conversation_and_cancels_stale_cards(tmp_path, monkeypatch):
    scheduled = CapturingScheduledTaskService()
    monkeypatch.setattr("app.scheduled_tasks.get_scheduled_task_service", lambda: scheduled)
    tool = SameDayAlarmsTool(rows=[
        {"id": 1, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 08:00:00", "content": "UPS 电源报警"},
    ])
    service = JiangsuSmartEventService(tool, data_root=tmp_path, evidence_fetcher=FakeEvidenceFetcher())
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    first_card = service.list_tasks()[0]
    service.apply_task_execution("alarm:1", build_jiangsu_smart_event_task(), _finished_execution("第一轮结论。", execution_id="exec:1"))
    # 合并新线索挂起一张增量卡。
    tool.rows = tool.rows + [
        {"id": 3, "code": "A", "stationName": "示例站", "alarmtime": "2026-09-09 15:00:00", "content": "数采仪离线"},
    ]
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    incremental = service.list_tasks()[-1]
    assert incremental["status"] == "待执行"

    # 人工“AI 重新研判”：全新会话，增量卡被取消。
    result = await service.run_ai_judgment("alarm:1")

    fresh = result["task"]
    assert fresh["conversation_id"] != first_card["conversation_id"]
    assert "continuity" not in fresh
    assert fresh["title"].startswith("AI研判：")
    store = service._load_store()
    statuses = {card["task_id"]: card["status"] for card in store["tasks"]}
    assert statuses[incremental["task_id"]] == "已取消"
    # 全新研判的派发不带增量上下文。
    dispatched = scheduled.events[-1][0]
    assert dispatched.payload["continuity_context"] is None
    # 完成后旧结论被替换进历史。
    service.apply_task_execution("alarm:1", build_jiangsu_smart_event_task(), _finished_execution("全新结论。", execution_id="exec:3"))
    event = service._load_store()["events"][0]
    assert event["event_status"] == "AI 已研判"
    assert event["ai_judgment"]["final_response"] == "全新结论。"
    assert event["judgment_history"][0]["final_response"] == "第一轮结论。"


@pytest.mark.asyncio
async def test_archive_with_confirmation_overrides_fields_without_prior_manual_confirmation(tmp_path):
    service = JiangsuSmartEventService(FakeAlarmTool(), data_root=tmp_path)
    await service.sync_alarm_events(
        start_time="2026-09-09T00:00:00+08:00", end_time="2026-09-09T23:59:59+08:00", dispatch_ai=False
    )
    actor = {"user_id": "u1", "username": "operator"}
    # 未带归档确认且无人工确认时仍拒绝旧式归档。
    with pytest.raises(ValueError, match="smart_event_judgment_not_confirmed"):
        service.archive_event("alarm:1", actor=actor)
    archived = service.archive_event(
        "alarm:1",
        actor=actor,
        comment="复核完成",
        confirmation={
            "event_type": "疑似站房停电",
            "event_name": "A疑似站房停电（有数据影响）",
            "level": "P1",
            "data_impact": "有数据影响",
        },
    )

    assert archived["event_status"] == "已归档"
    assert archived["event_name"] == "A疑似站房停电（有数据影响）"
    assert archived["ai_event_type"] == "疑似站房停电"
    assert archived["manual_final_level"] == "P1"
    confirmed = archived["archive_confirmed"]
    assert confirmed["event_type"] == "疑似站房停电"
    assert confirmed["confirmed_by"] == actor
    assert archived["manual_confirmation"]["source"] == "archive"


def test_smart_event_task_uses_event_trigger_and_history_learning():
    task = build_jiangsu_smart_event_task()
    assert task.event_type == "jiangsu.smart_event.alarm"
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
    task = build_jiangsu_smart_event_task()
    execution = TaskExecution(
        execution_id="exec:1",
        task_id=task.task_id,
        task_name=task.name,
        status=ExecutionStatus.SUCCESS,
        total_steps=1,
        event_id="alarm:1",
        event_type="jiangsu.smart_event.alarm",
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
        TaskEvent(event_id="alarm:1", event_type="jiangsu.smart_event.alarm"),
        execution,
    )
    event = service._load_store()["events"][0]
    assert event["event_status"] == "AI 已研判"
    assert event["ai_judgment"]["final_response"].startswith("研判结论")
    assert event["ai_diagnosis_note"] == event["ai_judgment"]["final_response"]


# ---------------------------------------------------------------------------
# Phase 4: NAMING_LABELS extension & normalize_compliance_tag
# ---------------------------------------------------------------------------


def test_naming_labels_covers_new_tag_types():
    assert NAMING_LABELS["站点级断数"] == "供电断数"
    assert NAMING_LABELS["多仪器断数"] == "公共系统报警"
    assert NAMING_LABELS["单仪器断数"] == "仪器报警"
    assert NAMING_LABELS["浓度超限"] == "超限报警"
    assert NAMING_LABELS["预警超限"] == "超限报警"
    assert NAMING_LABELS["数据突升"] == "数据异常"
    assert NAMING_LABELS["离群异常"] == "数据异常"
    assert NAMING_LABELS["恒值异常"] == "数据异常"
    assert NAMING_LABELS["负值或无效值"] == "数据异常"
    assert NAMING_LABELS["人员进入采样区"] == "人员进入采样区"
    assert NAMING_LABELS["雾炮喷淋"] == "雾炮喷淋"


def test_primary_tag_ranks_station_level_missing_above_instrument_alarm():
    unjudged_bucket = {
        "clue_tags": [
            {"tag_id": "t1", "tag_name": "站点级断数", "tag_category": "断数"},
            {"tag_id": "t2", "tag_name": "仪器报警", "tag_category": "告警"},
        ],
        "primary_clue_tag": None,
        "event_name": None,
        "clue_count": 2,
    }
    priority = ["人员进入采样区", "雾炮喷淋", "供电断数", "公共系统报警", "站房环境",
                "仪器报警", "超限报警", "数据异常"]
    primary = _primary_tag(unjudged_bucket["clue_tags"], priority)
    assert primary is not None
    assert primary["tag_name"] == "站点级断数"


def test_normalize_compliance_tag_work_order_matches_keywords():
    row = {"orderType": "维修", "orderTitle": "分析仪更换", "workingOrderCode": "WO-2026-001"}
    tag = normalize_compliance_tag(row, source_hint="工单")
    assert tag is not None
    assert tag["tag_name"] == "维修记录"
    assert tag["tag_source"] == "合规记录"
    assert tag["tag_display_text"] == "合规：维修记录（分析仪更换）"
    assert "WO-2026-001" in tag["tag_id"]


def test_normalize_compliance_tag_calibration():
    row = {"missionName": "季度校准与质控比对", "id": "qc-1"}
    tag = normalize_compliance_tag(row, source_hint="质控")
    assert tag is not None
    assert tag["tag_name"] == "校准记录"


def test_normalize_compliance_tag_door_defaults_to_visit():
    row = {"personName": "张三", "eventType": "刷卡"}
    tag = normalize_compliance_tag(row, source_hint="门禁")
    assert tag is not None
    assert tag["tag_name"] == "进站记录"


def test_normalize_compliance_tag_unmatched_returns_none():
    row = {"orderType": "其他", "orderTitle": "随机内容"}
    tag = normalize_compliance_tag(row, source_hint="工单")
    assert tag is None


# ---------------------------------------------------------------------------
# Phase 4: detect_data_clue_tags (missing / exceed / anomaly / outlier)
# ---------------------------------------------------------------------------


def _make_event(event_id="evt-1", site_name="示例站", site_id="A"):
    return {"event_id": event_id, "site_name": site_name, "site_id": site_id}


def _make_hour_records(records):
    return {"monitoring": {"data": {"station_hour": {"data": records}}}, "gaps": []}


def _make_package(station_hour_data, regional_deltas=None):
    pkg = {
        "status": "success",
        "sources": _make_hour_records(station_hour_data),
        "time_windows": {"query": {"start": "2026-09-09 00:00:00", "end": "2026-09-09 23:00:00"}},
    }
    if regional_deltas is not None:
        pkg["sources"]["comparison"] = {"regional_deltas": regional_deltas}
    return pkg


def _config(**overrides):
    base = {
        "station_missing_factor_threshold": 2,
        "multi_instrument_threshold": 2,
        "data_anomaly_threshold_pct": 20,
        "pollutant_hour_limits": {**DEFAULT_HOUR_LIMITS},
    }
    base.update(overrides)
    return base


def test_detect_missing_station_level_multiple_pollutants_missing():
    records = [
        {"timePoint": "2026-09-09 10:00:00", "SO2": 10.0, "NO2": None, "PM10": None, "PM2_5": None, "O3": 5.0, "CO": 0.5},
        {"timePoint": "2026-09-09 11:00:00", "SO2": 12.0, "NO2": None, "PM10": None, "PM2_5": None, "O3": 6.0, "CO": 0.6},
    ]
    tags = detect_data_clue_tags(_make_event(), _make_package(records), _config())
    names = [t["tag_name"] for t in tags]
    assert "站点级断数" in names
    assert "多仪器断数" not in names
    assert "单仪器断数" not in names


def test_detect_missing_multi_instrument():
    records = [
        {"timePoint": "2026-09-09 10:00:00", "SO2": 10.0, "NO2": None, "PM10": None, "PM2_5": 3.0, "O3": 5.0, "CO": 0.5},
    ]
    tags = detect_data_clue_tags(_make_event(), _make_package(records), _config(station_missing_factor_threshold=3))
    names = [t["tag_name"] for t in tags]
    assert "多仪器断数" in names
    assert "站点级断数" not in names


def test_detect_missing_single_instrument():
    records = [
        {"timePoint": "2026-09-09 10:00:00", "SO2": 10.0, "NO2": 20.0, "PM10": 30.0, "PM2_5": 15.0, "O3": 5.0, "CO": None},
    ]
    tags = detect_data_clue_tags(_make_event(), _make_package(records), _config())
    names = [t["tag_name"] for t in tags]
    assert "单仪器断数" in names
    assert "站点级断数" not in names
    assert "多仪器断数" not in names


def test_detect_exceed_tag():
    records = [
        {"timePoint": "2026-09-09 10:00:00", "SO2": 200.0, "NO2": 10.0, "PM10": 10.0, "PM2_5": 5.0, "O3": 5.0, "CO": 0.5},
        {"timePoint": "2026-09-09 11:00:00", "SO2": 50.0, "NO2": 10.0, "PM10": 10.0, "PM2_5": 5.0, "O3": 5.0, "CO": 0.5},
    ]
    tags = detect_data_clue_tags(_make_event(), _make_package(records), _config())
    exceed = [t for t in tags if t["tag_name"] == "浓度超限" and t["tag_object"] == "SO2"]
    assert len(exceed) == 1
    assert "200" in exceed[0]["tag_display_text"]


def test_detect_negative_value():
    records = [
        {"timePoint": "2026-09-09 10:00:00", "SO2": -5.0, "NO2": 10.0, "PM10": 10.0, "PM2_5": 5.0, "O3": 5.0, "CO": 0.5},
    ]
    tags = detect_data_clue_tags(_make_event(), _make_package(records), _config())
    neg = [t for t in tags if t["tag_name"] == "负值或无效值"]
    assert len(neg) == 1


def test_detect_flatline_anomaly():
    records = [
        {"timePoint": f"2026-09-09 {h:02d}:00:00", "SO2": 42.0, "NO2": 10.0 + h, "PM10": 30.0 + h, "PM2_5": 15.0 + h, "O3": 5.0 + h, "CO": 0.5 + h * 0.1}
        for h in range(5)
    ]
    tags = detect_data_clue_tags(_make_event(), _make_package(records), _config())
    flat = [t for t in tags if t["tag_name"] == "恒值异常"]
    assert len(flat) == 1
    assert flat[0]["tag_object"] == "SO2"


def test_detect_spike_anomaly():
    records = [
        {"timePoint": "2026-09-09 08:00:00", "SO2": 10.0, "NO2": 10.0, "PM10": 10.0, "PM2_5": 5.0, "O3": 5.0, "CO": 0.5},
        {"timePoint": "2026-09-09 09:00:00", "SO2": 50.0, "NO2": 10.0, "PM10": 10.0, "PM2_5": 5.0, "O3": 5.0, "CO": 0.5},
    ]
    tags = detect_data_clue_tags(_make_event(), _make_package(records), _config())
    spike = [t for t in tags if t["tag_name"] == "数据突升"]
    assert len(spike) == 1
    assert spike[0]["tag_object"] == "SO2"


def test_detect_drop_anomaly():
    records = [
        {"timePoint": "2026-09-09 08:00:00", "SO2": 50.0, "NO2": 10.0, "PM10": 10.0, "PM2_5": 5.0, "O3": 5.0, "CO": 0.5},
        {"timePoint": "2026-09-09 09:00:00", "SO2": 10.0, "NO2": 10.0, "PM10": 10.0, "PM2_5": 5.0, "O3": 5.0, "CO": 0.5},
    ]
    tags = detect_data_clue_tags(_make_event(), _make_package(records), _config())
    drop = [t for t in tags if t["tag_name"] == "数据突降"]
    assert len(drop) == 1


def test_detect_outlier_from_regional_deltas():
    records = [
        {"timePoint": "2026-09-09 10:00:00", "SO2": 10.0, "NO2": 100.0, "PM10": 10.0, "PM2_5": 5.0, "O3": 5.0, "CO": 0.5},
    ]
    deltas = {
        "nearby_station_delta": {"NO2": 80.0},
        "nearby_station_delta_pct": {"NO2": 30.0},
        "city_rest_delta": {"NO2": 60.0},
        "city_rest_delta_pct": {"NO2": 25.0},
    }
    tags = detect_data_clue_tags(_make_event(), _make_package(records, deltas), _config())
    outlier = [t for t in tags if t["tag_name"] == "离群异常"]
    assert len(outlier) == 1
    assert outlier[0]["tag_object"] == "NO2"


def test_detect_no_records_returns_empty():
    tags = detect_data_clue_tags(_make_event(), _make_package([]), _config())
    assert tags == []


def test_detect_noisy_records_skipped():
    records = [
        {"timePoint": "2026-09-09 10:00:00", "SO2": 10.0, "NO2": 10.0, "PM10": 10.0, "PM2_5": 10.0, "O3": 10.0, "CO": None},
    ]
    tags = detect_data_clue_tags(_make_event(), _make_package(records), _config())
    names = [t["tag_name"] for t in tags]
    assert "站点级断数" not in names
    assert "多仪器断数" not in names
    single = [t for t in tags if t["tag_name"] == "单仪器断数"]
    assert len(single) == 1
    assert single[0]["tag_object"] == "CO"


# ---------------------------------------------------------------------------
# Phase 4: _attach_tags_to_bucket
# ---------------------------------------------------------------------------


def test_attach_tags_deduplicates_by_tag_id(tmp_path):
    tool = SameDayAlarmsTool()
    service = JiangsuSmartEventService(tool, data_root=tmp_path, evidence_fetcher=FakeEvidenceFetcher())
    store = service._load_store()
    bucket = {
        "event_id": "evt-1", "site_name": "示例站", "site_id": "A",
        "alarm_time": "2026-09-09T08:00:00+08:00",
        "event_start_time": "2026-09-09T08:00:00+08:00", "event_end_time": "2026-09-09T08:00:00+08:00",
        "clue_tags": [{"tag_id": "existing-1", "tag_name": "仪器报警", "tag_category": "告警"}],
        "primary_clue_tag": "仪器报警", "clue_count": 1,
        "event_status": "未研判", "created_at": "2026-09-09T08:00:00+08:00", "updated_at": "2026-09-09T08:00:00+08:00",
    }
    store["events"] = [bucket]
    service._save_store(store)

    tags = [
        {"tag_id": "existing-1", "tag_name": "仪器报警", "tag_category": "告警", "tag_source": "告警"},
        {"tag_id": "new-compliance", "tag_name": "维修记录", "tag_category": "合规", "tag_source": "合规记录",
         "tag_start_time": "2026-09-09 10:00:00", "tag_end_time": "2026-09-09 10:00:00",
         "tag_object": "分析仪更换", "tag_confidence": None, "clue_id": "new-compliance",
         "tag_display_text": "合规：维修记录"},
    ]
    added = service._attach_tags_to_bucket(store, bucket, tags)
    assert added == ["new-compliance"]
    assert len(bucket["clue_tags"]) == 2


def test_attach_tags_pending_delta_on_judged_bucket(tmp_path):
    tool = SameDayAlarmsTool()
    service = JiangsuSmartEventService(tool, data_root=tmp_path, evidence_fetcher=FakeEvidenceFetcher())
    store = service._load_store()
    bucket = {
        "event_id": "evt-2", "site_name": "B站", "site_id": "B",
        "alarm_time": "2026-09-09T08:00:00+08:00",
        "event_start_time": "2026-09-09T08:00:00+08:00", "event_end_time": "2026-09-09T08:00:00+08:00",
        "clue_tags": [{"tag_id": "t1", "tag_name": "仪器报警"}],
        "primary_clue_tag": "仪器报警", "clue_count": 1,
        "event_status": "AI 已研判", "created_at": "2026-09-09T08:00:00+08:00", "updated_at": "2026-09-09T08:00:00+08:00",
    }
    store["events"] = [bucket]
    service._save_store(store)

    tags = [{"tag_id": "det:site:comp:maint", "tag_name": "维修记录", "tag_category": "合规",
             "tag_source": "合规记录", "tag_display_text": "合规：维修记录"}]
    added = service._attach_tags_to_bucket(store, bucket, tags)
    assert added == ["det:site:comp:maint"]
    assert bucket["pending_delta"]["clue_ids"] == ["det:site:comp:maint"]
    assert len(store["tasks"]) == 1
    assert store["tasks"][0]["task_type"] == "ai_judgment"
    assert store["tasks"][0]["event_id"] == "evt-2"


def test_attach_tags_no_new_cards_when_active_card_exists(tmp_path):
    tool = SameDayAlarmsTool()
    service = JiangsuSmartEventService(tool, data_root=tmp_path, evidence_fetcher=FakeEvidenceFetcher())
    store = service._load_store()
    bucket = {
        "event_id": "evt-3", "site_name": "C站", "site_id": "C",
        "alarm_time": "2026-09-09T08:00:00+08:00",
        "event_start_time": "2026-09-09T08:00:00+08:00", "event_end_time": "2026-09-09T08:00:00+08:00",
        "clue_tags": [{"tag_id": "t1", "tag_name": "仪器报警"}],
        "primary_clue_tag": "仪器报警", "clue_count": 1,
        "event_status": "AI 已研判", "created_at": "2026-09-09T08:00:00+08:00", "updated_at": "2026-09-09T08:00:00+08:00",
    }
    store["events"] = [bucket]
    store["tasks"] = [{"event_id": "evt-3", "task_type": "ai_judgment", "status": "执行中"}]
    service._save_store(store)

    tags = [{"tag_id": "det:new", "tag_name": "维修记录", "tag_category": "合规",
             "tag_source": "合规记录", "tag_display_text": "合规：维修记录"}]
    added = service._attach_tags_to_bucket(store, bucket, tags)
    assert len(added) == 1
    task_count = len([t for t in store["tasks"] if t.get("event_id") == "evt-3"])
    assert task_count == 1  # the pre-existing active card, no new one


# ---------------------------------------------------------------------------
# Phase 4: sync_compliance_clues
# ---------------------------------------------------------------------------


class FakeWorkOrderTool:
    def __init__(self, rows=None):
        self.rows = rows or []

    async def execute(self, **kwargs):
        return {"success": True, "data": self.rows, "metadata": {}}


class FakeQcTool:
    def __init__(self, rows=None):
        self.rows = rows or []

    async def execute(self, **kwargs):
        return {"success": True, "data": self.rows, "metadata": {}}


class FakeDoorAdapter:
    def __init__(self, rows=None):
        self.rows = rows or []

    async def door_records(self, **kwargs):
        return {"success": True, "data": self.rows, "metadata": {}}


class FakeEvidenceFetcherWithTools:
    def __init__(self, work_orders=None, qc_rows=None, door_rows=None):
        self.work_order_tool = FakeWorkOrderTool(work_orders or [])
        self.qc_history_tool = FakeQcTool(qc_rows or [])
        self.legacy_adapter = FakeDoorAdapter(door_rows or [])

    async def fetch(self, event):
        return {"status": "success", "sources": {}, "gaps": []}


@pytest.mark.asyncio
async def test_sync_compliance_clues_attaches_to_matching_bucket(tmp_path):
    work_orders = [
        {"workingOrderCode": "WO-001", "orderType": "维修", "orderTitle": "分析仪维修", "stationCode": "A"},
    ]
    evidence = FakeEvidenceFetcherWithTools(work_orders=work_orders)
    service = JiangsuSmartEventService(SameDayAlarmsTool(), data_root=tmp_path, evidence_fetcher=evidence)
    bucket = {
        "event_id": "evt-comp", "site_name": "示例站", "site_id": "A",
        "alarm_time": "2026-09-09T08:00:00+08:00",
        "event_start_time": "2026-09-09T08:00:00+08:00", "event_end_time": "2026-09-09T08:00:00+08:00",
        "clue_tags": [], "primary_clue_tag": None, "clue_count": 0,
        "event_status": "未研判", "created_at": "2026-09-09T08:00:00+08:00", "updated_at": "2026-09-09T08:00:00+08:00",
    }
    store = service._load_store()
    store["events"] = [bucket]
    service._save_store(store)

    result = await service.sync_compliance_clues(date="2026-09-09")
    assert result["attached"] == 1
    assert result["stations"] == 1

    reloaded = service._load_store()
    reloaded_bucket = reloaded["events"][0]
    assert len(reloaded_bucket["clue_tags"]) == 1
    assert reloaded_bucket["clue_tags"][0]["tag_name"] == "维修记录"


@pytest.mark.asyncio
async def test_sync_compliance_clues_skips_missing_buckets(tmp_path):
    work_orders = [
        {"workingOrderCode": "WO-002", "orderType": "维修", "orderTitle": "维修", "stationCode": "Z"},
    ]
    evidence = FakeEvidenceFetcherWithTools(work_orders=work_orders)
    service = JiangsuSmartEventService(SameDayAlarmsTool(), data_root=tmp_path, evidence_fetcher=evidence)
    result = await service.sync_compliance_clues(date="2026-09-09")
    assert result["attached"] == 0
    assert result["stations"] == 0


@pytest.mark.asyncio
async def test_sync_compliance_clues_unmatched_orders_not_attached(tmp_path):
    work_orders = [
        {"workingOrderCode": "WO-003", "orderType": "其他", "orderTitle": "随机任务", "stationCode": "A"},
    ]
    evidence = FakeEvidenceFetcherWithTools(work_orders=work_orders)
    service = JiangsuSmartEventService(SameDayAlarmsTool(), data_root=tmp_path, evidence_fetcher=evidence)
    bucket = {
        "event_id": "evt-unk", "site_name": "示例站", "site_id": "A",
        "alarm_time": "2026-09-09T08:00:00+08:00",
        "event_start_time": "2026-09-09T08:00:00+08:00", "event_end_time": "2026-09-09T08:00:00+08:00",
        "clue_tags": [], "primary_clue_tag": None, "clue_count": 0,
        "event_status": "未研判", "created_at": "2026-09-09T08:00:00+08:00", "updated_at": "2026-09-09T08:00:00+08:00",
    }
    store = service._load_store()
    store["events"] = [bucket]
    service._save_store(store)

    result = await service.sync_compliance_clues(date="2026-09-09")
    assert result["attached"] == 0


# ---------------------------------------------------------------------------
# Phase 4: _compact_tags
# ---------------------------------------------------------------------------


def test_compact_tags_limits_fields_and_truncates():
    tags = [{"tag_id": "t1", "tag_name": "x" * 200, "tag_source": "告警", "tag_category": "告警",
             "tag_display_text": "x" * 300, "irrelevant_field": "should_be_excluded",
             "tag_object": "site", "tag_start_time": "2026-09-09 10:00:00",
             "tag_end_time": "2026-09-09 10:00:00", "tag_confidence": 0.9, "clue_id": "x"}]
    compact = _compact_tags(tags)
    assert len(compact) == 1
    item = compact[0]
    assert "irrelevant_field" not in item
    assert "tag_confidence" not in item
    assert len(item["tag_name"]) == 160
    assert len(item["tag_display_text"]) == 160


def test_compact_tags_empty_input():
    assert _compact_tags([]) == []
    assert _compact_tags(None) == []
    assert _compact_tags([None, 123]) == []


# ---------------------------------------------------------------------------
# Phase 4: fetcher integration — alarm sync calls compliance sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alarm_sync_fetcher_calls_compliance_sync(tmp_path, monkeypatch):
    from app.fetchers.jiangsu_smart_event_alarm_sync import JiangsuSmartEventAlarmSyncFetcher

    evidence = FakeEvidenceFetcherWithTools()
    service = JiangsuSmartEventService(SameDayAlarmsTool(), data_root=tmp_path, evidence_fetcher=evidence)
    fetcher = JiangsuSmartEventAlarmSyncFetcher(service=service)
    result = await fetcher.fetch_and_store()
    assert "compliance_sync" in result
    assert result["compliance_sync"]["status"] == "no_buckets"


# ---------------------------------------------------------------------------
# Phase 4: evidence detection integration — _collect_event_evidence calls detect
# ---------------------------------------------------------------------------


class EvidenceWithHourDataFetcher:
    def __init__(self, hour_data):
        self.hour_data = hour_data
        self.fetched = []

    async def fetch(self, event, **kwargs):
        self.fetched.append(event.get("event_id"))
        return {
            "status": "success",
            "sources": {
                "monitoring": {"data": {"station_hour": {"data": self.hour_data}}},
            },
            "gaps": [],
        }


@pytest.mark.asyncio
async def test_collect_event_evidence_attaches_detection_tags(tmp_path):
    hour_data = [
        {"timePoint": "2026-09-09 10:00:00", "SO2": -5.0, "NO2": 10.0, "PM10": 10.0, "PM2.5": 5.0, "O3": 5.0, "CO": 0.5},
    ]
    evidence = EvidenceWithHourDataFetcher(hour_data)
    tool = SameDayAlarmsTool()
    service = JiangsuSmartEventService(tool, data_root=tmp_path, evidence_fetcher=evidence)
    store = service._load_store()
    bucket = {
        "event_id": "evt-detect", "site_name": "示例站", "site_id": "A",
        "alarm_time": "2026-09-09T08:00:00+08:00",
        "event_start_time": "2026-09-09T08:00:00+08:00", "event_end_time": "2026-09-09T08:00:00+08:00",
        "clue_tags": [], "primary_clue_tag": None, "clue_count": 0,
        "event_status": "未研判", "created_at": "2026-09-09T08:00:00+08:00", "updated_at": "2026-09-09T08:00:00+08:00",
    }
    store["events"] = [bucket]
    service._save_store(store)

    result = await service.collect_event_evidence("evt-detect")
    assert result["collected"] == 1

    reloaded = service._load_store()
    reloaded_bucket = reloaded["events"][0]
    tag_names = [t["tag_name"] for t in reloaded_bucket["clue_tags"]]
    assert "负值或无效值" in tag_names
    assert reloaded_bucket.get("evidence_fingerprint") is not None
