from types import SimpleNamespace

import pytest

from app.knowledge_base import shared_metadata
from app.knowledge_base.models import KnowledgeBaseStatus
from app.knowledge_base.service import KnowledgeBaseService


def test_shared_database_name_reuses_local_connection_credentials(monkeypatch):
    monkeypatch.delenv("SHARED_KNOWLEDGE_DATABASE_URL", raising=False)
    monkeypatch.setenv("SHARED_KNOWLEDGE_DATABASE_NAME", "knowledge_center")
    monkeypatch.setattr(
        shared_metadata,
        "DATABASE_URL",
        "postgresql+asyncpg://reader:secret@db.example:5432/project_db",
    )

    assert shared_metadata._build_shared_database_url() == (
        "postgresql+asyncpg://reader:secret@db.example:5432/knowledge_center"
    )


@pytest.mark.asyncio
async def test_list_knowledge_bases_merges_central_shared_metadata(monkeypatch):
    local = SimpleNamespace(id="local-kb")
    shared = SimpleNamespace(id="shared-kb")
    duplicate = SimpleNamespace(id="local-kb")

    async def local_list(**_kwargs):
        return [local]

    async def central_list(*, status=None):
        assert status == KnowledgeBaseStatus.ACTIVE
        return [shared, duplicate]

    monkeypatch.setattr(
        "app.knowledge_base.permissions.KnowledgeBasePermissions.get_accessible_knowledge_bases",
        local_list,
    )
    monkeypatch.setattr(
        shared_metadata,
        "list_central_shared_knowledge_bases",
        central_list,
    )

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.db = object()
    result = await service.list_knowledge_bases(
        status=KnowledgeBaseStatus.ACTIVE
    )

    assert [kb.id for kb in result] == ["local-kb", "shared-kb"]


@pytest.mark.asyncio
async def test_document_enrichment_replaces_null_vector_filename():
    document = SimpleNamespace(
        id="doc-1",
        filename="真实文档.pdf",
        original_file_oid=None,
        file_storage_type=None,
        file_path=None,
        file_type="pdf",
        file_size=123,
        file_mime_type="application/pdf",
        created_at=None,
        processed_at=None,
    )

    class FakeDB:
        async def execute(self, _statement):
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [document])
            )

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service.db = FakeDB()
    results = [{"document_id": "doc-1", "filename": None, "knowledge_base": {}}]

    await service._enrich_results_with_document_info(results)

    assert results[0]["filename"] == "真实文档.pdf"
