"""Result-to-reply integration with real SQLite transactions and fake transports."""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.conversations import ConversationSource
from app.db.models_session import SessionDB, SessionMessageDB
from app.db.models.scheduled_task_execution_db import ScheduledTaskExecutionDB
from app.db.models.scheduled_task_result_db import ScheduledTaskResultDB
from app.scheduled_tasks.models import ExecutionStatus, ScheduledTask, StepExecution, TaskExecution
from app.social.assistant_notification_models import AssistantNotificationDB as Notice
from app.social.assistant_notifications import AssistantNotificationService
from app.social.assistant_request import AssistantRequest
from app.social.assistant_task_models import AssistantTaskDB, AssistantTaskEventDB
from app.social.assistant_tasks import AssistantTaskService, TaskNotFound
from app.social.web_assistant import web_assistant_recipient


@pytest_asyncio.fixture
async def system(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'replies.db').as_posix()}")
    async with engine.begin() as conn:
        for model in (
            SessionDB,
            SessionMessageDB,
            Notice,
            AssistantTaskDB,
            AssistantTaskEventDB,
            ScheduledTaskExecutionDB,
            ScheduledTaskResultDB,
        ):
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(SessionDB(session_id="source", query="Please run this later", mode="assistant"))
        await session.commit()
    source = SimpleNamespace(owner_user_id="alice", source=ConversationSource.WEB)
    catalog = SimpleNamespace(find=AsyncMock(return_value=source))
    transport = AsyncMock(return_value="provider_accepted")
    service = AssistantNotificationService(factory, catalog, transport)
    task = ScheduledTask(
        task_id="job",
        name="Review",
        description="Review notes",
        prompt="Review notes",
        execution_mode="office",
        schedule_type="interval",
        interval_minutes=30,
        owner_user_id="alice",
        source_session_id="source",
        assistant_recipient=web_assistant_recipient("alice"),
        tags=["assistant-plan", "project:p"],
    )
    execution = TaskExecution(
        execution_id="exec1",
        task_id="job",
        task_name="Review",
        session_id="result-session",
        status=ExecutionStatus.SUCCESS,
        total_steps=1,
        steps=[
            StepExecution(
                step_id="task",
                status=ExecutionStatus.SUCCESS,
                agent_prompt="Review",
                agent_response="Findings ready",
            )
        ],
    )
    yield SimpleNamespace(
        engine=engine,
        service=service,
        factory=factory,
        task=task,
        execution=execution,
        source=source,
        transport=transport,
    )
    await engine.dispose()


async def messages(system):
    async with system.factory() as session:
        return (
            (await session.execute(select(SessionMessageDB).order_by(SessionMessageDB.id)))
            .scalars()
            .all()
        )


@pytest.mark.asyncio
async def test_execution_reply_is_durable_idempotent_and_in_original_conversation(system):
    for _ in range(2):
        key = await system.service.enqueue_execution("p", system.task, system.execution)
        assert await system.service.deliver(key) == "inbox_saved"
    rows = await messages(system)
    assert len(rows) == 1
    assert rows[0].session_id == "source" and rows[0].msg_type == "final"
    assert "Findings ready" in rows[0].content
    inbox = await system.service.list("p", "alice")
    assert inbox["unread_count"] == 1
    assert inbox["notifications"][0]["transcript_message_id"] == f"msg_{rows[0].id}"
    assert inbox["notifications"][0]["execution_session_id"] == "result-session"
    system.transport.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", [ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT, ExecutionStatus.CANCELLED]
)
async def test_failure_and_timeout_reply_without_exposing_internal_errors(system, status):
    system.execution.status = status
    system.execution.error_message = "SECRET database credential"
    key = await system.service.enqueue_execution("p", system.task, system.execution)
    await system.service.deliver(key)
    content = (await messages(system))[0].content
    assert "SECRET" not in content and "Findings ready" not in content
    assert system.execution.status == status


@pytest.mark.asyncio
async def test_owner_and_project_isolation_including_read_receipts(system):
    key = await system.service.enqueue_execution("p", system.task, system.execution)
    assert (await system.service.list("p", "bob"))["notifications"] == []
    assert (await system.service.list("other", "alice"))["notifications"] == []
    with pytest.raises(TaskNotFound):
        await system.service.mark_read("p", "bob", key)
    with pytest.raises(ValueError, match="投递"):
        await system.service.mark_read("p", "alice", key)
    await system.service.deliver(key)
    await system.service.mark_read("p", "alice", key)
    assert (await system.service.list("p", "alice", unread_only=True))["unread_count"] == 0


@pytest.mark.asyncio
async def test_changed_session_ownership_prevents_delivery(system):
    key = await system.service.enqueue_execution("p", system.task, system.execution)
    system.source.owner_user_id = "bob"
    assert await system.service.deliver(key) == "rejected"
    assert not await messages(system)


@pytest.mark.asyncio
async def test_external_send_ambiguity_is_not_retried_or_marked_as_execution_failure(system):
    system.task.assistant_recipient = "weixin:bot:user"
    system.transport.side_effect = TimeoutError()
    key = await system.service.enqueue_execution("p", system.task, system.execution)
    assert await system.service.deliver(key) == "unknown"
    assert await system.service.deliver(key) == "unknown"
    assert system.transport.await_count == 1
    assert system.execution.status == ExecutionStatus.SUCCESS


