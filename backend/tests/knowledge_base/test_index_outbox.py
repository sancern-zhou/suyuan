from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.graph_models import KnowledgeIndexOutbox
from app.knowledge_base.index_outbox import (
    KnowledgeIndexOutboxRepository,
    KnowledgeIndexOutboxWorker,
)
from app.knowledge_base.models import KnowledgeBase


@pytest.fixture
async def outbox_repository(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'outbox.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[KnowledgeBase.__table__, KnowledgeIndexOutbox.__table__],
            )
        )
    async with factory() as session:
        session.add(
            KnowledgeBase(
                id="kb1",
                name="测试知识库",
                qdrant_collection="kb_kb1",
            )
        )
        await session.commit()
    yield KnowledgeIndexOutboxRepository(factory)
    await engine.dispose()


@pytest.mark.asyncio
async def test_enqueue_is_idempotent_and_claims_once(outbox_repository):
    payload = {
        "record_type": "entity",
        "record_id": "e1",
        "content": "实体一",
        "embedding_text": "实体一",
    }
    first = await outbox_repository.enqueue_upsert(
        kb_id="kb1",
        record_type="entity",
        record_id="e1",
        payload_version=1,
        payload=payload,
    )
    second = await outbox_repository.enqueue_upsert(
        kb_id="kb1",
        record_type="entity",
        record_id="e1",
        payload_version=1,
        payload=payload,
    )

    assert first.id == second.id
    assert await outbox_repository.pending_count() == 1
    claimed = await outbox_repository.claim_batch(limit=10)
    assert [item.id for item in claimed] == [first.id]
    assert await outbox_repository.claim_batch(limit=10) == []


@pytest.mark.asyncio
async def test_retry_uses_exponential_backoff(outbox_repository):
    item = await outbox_repository.enqueue_delete(
        kb_id="kb1",
        record_type="chunk",
        record_id="c1",
        payload_version=3,
    )
    await outbox_repository.claim_batch(limit=1)
    before = datetime.utcnow()

    await outbox_repository.mark_retry(item.id, "temporary failure")

    retried = await outbox_repository.get(item.id)
    assert retried.status == "pending"
    assert retried.attempts == 1
    assert retried.last_error == "temporary failure"
    assert retried.next_retry_at >= before + timedelta(seconds=1)


class _RetryRepository:
    def __init__(self):
        self.item = SimpleNamespace(
            id="outbox-1",
            kb_id="kb1",
            record_type="entity",
            record_id="e1",
            operation="upsert",
            payload_version=1,
            payload={
                "record_type": "entity",
                "record_id": "e1",
                "content": "实体一",
                "embedding_text": "实体一",
            },
            status="pending",
        )
        self.claimed = False

    async def claim_batch(self, limit):
        if self.item.status == "completed" or self.claimed:
            return []
        self.claimed = True
        return [self.item]

    async def is_latest(self, item):
        return True

    async def mark_retry(self, item_id, error):
        self.claimed = False
        self.item.status = "pending"

    async def mark_completed(self, item_id):
        self.item.status = "completed"


class _FailingOnceStore:
    def __init__(self):
        self.calls = 0

    async def upsert_records(self, collection_name, records):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("qdrant unavailable")
        return len(records)


@pytest.mark.asyncio
async def test_worker_retries_failed_item_then_completes():
    repository = _RetryRepository()
    store = _FailingOnceStore()
    worker = KnowledgeIndexOutboxWorker(
        repository=repository,
        vector_store=store,
        collection_resolver=lambda kb_id: "kb_kb1",
    )

    assert await worker.run_once() == 0
    assert repository.item.status == "pending"
    assert await worker.run_once() == 1
    assert repository.item.status == "completed"


@pytest.mark.asyncio
async def test_worker_discards_superseded_payload_without_indexing():
    repository = _RetryRepository()
    repository.is_latest = lambda item: _async_value(False)
    store = _FailingOnceStore()
    worker = KnowledgeIndexOutboxWorker(
        repository=repository,
        vector_store=store,
        collection_resolver=lambda kb_id: "kb_kb1",
    )

    assert await worker.run_once() == 1
    assert repository.item.status == "completed"
    assert store.calls == 0


async def _async_value(value):
    return value
