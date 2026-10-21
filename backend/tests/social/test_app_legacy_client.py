"""Exercise unmodified App request shapes against real SQL and upload storage."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api import social_app_routes as routes, upload_routes
from app.agent.resources.resource_service import SessionResourceService
from app.conversations.models import ConversationCatalogDB, ConversationReadDB
from app.conversations.repository import ConversationCatalogRepository
from app.conversations.service import ConversationCatalogService
from app.db.database import get_db
from app.db.models_session import SessionDB
from app.knowledge_base.models import UploadedFile
from app.social.app_identity import AppIdentity, require_app_identity
from app.social.app_runs import AppRunStore
from app.social.models import SocialSessionMapping
from app.social.session_mapper import SessionMapper


@pytest_asyncio.fixture
async def legacy(app_transcript_db, monkeypatch, tmp_path, fake_lock_db):
    from app.conversations import repository
    from app.conversations import adapters
    from app.db import session_database

    engine = app_transcript_db.repository.engine
    async with engine.begin() as conn:
        for model in (ConversationCatalogDB, ConversationReadDB, UploadedFile, SocialSessionMapping):
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(session_database, "session_async_session", factory)
    monkeypatch.setattr(repository, "async_session", factory)
    monkeypatch.setattr(adapters, "get_session_manager", lambda: app_transcript_db)
    catalog = ConversationCatalogService(ConversationCatalogRepository())
    monkeypatch.setattr(routes, "get_conversation_catalog", lambda: catalog)
    mapper = SessionMapper(factory)
    monkeypatch.setattr(routes, "_loaded_session_mapper", AsyncMock(return_value=mapper))
    resources = SessionResourceService.in_memory()
    monkeypatch.setattr(SessionResourceService, "database", classmethod(lambda cls: resources))
    monkeypatch.setattr(upload_routes, "UPLOAD_STORAGE_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(routes, "get_data_registry", lambda: tmp_path)
    store = AppRunStore(tmp_path / "runs.sqlite")
    monkeypatch.setattr(routes, "get_app_run_store", lambda: store)
    calls = []

    class Agent:
        async def analyze(self, **kwargs):
            calls.append(kwargs)
            yield {"type": "complete", "data": {"answer": "SQL-backed answer"}}

    monkeypatch.setattr(routes, "_get_agent", AsyncMock(return_value=Agent()))
    monkeypatch.setattr(routes, "_get_memory_store", AsyncMock(return_value=object()))
    monkeypatch.setattr(routes, "_social_preferences", lambda identity: {})
    system = SimpleNamespace(factory=factory, catalog=catalog, mapper=mapper, resources=resources,
        store=store, manager=app_transcript_db, calls=calls,
        identity=AppIdentity("42", "Alice", "company:42", 9999999999))
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[require_app_identity] = lambda: system.identity

    async def database():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = database
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        system.client = client
        yield system
        if store.tasks:
            await asyncio.gather(*store.tasks)


async def send(system, *, session_id=None, mode="query", attachments=None, request_id="first"):
    payload = {"query": "Please analyze", "mode": mode, "request_id": request_id, "attachments": attachments or []}
    if session_id is not None:
        payload["session_id"] = session_id
    response = await system.client.post("/api/social/app/chat/runs", json=payload)
    if system.store.tasks:
        await asyncio.gather(*system.store.tasks)
    return response


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["query", "expert", "knowledge"])
async def test_old_create_then_two_turns_bind_actual_mode_and_persist_sql(legacy, mode):
    response = await legacy.client.post("/api/social/app/sessions", content="")
    assert response.status_code == 200
    sid = response.json()["session_id"]
    assert (await legacy.catalog.find(sid)).mode is None
    first = await send(legacy, session_id=sid, mode=mode)
    assert first.status_code == 200, first.text
    assert (await send(legacy, session_id=sid, mode=mode, request_id="next")).status_code == 200
    assert (await send(legacy, session_id=sid, mode=mode)).json()["run_id"] == first.json()["run_id"]
    frames = await legacy.client.get(f"/api/social/app/chat/runs/{first.json()['run_id']}/events")
    assert "SQL-backed answer" in frames.text
    assert "fatal_error" not in frames.text
    restored = await legacy.client.get(f"/api/social/app/sessions/{sid}/messages")
    assert restored.status_code == 200
    assert len(restored.json()["messages"]) == 4
    assert (await legacy.catalog.find(sid)).mode == mode
    async with legacy.factory() as db:
        row = (await db.execute(select(SessionDB).where(SessionDB.session_id == sid))).scalar_one()
        assert row.mode == mode
        assert "app_legacy_mode_pending" not in row.session_metadata
    assert all(call["session_storage_mode"] == "assistant" for call in legacy.calls)


@pytest.mark.asyncio
async def test_old_file_only_upload_and_chat_without_session_id_share_sql_draft(legacy):
    upload = await legacy.client.post("/api/social/app/upload", files={"file": ("notes.txt", b"field feedback", "text/plain")})
    assert upload.status_code == 200, upload.text
    attachment = upload.json()
    preview = await legacy.client.get(attachment["url"])
    assert preview.status_code == 200
    assert preview.content == b"field feedback"
    sid = await legacy.mapper.get_session(legacy.identity.social_user_id)
    assert (await legacy.catalog.find(sid)).mode is None
    response = await send(legacy, mode="expert", attachments=[attachment])
    assert response.status_code == 200, response.text
    assert response.json()["session_id"] == sid
    assert legacy.calls[0]["selected_resource_refs"][0].metadata["file_id"] == attachment["file_id"]


@pytest.mark.asyncio
async def test_old_attachment_survives_switch_back_to_another_created_mode(legacy):
    first = (await legacy.client.post("/api/social/app/sessions", content="")).json()["session_id"]
    second = (await legacy.client.post("/api/social/app/sessions", content="")).json()["session_id"]
    upload = (await legacy.client.post("/api/social/app/upload", files={"file": ("notes.txt", b"feedback", "text/plain")})).json()
    assert (await legacy.resources.list_resources(second)).resources
    response = await send(legacy, session_id=first, mode="query", attachments=[upload])
    assert response.status_code == 200, response.text
    selected = legacy.calls[0]["selected_resource_refs"]
    assert selected[0].session_id == first
    assert selected[0].metadata["file_id"] == upload["file_id"]
    restored = (await legacy.client.get(f"/api/social/app/sessions/{first}/messages")).json()
    attachment = restored["messages"][0]["attachments"][0]
    assert (await legacy.client.get(attachment["url"])).content == b"feedback"
    again = await send(legacy, session_id=first, mode="query", attachments=[upload], request_id="again")
    assert again.status_code == 200
    resources = (await legacy.resources.list_resources(first)).resources
    assert len([item for item in resources if item.metadata.get("file_id") == upload["file_id"]]) == 1


@pytest.mark.asyncio
async def test_old_client_cannot_import_another_accounts_attachment(legacy):
    upload = (await legacy.client.post("/api/social/app/upload", files={"file": ("private.txt", b"private", "text/plain")})).json()
    legacy.identity = AppIdentity("43", "Bob", "company:43", 9999999999)
    sid = (await legacy.client.post("/api/social/app/sessions", content="")).json()["session_id"]
    response = await send(legacy, session_id=sid, attachments=[upload])
    assert response.status_code == 404
    assert legacy.calls == []
    assert not (await legacy.resources.list_resources(sid)).resources


@pytest.mark.asyncio
async def test_new_client_keeps_explicit_modes_and_strict_attachment_scope(legacy):
    legacy.client.headers["X-App-Conversation-Version"] = "2"
    first = (await legacy.client.post("/api/social/app/sessions?mode=query", content="")).json()["session_id"]
    second = (await legacy.client.post("/api/social/app/sessions?mode=expert", content="")).json()["session_id"]
    assert (await send(legacy, session_id=first, mode="expert")).status_code == 409
    upload = (await legacy.client.post("/api/social/app/upload", data={"session_id": first, "mode": "query"},
        files={"file": ("notes.txt", b"feedback", "text/plain")})).json()
    assert (await send(legacy, session_id=second, mode="expert", attachments=[upload])).status_code == 404
    assert await legacy.mapper.get_session(legacy.identity.social_user_id) is None


@pytest.mark.asyncio
async def test_concurrent_old_first_turns_cannot_change_each_others_mode(legacy):
    sid = (await legacy.client.post("/api/social/app/sessions", content="")).json()["session_id"]
    results = await asyncio.gather(*(routes._ensure_session(None, legacy.identity, sid, mode)
        for mode in ("query", "expert")), return_exceptions=True)
    assert sum(isinstance(result, str) for result in results) == 1
    assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results) == 1


@pytest.mark.asyncio
async def test_old_client_does_not_claim_unknown_or_pre_upgrade_sessions(legacy):
    assert (await send(legacy, session_id="assistant_session_1234567890123_abcdefabcdef")).status_code == 404
    from app.conversations.schemas import ConversationSource
    await legacy.catalog.register_identity(session_id="old-channel", owner_user_id="42", owner_username="Alice",
        owner_display_name="Alice", source=ConversationSource.SOCIAL, mode="assistant", title="Old", read_only_on_web=True)
    assert (await send(legacy, session_id="old-channel")).status_code == 404


@pytest.mark.asyncio
async def test_old_history_lists_only_modes_the_client_can_resume(legacy):
    sid = (await legacy.client.post("/api/social/app/sessions", content="")).json()["session_id"]
    assert (await send(legacy, session_id=sid)).status_code == 200
    assistant = (await legacy.client.post("/api/social/app/sessions?mode=assistant", content="")).json()["session_id"]
    from app.agent.session.models import Session
    await legacy.manager.save_session(Session(session_id=assistant, query="Assistant", metadata={"mode": "assistant"},
        conversation_history=[{"type": "user", "role": "user", "content": "Assistant"}]))
    old = (await legacy.client.get("/api/social/app/sessions")).json()
    assert [row["session_id"] for row in old] == [sid]
    new = (await legacy.client.get("/api/social/app/sessions", headers={"X-App-Conversation-Version": "2"})).json()
    assert {row["session_id"] for row in new} == {sid, assistant}
