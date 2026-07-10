import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from app.db.database import Base
from app.knowledge_base.graph_build_service import GraphBuildService
from app.knowledge_base.models import KnowledgeBase
from app.knowledge_base.graph_models import KnowledgeChunk, KnowledgeGraphEntity, KnowledgeIndexOutbox

@pytest.mark.asyncio
async def test_reset_graph_sqlite_keeps_chunks_and_removes_facts():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    # Import models so metadata is populated; SQLite integration exercises real persistence.
    import app.knowledge_base.graph_build_models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    kb_id = "kb-integration"
    async with Session() as db:
        db.add(KnowledgeBase(id=kb_id, name="KB", qdrant_collection="qc-integration"))
        await db.flush()
        db.add(KnowledgeChunk(kb_id=kb_id, document_id="doc-missing", content_generation=1,
                              chunk_key="c", content_hash="h", chunk_index=0, content="x", embedding_text="x"))
        await db.commit()
    service = GraphBuildService(Session)
    await service.reset_graph(kb_id)
    async with Session() as db:
        assert await db.scalar(select(KnowledgeChunk).where(KnowledgeChunk.kb_id == kb_id))
        assert (await db.scalars(select(KnowledgeGraphEntity).where(KnowledgeGraphEntity.kb_id == kb_id))).all() == []
        assert (await db.scalars(select(KnowledgeIndexOutbox).where(KnowledgeIndexOutbox.kb_id == kb_id))).all() == []
    await engine.dispose()
