"""Contract tests for graph build executor."""
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.graph_build_models import KnowledgeGraphBuildTask
from app.knowledge_base.graph_models import (
    KnowledgeChunk,
    KnowledgeGraphEntity,
    KnowledgeGraphEntityMention,
    KnowledgeIndexOutbox,
)
from app.knowledge_base.graph_build_service import GraphBuildService
from app.knowledge_base.graph_schemas import ChunkGraphExtraction, ExtractedEntity
from app.knowledge_base.models import Document, KnowledgeBase


def test_service_exposes_lifecycle_api():
    service = GraphBuildService(lambda: None, extractor=object())
    for name in ("create_task", "get_status", "run", "retry", "cancel", "reset_graph"):
        assert callable(getattr(service, name))


@pytest.mark.asyncio
async def test_retry_missing_task_is_rejected():
    service = GraphBuildService(lambda: None)
    service.get_status = lambda **kw: _none()
    with pytest.raises(ValueError):
        await service.retry(task_id="missing")


@pytest.mark.asyncio
async def test_run_persists_graph_facts_mentions_outbox_and_chunk_status(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'build.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session, session.begin():
        session.add(KnowledgeBase(
            id="kb1",
            name="KB1",
            qdrant_collection="kb1",
            scene_status="ready",
            schema_version=1,
            graph_schema={
                "allowed_entity_types": ["Topic"],
                "allowed_relation_types": [],
                "schema_version": 1,
            },
        ))
        session.add(Document(
            id="doc1",
            knowledge_base_id="kb1",
            filename="a.md",
            graph_status="pending",
        ))
        session.add(
            KnowledgeChunk(
                id="chunk1",
                kb_id="kb1",
                document_id="doc1",
                content_generation=1,
                chunk_key="a",
                content_hash="a",
                chunk_index=0,
                content="噪声监测",
                embedding_text="噪声监测",
                graph_status="pending",
            )
        )

    class Extractor:
        async def extract_chunk(self, *, kb_id, chunk, schema):
            return ChunkGraphExtraction(
                chunk_id=chunk.id,
                extractor_name="test",
                entities=[
                    ExtractedEntity(
                        local_id="noise",
                        entity_type="Topic",
                        name="噪声",
                        evidence_text=chunk.content,
                    )
                ],
            )

    service = GraphBuildService(factory, extractor=Extractor(), concurrency=1)
    task = await service.create_task("kb1")
    await service.run(task.id)

    async with factory() as session:
        chunk = await session.get(KnowledgeChunk, "chunk1")
        entity_count = await session.scalar(
            select(func.count()).select_from(KnowledgeGraphEntity)
        )
        entity = await session.scalar(select(KnowledgeGraphEntity))
        mention_count = await session.scalar(
            select(func.count()).select_from(KnowledgeGraphEntityMention)
        )
        outbox_count = await session.scalar(
            select(func.count()).select_from(KnowledgeIndexOutbox)
        )
        build = await session.get(KnowledgeGraphBuildTask, task.id)
        document = await session.get(Document, "doc1")

    assert chunk.graph_status == "completed"
    assert entity_count == mention_count == outbox_count == 1
    assert entity.schema_version == 1
    assert build.status == "completed"
    assert document.graph_status == "completed"

    async with factory() as session, session.begin():
        entity = await session.scalar(select(KnowledgeGraphEntity))
        entity.schema_version = 0
    rebuild = await service.create_task("kb1", mode="pending")
    assert rebuild.mode == "reset_and_build"
    await engine.dispose()


async def _none():
    return None
