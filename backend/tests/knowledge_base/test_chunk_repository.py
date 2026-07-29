import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.chunk_diff import build_chunk_drafts
from app.knowledge_base.graph_models import KnowledgeChunk
from app.knowledge_base.models import Document, KnowledgeBase


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        kb = KnowledgeBase(
            id="kb1",
            name="测试知识库",
            qdrant_collection="kb_kb1",
        )
        document = Document(
            id="doc1",
            knowledge_base_id="kb1",
            filename="source.md",
            content_generation=2,
        )
        session.add_all([kb, document])
        await session.flush()

        old_drafts = build_chunk_drafts(
            [
                {"content": "A", "start_char": 0, "end_char": 1},
                {"content": "B", "start_char": 2, "end_char": 3},
            ]
        )
        for draft in old_drafts:
            session.add(
                KnowledgeChunk(
                    id=f"old-{draft.chunk_index}",
                    kb_id="kb1",
                    document_id="doc1",
                    content_generation=1,
                    chunk_key=draft.chunk_key,
                    content_hash=draft.content_hash,
                    chunk_index=draft.chunk_index,
                    content=draft.content,
                    embedding_text=draft.embedding_text,
                    context_prefix=draft.context_prefix,
                    start_char=draft.start_char,
                    end_char=draft.end_char,
                )
            )
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_replace_document_chunks_reuses_adds_and_reports_removed(db_session):
    from app.knowledge_base.chunk_repository import KnowledgeChunkRepository

    repository = KnowledgeChunkRepository(db_session)
    drafts = build_chunk_drafts(
        [
            {"content": "A", "start_char": 10, "end_char": 11},
            {"content": "C", "start_char": 12, "end_char": 13},
        ]
    )

    result = await repository.replace_document_chunks(
        kb_id="kb1",
        document_id="doc1",
        content_generation=2,
        drafts=drafts,
    )

    assert [chunk.id for chunk in result.reused] == ["old-0"]
    assert result.reused[0].content_generation == 2
    assert result.reused[0].start_char == 10
    assert [chunk.content for chunk in result.added] == ["C"]
    assert [chunk.id for chunk in result.removed] == ["old-1"]


@pytest.mark.asyncio
async def test_replace_document_chunks_rejects_stale_generation(db_session):
    from app.knowledge_base.chunk_repository import (
        KnowledgeChunkRepository,
        StaleContentGeneration,
    )

    repository = KnowledgeChunkRepository(db_session)

    with pytest.raises(StaleContentGeneration, match="expected generation 1, current is 2"):
        await repository.replace_document_chunks(
            kb_id="kb1",
            document_id="doc1",
            content_generation=1,
            drafts=[],
        )


@pytest.mark.asyncio
async def test_chunk_status_updates_are_scoped_to_requested_ids(db_session):
    from app.knowledge_base.chunk_repository import KnowledgeChunkRepository

    repository = KnowledgeChunkRepository(db_session)

    await repository.mark_vector_status(["old-0"], "failed", "qdrant unavailable")
    await repository.mark_graph_status(["old-1"], "completed")
    await db_session.commit()

    chunks = {chunk.id: chunk for chunk in await repository.list_by_document("doc1")}
    assert chunks["old-0"].vector_status == "failed"
    assert chunks["old-0"].last_error == "qdrant unavailable"
    assert chunks["old-1"].vector_status == "pending"
    assert chunks["old-1"].graph_status == "completed"


@pytest.mark.asyncio
async def test_reused_chunk_is_reindexed_when_embedding_text_changes(db_session):
    from app.knowledge_base.chunk_repository import KnowledgeChunkRepository

    repository = KnowledgeChunkRepository(db_session)
    await repository.mark_vector_status(["old-0"], "indexed")
    drafts = build_chunk_drafts(
        [
            {"content": "A", "embedding_text": "new context A"},
            {"content": "B"},
        ]
    )

    result = await repository.replace_document_chunks(
        kb_id="kb1",
        document_id="doc1",
        content_generation=2,
        drafts=drafts,
    )

    assert result.reused[0].id == "old-0"
    assert result.reused[0].vector_status == "pending"
    assert result.reused[0].embedding_text == "new context A"
