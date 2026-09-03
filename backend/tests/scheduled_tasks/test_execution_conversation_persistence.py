import pytest
from types import SimpleNamespace

from app.agent.session.models import Session
from app.conversations.schemas import ConversationSource
from app.scheduled_tasks.conversation_persistence import (
    ScheduledTaskConversationPersistence,
)
from app.scheduled_tasks.models import ScheduledTask, TaskExecution


class FakeSessionManager:
    def __init__(self):
        self.saved = []
        self.deleted = []
        self.existing = None

    async def load_session(self, session_id):
        return self.existing

    async def save_session(self, session, **kwargs):
        self.saved.append(session)
        self.existing = session.model_copy(deep=True)
        return True

    async def delete_session(self, session_id):
        self.deleted.append(session_id)
        return True


class FakeCatalog:
    def __init__(self):
        self.registrations = []

    async def register_identity(self, **kwargs):
        self.registrations.append(kwargs)
        return kwargs

    async def find(self, session_id):
        return None


class FakeAgent:
    def __init__(self):
        self.exports = []

    def export_runtime_session(self, session_id, *, query, mode):
        self.exports.append((session_id, query, mode))
        return Session(
            session_id=session_id,
            query=query,
            conversation_history=[
                {"type": "user", "role": "user", "content": "LLM运行时消息"},
            ],
            metadata={"mode": mode},
        )


def task():
    return ScheduledTask(
        task_id="task-1",
        name="告警分析",
        description="分析告警并生成报告",
        execution_mode="social",
        schedule_type="once",
        run_at="2026-07-17T12:00:00",
        owner_user_id="owner-1",
        owner_username="alice",
        owner_display_name="Alice",
        prompt="执行",
    )


@pytest.mark.asyncio
async def test_persists_runtime_transcript_as_owned_web_conversation():
    manager = FakeSessionManager()
    catalog = FakeCatalog()
    persistence = ScheduledTaskConversationPersistence(
        session_manager=manager,
        catalog=catalog,
    )
    agent = FakeAgent()
    execution = TaskExecution(
        execution_id="exec-1",
        task_id="task-1",
        task_name="告警分析",
        session_id="scheduled-session-1",
        status="running",
        total_steps=1,
    )

    saved = await persistence.persist_agent_session(
        agent=agent,
        task=task(),
        execution=execution,
        display_history=[
            {"type": "user", "content": "执行任务"},
            {"type": "tool_use", "content": "调用工具", "data": {}},
            {"type": "tool_result", "content": "工具结果", "data": {}},
            {"type": "final", "content": "执行完成"},
        ],
    )
    published = await persistence.publish_conversation(
        task=task(),
        execution=execution,
    )

    assert saved is True
    assert published is True
    assert agent.exports == [
        ("scheduled-session-1", "分析告警并生成报告", "social")
    ]
    assert [message["type"] for message in manager.saved[0].conversation_history] == [
        "user", "tool_use", "tool_result", "final"
    ]
    assert manager.saved[0].metadata["scheduled_task_id"] == "task-1"
    assert manager.saved[0].metadata["scheduled_execution_id"] == "exec-1"
    assert catalog.registrations == [{
        "session_id": "scheduled-session-1",
        "owner_user_id": "owner-1",
        "owner_username": "alice",
        "owner_display_name": "Alice",
        "source": ConversationSource.WEB,
        "mode": "social",
        "title": "告警分析",
        "read_only_on_web": False,
    }]


@pytest.mark.asyncio
async def test_publication_failure_keeps_verified_session_for_reconciliation():
    class FailingCatalog(FakeCatalog):
        async def register_identity(self, **kwargs):
            raise RuntimeError("catalog failed")

    manager = FakeSessionManager()
    persistence = ScheduledTaskConversationPersistence(
        session_manager=manager,
        catalog=FailingCatalog(),
    )
    execution = TaskExecution(
        execution_id="exec-1",
        task_id="task-1",
        task_name="告警分析",
        session_id="scheduled-session-1",
        status="running",
        total_steps=1,
    )

    await persistence.persist_agent_session(
        agent=FakeAgent(),
        task=task(),
        execution=execution,
        display_history=[],
    )

    with pytest.raises(RuntimeError, match="catalog failed"):
        await persistence.publish_conversation(task=task(), execution=execution)

    assert manager.deleted == []


