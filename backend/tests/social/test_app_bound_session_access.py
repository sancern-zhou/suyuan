from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api import social_app_routes
from app.auth import identity_matching
from app.conversations.schemas import ConversationCatalogRecord, ConversationSource
from app.conversations.service import ConversationCatalogService
from app.social.app_identity import AppIdentity


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "caller,owner,source,allowed",
    [
        ("app:android:alice", "company:2", ConversationSource.SOCIAL, True),
        ("company:2", "app:android:alice", ConversationSource.SOCIAL, True),
        ("app:android:alice", "app:android:alice", ConversationSource.SOCIAL, True),
        ("app:android:alice", "company:3", ConversationSource.SOCIAL, False),
        ("app:android:bob", "company:2", ConversationSource.SOCIAL, False),
        ("app:android:alice", "company:2", ConversationSource.WEB, False),
    ],
)
async def test_bound_app_history_resume_preserves_owner(monkeypatch, caller, owner, source, allowed):
    monkeypatch.setattr(
        identity_matching, "settings",
        SimpleNamespace(app_accounts_json='{"alice": {"bind_user_id": "2"}, "bob": {}}'),
    )
    identity_matching._app_accounts.cache_clear()
    row = ConversationCatalogRecord(
        session_id="history", owner_user_id=owner, owner_username="original",
        owner_display_name="Original owner", source=source, mode="query",
        title="历史会话", read_only_on_web=True,
    )
    repository = SimpleNamespace(get=AsyncMock(return_value=row), upsert=AsyncMock())
    catalog = ConversationCatalogService(repository)
    monkeypatch.setattr(social_app_routes, "get_conversation_catalog", lambda: catalog)
    monkeypatch.setattr(social_app_routes, "_loaded_session_mapper", AsyncMock(return_value=object()))
    identity = AppIdentity("caller", "Caller", caller, 9999999999)
    try:
        if allowed:
            assert await catalog.require_read("history", identity.as_current_user()) is row
            assert await social_app_routes._ensure_session(object(), identity, "history") == "history"
        else:
            with pytest.raises(HTTPException) as exc:
                await social_app_routes._ensure_session(object(), identity, "history")
            assert exc.value.status_code == 404
        repository.upsert.assert_not_awaited()
        assert row.owner_user_id == owner
        assert row.mode == "query"
        assert row.title == "历史会话"
    finally:
        identity_matching._app_accounts.cache_clear()
