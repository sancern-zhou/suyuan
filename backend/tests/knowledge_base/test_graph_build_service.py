"""Contract tests for graph build executor."""
import asyncio
from datetime import datetime, timedelta
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
from app.knowledge_base.scene_models import KnowledgeGraphExtractionRun


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
        extraction_run = await session.scalar(select(KnowledgeGraphExtractionRun))

    assert chunk.graph_status == "completed"
    assert entity_count == mention_count == outbox_count == 1
    assert entity.schema_version == 1
    assert build.status == "completed"
    assert document.graph_status == "completed"
    assert extraction_run is not None
    assert extraction_run.status == "completed"
    assert extraction_run.chunk_id == "chunk1"

    async with factory() as session, session.begin():
        entity = await session.scalar(select(KnowledgeGraphEntity))
        entity.schema_version = 0
    rebuild = await service.create_task("kb1", mode="pending")
    assert rebuild.mode == "reset_and_build"
    await engine.dispose()


@pytest.mark.asyncio
async def test_long_extraction_renews_lease_and_completes(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'heartbeat.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session, session.begin():
        session.add(KnowledgeBase(
            id="kb-heartbeat",
            name="Heartbeat KB",
            qdrant_collection="kb-heartbeat",
            scene_status="ready",
            schema_version=1,
            graph_schema={
                "allowed_entity_types": ["Topic"],
                "allowed_relation_types": [],
                "schema_version": 1,
            },
        ))
        session.add(Document(
            id="doc-heartbeat",
            knowledge_base_id="kb-heartbeat",
            filename="slow.md",
            graph_status="pending",
        ))
        session.add(KnowledgeChunk(
            id="chunk-heartbeat",
            kb_id="kb-heartbeat",
            document_id="doc-heartbeat",
            content_generation=1,
            chunk_key="slow",
            content_hash="slow",
            chunk_index=0,
            content="慢请求测试",
            embedding_text="慢请求测试",
            graph_status="pending",
        ))

    class SlowExtractor:
        async def extract_chunk(self, *, kb_id, chunk, schema):
            await asyncio.sleep(1.2)
            return ChunkGraphExtraction(
                chunk_id=chunk.id,
                extractor_name="slow-test",
                entities=[ExtractedEntity(
                    local_id="slow",
                    entity_type="Topic",
                    name="慢请求",
                    evidence_text=chunk.content,
                )],
            )

    service = GraphBuildService(
        factory,
        extractor=SlowExtractor(),
        batch_size=1,
        concurrency=1,
        lease_seconds=1,
    )
    task = await service.create_task("kb-heartbeat")
    result = await service.run(task.id)

    assert result.status == "completed"
    async with factory() as session:
        chunk = await session.get(KnowledgeChunk, "chunk-heartbeat")
        extraction_run = await session.scalar(select(KnowledgeGraphExtractionRun))
    assert chunk.graph_status == "completed"
    assert extraction_run.status == "completed"
    await engine.dispose()


@pytest.mark.asyncio
async def test_recover_expired_marks_orphan_extraction_runs_failed(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'recovery.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    now = datetime.utcnow()
    async with factory() as session, session.begin():
        session.add(KnowledgeBase(
            id="kb-recovery",
            name="Recovery KB",
            qdrant_collection="kb-recovery",
            scene_status="ready",
            schema_version=1,
        ))
        session.add(KnowledgeGraphBuildTask(
            id="task-recovery",
            kb_id="kb-recovery",
            status="running",
            started_at=now - timedelta(minutes=6),
            lease_until=now - timedelta(minutes=1),
            total_chunks=1,
            remaining_chunks=1,
            created_by="test",
        ))
        session.add(KnowledgeGraphExtractionRun(
            id="run-orphan",
            kb_id="kb-recovery",
            document_id="doc-recovery",
            chunk_id="chunk-recovery",
            content_generation=1,
            scene_profile_version=1,
            schema_version=1,
            prompt_version="test",
            model_name="test",
            status="running",
            created_at=now - timedelta(minutes=2),
        ))

    service = GraphBuildService(factory)
    assert await service.recover_expired_tasks(kb_id="kb-recovery") == ["task-recovery"]
    async with factory() as session:
        task = await session.get(KnowledgeGraphBuildTask, "task-recovery")
        run = await session.get(KnowledgeGraphExtractionRun, "run-orphan")
    assert task.status == "queued"
    assert run.status == "failed"
    assert run.validation_errors == ["orphaned_after_graph_build_lease_expired"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_resumed_build_preserves_cumulative_chunk_counts(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'resume-counts.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session, session.begin():
        session.add(KnowledgeBase(
            id="kb-resume",
            name="Resume KB",
            qdrant_collection="kb-resume",
            scene_status="ready",
            schema_version=1,
            graph_schema={
                "allowed_entity_types": ["Topic"],
                "allowed_relation_types": [],
                "schema_version": 1,
            },
        ))
        session.add(Document(
            id="doc-resume",
            knowledge_base_id="kb-resume",
            filename="resume.md",
            graph_status="processing",
        ))
        session.add_all([
            KnowledgeChunk(
                id="chunk-resume-done",
                kb_id="kb-resume",
                document_id="doc-resume",
                content_generation=1,
                chunk_key="done",
                content_hash="done",
                chunk_index=0,
                content="已完成",
                embedding_text="已完成",
                graph_status="completed",
            ),
            KnowledgeChunk(
                id="chunk-resume-pending",
                kb_id="kb-resume",
                document_id="doc-resume",
                content_generation=1,
                chunk_key="pending",
                content_hash="pending",
                chunk_index=1,
                content="待完成",
                embedding_text="待完成",
                graph_status="pending",
            ),
        ])
        session.add(KnowledgeGraphBuildTask(
            id="task-resume",
            kb_id="kb-resume",
            status="queued",
            total_chunks=2,
            remaining_chunks=1,
            created_by="test",
        ))

    class Extractor:
        async def extract_chunk(self, *, kb_id, chunk, schema):
            return ChunkGraphExtraction(
                chunk_id=chunk.id,
                extractor_name="resume-test",
                entities=[ExtractedEntity(
                    local_id="resume",
                    entity_type="Topic",
                    name="恢复",
                    evidence_text=chunk.content,
                )],
            )

    result = await GraphBuildService(factory, extractor=Extractor()).run("task-resume")
    assert result.status == "completed"
    assert result.processed_chunks == 2
    assert result.remaining_chunks == 0
    await engine.dispose()


async def _none():
    return None
