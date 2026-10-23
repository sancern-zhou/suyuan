from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.models import CurrentUser
from app.conversations.assistant_sync import AssistantConversationSync
from app.conversations.models import ConversationCatalogDB, ConversationReadDB
from app.conversations.schemas import ConversationSource
from app.db.models_session import SessionDB, SessionMessageDB
from app.social.app_identity import AppIdentity
from app.social.assistant_notification_models import AssistantNotificationDB
from app.social.assistant_notifications import AssistantNotificationService
from app.social.web_assistant import web_assistant_recipient

WEB = CurrentUser(id="42", username="alice", display_name="Alice")
APP = AppIdentity("42", "Alice", "company:42", 9999999999, auth_source="company")


@pytest_asyncio.fixture
async def shared(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    async with engine.begin() as conn:
        for model in (ConversationCatalogDB, ConversationReadDB, SessionDB, SessionMessageDB):
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add(ConversationCatalogDB(session_id="shared", owner_user_id="42", owner_username="alice",
                                    owner_display_name="Alice", source="web", mode="assistant", title="Track"))
        db.add(SessionDB(session_id="shared", query="Track", mode="assistant"))
        await db.commit()
    yield SimpleNamespace(engine=engine, factory=factory, sync=AssistantConversationSync(factory))
    await engine.dispose()


async def append(system, sequence, content, msg_type="final"):
    async with system.factory() as db:
        db.add(SessionMessageDB(session_id="shared", role="user" if msg_type == "user" else "assistant",
                                msg_type=msg_type, content=content, sequence_number=sequence,
                                msg_metadata={"attachments": [{"file_id": "file-1", "filename": "notes.txt"}]}))
        await db.commit()


@pytest.mark.asyncio
async def test_web_app_share_messages_read_state_and_continue(shared):
    await append(shared, 0, "Question from Web", "user")
    await append(shared, 1, "Answer from Web")
    first = await shared.sync.snapshot(APP.as_current_user(), "shared")
    assert [message["content"] for message in first["messages"]] == ["Question from Web", "Answer from Web"]
    assert first["messages"][1]["attachments"][0]["filename"] == "notes.txt"
    assert (await shared.sync.summaries(APP.as_current_user()))[0]["unread_count"] == 2
    await shared.sync.mark_read(APP.as_current_user(), "shared", first["through_sequence"])
    assert (await shared.sync.summaries(WEB))[0]["unread_count"] == 0
    await append(shared, 2, "Follow-up from App", "user")
    await append(shared, 3, "Answer to App")
    second = await shared.sync.snapshot(WEB, "shared", revision=first["revision"])
    assert [message["content"] for message in second["messages"]][-2:] == ["Follow-up from App", "Answer to App"]
    assert (await shared.sync.summaries(WEB))[0]["unread_count"] == 2
    assert (await shared.sync.snapshot(WEB, "shared", revision=second["revision"]))["unchanged"]


@pytest.mark.asyncio
async def test_read_watermark_is_monotonic_and_never_acknowledges_future_rows(shared):
    await append(shared, 0, "One")
    await shared.sync.mark_read(WEB, "shared", 99999)
    await append(shared, 1, "Two")
    await shared.sync.mark_read(APP.as_current_user(), "shared", -1)
    assert (await shared.sync.summaries(WEB))[0]["unread_count"] == 1
    async with shared.factory() as db:
        assert (await db.get(ConversationReadDB, ("shared", "42"))).through_sequence == 0


@pytest.mark.asyncio
async def test_other_users_and_admin_cannot_access_personal_sync(shared):
    await append(shared, 0, "Private")
    for user in [CurrentUser(id="other", username="b", display_name="B"),
                 CurrentUser(id="admin", username="admin", display_name="Admin", is_admin=True)]:
        assert await shared.sync.summaries(user) == []
        for operation in [shared.sync.snapshot(user, "shared"), shared.sync.mark_read(user, "shared", 0)]:
            with pytest.raises(HTTPException) as exc:
                await operation
            assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_empty_drafts_do_not_appear_and_pagination_is_stable(shared):
    assert await shared.sync.summaries(WEB) == []
    await append(shared, 0, "Visible")
    assert len(await shared.sync.summaries(WEB, limit=1)) == 1
    assert await shared.sync.summaries(WEB, limit=1, offset=1) == []


@pytest.mark.asyncio
async def test_app_can_resume_web_session_but_cannot_claim_unknown_id(shared, monkeypatch):
    from app.api import social_app_routes as routes
    row = SimpleNamespace(owner_user_id="42", source=ConversationSource.WEB,
                          read_only_on_web=False, mode="assistant")
    catalog = SimpleNamespace(find=AsyncMock(return_value=row))
    monkeypatch.setattr(routes, "get_conversation_catalog", lambda: catalog)
    assert await routes._ensure_session(None, APP, "shared", "assistant") == "shared"
    with pytest.raises(HTTPException) as exc:
        await routes._ensure_session(None, APP, "shared", "expert")
    assert exc.value.status_code == 409
    catalog.find.return_value = None
    with pytest.raises(HTTPException) as exc:
        await routes._ensure_session(None, APP, "assistant_session_1234567890123_abcdef123456", "assistant")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_background_reply_uses_session_database_and_replays_without_duplicates(shared, tmp_path):
    queue_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'business.db'}")
    async with queue_engine.begin() as conn:
        await conn.run_sync(AssistantNotificationDB.__table__.create)
    queue_factory = async_sessionmaker(queue_engine, expire_on_commit=False)
    catalog = SimpleNamespace(find=AsyncMock(return_value=SimpleNamespace(owner_user_id="42", source=ConversationSource.WEB)))
    service = AssistantNotificationService(queue_factory, catalog, transcript_factory=shared.factory)
    await service.enqueue(message_id="result", project="default", owner="42", source_session_id="shared",
                          recipient=web_assistant_recipient("42"), content="Task done", data={})
    assert await service.deliver("result") == "inbox_saved"
    # Reproduce a crash after transcript commit but before queue acknowledgement.
    async with queue_factory() as db:
        notice = await db.get(AssistantNotificationDB, "result")
        notice.state = "pending"
        await db.commit()
    assert await service.deliver("result") == "inbox_saved"
    snapshot = await shared.sync.snapshot(APP.as_current_user(), "shared")
    assert [message["content"] for message in snapshot["messages"]] == ["Task done"]
    async with shared.factory() as db:
        assert len((await db.execute(select(SessionMessageDB))).scalars().all()) == 1
    await queue_engine.dispose()


