import json
import asyncio
from types import SimpleNamespace

import pytest

from app.scheduled_tasks.event_output import parse_event_task_output
from app.scheduled_tasks.executor import ScheduledTaskExecutor
from app.scheduled_tasks.models import ScheduledTask, TaskEvent, TaskExecution, TaskStep
from app.scheduled_tasks.storage import ExecutionStorage, TaskStorage


def test_parser_accepts_fenced_broadcast_json(tmp_path):
    report = tmp_path / "report.docx"
    report.write_bytes(b"docx")

    payload = {
        "success": True,
        "broadcast": {"message": "告警摘要", "media": [str(report)]},
    }
    output = parse_event_task_output(f"```json\n{json.dumps(payload)}\n```")

    assert output.success is True
    assert output.broadcast.message == "告警摘要"
    assert output.broadcast.media == [str(report)]


def test_parser_accepts_single_json_fence_with_brief_model_preamble(tmp_path):
    report = tmp_path / "report.docx"
    report.write_bytes(b"docx")
    payload = {
        "success": True,
        "broadcast": {"message": "告警摘要", "media": [str(report)]},
    }

    output = parse_event_task_output(
        "报告验收通过，现在返回结果。\n\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"
    )

    assert output.success is True
    assert output.broadcast.media == [str(report)]


@pytest.mark.parametrize("text", [
    '```json\n{"success":false,"error":"失败"}\n```\n尾随说明',
    f'{"前言" * 101}\n```json\n{{"success":false,"error":"失败"}}\n```',
    '```text\n其他内容\n```\n```json\n{"success":false,"error":"失败"}\n```',
])
def test_parser_rejects_ambiguous_content_around_json_fence(text):
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_event_task_output(text)


def test_parser_rejects_missing_attachment(tmp_path):
    missing = tmp_path / "missing.docx"

    with pytest.raises(ValueError, match="attachment does not exist"):
        parse_event_task_output(json.dumps({
            "success": True,
            "broadcast": {"message": "告警摘要", "media": [str(missing)]},
        }))


class FakeAgent:
    def __init__(self, report_path):
        self.report_path = report_path
        self.prompts = []

    async def analyze(self, prompt, **kwargs):
        self.prompts.append(prompt)
        payload = {
            "success": True,
            "broadcast": {
                "message": "告警摘要",
                "media": [str(self.report_path)],
            },
        }
        yield {
            "type": "final_response",
            "content": json.dumps(payload, ensure_ascii=False),
        }


class CurrentRuntimeAgent:
    async def analyze(self, prompt, **kwargs):
        payload = json.dumps({
            "success": True,
            "broadcast": {"message": "告警摘要", "media": []},
        }, ensure_ascii=False)
        yield {"type": "agent_finish", "answer": payload, "data": {}}
        yield {
            "type": "complete",
            "data": {"answer": payload, "response": payload},
        }


class RecordingAgent:
    def __init__(self):
        self.analyze_kwargs = None

    async def analyze(self, prompt, **kwargs):
        self.analyze_kwargs = kwargs
        yield {"type": "complete", "data": {"answer": "完成"}}


class RecordingConversationPersistence:
    def __init__(self):
        self.calls = []

    async def persist_agent_session(self, **kwargs):
        self.calls.append(kwargs)
        return True

    async def publish_conversation(self, **kwargs):
        self.calls.append({"published": kwargs})
        return True

    async def ensure_terminal_session(self, **kwargs):
        self.calls.append({"ensured": kwargs})
        return True


class SlowAgent:
    async def analyze(self, prompt, **kwargs):
        await asyncio.sleep(2)
        yield {"type": "complete", "data": {"answer": "too late"}}


