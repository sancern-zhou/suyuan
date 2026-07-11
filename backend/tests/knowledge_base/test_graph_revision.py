import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.models import KnowledgeBase


@pytest.mark.asyncio
async def test_bump_graph_revision_is_monotonic():
    from app.knowledge_base.graph_revision import bump_graph_revision

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session, session.begin():
        session.add(KnowledgeBase(id="kb-revision", name="KB", qdrant_collection="qc-revision"))
    async with sessions() as session, session.begin():
        assert await bump_graph_revision(session, "kb-revision") == 1
    async with sessions() as session, session.begin():
        assert await bump_graph_revision(session, "kb-revision") == 2
    await engine.dispose()