@pytest.mark.asyncio
async def test_appends_each_step_to_the_existing_display_transcript():
    manager = FakeSessionManager()
    manager.existing = Session(
        session_id="scheduled-session-1",
        query="分析告警并生成报告",
        conversation_history=[
            {"type": "user", "content": "第一步"},
            {"type": "final", "content": "第一步完成"},
        ],
    )
    persistence = ScheduledTaskConversationPersistence(
        session_manager=manager,
        catalog=FakeCatalog(),
    )
    execution = TaskExecution(
        execution_id="exec-1",
        task_id="task-1",
        task_name="告警分析",
        session_id="scheduled-session-1",
        status="running",
        total_steps=2,
    )

    await persistence.persist_agent_session(
        agent=FakeAgent(),
        task=task(),
        execution=execution,
        display_history=[
            {"type": "user", "content": "第二步"},
            {"type": "tool_use", "content": "调用工具", "data": {}},
            {"type": "final", "content": "第二步完成"},
        ],
    )

    assert [message["content"] for message in manager.saved[0].conversation_history] == [
        "第一步", "第一步完成", "第二步", "调用工具", "第二步完成"
    ]


def test_legacy_tasks_default_to_system_ownership_for_future_executions():
    legacy = ScheduledTask(
        task_id="legacy",
        name="旧任务",
        description="旧任务",
        schedule_type="once",
        run_at="2026-07-17T12:00:00",
        prompt="执行",
    )

    assert legacy.owner_user_id == "system"
    assert legacy.owner_username == "scheduled-task"
    assert legacy.owner_display_name == "定时任务"


@pytest.mark.asyncio
async def test_ambiguous_catalog_error_accepts_the_committed_matching_record():
    class CommittedThenFailedCatalog(FakeCatalog):
        async def register_identity(self, **kwargs):
            raise RuntimeError("connection lost after commit")

        async def find(self, session_id):
            return SimpleNamespace(
                session_id=session_id,
                owner_user_id="owner-1",
                source=ConversationSource.WEB,
            )

    manager = FakeSessionManager()
    persistence = ScheduledTaskConversationPersistence(
        session_manager=manager,
        catalog=CommittedThenFailedCatalog(),
    )
    execution = TaskExecution(
        execution_id="exec-1",
        task_id="task-1",
        task_name="告警分析",
        session_id="scheduled-session-1",
        status="success",
        total_steps=1,
    )
    await persistence.persist_agent_session(
        agent=FakeAgent(), task=task(), execution=execution, display_history=[]
    )

    assert await persistence.publish_conversation(task=task(), execution=execution)


@pytest.mark.asyncio
async def test_rejects_a_session_when_saved_transcript_cannot_be_read_back():
    class CorruptingManager(FakeSessionManager):
        async def save_session(self, session, **kwargs):
            self.existing = session.model_copy(deep=True)
            self.existing.conversation_history = []
            return True

    persistence = ScheduledTaskConversationPersistence(
        session_manager=CorruptingManager(),
        catalog=FakeCatalog(),
    )
    execution = TaskExecution(
        execution_id="exec-1",
        task_id="task-1",
        task_name="告警分析",
        session_id="scheduled-session-1",
        status="running",
        total_steps=1,
    )

    with pytest.raises(RuntimeError, match="transcript_verification_failed"):
        await persistence.persist_agent_session(
            agent=FakeAgent(),
            task=task(),
            execution=execution,
            display_history=[{"type": "user", "content": "执行"}],
        )


@pytest.mark.asyncio
async def test_creates_terminal_fallback_when_runtime_export_never_started():
    manager = FakeSessionManager()
    catalog = FakeCatalog()
    persistence = ScheduledTaskConversationPersistence(
        session_manager=manager,
        catalog=catalog,
    )
    execution = TaskExecution(
        execution_id="exec-startup-failed",
        task_id="task-1",
        task_name="告警分析",
        session_id="scheduled-startup-failed",
        status="failed",
        total_steps=1,
        error_message="Agent initialization failed",
    )

    assert await persistence.ensure_terminal_session(task=task(), execution=execution)
    assert [message["type"] for message in manager.existing.conversation_history] == [
        "user", "error"
    ]
    assert await persistence.publish_conversation(task=task(), execution=execution)