@pytest.mark.asyncio
async def test_pending_question_changes_sync_without_new_message(shared):
    snapshot = await shared.sync.snapshot(WEB, "shared")
    pending = {"interaction_id": "question", "kind": "structured_question", "session_id": "shared"}
    async with shared.factory() as db:
        row = (await db.execute(select(SessionDB))).scalar_one()
        row.session_metadata = {"pending_interaction": pending}
        await db.commit()
    synced = await shared.sync.snapshot(APP.as_current_user(), "shared", revision=snapshot["revision"])
    assert synced["unchanged"]
    assert synced["pending_interaction"] == pending


@pytest.mark.asyncio
async def test_reconciliation_reads_separate_execution_database_past_known_page(shared, tmp_path):
    from app.db.models.scheduled_task_execution_db import ScheduledTaskExecutionDB as Execution
    async with shared.engine.begin() as conn:
        await conn.run_sync(Execution.__table__.create)
    queue_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'outbox.db'}")
    async with queue_engine.begin() as conn:
        await conn.run_sync(AssistantNotificationDB.__table__.create)
    queue_factory = async_sessionmaker(queue_engine, expire_on_commit=False)
    async with shared.factory() as db:
        for index in range(102):
            db.add(Execution(execution_id=f"{index:04}", task_id="task", status="success",
                             started_at=datetime.utcnow(), created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
                             data={"index": index}))
        await db.commit()
    async with queue_factory() as db:
        for index in range(101):
            db.add(AssistantNotificationDB(message_id=f"execution:{index:04}", project_id="p",
                    owner_user_id="42", source_session_id="shared", recipient="web", content="done", data={}))
        await db.commit()
    service = AssistantNotificationService(queue_factory, SimpleNamespace(), transcript_factory=shared.factory)
    assert await service._unreported_executions("p", {"task": object()}) == [{"index": 101}]
    await queue_engine.dispose()