@pytest.mark.asyncio
async def test_executor_uses_web_storage_and_persists_completed_runtime(tmp_path):
    agent = RecordingAgent()
    persistence = RecordingConversationPersistence()
    task = ScheduledTask(
        task_id="task-1",
        name="任务",
        description="任务描述",
        execution_mode="social",
        schedule_type="once",
        run_at="2026-07-17T12:00:00",
        steps=[TaskStep(step_id="step-1", description="执行", agent_prompt="执行")],
    )
    execution = TaskExecution(
        execution_id="exec-1",
        task_id=task.task_id,
        task_name=task.name,
        session_id="scheduled-session",
        status="running",
        total_steps=1,
    )
    executor = ScheduledTaskExecutor(
        task_storage=TaskStorage(storage_dir=tmp_path),
        execution_storage=ExecutionStorage(storage_dir=tmp_path),
        agent_factory=lambda: agent,
        conversation_persistence=persistence,
    )

    await executor._run_agent_step(
        "执行",
        execution.session_id,
        manual_mode="social",
        task=task,
        execution=execution,
    )

    assert agent.analyze_kwargs["manual_mode"] == "social"
    assert agent.analyze_kwargs["session_storage_mode"] == "assistant"
    assert len(persistence.calls) == 1
    assert persistence.calls[0]["agent"] is agent
    assert persistence.calls[0]["task"] is task
    assert persistence.calls[0]["execution"] is execution
    assert [message["type"] for message in persistence.calls[0]["display_history"]] == [
        "user", "final"
    ]


@pytest.mark.asyncio
async def test_executor_injects_task_skill_context(monkeypatch, tmp_path):
    agent = RecordingAgent()
    task = ScheduledTask(
        task_id="task-with-skill",
        name="技能任务",
        description="技能任务",
        execution_mode="expert",
        skill_id="sample-skill",
        schedule_type="once",
        run_at="2026-07-17T12:00:00",
        steps=[TaskStep(step_id="step", description="执行", agent_prompt="执行")],
    )
    execution = TaskExecution(
        execution_id="exec-with-skill",
        task_id=task.task_id,
        task_name=task.name,
        session_id="scheduled-with-skill",
        status="running",
        total_steps=1,
    )
    monkeypatch.setattr(
        "app.agent.selection_context.load_skill_selection",
        lambda *args, **kwargs: SimpleNamespace(content="skill-context-marker"),
    )
    executor = ScheduledTaskExecutor(
        task_storage=TaskStorage(storage_dir=tmp_path),
        execution_storage=ExecutionStorage(storage_dir=tmp_path),
        agent_factory=lambda: agent,
    )

    await executor._run_agent_step(
        "执行",
        execution.session_id,
        manual_mode=task.execution_mode,
        task=task,
        execution=execution,
    )

    assert agent.analyze_kwargs["selected_skill_context"] == "skill-context-marker"


@pytest.mark.asyncio
async def test_custom_task_injects_skill_without_tool_compatibility_check(monkeypatch, tmp_path):
    agent = RecordingAgent()
    task = ScheduledTask(
        task_id="custom-task-with-skill",
        name="自定义技能任务",
        description="自定义技能任务",
        execution_mode="custom",
        tool_names=["read_file"],
        skill_id="sample-skill",
        schedule_type="once",
        run_at="2026-07-17T12:00:00",
        steps=[TaskStep(step_id="step", description="执行", agent_prompt="执行")],
    )
    execution = TaskExecution(
        execution_id="custom-exec-with-skill",
        task_id=task.task_id,
        task_name=task.name,
        session_id="scheduled-custom-with-skill",
        status="running",
        total_steps=1,
    )
    monkeypatch.setattr(
        "app.agent.selection_context.load_skill_selection",
        lambda skill_id: SimpleNamespace(content=f"skill-context:{skill_id}"),
    )
    executor = ScheduledTaskExecutor(
        task_storage=TaskStorage(storage_dir=tmp_path),
        execution_storage=ExecutionStorage(storage_dir=tmp_path),
        agent_factory=lambda: agent,
    )

    await executor._run_agent_step(
        "执行",
        execution.session_id,
        manual_mode=task.execution_mode,
        task=task,
        execution=execution,
    )

    assert agent.analyze_kwargs["manual_mode"] == "custom"
    assert agent.analyze_kwargs["selected_skill_context"] == (
        "skill-context:sample-skill"
    )


