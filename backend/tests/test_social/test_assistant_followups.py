"""Durable reminder integration tests; all delivery is local and fake."""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.social.assistant_followup_models import (
    AssistantOutboxDB,
    AssistantRunDB,
    AssistantTriggerDB,
)
from app.social.assistant_followup_worker import AssistantFollowupWorker
from app.social.assistant_followups import AssistantFollowupService
from app.social.assistant_reminder_delivery import deliver_reminder
from app.social.assistant_request import (
    AssistantRequest,
    begin_assistant_request,
    end_assistant_request,
)
from app.social.assistant_schedule import definition_hash, normalize_schedule
from app.social.assistant_task_models import AssistantTaskDB, AssistantTaskEventDB
from app.social.assistant_tasks import AssistantTaskService, TaskConflict, TaskNotFound
from app.tools.social.assistant_followups.tool import ManageAssistantFollowupsTool

NOW = datetime(2026, 10, 18, 1)
REQUEST = AssistantRequest(
    "session-a", "request-a", "Remind me to collect the field results", "app:bot:alice"
)


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "assistant_followups_enabled", True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'reminders.db').as_posix()}")
    tables = [
        AssistantTaskDB.__table__,
        AssistantTaskEventDB.__table__,
        AssistantTriggerDB.__table__,
        AssistantRunDB.__table__,
        AssistantOutboxDB.__table__,
    ]
    async with engine.begin() as conn:
        for table in tables:
            await conn.run_sync(table.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    tasks = AssistantTaskService(factory)
    task = await tasks.create(
        "p1",
        "app:bot:alice",
        REQUEST,
        goal="Field investigation",
        completion_criteria="Reviewed field evidence",
    )
    yield SimpleNamespace(
        service=AssistantFollowupService(factory),
        tasks=tasks,
        task=task,
        factory=factory,
        engine=engine,
    )
    await engine.dispose()


async def create(db, **kwargs):
    return await db.service.create(
        "p1",
        "app:bot:alice",
        db.task["task_id"],
        REQUEST,
        expected_version=1,
        kind=kwargs.pop("kind", "now"),
        instructions="Collect the field results",
        now=kwargs.pop("now", NOW),
        **kwargs,
    )


async def inspect(db):
    return await db.service.inspect("p1", "app:bot:alice", db.task["task_id"])


async def pending(db):
    await create(db)
    await db.service.materialize("p1", NOW)
    await db.service.prepare_notifications("p1", NOW)
    return await db.service.claim_notification("p1", NOW)


@pytest.mark.asyncio
async def test_restart_and_duplicate_ticks_do_not_duplicate_occurrences(db):
    trigger = await create(db)
    assert (await create(db))["trigger_id"] == trigger["trigger_id"]
    service = AssistantFollowupService(db.factory)
    for _ in range(2):
        await service.materialize("p1", NOW)
        await service.prepare_notifications("p1", NOW)
    state = await inspect(db)
    assert len(state["runs"]) == len(state["notifications"]) == 1
    assert state["runs"][0]["state"] == "succeeded"
    assert (await db.tasks.get("p1", "app:bot:alice", db.task["task_id"]))["status"] == "ready"
    first, second = await asyncio.gather(
        service.claim_notification("p1", NOW), db.service.claim_notification("p1", NOW)
    )
    assert sum(item is not None for item in (first, second)) == 1


@pytest.mark.asyncio
async def test_concurrent_creation_and_materialization(db):
    triggers = await asyncio.gather(create(db), create(db))
    assert triggers[0]["trigger_id"] == triggers[1]["trigger_id"]
    await asyncio.gather(db.service.materialize("p1", NOW), db.service.materialize("p1", NOW))
    assert len((await inspect(db))["runs"]) == 1
    await asyncio.gather(
        db.service.prepare_notifications("p1", NOW), db.service.prepare_notifications("p1", NOW)
    )
    assert len((await inspect(db))["notifications"]) == 1


@pytest.mark.asyncio
async def test_owner_project_version_and_missing_recipient_are_denied(db):
    with pytest.raises(TaskNotFound):
        await db.service.inspect("p2", "app:bot:alice", db.task["task_id"])
    with pytest.raises(TaskNotFound):
        await db.service.disable("p1", "bob", db.task["task_id"], REQUEST, expected_version=1)
    with pytest.raises(TaskConflict):
        await db.service.create(
            "p1",
            "app:bot:alice",
            db.task["task_id"],
            REQUEST,
            expected_version=2,
            kind="now",
            instructions="test",
            now=NOW,
        )
    with pytest.raises(PermissionError):
        await db.service.create(
            "p1",
            "app:bot:alice",
            db.task["task_id"],
            AssistantRequest("session-a", "other", "test"),
            expected_version=1,
            kind="now",
            instructions="test",
            now=NOW,
        )
    await create(db)
    await db.service.materialize("p2", NOW)
    assert (await inspect(db))["runs"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,changes",
    [
        ("cancel", {}),
        ("complete", {"result_summary": "Checked the evidence"}),
        ("update", {"goal": "Changed goal"}),
        ("update", {"completion_criteria": "New acceptance criteria"}),
    ],
)
async def test_human_cancellation_or_scope_change_revokes_pending_send(db, action, changes):
    claimed = await pending(db)
    await db.tasks.change(
        "p1",
        "app:bot:alice",
        db.task["task_id"],
        REQUEST,
        expected_version=1,
        action=action,
        **changes,
    )
    adapter = AsyncMock(return_value="inbox_saved")
    await db.service.deliver("p1", claimed, adapter, now=NOW)
    adapter.assert_not_awaited()
    state = await inspect(db)
    assert not state["triggers"][0]["enabled"]
    assert state["notifications"][0]["state"] == "cancelled"


@pytest.mark.asyncio
async def test_disable_all_is_versioned_and_terminal_task_cannot_start_another_plan(db):
    await create(db)
    result = await db.service.disable(
        "p1", "app:bot:alice", db.task["task_id"], REQUEST, expected_version=1
    )
    assert result["version"] == 2
    assert not (await create(db))["enabled"]
    await db.tasks.change(
        "p1", "app:bot:alice", db.task["task_id"], REQUEST, expected_version=2, action="cancel"
    )
    with pytest.raises(TaskConflict):
        await db.service.create(
            "p1",
            "app:bot:alice",
            db.task["task_id"],
            AssistantRequest("session-a", "request-new", "new", REQUEST.delivery_user_id),
            expected_version=3,
            kind="now",
            instructions="new",
            now=NOW,
        )


@pytest.mark.asyncio
async def test_outbox_failure_rolls_back_execution_and_retries_without_duplicate(db):
    await create(db)
    await db.service.materialize("p1", NOW)

    def fail(_connection, _cursor, statement, *_args):
        if statement.startswith("INSERT INTO assistant_outbox"):
            raise RuntimeError("simulated storage failure")

    event.listen(db.engine.sync_engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            await db.service.prepare_notifications("p1", NOW)
    finally:
        event.remove(db.engine.sync_engine, "before_cursor_execute", fail)
    state = await inspect(db)
    assert state["runs"][0]["state"] == "queued" and state["notifications"] == []
    await db.service.prepare_notifications("p1", NOW)
    assert len((await inspect(db))["notifications"]) == 1


@pytest.mark.asyncio
async def test_cancellation_rolls_back_if_revoke_cannot_be_persisted(db):
    await pending(db)

    def fail(_connection, _cursor, statement, *_args):
        if statement.startswith("UPDATE assistant_outbox"):
            raise RuntimeError("simulated revoke failure")

    event.listen(db.engine.sync_engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            await db.tasks.change(
                "p1",
                "app:bot:alice",
                db.task["task_id"],
                REQUEST,
                expected_version=1,
                action="cancel",
            )
    finally:
        event.remove(db.engine.sync_engine, "before_cursor_execute", fail)
    task = await db.tasks.get("p1", "app:bot:alice", db.task["task_id"])
    assert task["version"] == 1 and task["status"] == "ready"
    assert (await inspect(db))["triggers"][0]["enabled"]


@pytest.mark.asyncio
async def test_lost_delivery_receipt_is_unknown_never_automatically_replayed(db):
    claimed = await pending(db)
    adapter = AsyncMock(side_effect=TimeoutError("receipt lost after possible send"))
    await db.service.deliver("p1", claimed, adapter, now=NOW)
    assert (await inspect(db))["notifications"][0]["state"] == "unknown"
    assert await db.service.claim_notification("p1", NOW + timedelta(days=1)) is None
    assert adapter.await_count == 1


@pytest.mark.asyncio
async def test_interrupted_send_expires_to_unknown_and_old_claim_cannot_send(db):
    claimed = await pending(db)
    restarted = AssistantFollowupService(db.factory)
    assert await restarted.claim_notification("p1", NOW + timedelta(seconds=91)) is None
    adapter = AsyncMock(return_value="provider_accepted")
    await restarted.deliver("p1", claimed, adapter, now=NOW)
    adapter.assert_not_awaited()
    assert (await inspect(db))["notifications"][0]["state"] == "unknown"


@pytest.mark.asyncio
async def test_successful_delivery_cannot_be_replayed_with_the_same_claim(db):
    claimed = await pending(db)
    adapter = AsyncMock(return_value="inbox_saved")
    await db.service.deliver("p1", claimed, adapter, now=NOW)
    await db.service.deliver("p1", claimed, adapter, now=NOW)
    assert adapter.await_count == 1
    assert (await inspect(db))["notifications"][0]["state"] == "inbox_saved"


@pytest.mark.asyncio
async def test_expired_claim_is_not_admitted_without_another_clock_tick(db):
    claimed = await pending(db)
    adapter = AsyncMock(return_value="inbox_saved")
    await db.service.deliver("p1", claimed, adapter, now=NOW + timedelta(seconds=91))
    adapter.assert_not_awaited()
    assert (await inspect(db))["notifications"][0]["state"] == "unknown"


@pytest.mark.asyncio
async def test_periodic_downtime_coalesces_but_one_shot_misfire_expires(db):
    await create(db, kind="interval", interval_minutes=5)
    await db.service.materialize("p1", NOW + timedelta(days=2))
    state = await inspect(db)
    assert len(state["runs"]) == 1
    assert state["triggers"][0]["next_at"] == NOW + timedelta(days=2, minutes=5)
    await db.service.disable("p1", "app:bot:alice", db.task["task_id"], REQUEST, expected_version=1)
    async with db.factory() as session:
        task = await session.get(AssistantTaskDB, db.task["task_id"])
        session.add(
            AssistantTriggerDB(
                trigger_id="expired-trigger",
                task_id=task.task_id,
                request_key="expired",
                kind="once",
                action="remind",
                instructions="old",
                schedule={},
                next_at=NOW,
                enabled=True,
                definition_hash=definition_hash(task),
                recipient=REQUEST.delivery_user_id,
                grant_session_id=REQUEST.session_id,
                grant_request_id="expired",
                grant_message="old",
            )
        )
        await session.commit()
    await db.service.materialize("p1", NOW + timedelta(days=2))
    state = await inspect(db)
    assert any(run["state"] == "expired" for run in state["runs"])


def test_timezone_and_cron_follow_existing_scheduler_semantics():
    _, due = normalize_schedule("once", run_at="2026-10-18T10:00:00", now=NOW)
    assert due == datetime(2026, 10, 18, 2)
    _, next_at = normalize_schedule("cron", cron="0 10 * * *", now=NOW)
    assert next_at == datetime(2026, 10, 18, 2)
    for params in (
        {"kind": "cron", "cron": "bad"},
        {"kind": "interval", "interval_minutes": 0},
        {"kind": "now", "timezone_name": "invalid/zone"},
    ):
        with pytest.raises(ValueError):
            normalize_schedule(now=NOW, **params)


@pytest.mark.asyncio
async def test_tool_denies_disabled_background_and_injected_recipient(db, monkeypatch):
    import app.tools.social.assistant_followups.tool as module
    from config.settings import settings

    monkeypatch.setattr(
        module, "resolve_task_user", AsyncMock(return_value=SimpleNamespace(id="app:bot:alice"))
    )
    monkeypatch.setattr(settings, "project_id", "p1")
    tool = ManageAssistantFollowupsTool(db.service)
    context = SimpleNamespace(session_id="session-a", scheduled_task_context=None)
    params = dict(
        context=context,
        action="create",
        task_id=db.task["task_id"],
        expected_version=1,
        kind="now",
        instructions="remind",
    )
    assert not (await tool.execute(**params))["success"]
    token = begin_assistant_request(
        "session-a", "remind me", delivery_user_id=REQUEST.delivery_user_id
    )
    try:
        assert not (await tool.execute(**params, recipient="bob"))["success"]
        context.scheduled_task_context = {"run_id": "background"}
        assert not (await tool.execute(**params))["success"]
        context.scheduled_task_context = None
        monkeypatch.setattr(settings, "assistant_followups_enabled", False)
        assert not (await tool.execute(**params))["success"]
        monkeypatch.setattr(settings, "assistant_followups_enabled", True)
        assert (await tool.execute(**params))["success"]
    finally:
        end_assistant_request(token)


@pytest.mark.asyncio
async def test_adapter_revalidates_owner_and_preserves_saved_app_inbox_on_push_failure(monkeypatch):
    import app.conversations.dependencies as catalog_module
    import app.social.broadcast_context as inbox_module
    import app.social.push_service as push_module

    catalog = SimpleNamespace(find=AsyncMock(return_value=SimpleNamespace(owner_user_id="alice")))
    monkeypatch.setattr(catalog_module, "get_conversation_catalog", lambda: catalog)
    persist = AsyncMock(return_value=True)
    monkeypatch.setattr(inbox_module, "persist_broadcast_context", persist)
    push = SimpleNamespace(send_broadcast=AsyncMock(side_effect=RuntimeError("offline")))
    monkeypatch.setattr(push_module, "get_unified_push_service", lambda: push)
    task = SimpleNamespace(owner_user_id="app:bot:alice", task_id="task")
    trigger = SimpleNamespace(grant_session_id="session")
    message = SimpleNamespace(recipient="app:bot:alice", content="reminder", message_id="outbox")
    assert await deliver_reminder(task, trigger, message) == "rejected"
    persist.assert_not_awaited()
    catalog.find.return_value.owner_user_id = task.owner_user_id
    assert await deliver_reminder(task, trigger, message) == "inbox_saved"
    assert persist.await_args.kwargs["metadata"]["event_id"] == "outbox"


@pytest.mark.asyncio
async def test_unbound_weixin_is_rejected_without_sending(monkeypatch):
    import app.conversations.dependencies as catalog_module
    import app.social.binding_service as binding_module

    catalog = SimpleNamespace(find=AsyncMock(return_value=SimpleNamespace(owner_user_id="alice")))
    monkeypatch.setattr(catalog_module, "get_conversation_catalog", lambda: catalog)
    binding = SimpleNamespace(active_for_platform_user=AsyncMock(return_value=None))
    monkeypatch.setattr(binding_module, "get_social_binding_service", lambda: binding)
    assert (
        await deliver_reminder(
            SimpleNamespace(owner_user_id="alice"),
            SimpleNamespace(grant_session_id="session"),
            SimpleNamespace(recipient="weixin:bot:user"),
        )
        == "rejected"
    )


@pytest.mark.asyncio
async def test_worker_stop_does_not_spawn_another_delivery():
    service = SimpleNamespace(
        materialize=AsyncMock(),
        prepare_notifications=AsyncMock(),
        claim_notification=AsyncMock(return_value=None),
    )
    worker = AssistantFollowupWorker("p1", service)
    await worker.tick()
    await asyncio.sleep(0)
    await worker.stop()
    await worker.tick()
    assert service.materialize.await_count == 1


@pytest.mark.asyncio
async def test_interval_does_not_drift_with_the_polling_delay(db):
    await create(db, kind="interval", interval_minutes=5)
    await db.service.materialize("p1", NOW + timedelta(minutes=5, seconds=3))
    assert (await inspect(db))["triggers"][0]["next_at"] == NOW + timedelta(minutes=10)


@pytest.mark.asyncio
async def test_already_admitted_send_finishes_before_cancellation_commits(db):
    claimed = await pending(db)
    entered, release = asyncio.Event(), asyncio.Event()

    async def send(*_args):
        entered.set()
        await release.wait()
        return "inbox_saved"

    delivery = asyncio.create_task(db.service.deliver("p1", claimed, send, now=NOW))
    await asyncio.wait_for(entered.wait(), 2)
    cancel = asyncio.create_task(
        db.tasks.change(
            "p1", "app:bot:alice", db.task["task_id"], REQUEST, expected_version=1, action="cancel"
        )
    )
    try:
        await asyncio.sleep(0.05)
        assert not cancel.done()
    finally:
        release.set()
        await asyncio.gather(delivery, cancel)
    assert (await inspect(db))["notifications"][0]["state"] == "inbox_saved"


@pytest.mark.asyncio
async def test_single_attempt_metadata_prevents_transport_retry_and_wrong_bot():
    from app.channels.manager import ChannelManager
    from app.social.events import OutboundMessage

    manager = object.__new__(ChannelManager)
    manager.config = SimpleNamespace(channels=SimpleNamespace(send_max_retries=3))
    channel = SimpleNamespace(
        bot_account="bot", send=AsyncMock(side_effect=TimeoutError("ambiguous"))
    )
    message = OutboundMessage(
        channel="weixin:one",
        chat_id="alice",
        content="reminder",
        metadata={"_single_attempt": True, "_expected_bot_account": "bot"},
    )
    assert not await manager._send_with_retry(channel, message)
    assert channel.send.await_count == 1
    channel.send.reset_mock()
    channel.bot_account = "another-bot"
    assert not await manager._send_with_retry(channel, message)
    channel.send.assert_not_awaited()


def test_followup_tool_is_only_visible_in_enabled_social_mode(monkeypatch):
    from app.agent.prompts.tool_registry import get_tools_by_mode
    from config.settings import settings

    monkeypatch.setattr(settings, "assistant_followups_enabled", False)
    assert "manage_assistant_followups" not in get_tools_by_mode("social")
    monkeypatch.setattr(settings, "assistant_followups_enabled", True)
    assert "manage_assistant_followups" in get_tools_by_mode("social")
    assert "manage_assistant_followups" not in get_tools_by_mode("expert")


@pytest.mark.asyncio
async def test_worker_registers_one_clock_on_the_existing_scheduler(monkeypatch):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    import app.social.assistant_followup_worker as module

    worker = SimpleNamespace(tick=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr(module, "AssistantFollowupWorker", lambda project: worker)
    monkeypatch.setattr(module, "_worker", None)
    scheduler = AsyncIOScheduler()
    module.start_assistant_followups(scheduler, "p1")
    module.start_assistant_followups(scheduler, "p1")
    assert len(scheduler.get_jobs()) == 1
    assert scheduler.get_job(module.JOB_ID).max_instances == 1
    await module.stop_assistant_followups(scheduler)
    assert scheduler.get_jobs() == []
    worker.stop.assert_awaited_once()


def test_saved_migration_matches_model_columns_without_a_real_service():
    import sqlite3

    from app.utils.path_config import PROJECT_ROOT

    with sqlite3.connect(":memory:") as connection:
        for number in (
            "021_create_assistant_tasks.sql",
            "022_create_assistant_followups.sql",
            "023_assistant_analysis_leases.sql",
        ):
            sql = (PROJECT_ROOT / "backend" / "app" / "db" / "migrations" / number).read_text(
                encoding="utf-8"
            )
            # SQLite lacks PostgreSQL's idempotent ADD COLUMN syntax.
            connection.executescript(sql.replace("ADD COLUMN IF NOT EXISTS", "ADD COLUMN"))
        for model in (AssistantTriggerDB, AssistantRunDB, AssistantOutboxDB):
            columns = {
                row[1] for row in connection.execute(f"PRAGMA table_info({model.__tablename__})")
            }
            assert columns == {column.name for column in model.__table__.columns}


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted", [True, False])
async def test_weixin_adapter_bus_and_channel_keep_single_attempt_policy(monkeypatch, accepted):
    import app.conversations.dependencies as catalog_module
    import app.social.binding_service as binding_module
    import app.social.broadcast_service as broadcast_module
    from app.channels.manager import ChannelManager
    from app.social.message_bus import MessageBus

    catalog = SimpleNamespace(find=AsyncMock(return_value=SimpleNamespace(owner_user_id="alice")))
    monkeypatch.setattr(catalog_module, "get_conversation_catalog", lambda: catalog)
    binding = SimpleNamespace(
        active_for_platform_user=AsyncMock(
            return_value=SimpleNamespace(bot_account="bot", ilink_user_id="alice")
        )
    )
    monkeypatch.setattr(binding_module, "get_social_binding_service", lambda: binding)
    bus = MessageBus()
    monkeypatch.setattr(broadcast_module, "get_message_bus", lambda: bus)
    monkeypatch.setattr(
        broadcast_module.SocialBroadcastService,
        "_get_session_mapper",
        AsyncMock(return_value=SimpleNamespace()),
    )
    monkeypatch.setattr(broadcast_module, "persist_broadcast_context", AsyncMock(return_value=True))
    channel = SimpleNamespace(
        bot_account="bot",
        send=AsyncMock(side_effect=None if accepted else TimeoutError("provider receipt lost")),
    )
    manager = object.__new__(ChannelManager)
    manager.bus = bus
    manager.config = SimpleNamespace(channels=SimpleNamespace(send_max_retries=3))
    manager.channels = {"weixin:one": channel}
    dispatcher = asyncio.create_task(manager._dispatch_outbound())
    try:
        state = await deliver_reminder(
            SimpleNamespace(owner_user_id="alice", task_id="task"),
            SimpleNamespace(grant_session_id="session"),
            SimpleNamespace(
                recipient="weixin:one:bot:alice", content="reminder", message_id="message"
            ),
        )
        assert state == ("provider_accepted" if accepted else "unknown")
        assert channel.send.await_count == 1
        assert channel.send.await_args.args[0].metadata == {
            "_single_attempt": True,
            "_expected_bot_account": "bot",
        }
    finally:
        dispatcher.cancel()
        await dispatcher
