import pytest
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.session_routes import router
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser
from app.conversations.dependencies import get_conversation_catalog
from app.conversations.adapters import get_conversation_adapters
from app.conversations.schemas import ConversationCatalogRecord, ConversationSource


class DenyingCatalog:
    async def require_read(self, session_id, user):
        raise HTTPException(status_code=404, detail="session_not_found")

    async def require_write(self, session_id, user):
        raise HTTPException(status_code=404, detail="session_not_found")


def make_client(user=None, catalog=None, adapters=None):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_current_user] = lambda: user or CurrentUser(
        id="u1", username="u1", display_name="U1"
    )
    app.dependency_overrides[get_conversation_catalog] = lambda: catalog or DenyingCatalog()
    if adapters is not None:
        app.dependency_overrides[get_conversation_adapters] = lambda: adapters
    return TestClient(app)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/sessions/other"),
        ("POST", "/api/sessions/other/restore"),
        ("GET", "/api/sessions/other/messages"),
        ("GET", "/api/sessions/other/visualizations"),
        ("GET", "/api/sessions/other/office-documents"),
        ("GET", "/api/sessions/other/drawio-board"),
        ("POST", "/api/sessions/other/save"),
        ("POST", "/api/sessions/other/case"),
        ("DELETE", "/api/sessions/other/case"),
        ("DELETE", "/api/sessions/other"),
        ("POST", "/api/sessions/other/export"),
    ],
)
def test_all_session_id_endpoints_hide_unauthorized_sessions(method, path):
    response = make_client().request(method, path)

    assert response.status_code == 404
    assert response.json()["detail"] == "session_not_found"


def test_auto_save_checks_catalog_before_loading_source_session():
    response = make_client().post(
        "/api/sessions/auto-save",
        json={"session_id": "other", "messages": []},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "session_not_found"


def test_cleanup_is_admin_only():
    response = make_client().post("/api/sessions/cleanup")

    assert response.status_code == 403
    assert response.json()["detail"] == "admin_required"


def test_knowledge_catalog_record_dispatches_to_knowledge_adapter():
    row = ConversationCatalogRecord(
        session_id="kqa-1",
        owner_user_id="u1",
        owner_username="u1",
        owner_display_name="U1",
        source=ConversationSource.KNOWLEDGE_QA,
        mode="knowledge_qa",
        title="knowledge",
        created_at=datetime(2026, 7, 14),
        updated_at=datetime(2026, 7, 14),
    )

    class AllowedCatalog:
        async def require_read(self, session_id, user):
            return row

        async def require_write(self, session_id, user):
            return row

        async def delete(self, session_id):
            return True

    class Adapter:
        async def get(self, catalog_row):
            return {"session_id": catalog_row.session_id, "source": "knowledge_qa"}

        async def restore(self, catalog_row, **options):
            return {
                "normalized_session": {
                    "session_id": catalog_row.session_id,
                    "source": "knowledge_qa",
                }
            }

        async def delete(self, catalog_row):
            assert catalog_row.source == ConversationSource.KNOWLEDGE_QA
            return True

    class Adapters:
        def get(self, source):
            assert source == ConversationSource.KNOWLEDGE_QA
            return Adapter()

    client = make_client(catalog=AllowedCatalog(), adapters=Adapters())

    assert client.get("/api/sessions/kqa-1").json()["source"] == "knowledge_qa"
    assert (
        client.post("/api/sessions/kqa-1/restore").json()["session"]["source"]
        == "knowledge_qa"
    )
    assert client.delete("/api/sessions/kqa-1").status_code == 200