@pytest.mark.asyncio
async def test_timeout_still_persists_partial_runtime_before_returning(tmp_path):
    persistence = RecordingConversationPersistence()
    task = ScheduledTask(
        task_id="task-timeout",
        name="超时任务",
        description="超时任务",
        execution_mode="assistant",
        schedule_type="once",
        run_at="2026-07-17T12:00:00",
        steps=[TaskStep(
            step_id="slow",
            description="慢步骤",
            agent_prompt="执行",
            timeout_seconds=1,
        )],
    )
    execution = TaskExecution(
        execution_id="exec-timeout",
        task_id=task.task_id,
        task_name=task.name,
        session_id="scheduled-timeout",
        status="running",
        total_steps=1,
    )
    executor = ScheduledTaskExecutor(
        task_storage=TaskStorage(storage_dir=tmp_path),
        execution_storage=ExecutionStorage(storage_dir=tmp_path),
        agent_factory=SlowAgent,
        conversation_persistence=persistence,
    )

    result = await executor._execute_step(
        task.steps[0],
        execution,
        execution.session_id,
        task.execution_mode,
        task=task,
        prompt="执行",
    )

    assert result.status.value == "timeout"
    assert len(persistence.calls) == 1
    assert persistence.calls[0]["execution"] is execution
    assert persistence.calls[0]["display_history"][-1]["type"] == "error"


@pytest.mark.asyncio
async def test_execution_is_published_only_after_all_steps_finish(tmp_path):
    persistence = RecordingConversationPersistence()
    task_storage = TaskStorage(storage_dir=tmp_path)
    task = ScheduledTask(
        task_id="task-publish",
        name="发布任务",
        description="发布任务",
        execution_mode="social",
        schedule_type="once",
        run_at="2026-07-17T12:00:00",
        steps=[TaskStep(step_id="step", description="执行", agent_prompt="执行")],
    )
    task_storage.create(task)
    executor = ScheduledTaskExecutor(
        task_storage=task_storage,
        execution_storage=ExecutionStorage(storage_dir=tmp_path),
        agent_factory=RecordingAgent,
        conversation_persistence=persistence,
    )

    execution = await executor.execute_task(task)

    assert execution.status.value == "success"
    assert len(persistence.calls) == 2
    assert "display_history" in persistence.calls[0]
    assert persistence.calls[1]["published"]["execution"] is execution


@pytest.mark.asyncio
async def test_executor_collects_current_runtime_complete_response(tmp_path):
    executor = ScheduledTaskExecutor(
        task_storage=TaskStorage(storage_dir=tmp_path),
        execution_storage=ExecutionStorage(storage_dir=tmp_path),
        agent_factory=CurrentRuntimeAgent,
    )

    result = await executor._run_agent_step(
        "处理告警",
        "scheduled-task-session",
        manual_mode="assistant",
    )

    output = parse_event_task_output(result["summary"])
    assert output.success is True
    assert output.broadcast.message == "告警摘要"


@pytest.mark.asyncio
async def test_executor_appends_event_context_to_agent_prompt(tmp_path):
    report = tmp_path / "report.docx"
    report.write_bytes(b"docx")
    agent = FakeAgent(report)
    task_storage = TaskStorage(storage_dir=tmp_path)
    execution_storage = ExecutionStorage(storage_dir=tmp_path)
    task = ScheduledTask(
        task_id="event-task",
        name="event task",
        description="event task",
        execution_mode="social",
        trigger_type="event",
        event_type="yuncheng.alert.created",
        broadcast_enabled=True,
        target_user_ids=["admin-1"],
        steps=[TaskStep(step_id="report", description="report", agent_prompt="处理告警")],
    )
    task_storage.create(task)
    executor = ScheduledTaskExecutor(
        task_storage=task_storage,
        execution_storage=execution_storage,
        agent_factory=lambda: agent,
        conversation_persistence=RecordingConversationPersistence(),
    )
    event = TaskEvent(
        event_id="alert-1",
        event_type="yuncheng.alert.created",
        attributes={"city": "运城市"},
        payload={"evidence_dir": "/tmp/evidence"},
    )

    execution = await executor.execute_task(
        task,
        event=event,
        broadcast_user_names=["运城值班员"],
    )

    assert execution.trigger_type == "event"
    assert execution.event_id == "alert-1"
    assert "alert-1" in agent.prompts[0]
    assert "yuncheng.alert.created" in agent.prompts[0]
    assert "/tmp/evidence" in agent.prompts[0]
    assert "broadcast_social_users" in agent.prompts[0]
    assert "运城值班员" in agent.prompts[0]
    assert "不需要返回 JSON" in agent.prompts[0]