@pytest.mark.asyncio
async def test_matter_waits_for_acceptance_and_user_edits_are_preserved(system):
    tasks = AssistantTaskService(system.factory)
    matter = await tasks.create(
        "p",
        "alice",
        AssistantRequest("source", "request", "Review notes"),
        goal="Review",
        completion_criteria="User accepts findings",
    )
    system.task.assistant_matter_id = matter["task_id"]
    system.task.assistant_matter_version = 1
    await system.service.enqueue_execution("p", system.task, system.execution)
    await system.service.enqueue_execution("p", system.task, system.execution)
    updated = await tasks.get("p", "alice", matter["task_id"])
    assert updated["status"] == "waiting_input" and updated["version"] == 2
    assert "Findings ready" in updated["result_summary"]
    await tasks.change(
        "p",
        "alice",
        matter["task_id"],
        AssistantRequest("source", "edit", "Change next step"),
        expected_version=2,
        action="update",
        next_step="Wait for my revised instructions",
    )
    # A later run using an obsolete grant cannot overwrite feedback or mark completion.
    system.execution.execution_id = "exec2"
    await system.service.enqueue_execution("p", system.task, system.execution)
    assert (await tasks.get("p", "alice", matter["task_id"]))["version"] == 3
    assert (await system.service.list("p", "alice"))["notifications"][0][
        "matter_update"
    ] == "superseded"


@pytest.mark.asyncio
async def test_restart_reconciles_terminal_execution_and_never_replays_ambiguous_send(system):
    async with system.factory() as session:
        session.add(
            ScheduledTaskExecutionDB(
                execution_id="exec1",
                task_id="job",
                task_name="Review",
                status="success",
                started_at=datetime.utcnow(),
                data=system.execution.model_dump(mode="json"),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        await session.commit()
    jobs = SimpleNamespace(list_tasks=lambda _: [system.task])
    await system.service.tick("p", jobs)
    await system.service.tick("p", jobs)
    assert len(await messages(system)) == 1
    async with system.factory() as session:
        row = await session.get(Notice, "execution:exec1")
        row.state, row.lease_until = "sending", datetime.utcnow() - timedelta(minutes=1)
        await session.commit()
    await system.service.tick("p", jobs)
    assert (await system.service.list("p", "alice"))["notifications"][0][
        "delivery_state"
    ] == "unknown"
    system.transport.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_web_deliveries_do_not_duplicate_messages(system):
    key = await system.service.enqueue_execution("p", system.task, system.execution)
    await asyncio.gather(system.service.deliver(key), system.service.deliver(key))
    assert len(await messages(system)) == 1


@pytest.mark.asyncio
async def test_foreground_append_and_background_reply_preserve_ids_and_order(system):
    from app.db.session_repository import SessionRepository

    repository = SessionRepository()
    repository.engine = system.engine
    repository._pool_status = lambda: {}
    history = [{"type": "user", "content": "Continue my work"}]
    key = await system.service.enqueue_execution("p", system.task, system.execution)
    await asyncio.gather(
        repository.sync_conversation_history_incremental("source", history),
        system.service.deliver(key),
    )
    assert await repository.sync_conversation_history_incremental("source", history)
    rows = await messages(system)
    assert len(rows) == 2
    assert len({row.sequence_number for row in rows}) == 2
    user = next(row for row in rows if row.role == "user")
    assert history[0]["id"] == f"msg_{user.id}"


@pytest.mark.asyncio
async def test_scheduled_service_enqueues_reply_without_broadcast_tool(system, monkeypatch):
    from app.scheduled_tasks.service import ScheduledTaskService
    from app.social import assistant_notifications
    from config.settings import settings

    monkeypatch.setattr(settings, "project_id", "p")
    monkeypatch.setattr(assistant_notifications, "AssistantNotificationService", lambda: system.service)
    service = ScheduledTaskService.__new__(ScheduledTaskService)
    service.executor = SimpleNamespace(execute_task=AsyncMock(return_value=system.execution))
    service.task_storage = SimpleNamespace(update_run_stats=lambda *args, **kwargs: None)
    result = await service._execute_scheduled_task(system.task)
    assert result.status == ExecutionStatus.SUCCESS
    assert (await system.service.list("p", "alice"))["unread_count"] == 1
    assert await system.service.deliver("execution:exec1") == "inbox_saved"


@pytest.mark.asyncio
async def test_queue_failure_does_not_rewrite_execution_status(system, monkeypatch):
    from app.scheduled_tasks.service import ScheduledTaskService
    from app.social import assistant_notifications
    from config.settings import settings

    monkeypatch.setattr(settings, "project_id", "p")
    notifier = SimpleNamespace(enqueue_execution=AsyncMock(side_effect=RuntimeError("database temporarily unavailable")))
    monkeypatch.setattr(assistant_notifications, "AssistantNotificationService", lambda: notifier)
    service = ScheduledTaskService.__new__(ScheduledTaskService)
    service.executor = SimpleNamespace(execute_task=AsyncMock(return_value=system.execution))
    service.task_storage = SimpleNamespace(update_run_stats=lambda *args, **kwargs: None)
    assert (await service._execute_scheduled_task(system.task)).status == ExecutionStatus.SUCCESS
    notifier.enqueue_execution.assert_awaited_once()
