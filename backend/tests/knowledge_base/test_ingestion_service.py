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
from app.knowledge_base.graph_schemas import (
    ChunkGraphExtraction,
    ExtractedEntity,
    ExtractedRelation,
)
from app.knowledge_base.ingestion_service import KnowledgeIngestionService
from app.knowledge_base.models import Document, DocumentStatus, KnowledgeBase


class _Processor:
    async def parse(self, file_path):
        return "臭氧受光化学反应影响。\n监测站记录臭氧。"

    async def chunk(self, **kwargs):
        return [
            {"content": "臭氧受光化学反应影响。"},
            {"content": "监测站记录臭氧。"},
        ]


class _Extractor:
    async def extract_chunk(self, *, kb_id, chunk, schema):
        if chunk.chunk_index == 1:
            return ChunkGraphExtraction(chunk_id=chunk.id, extractor_name="fake")
        return ChunkGraphExtraction(
            chunk_id=chunk.id,
            extractor_name="fake",
            entities=[
                ExtractedEntity(
                    local_id="mechanism",
                    entity_type="ProcessMechanism",
                    name="光化学反应",
                    evidence_text=chunk.content,
                ),
                ExtractedEntity(
                    local_id="o3",
                    entity_type="Pollutant",
                    name="臭氧",
                    evidence_text=chunk.content,
                ),
            ],
            relations=[
                ExtractedRelation(
                    source_local_id="mechanism",
                    target_local_id="o3",
                    relation_type="affects",
                    evidence_text=chunk.content,
                )
            ],
        )


class _FailingExtractor:
    async def extract_chunk(self, *, kb_id, chunk, schema):
        raise RuntimeError("graph provider unavailable")


@pytest.fixture
async def ingestion_database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ingestion.db'}")
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
                filename="report.md",
                file_path="/tmp/report.md",
                file_type="md",
                file_size=42,
                status=DocumentStatus.PROCESSING,
            )
        )
        await session.commit()
    yield factory
    await engine.dispose()


def _service(factory, extractor):
    return KnowledgeIngestionService(
        session_factory=factory,
        processor=_Processor(),
        extractor=extractor,
        file_storage=None,
        max_graph_concurrency=2,
    )


@pytest.mark.asyncio
async def test_ingest_writes_chunks_before_incremental_graph(ingestion_database):
    result = await _service(ingestion_database, _Extractor()).ingest_document("doc1")

    assert result.document_id == "doc1"
    assert result.content_generation == 1
    assert result.added_chunks == 2
    assert result.reused_chunks == 0
    assert result.removed_chunks == 0
    assert result.changed_entities == 2
    assert result.changed_relations == 1
    assert result.status == "completed"

    async with ingestion_database() as session:
        document = await session.get(Document, "doc1")
        assert document.status == DocumentStatus.COMPLETED
        assert document.ingestion_status == "completed"
        assert document.graph_status == "completed"
        items = list(
            (
                await session.execute(
                    select(KnowledgeIndexOutbox).order_by(KnowledgeIndexOutbox.created_at)
                )
            ).scalars()
        )
        assert [item.record_type for item in items] == [
            "chunk",
            "chunk",
            "entity",
            "entity",
            "relation",
        ]


@pytest.mark.asyncio
async def test_graph_failure_keeps_chunk_outbox_and_marks_partial(ingestion_database):
    result = await _service(ingestion_database, _FailingExtractor()).ingest_document("doc1")

    assert result.status == "partial"
    async with ingestion_database() as session:
        document = await session.get(Document, "doc1")
        assert document.status == DocumentStatus.COMPLETED
        assert document.ingestion_status == "partial"
        assert document.graph_status == "failed"
        assert "graph provider unavailable" in document.processing_error
        record_types = list(
            (
                await session.execute(
                    select(KnowledgeIndexOutbox.record_type).order_by(
                        KnowledgeIndexOutbox.created_at
                    )
                )
            ).scalars()
        )
        assert record_types == ["chunk", "chunk"]
        chunks = list((await session.execute(select(KnowledgeChunk))).scalars())
        assert {chunk.graph_status for chunk in chunks} == {"failed"}
