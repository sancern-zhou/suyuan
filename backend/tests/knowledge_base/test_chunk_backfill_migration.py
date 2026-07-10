import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.graph_models import KnowledgeChunk
from app.knowledge_base.models import Document, KnowledgeBase
from scripts.migrate_unified_knowledge_graph import ChunkBackfillMigrator


class _Point:
    def __init__(self, payload):
        self.payload = payload


class _Qdrant:
    def scroll(self, **kwargs):
        return (
            [
                _Point({"document_id": "doc1", "chunk_id": "legacy-1", "chunk_index": 0, "content": "A"}),
                _Point({"document_id": "doc1", "chunk_id": "legacy-2", "chunk_index": 1, "content": "B"}),
            ],
            None,
        )


@pytest.mark.asyncio
async def test_chunk_backfill_is_repeatable_and_marks_unrecovered_metadata(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'backfill.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        session.add(KnowledgeBase(id="kb1", name="KB", qdrant_collection="kb_kb1"))
        session.add(Document(id="doc1", knowledge_base_id="kb1", filename="a.md"))
        await session.commit()

    migrator = ChunkBackfillMigrator(factory, _Qdrant())
    dry_run = await migrator.migrate_kb("kb1", apply=False)
    first = await migrator.migrate_kb("kb1", apply=True)
    second = await migrator.migrate_kb("kb1", apply=True)

    assert dry_run["qdrant_points"] == 2
    assert first["postgres_chunks"] == 2
    assert second["postgres_chunks"] == 2
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(KnowledgeChunk)) == 2
        chunks = list((await session.execute(select(KnowledgeChunk))).scalars())
        assert {chunk.chunk_metadata["metadata_recovered"] for chunk in chunks} == {False}
    await engine.dispose()
