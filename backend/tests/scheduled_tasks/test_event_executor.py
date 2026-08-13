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
async def test_executor_appends_broadcast_tool_instruction_to_scheduled_task_prompt(tmp_path):
    report = tmp_path / "report.xlsx"
    report.write_bytes(b"xlsx")
    agent = FakeAgent(report)
    task = ScheduledTask(
        task_id="scheduled-broadcast-task",
        name="scheduled broadcast task",
        description="scheduled broadcast task",
        execution_mode="social",
        schedule_type="once",
        run_at="2026-07-20T12:00:00",
        broadcast_enabled=True,
        target_user_ids=["admin-1"],
        steps=[TaskStep(step_id="report", description="report", agent_prompt="生成日报")],
    )
    executor = ScheduledTaskExecutor(
        task_storage=TaskStorage(storage_dir=tmp_path),
        execution_storage=ExecutionStorage(storage_dir=tmp_path),
        agent_factory=lambda: agent,
        conversation_persistence=RecordingConversationPersistence(),
    )

    execution = await executor.execute_task(
        task,
        update_stats=False,
        broadcast_user_names=["日报接收人"],
    )

    assert execution.status.value == "success"
    assert agent.prompts[0].startswith("生成日报\n\n## 输出与投递约束")
    assert "broadcast_social_users" in agent.prompts[0]
    assert "日报接收人" in agent.prompts[0]
    assert "不需要返回 JSON" in agent.prompts[0]
    assert "## 可信事件上下文" not in agent.prompts[0]


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
async def test_custom_task_reuses_one_agent_with_one_fixed_tool_registry(tmp_path, monkeypatch):
    created_agents = []
    factory_kwargs = []

    class MultiStepAgent:
        def __init__(self):
            self.prompts = []

        async def analyze(self, prompt, **kwargs):
            self.prompts.append((prompt, kwargs))
            yield {"type": "complete", "data": {"answer": f"完成: {prompt}"}}

    def factory(**kwargs):
        factory_kwargs.append(kwargs)
        agent = MultiStepAgent()
        created_agents.append(agent)
        return agent

    monkeypatch.setattr(
        "app.scheduled_tasks.executor.task_executor.build_runtime_custom_tool_registry",
        lambda names: {"beta": "B", "alpha": "A"},
    )
    task = ScheduledTask(
        task_id="custom-multi-step",
        name="自定义多步骤任务",
        description="共享 Agent",
        execution_mode="custom",
        tool_names=["beta", "alpha"],
        schedule_type="once",
        run_at="2026-07-20T12:00:00",
        steps=[
            TaskStep(step_id="one", description="一", agent_prompt="第一步"),
            TaskStep(step_id="two", description="二", agent_prompt="第二步"),
        ],
    )
    executor = ScheduledTaskExecutor(
        task_storage=TaskStorage(storage_dir=tmp_path),
        execution_storage=ExecutionStorage(storage_dir=tmp_path),
        agent_factory=factory,
        conversation_persistence=RecordingConversationPersistence(),
    )

    result = await executor.execute_task(task, update_stats=False)

    assert result.status.value == "success"
    assert len(created_agents) == 1
    assert list(factory_kwargs[0]["tool_registry"]) == ["beta", "alpha"]
    assert factory_kwargs[0]["enable_memory"] is False
    assert [prompt for prompt, _ in created_agents[0].prompts] == ["第一步", "第二步"]
    assert all(kwargs["manual_mode"] == "custom" for _, kwargs in created_agents[0].prompts)
    assert all(kwargs["session_storage_mode"] == "custom" for _, kwargs in created_agents[0].prompts)


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


@pytest.mark.asyncio
async def test_custom_fatal_error_stops_following_steps_even_when_retry_enabled(tmp_path, monkeypatch):
    prompts = []

    class FatalAgent:
        async def analyze(self, prompt, **kwargs):
            prompts.append(prompt)
            yield {"type": "fatal_error", "data": {"error": "iteration limit reached"}}

    monkeypatch.setattr(
        "app.scheduled_tasks.executor.task_executor.build_runtime_custom_tool_registry",
        lambda names: {"alpha": "A"},
    )
    task = ScheduledTask(
        task_id="custom-fatal",
        name="终态失败",
        description="不能继续后续步骤",
        execution_mode="custom",
        tool_names=["alpha"],
        schedule_type="once",
        run_at="2026-07-20T12:00:00",
        steps=[
            TaskStep(
                step_id="one",
                description="失败",
                agent_prompt="第一步",
                retry_on_failure=True,
            ),
            TaskStep(step_id="two", description="不应执行", agent_prompt="第二步"),
        ],
    )
    executor = ScheduledTaskExecutor(
        task_storage=TaskStorage(storage_dir=tmp_path),
        execution_storage=ExecutionStorage(storage_dir=tmp_path),
        agent_factory=lambda **kwargs: FatalAgent(),
        conversation_persistence=RecordingConversationPersistence(),
    )

    result = await executor.execute_task(task, update_stats=False)

    assert result.status.value == "failed"
    assert prompts == ["第一步"]
    assert "iteration limit reached" in result.error_message
