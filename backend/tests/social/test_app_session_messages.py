from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import social_app_routes
from app.social.app_identity import AppIdentity
from app.social.app_identity import require_app_identity
from app.conversations import adapters as conversations_adapters
from app.conversations.schemas import ConversationCatalogRecord, ConversationSource


def _identity() -> AppIdentity:
    return AppIdentity(
        account_id="acc-1",
        display_name="Alice",
        social_user_id="u1",
        expires_at=9999999999,
    )


def _web_row() -> ConversationCatalogRecord:
    return ConversationCatalogRecord(
        session_id="scheduled_task_task_demo_20261007_080000_abcd1234",
        owner_user_id="u1", owner_username="alice",
        owner_display_name="Alice", source=ConversationSource.WEB,
        mode="expert", title="日报任务", read_only_on_web=False,
        created_at=datetime(2026, 10, 7), updated_at=datetime(2026, 10, 7),
    )


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(social_app_routes.router)
    app.dependency_overrides[require_app_identity] = _identity
    return TestClient(app)


def test_app_messages_restore_scheduled_task_web_session(monkeypatch):
    row = _web_row()

    class Catalog:
        async def require_read(self, session_id, user):
            assert session_id == row.session_id
            return row

    class WebAdapter:
        async def restore(self, catalog_row, **options):
            assert catalog_row.source == ConversationSource.WEB
            session = SimpleNamespace(model_dump=lambda **kwargs: {
                "session_id": catalog_row.session_id,
                "conversation_history": [
                    {"type": "user", "content": "任务输入"},
                    {"type": "final", "role": "assistant", "content": "任务结论"},
                ],
            })
            return {"session": session, "pagination": {"has_more": False, "total_count": 2, "oldest_sequence": None}}

    class Adapters:
        def get(self, source):
            assert source == ConversationSource.WEB
            return WebAdapter()

    monkeypatch.setattr(social_app_routes, "get_conversation_catalog", lambda: Catalog())
    monkeypatch.setattr(conversations_adapters, "get_conversation_adapters", lambda: Adapters())

    response = _client().get(f"/api/social/app/sessions/{row.session_id}/messages")
    assert response.status_code == 200
    messages = response.json()["messages"]
    assert messages[0]["content"] == "任务输入"
    assert messages[1]["content"] == "任务结论"


def test_app_messages_still_rejects_non_social_non_web_sources(monkeypatch):
    row = ConversationCatalogRecord(
        session_id="kqa-1", owner_user_id="u1", owner_username="alice",
        owner_display_name="Alice", source=ConversationSource.KNOWLEDGE_QA,
        mode="knowledge_qa", title="知识问答", read_only_on_web=False,
        created_at=datetime(2026, 10, 7), updated_at=datetime(2026, 10, 7),
    )

    class Catalog:
        async def require_read(self, session_id, user):
            return row

    monkeypatch.setattr(social_app_routes, "get_conversation_catalog", lambda: Catalog())

    response = _client().get("/api/social/app/sessions/kqa-1/messages")
    assert response.status_code == 404
    assert response.json()["detail"] == "session_not_found"


def test_app_messages_allows_system_owned_scheduled_task_session(monkeypatch):
    from app.api import scheduled_task_routes

    row = ConversationCatalogRecord(
        session_id="scheduled_task_task_demo_20261007_080000_abcd1234",
        owner_user_id="system", owner_username="system",
        owner_display_name="系统", source=ConversationSource.WEB,
        mode="custom", title="污染回顾分析", read_only_on_web=False,
        created_at=datetime(2026, 10, 7), updated_at=datetime(2026, 10, 7),
    )
    task = SimpleNamespace(
        task_id="task_demo", owner_user_id="system", created_by="system",
        workspace_entry=SimpleNamespace(enabled=True),
        broadcast_enabled=False, target_user_ids=[],
    )
    service = SimpleNamespace(get_task=lambda task_id: task if task_id == "task_demo" else None)

    class Catalog:
        async def require_read(self, session_id, user):
            raise HTTPException(status_code=404, detail="session_not_found")

        async def find(self, session_id):
            return row if session_id == row.session_id else None

    class WebAdapter:
        async def restore(self, catalog_row, **options):
            session = SimpleNamespace(model_dump=lambda **kwargs: {
                "session_id": catalog_row.session_id,
                "conversation_history": [{"type": "final", "content": "系统任务结论"}],
            })
            return {"session": session, "pagination": {"has_more": False, "total_count": 1, "oldest_sequence": None}}

    class Adapters:
        def get(self, source):
            assert source == ConversationSource.WEB
            return WebAdapter()

    monkeypatch.setattr(social_app_routes, "get_conversation_catalog", lambda: Catalog())
    monkeypatch.setattr(scheduled_task_routes, "get_scheduled_task_service", lambda: service)
    monkeypatch.setattr(conversations_adapters, "get_conversation_adapters", lambda: Adapters())

    response = _client().get(f"/api/social/app/sessions/{row.session_id}/messages")
    assert response.status_code == 200
    assert response.json()["messages"][0]["content"] == "系统任务结论"


def test_app_messages_rejects_unknown_scheduled_session(monkeypatch):
    from app.api import scheduled_task_routes

    service = SimpleNamespace(get_task=lambda task_id: None)

    class Catalog:
        async def require_read(self, session_id, user):
            raise HTTPException(status_code=404, detail="session_not_found")

    monkeypatch.setattr(social_app_routes, "get_conversation_catalog", lambda: Catalog())
    monkeypatch.setattr(scheduled_task_routes, "get_scheduled_task_service", lambda: service)

    response = _client().get("/api/social/app/sessions/scheduled_task_missing_20261007_080000_abcd1234/messages")
    assert response.status_code == 404
    assert response.json()["detail"] == "session_not_found"
