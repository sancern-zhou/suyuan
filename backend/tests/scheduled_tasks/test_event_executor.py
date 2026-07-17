import json
import asyncio

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

    execution = await executor.execute_task(task, event=event)

    assert execution.trigger_type == "event"
    assert execution.event_id == "alert-1"
    assert "alert-1" in agent.prompts[0]
    assert "yuncheng.alert.created" in agent.prompts[0]
    assert "/tmp/evidence" in agent.prompts[0]
    assert "不要直接发送通知" in agent.prompts[0]
