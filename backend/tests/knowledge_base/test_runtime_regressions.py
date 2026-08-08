import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.graph_models import KnowledgeChunk
from app.knowledge_base.graph_repository import KnowledgeGraphRepository
from app.knowledge_base.index_outbox import KnowledgeIndexOutboxRepository
from app.knowledge_base.models import Document, DocumentStatus, KnowledgeBase
from app.knowledge_base.service import KnowledgeBaseService
from app.knowledge_base.tasks import DocumentProcessingQueue
from app.services.llm_failover import get_llm_pool_semaphore


def test_llm_semaphores_are_isolated_by_event_loop():
    async def read_pair():
        first = get_llm_pool_semaphore("bailian", "qwen3.6-flash")
        second = get_llm_pool_semaphore("bailian", "qwen3.6-flash")
        return first, second

    first_loop_pair = asyncio.run(read_pair())
    second_loop_pair = asyncio.run(read_pair())

    assert first_loop_pair[0] is first_loop_pair[1]
    assert first_loop_pair[0] is not second_loop_pair[0]


@pytest.mark.asyncio
async def test_document_queue_forwards_processing_options(monkeypatch):
    captured = {}

    class FakeDB:
        async def execute(self, statement):
            return SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(id="doc1"))

        async def close(self):
            captured["closed"] = True

    class FakeService:
        async def get_knowledge_base(self, kb_id):
            return SimpleNamespace(id=kb_id)

        async def ingest_document(self, doc_id, **options):
            captured["doc_id"] = doc_id
            captured["options"] = options

    queue = DocumentProcessingQueue(max_workers=1)
    monkeypatch.setattr(queue, "_get_db_session", lambda: _async_value(FakeDB()))
    monkeypatch.setattr(queue, "_get_service", lambda db: _async_value(FakeService()))
    task = await queue.enqueue(
        "doc1",
        "kb1",
        "/tmp/report.pdf",
        "user1",
        processing_options={"chunking_strategy": "llm", "llm_mode": "online"},
    )

    await queue._process_task(task, worker_id=0)

    assert captured["doc_id"] == "doc1"
    assert captured["options"] == {
        "chunking_strategy": "llm",
        "llm_mode": "online",
    }
    assert captured["closed"] is True


@pytest.mark.asyncio
async def test_document_queue_recovers_interrupted_processing_once(monkeypatch, tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'recovery.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session, session.begin():
        session.add(KnowledgeBase(id="kb1", name="KB1", qdrant_collection="kb1"))
        session.add(
            Document(
                id="doc1",
                knowledge_base_id="kb1",
                filename="report.pdf",
                file_path="/tmp/report.pdf",
                status=DocumentStatus.PROCESSING,
                ingestion_status="processing",
            )
        )

    queued = []
    queue = DocumentProcessingQueue(max_workers=1)

    async def record_enqueue(**kwargs):
        queued.append(kwargs)

    monkeypatch.setattr("app.db.database.async_session", factory)
    monkeypatch.setattr(queue, "enqueue", record_enqueue)

    assert await queue.recover_interrupted() == 1
    assert await queue.recover_interrupted() == 0
    assert queued[0]["doc_id"] == "doc1"
    async with factory() as session:
        document = await session.get(Document, "doc1")
        assert document.ingestion_status == "queued"
    await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_advisory_locks_cast_function_arguments():
    executed = []

    class FakeSession:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        async def execute(self, statement, params=None):
            executed.append((str(statement), params))

    session = FakeSession()
    await KnowledgeGraphRepository(session)._lock_kb_graph("kb1")
    outbox = KnowledgeIndexOutboxRepository(session=session)
    # Stop after the lock query; the max-version query is outside this regression.
    session.scalar = _raise_after_lock
    with pytest.raises(RuntimeError, match="after lock"):
        await outbox.next_payload_version("kb1", "chunk", "chunk1")

    assert len(executed) == 2
    for statement, params in executed:
        assert "hashtext(" in statement
        assert "hashtextextended" not in statement
        assert "CAST(:lock_key AS text)" in statement
        assert params["lock_key"]


@pytest.mark.asyncio
async def test_document_chunks_are_read_from_canonical_database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'chunks.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session, session.begin():
        session.add(KnowledgeBase(id="kb1", name="KB1", qdrant_collection="kb1"))
        session.add(
            Document(
                id="doc1",
                knowledge_base_id="kb1",
                filename="report.pdf",
                status=DocumentStatus.COMPLETED,
                chunk_count=1,
            )
        )
        session.add(
            KnowledgeChunk(
                id="chunk1",
                kb_id="kb1",
                document_id="doc1",
                content_generation=1,
                chunk_key="key1",
                content_hash="hash1",
                chunk_index=0,
                content="Original text",
                embedding_text="Document context\nOriginal text",
                context_prefix="Document context",
                section_path=["Section 1"],
                chunk_metadata={"topic": "Test"},
            )
        )

    async with factory() as session:
        result = await KnowledgeBaseService(
            db=session,
            vector_store=SimpleNamespace(),
        ).get_document_chunks("kb1", "doc1")

    assert result["total"] == 1
    assert result["chunks"] == [
        {
            "chunk_index": 0,
            "content": "Original text",
            "original_content": "Original text",
            "context_prefix": "Document context",
            "embedding_text": "Document context\nOriginal text",
            "chunk_id": "chunk1",
            "start_char": None,
            "end_char": None,
            "metadata": {"topic": "Test", "section_path": ["Section 1"]},
        }
    ]
    await engine.dispose()


async def _async_value(value):
    return value


async def _raise_after_lock(statement):
    raise RuntimeError("after lock")
