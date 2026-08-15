import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sse_starlette import EventSourceResponse

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from config.settings import settings


def test_knowledge_dependencies_ignore_forged_identity_headers():
    from app.api import knowledge_base_routes

    app = FastAPI()

    @app.get("/identity")
    async def identity(
        user_id=Depends(knowledge_base_routes.get_user_id),
        is_admin=Depends(knowledge_base_routes.get_is_admin),
    ):
        return {"user_id": user_id, "is_admin": is_admin}

    app.dependency_overrides[require_current_user] = lambda: CurrentUser(
        id="viewer", username="viewer", display_name="Viewer", is_admin=False
    )

    response = TestClient(app).get(
        "/identity",
        headers={"X-User-Id": "owner", "X-Is-Admin": "true"},
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": "viewer", "is_admin": False}


@pytest.mark.asyncio
async def test_qa_stream_stores_authenticated_user_id(monkeypatch):
    from app.api import knowledge_qa

    seen = {}

    class Store:
        async def get_or_create_session(self, **kwargs):
            seen.update(kwargs)
            return "session-1", [], True

    async def fake_store(db):
        return Store()

    async def fake_search(**kwargs):
        return []

    monkeypatch.setattr(knowledge_qa, "get_conversation_store", fake_store)
    monkeypatch.setattr(knowledge_qa, "search_knowledge_bases", fake_search)
    user = CurrentUser(id="authenticated", username="u", display_name="U")

    response = await knowledge_qa.knowledge_qa_stream(
        knowledge_qa.KnowledgeQARequest(query="问题"),
        db=object(),
        user=user,
    )

    assert isinstance(response, EventSourceResponse)
    assert response.status_code == 200
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.ping_interval == settings.sse_heartbeat_interval_seconds
    assert seen["user_id"] == "authenticated"


@pytest.mark.asyncio
async def test_qa_stream_hides_foreign_session_as_not_found(monkeypatch):
    from fastapi import HTTPException
    from app.knowledge_base.conversation_store import ConversationAccessDenied
    from app.api import knowledge_qa

    class Store:
        async def get_or_create_session(self, **kwargs):
            raise ConversationAccessDenied("foreign")

    async def fake_store(db):
        return Store()

    monkeypatch.setattr(knowledge_qa, "get_conversation_store", fake_store)
    user = CurrentUser(id="authenticated", username="u", display_name="U")

    with pytest.raises(HTTPException) as exc:
        await knowledge_qa.knowledge_qa_stream(
            knowledge_qa.KnowledgeQARequest(query="问题", session_id="foreign"),
            db=object(),
            user=user,
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_non_stream_qa_search_uses_authenticated_user_id(monkeypatch):
    from app.api import knowledge_qa
    from app.services.llm_service import llm_service

    seen = {}

    async def fake_search(**kwargs):
        seen.update(kwargs)
        return []

    async def fake_chat(**kwargs):
        return "回答"

    monkeypatch.setattr(knowledge_qa, "search_knowledge_bases", fake_search)
    monkeypatch.setattr(llm_service, "chat", fake_chat)
    user = CurrentUser(id="authenticated", username="u", display_name="U")

    response = await knowledge_qa.knowledge_qa_non_stream(
        knowledge_qa.KnowledgeQARequest(query="问题"),
        user=user,
    )

    assert response.answer == "回答"
    assert seen["user_id"] == "authenticated"


@pytest.mark.asyncio
async def test_knowledge_history_requires_catalog_ownership():
    from fastapi import HTTPException
    from app.api import knowledge_qa

    class DenyingCatalog:
        async def require_read(self, session_id, user):
            raise HTTPException(status_code=404, detail="session_not_found")

    user = CurrentUser(id="intruder", username="u", display_name="U")

    with pytest.raises(HTTPException) as exc:
        await knowledge_qa.get_conversation_history(
            "owned-by-someone-else",
            db=object(),
            user=user,
            catalog=DenyingCatalog(),
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_knowledge_history_list_ignores_client_user_id(monkeypatch):
    from app.api import knowledge_qa

    seen = {}

    class Store:
        async def list_user_sessions(self, **kwargs):
            seen.update(kwargs)
            return []

    async def fake_store(db):
        return Store()

    monkeypatch.setattr(knowledge_qa, "get_conversation_store", fake_store)
    user = CurrentUser(id="authenticated", username="u", display_name="U")

    response = await knowledge_qa.list_user_sessions(
        user_id="forged-owner",
        db=object(),
        user=user,
    )

    assert response == {"sessions": [], "total": 0}
    assert seen["user_id"] == "authenticated"


def test_knowledge_history_static_list_route_precedes_dynamic_session_route():
    from app.api import knowledge_qa

    paths = [route.path for route in knowledge_qa.router.routes]
    assert paths.index("/api/knowledge-qa/history/list") < paths.index(
        "/api/knowledge-qa/history/{session_id}"
    )
