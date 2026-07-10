from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.graph_models import (
    KnowledgeChunk,
    KnowledgeGraphEntity,
    KnowledgeGraphEntityMention,
    KnowledgeGraphRelation,
    KnowledgeGraphRelationMention,
    KnowledgeIndexOutbox,
)
from app.knowledge_base.graph_schemas import ChunkGraphExtraction
from app.knowledge_base.ingestion_service import KnowledgeIngestionService
from app.knowledge_base.models import Document, DocumentStatus, KnowledgeBase


class _MutableProcessor:
    def __init__(self):
        self.chunks = [{"content": "A"}, {"content": "B"}]
        self.error = None

    async def parse(self, file_path):
        if self.error:
            raise RuntimeError(self.error)
        return "\n".join(chunk["content"] for chunk in self.chunks)

    async def chunk(self, **kwargs):
        return list(self.chunks)


class _EmptyExtractor:
    async def extract_chunk(self, *, kb_id, chunk, schema):
        return ChunkGraphExtraction(chunk_id=chunk.id, extractor_name="empty")


class _FileStorage:
    def __init__(self):
        self.deleted = []

    async def delete_file(self, reference):
        self.deleted.append(reference)
        return True

    async def store_file(self, **kwargs):
        return {
            "storage_type": "local",
            "storage_path": kwargs["temp_file_path"],
            "size": 1,
        }


@pytest.fixture
async def replacement_context(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'replace.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    tables = [
        KnowledgeBase.__table__,
        Document.__table__,
        KnowledgeChunk.__table__,
        KnowledgeGraphEntity.__table__,
        KnowledgeGraphRelation.__table__,
        KnowledgeGraphEntityMention.__table__,
        KnowledgeGraphRelationMention.__table__,
        KnowledgeIndexOutbox.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=tables,
            )
        )
    old_file = tmp_path / "old.md"
    old_file.write_text("A\nB")
    async with factory() as session:
        session.add(
            KnowledgeBase(
                id="kb1",
                name="测试知识库",
                qdrant_collection="kb_kb1",
                graph_enabled=True,
            )
        )
        session.add(
            Document(
                id="doc1",
                knowledge_base_id="kb1",
                filename="old.md",
                file_path=str(old_file),
                file_type="md",
                file_size=3,
                status=DocumentStatus.PROCESSING,
                file_storage_type="local",
            )
        )
        await session.commit()
    processor = _MutableProcessor()
    storage = _FileStorage()
    service = KnowledgeIngestionService(
        session_factory=factory,
        processor=processor,
        extractor=_EmptyExtractor(),
        file_storage=storage,
    )
    await service.ingest_document("doc1")
    yield factory, processor, storage, service, tmp_path
    await engine.dispose()


@pytest.mark.asyncio
async def test_replace_reuses_unchanged_chunk_and_deletes_changed_chunk(replacement_context):
    factory, processor, storage, service, tmp_path = replacement_context
    async with factory() as session:
        old_chunks = list(
            (
                await session.execute(
                    select(KnowledgeChunk).order_by(KnowledgeChunk.chunk_index)
                )
            ).scalars()
        )
    processor.chunks = [{"content": "A"}, {"content": "C"}]
    new_file = tmp_path / "new.md"
    new_file.write_text("A\nC")

    result = await service.replace_document(
        "doc1",
        str(new_file),
        {"filename": "new.md", "file_type": "md", "file_size": 3},
    )

    assert result.content_generation == 2
    assert (result.reused_chunks, result.added_chunks, result.removed_chunks) == (1, 1, 1)
    async with factory() as session:
        current = list(
            (
                await session.execute(
                    select(KnowledgeChunk).order_by(KnowledgeChunk.chunk_index)
                )
            ).scalars()
        )
        document = await session.get(Document, "doc1")
        delete_ids = set(
            (
                await session.execute(
                    select(KnowledgeIndexOutbox.record_id).where(
                        KnowledgeIndexOutbox.operation == "delete",
                        KnowledgeIndexOutbox.record_type == "chunk",
                    )
                )
            ).scalars()
        )
    assert current[0].id == old_chunks[0].id
    assert current[1].id != old_chunks[1].id
    assert old_chunks[1].id in delete_ids
    assert document.filename == "new.md"
    assert storage.deleted == [str(tmp_path / "old.md")]


@pytest.mark.asyncio
async def test_replace_parse_failure_cleans_old_derived_data(replacement_context):
    factory, processor, _storage, service, tmp_path = replacement_context
    processor.error = "invalid replacement"
    new_file = tmp_path / "broken.md"
    new_file.write_text("broken")

    with pytest.raises(RuntimeError, match="invalid replacement"):
        await service.replace_document(
            "doc1",
            str(new_file),
            {"filename": "broken.md", "file_type": "md", "file_size": 6},
        )

    async with factory() as session:
        document = await session.get(Document, "doc1")
        chunks = list((await session.execute(select(KnowledgeChunk))).scalars())
    assert document.content_generation == 2
    assert document.status == DocumentStatus.FAILED
    assert document.ingestion_status == "failed"
    assert chunks == []


@pytest.mark.asyncio
async def test_delete_removes_document_chunks_and_enqueues_index_deletes(replacement_context):
    factory, _processor, storage, service, _tmp_path = replacement_context

    await service.delete_document("kb1", "doc1")

    async with factory() as session:
        assert await session.get(Document, "doc1") is None
        assert list((await session.execute(select(KnowledgeChunk))).scalars()) == []
        operations = list(
            (
                await session.execute(
                    select(
                        KnowledgeIndexOutbox.record_type,
                        KnowledgeIndexOutbox.operation,
                    ).where(KnowledgeIndexOutbox.operation == "delete")
                )
            ).all()
        )
    assert operations == [("chunk", "delete"), ("chunk", "delete")]
    assert storage.deleted
