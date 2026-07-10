from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import knowledge_base_routes
from app.db.database import get_db
from app.knowledge_base.models import DocumentStatus


class _FakeService:
    def __init__(self, db=None):
        pass

    async def replace_document_content(self, **kwargs):
        return SimpleNamespace(
            id=kwargs["doc_id"],
            filename=kwargs["upload"].filename,
            file_type="md",
            file_size=11,
            status=DocumentStatus.COMPLETED,
            chunk_count=1,
            error_message=None,
            extra_metadata={},
            created_at=datetime(2026, 1, 1),
            processed_at=datetime(2026, 1, 1),
            file_storage_type="local",
            file_mime_type="text/markdown",
            original_file_oid=None,
            file_path="/tmp/replacement.md",
            file_preview_text="new content",
            content_generation=2,
            ingestion_status="completed",
            graph_status="completed",
            processing_error=None,
        )


def test_replace_document_content_route(monkeypatch, tmp_path):
    monkeypatch.setattr(knowledge_base_routes, "KnowledgeBaseService", _FakeService)
    monkeypatch.setenv("KNOWLEDGE_BASE_STORAGE_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(knowledge_base_routes.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)

    response = client.put(
        "/api/knowledge-base/kb1/documents/doc1/content",
        files={"file": ("replacement.md", b"new content", "text/markdown")},
        headers={"X-User-Id": "owner"},
    )

    assert response.status_code == 200
    assert response.json()["content_generation"] == 2
    assert response.json()["filename"] == "replacement.md"
