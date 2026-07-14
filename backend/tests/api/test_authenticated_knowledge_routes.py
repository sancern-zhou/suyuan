import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser


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
    from app.routers import knowledge_qa

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

    assert response.status_code == 200
    assert seen["user_id"] == "authenticated"


@pytest.mark.asyncio
async def test_non_stream_qa_search_uses_authenticated_user_id(monkeypatch):
    from app.routers import knowledge_qa
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