@pytest.mark.asyncio
async def test_executor_compacts_oversized_event_payload_in_agent_prompt(tmp_path):
    report = tmp_path / "report.docx"
    report.write_bytes(b"docx")
    agent = FakeAgent(report)
    task_storage = TaskStorage(storage_dir=tmp_path)
    execution_storage = ExecutionStorage(storage_dir=tmp_path)
    task = ScheduledTask(
        task_id="event-task-oversized",
        name="event task",
        description="event task",
        execution_mode="report",
        trigger_type="event",
        event_type="xuchang.station_daily_pollution.review_completed",
        broadcast_enabled=False,
        steps=[TaskStep(step_id="report", description="report", agent_prompt="生成回顾报告")],
    )
    task_storage.create(task)
    executor = ScheduledTaskExecutor(
        task_storage=task_storage,
        execution_storage=execution_storage,
        agent_factory=lambda: agent,
        conversation_persistence=RecordingConversationPersistence(),
    )
    event = TaskEvent(
        event_id="xuchang-station-daily-review-20260829",
        event_type="xuchang.station_daily_pollution.review_completed",
        attributes={"city": "许昌市", "target_date": "2026-08-29"},
        payload={
            "city": "许昌市",
            "target_date": "2026-08-29",
            "event_count": 7,
            "events": [
                {"station_hourly": [f"row-{index}" for index in range(500)]}
                for _ in range(7)
            ],
            "evidence_package_path": (
                "backend/backend_data_registry/xuchang_station_daily_reviews/20260829.json"
            ),
        },
    )

    await executor.execute_task(task, event=event)

    prompt = agent.prompts[0]
    assert "## 可信事件上下文" in prompt
    assert "event_count" in prompt
    assert "evidence_package_path" in prompt
    assert "row-499" not in prompt
    assert "payload 过大" in prompt
    assert len(prompt) < 20000


@pytest.mark.asyncio
async def test_custom_broadcast_task_adds_broadcast_tool_at_runtime(tmp_path, monkeypatch):
    requested_tools = []

    monkeypatch.setattr(
        "app.scheduled_tasks.executor.task_executor.build_runtime_custom_tool_registry",
        lambda names: requested_tools.extend(names) or {name: name for name in names},
    )
    task = ScheduledTask(
        task_id="custom-broadcast",
        name="custom broadcast",
        description="custom broadcast",
        execution_mode="custom",
        tool_names=["execute_python"],
        schedule_type="once",
        run_at="2026-07-20T12:00:00",
        broadcast_enabled=True,
        target_user_ids=["admin-1"],
        steps=[TaskStep(step_id="report", description="report", agent_prompt="生成日报")],
    )
    executor = ScheduledTaskExecutor(
        task_storage=TaskStorage(storage_dir=tmp_path),
        execution_storage=ExecutionStorage(storage_dir=tmp_path),
        agent_factory=lambda **kwargs: RecordingAgent(),
        conversation_persistence=RecordingConversationPersistence(),
    )

    execution = await executor.execute_task(
        task,
        update_stats=False,
        broadcast_user_names=["日报接收人"],
    )

    assert execution.status.value == "success"
    assert requested_tools == ["execute_python", "broadcast_social_users"]


@pytest.mark.asyncio
async def test_custom_task_invalid_runtime_tools_fail_before_agent_request(tmp_path, monkeypatch):
    factory_calls = []
    monkeypatch.setattr(
        "app.scheduled_tasks.executor.task_executor.build_runtime_custom_tool_registry",
        lambda names: (_ for _ in ()).throw(ValueError("tool disabled")),
    )
    task = ScheduledTask(
        task_id="custom-invalid-runtime",
        name="失效工具任务",
        description="启动前失败",
        execution_mode="custom",
        tool_names=["alpha"],
        schedule_type="once",
        run_at="2026-07-20T12:00:00",
        steps=[TaskStep(step_id="one", description="一", agent_prompt="执行")],
    )
    executor = ScheduledTaskExecutor(
        task_storage=TaskStorage(storage_dir=tmp_path),
        execution_storage=ExecutionStorage(storage_dir=tmp_path),
        agent_factory=lambda **kwargs: factory_calls.append(kwargs),
        conversation_persistence=RecordingConversationPersistence(),
    )

    result = await executor.execute_task(task, update_stats=False)

    assert result.status.value == "failed"
    assert result.error_message == "tool disabled"
    assert factory_calls == []
