"""App drafts are registered immediately in SQL; unknown IDs cannot be claimed."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api import social_app_routes as routes
from app.conversations.schemas import ConversationSource
from app.conversations.service import ConversationCatalogService
from app.social.app_identity import AppIdentity


@pytest.mark.asyncio
async def test_app_creates_owned_database_draft_and_web_can_continue(app_transcript_db, monkeypatch, tmp_path):
    records = {}

    async def upsert(record):
        records[record.session_id] = record
        return record

    repository = SimpleNamespace(get=AsyncMock(side_effect=lambda sid: records.get(sid)), upsert=upsert)
    catalog = ConversationCatalogService(repository)
    monkeypatch.setattr(routes, "get_conversation_catalog", lambda: catalog)
    identity = AppIdentity("alice", "Alice", "company:42", 9999999999, auth_source="company")
    result = await routes.create_app_session(None, identity)
    row = records[result["session_id"]]
    assert row.owner_user_id == "42"
    assert row.source == ConversationSource.WEB
    assert not row.read_only_on_web
    assert await catalog.require_write(row.session_id, identity.as_current_user()) == row
    assert await app_transcript_db.load_session(row.session_id) is not None
    assert list(tmp_path.glob("*.json")) == []
    assert await routes._ensure_session(None, identity, row.session_id, "assistant") == row.session_id


@pytest.mark.asyncio
async def test_new_upload_session_is_also_owned_database_draft(app_transcript_db, monkeypatch):
    catalog = SimpleNamespace(register_identity=AsyncMock())
    monkeypatch.setattr(routes, "get_conversation_catalog", lambda: catalog)
    identity = AppIdentity("alice", "Alice", "company:42", 9999999999, auth_source="company")
    sid = await routes._ensure_session(None, identity, None, "assistant")
    assert (await app_transcript_db.load_session(sid)).metadata["mode"] == "assistant"
    assert catalog.register_identity.call_args.kwargs["owner_user_id"] == "42"


@pytest.mark.asyncio
async def test_unknown_draft_cannot_be_claimed_by_guessing_its_format(monkeypatch):
    catalog = SimpleNamespace(find=AsyncMock(return_value=None), register_identity=AsyncMock())
    monkeypatch.setattr(routes, "get_conversation_catalog", lambda: catalog)
    identity = AppIdentity("alice", "Alice", "company:42", 9999999999)
    for sid in ("assistant_session_1791910261228_a9985d22e841", "forged"):
        with pytest.raises(HTTPException) as exc:
            await routes._ensure_session(None, identity, sid)
        assert exc.value.status_code == 404
    catalog.register_identity.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_preserves_selected_shared_session_and_uses_authorized_resource_url(monkeypatch):
    from app.api import upload_routes
    ensure = AsyncMock(return_value="shared")
    upload = AsyncMock(return_value={"file_id": "file", "url": "/api/upload/file",
        "preview_url": "/api/upload/file", "resource_ref": {"resource_id": "resource"}})
    monkeypatch.setattr(routes, "_ensure_session", ensure)
    monkeypatch.setattr(upload_routes, "upload_chat_file", upload)
    monkeypatch.setattr(routes, "get_conversation_catalog", lambda: object())
    identity = AppIdentity("alice", "Alice", "company:42", 9999999999)
    result = await routes.upload_file(None, file=object(), session_id="shared", mode="assistant", db=None, identity=identity)
    ensure.assert_awaited_once_with(None, identity, "shared", "assistant")
    assert upload.call_args.kwargs["session_id"] == "shared"
    assert result["url"] == result["preview_url"] == "/api/social/app/sessions/shared/resources/resource/content"
