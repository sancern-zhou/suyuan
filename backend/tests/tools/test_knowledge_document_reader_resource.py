from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.resources.contracts import ResourceDeclaration
from app.agent.resources.resource_service import SessionResourceService
from app.tools.workflow.knowledge_document_reader import KnowledgeDocumentReader


class _FakeKnowledgeBaseService:
    def __init__(self, db=None):
        del db

    async def get_document_chunks(self, **kwargs):
        assert kwargs["user_id"] == "user-1"
        return {
            "filename": "source.pdf",
            "chunks": [{"chunk_index": 0, "content": "source text"}],
        }

    async def get_document_original(self, **kwargs):
        assert kwargs["user_id"] == "user-1"
        content = b"%PDF-1.4 original"
        return {
            "filename": "source.pdf",
            "content": content,
            "checksum": hashlib.sha256(content).hexdigest(),
            "size": len(content),
            "mime_type": "application/pdf",
            "storage_type": "database",
        }


@pytest.mark.asyncio
async def test_reader_materializes_original_and_declares_session_resource(
    monkeypatch, tmp_path
):
    @asynccontextmanager
    async def fake_session():
        yield object()

    import app.db.knowledge_database as knowledge_database_module
    import app.knowledge_base.service as service_module

    monkeypatch.setattr(
        knowledge_database_module, "knowledge_async_session", fake_session
    )
    monkeypatch.setattr(service_module, "KnowledgeBaseService", _FakeKnowledgeBaseService)
    resource_service = SessionResourceService(storage_root=tmp_path / "resource_content")
    reader = KnowledgeDocumentReader(resource_service=resource_service)
    context = SimpleNamespace(session_id="session-1", user_identifier="user-1")

    first = await reader.execute(
        context,
        knowledge_base_id="kb-1",
        document_id="doc-1",
        chunk_index=0,
    )
    second = await reader.execute(
        context,
        knowledge_base_id="kb-1",
        document_id="doc-1",
        chunk_index=0,
    )

    assert first["success"] is True
    declaration = ResourceDeclaration.model_validate(first["resources"][0])
    materialized = Path(declaration.locator.path)
    assert materialized.is_file()
    assert materialized.read_bytes() == b"%PDF-1.4 original"
    assert declaration.renderer.value == "pdf"
    assert declaration.role.value == "output"
    assert {item.value for item in declaration.capabilities} == {"preview", "download"}
    assert first["file_path"] == first["data"]["original_resource"]["file_path"]
    assert first["content_preview"] == "source text"
    assert first["content_truncated"] is False
    assert second["resources"][0]["locator"]["path"] == str(materialized)


@pytest.mark.asyncio
async def test_reader_requires_session_context(tmp_path):
    reader = KnowledgeDocumentReader(
        resource_service=SessionResourceService(storage_root=tmp_path)
    )
    result = await reader.execute(
        knowledge_base_id="kb-1",
        document_id="doc-1",
    )
    assert result["success"] is False
    assert "会话上下文" in result["summary"]


def test_reader_schema_exposes_bounded_text_and_materialized_resource_contract():
    schema = KnowledgeDocumentReader().get_function_schema()

    assert schema["parameters"]["properties"]["max_content_chars"]["default"] == 20000
    assert "物化" in schema["description"]
    assert "original_resource.file_path" in (
        schema["parameters"]["properties"]["max_content_chars"]["description"]
    )


def test_reader_bounds_chunk_text_without_losing_chunk_identity():
    chunks = [
        {"chunk_index": 3, "content": "a" * 900},
        {"chunk_index": 4, "content": "b" * 900},
    ]

    bounded, stats = KnowledgeDocumentReader._bound_chunk_content(
        chunks,
        max_chars=1000,
    )

    assert [chunk["chunk_index"] for chunk in bounded] == [3, 4]
    assert len(bounded[1]["content"]) == 100
    assert bounded[1]["content_truncated"] is True
    assert stats == {
        "total_chars": 1800,
        "returned_chars": 1000,
        "content_truncated": True,
    }
