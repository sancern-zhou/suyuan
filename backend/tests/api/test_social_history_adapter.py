from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.session_routes import router
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.conversations.adapters import SocialConversationAdapter, get_conversation_adapters
from app.conversations.dependencies import get_conversation_catalog
from app.conversations.schemas import ConversationCatalogRecord, ConversationSource


def _row():
    return ConversationCatalogRecord(
        session_id="social-1", owner_user_id="u1", owner_username="alice",
        owner_display_name="Alice", source=ConversationSource.SOCIAL,
        mode="social", title="微信消息", read_only_on_web=True,
        created_at=datetime(2026, 7, 14), updated_at=datetime(2026, 7, 14),
    )


@pytest.mark.asyncio
async def test_social_adapter_normalizes_file_session(monkeypatch):
    from app.conversations import adapters

    session = SimpleNamespace(
        session_id="social-1", query="微信消息",
        conversation_history=[{"type": "user", "content": "hello"}],
        model_dump=lambda **kwargs: {
            "session_id": "social-1", "query": "微信消息",
            "conversation_history": [{"type": "user", "content": "hello"}],
            "metadata": {},
        },
    )

    async def fake_load(*args, **kwargs):
        return session

    monkeypatch.setattr(adapters, "load_session_for_mode", fake_load)
    result = await SocialConversationAdapter().restore(
        _row(), message_limit=100, lazy_artifacts=True
    )

    payload = result["normalized_session"]
    assert payload["source"] == "social"
    assert payload["read_only_on_web"] is True
    assert payload["conversation_history"][0]["content"] == "hello"


def test_owner_can_restore_social_history_but_cannot_mutate_it():
    row = _row()

    class Catalog:
        async def require_read(self, session_id, user):
            return row

        async def require_write(self, session_id, user):
            raise HTTPException(status_code=409, detail="social_session_read_only")

    class Adapter:
        async def restore(self, catalog_row, **options):
            return {"normalized_session": {
                **catalog_row.model_dump(mode="json"),
                "conversation_history": [{"type": "user", "content": "hello"}],
            }}

    class Adapters:
        def get(self, source):
            assert source == ConversationSource.SOCIAL
            return Adapter()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_current_user] = lambda: CurrentUser(
        id="u1", username="alice", display_name="Alice"
    )
    app.dependency_overrides[get_conversation_catalog] = lambda: Catalog()
    app.dependency_overrides[get_conversation_adapters] = lambda: Adapters()
    client = TestClient(app)

    restored = client.post("/api/sessions/social-1/restore")
    assert restored.status_code == 200
    assert restored.json()["session"]["read_only_on_web"] is True
    assert restored.json()["session"]["source"] == "social"

    messages = client.get("/api/sessions/social-1/messages")
    assert messages.status_code == 200
    assert messages.json()["messages"][0]["content"] == "hello"
    assert client.get("/api/sessions/social-1/visualizations").status_code == 404
    assert client.get("/api/sessions/social-1/office-documents").status_code == 404

    for method, suffix in (("POST", "/save"), ("DELETE", ""), ("POST", "/case")):
        response = client.request(method, f"/api/sessions/social-1{suffix}")
        assert response.status_code == 409
        assert response.json()["detail"] == "social_session_read_only"
