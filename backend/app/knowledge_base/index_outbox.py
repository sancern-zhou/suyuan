"""Transactional outbox for rebuilding typed Qdrant knowledge records."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.knowledge_base.graph_models import KnowledgeIndexOutbox

logger = structlog.get_logger()

CollectionResolver = Callable[[str], str | Awaitable[str]]


class KnowledgeIndexOutboxRepository:
    """Persist and claim idempotent knowledge-index operations."""

    def __init__(self, session_factory=None, *, session=None):
        if session_factory is None and session is None:
            raise ValueError("session_factory or session is required")
        self.session_factory = session_factory
        self.session = session

    @classmethod
    def for_session(cls, session) -> KnowledgeIndexOutboxRepository:
        """Bind enqueue operations to the caller's fact transaction."""
        return cls(session=session)

    async def enqueue_upsert(
        self,
        kb_id: str,
        record_type: str,
        record_id: str,
        payload_version: int,
        payload: dict[str, Any],
    ) -> KnowledgeIndexOutbox:
        return await self._enqueue(
            kb_id=kb_id,
            record_type=record_type,
            record_id=record_id,
            operation="upsert",
            payload_version=payload_version,
            payload=payload,
        )

    async def enqueue_delete(
        self,
        kb_id: str,
        record_type: str,
        record_id: str,
        payload_version: int,
    ) -> KnowledgeIndexOutbox:
        return await self._enqueue(
            kb_id=kb_id,
            record_type=record_type,
            record_id=record_id,
            operation="delete",
            payload_version=payload_version,
            payload={},
        )

    async def _enqueue(
        self,
        *,
        kb_id: str,
        record_type: str,
        record_id: str,
        operation: str,
        payload_version: int,
        payload: dict[str, Any],
    ) -> KnowledgeIndexOutbox:
        if record_type not in {"chunk", "entity", "relation"}:
            raise ValueError(f"Unsupported knowledge record type: {record_type}")
        if payload_version < 1:
            raise ValueError("payload_version must be positive")

        identity = (record_type, record_id, operation, payload_version)
        if self.session is not None:
            existing = await self._find_identity(self.session, identity)
            if existing is not None:
                return existing
            item = KnowledgeIndexOutbox(
                kb_id=kb_id,
                record_type=record_type,
                record_id=record_id,
                operation=operation,
                payload_version=payload_version,
                payload=payload,
            )
            self.session.add(item)
            await self.session.flush()
            return item

        async with self.session_factory() as session:
            existing = await self._find_identity(session, identity)
            if existing is not None:
                return existing
            item = KnowledgeIndexOutbox(
                kb_id=kb_id,
                record_type=record_type,
                record_id=record_id,
                operation=operation,
                payload_version=payload_version,
                payload=payload,
            )
            session.add(item)
            try:
                await session.commit()
                return item
            except IntegrityError:
                await session.rollback()

        # A concurrent transaction inserted the same idempotency key.
        async with self.session_factory() as session:
            existing = await self._find_identity(session, identity)
            if existing is None:
                raise RuntimeError("Outbox idempotency conflict could not be resolved")
            return existing

    @staticmethod
    async def _find_identity(session, identity) -> KnowledgeIndexOutbox | None:
        record_type, record_id, operation, payload_version = identity
        result = await session.execute(
            select(KnowledgeIndexOutbox).where(
                KnowledgeIndexOutbox.record_type == record_type,
                KnowledgeIndexOutbox.record_id == record_id,
                KnowledgeIndexOutbox.operation == operation,
                KnowledgeIndexOutbox.payload_version == payload_version,
            )
        )
        return result.scalar_one_or_none()

    async def claim_batch(self, limit: int) -> list[KnowledgeIndexOutbox]:
        if limit <= 0:
            return []
        async with self.session_factory() as session, session.begin():
            result = await session.execute(
                select(KnowledgeIndexOutbox)
                .where(
                    KnowledgeIndexOutbox.status == "pending",
                    KnowledgeIndexOutbox.next_retry_at <= datetime.utcnow(),
                )
                .order_by(
                    KnowledgeIndexOutbox.created_at,
                    KnowledgeIndexOutbox.payload_version,
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            items = list(result.scalars())
            for item in items:
                item.status = "processing"
            await session.flush()
            return items

    async def is_latest(self, item: KnowledgeIndexOutbox) -> bool:
        """Return false when a newer generation supersedes this operation."""
        async with self.session_factory() as session:
            latest = await session.scalar(
                select(func.max(KnowledgeIndexOutbox.payload_version)).where(
                    KnowledgeIndexOutbox.kb_id == item.kb_id,
                    KnowledgeIndexOutbox.record_type == item.record_type,
                    KnowledgeIndexOutbox.record_id == item.record_id,
                )
            )
        return latest is None or item.payload_version >= latest

    async def mark_completed(self, item_id: str) -> None:
        async with self.session_factory() as session, session.begin():
            item = await session.get(KnowledgeIndexOutbox, item_id)
            if item is None:
                return
            item.status = "completed"
            item.last_error = None
            if item.record_type == "chunk" and item.operation == "upsert":
                from app.knowledge_base.graph_models import KnowledgeChunk

                chunk = await session.get(KnowledgeChunk, item.record_id)
                if chunk is not None and chunk.content_generation == item.payload_version:
                    chunk.vector_status = "indexed"
                    chunk.last_error = None

    async def mark_retry(self, item_id: str, error: str) -> None:
        async with self.session_factory() as session, session.begin():
            item = await session.get(KnowledgeIndexOutbox, item_id)
            if item is None:
                return
            item.attempts += 1
            delay = min(300, 2**item.attempts)
            item.status = "pending"
            item.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
            item.last_error = error

    async def get(self, item_id: str) -> KnowledgeIndexOutbox | None:
        async with self.session_factory() as session:
            return await session.get(KnowledgeIndexOutbox, item_id)

    async def pending_count(self) -> int:
        async with self.session_factory() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(KnowledgeIndexOutbox)
                    .where(KnowledgeIndexOutbox.status == "pending")
                )
                or 0
            )


class KnowledgeIndexOutboxWorker:
    """Apply outbox operations to the rebuildable Qdrant index."""

    def __init__(
        self,
        *,
        repository: KnowledgeIndexOutboxRepository,
        vector_store,
        collection_resolver: CollectionResolver,
        batch_size: int = 50,
        idle_poll_seconds: float = 1.0,
    ):
        self.repository = repository
        self.vector_store = vector_store
        self.collection_resolver = collection_resolver
        self.batch_size = batch_size
        self.idle_poll_seconds = idle_poll_seconds
        self._stopping = asyncio.Event()
        self._batch_lock = asyncio.Lock()

    async def run_once(self) -> int:
        succeeded = 0
        async with self._batch_lock:
            items = await self.repository.claim_batch(self.batch_size)
            for item in items:
                try:
                    if not await self.repository.is_latest(item):
                        await self.repository.mark_completed(item.id)
                        succeeded += 1
                        continue
                    collection_name = self.collection_resolver(item.kb_id)
                    if inspect.isawaitable(collection_name):
                        collection_name = await collection_name
                    if item.operation == "upsert":
                        await self.vector_store.upsert_records(
                            collection_name,
                            [dict(item.payload)],
                        )
                    elif item.operation == "delete":
                        await self.vector_store.delete_records(
                            collection_name,
                            item.record_type,
                            [item.record_id],
                        )
                    else:
                        raise ValueError(f"Unsupported outbox operation: {item.operation}")
                    await self.repository.mark_completed(item.id)
                    succeeded += 1
                except Exception as exc:
                    await self.repository.mark_retry(item.id, str(exc))
                    logger.warning(
                        "knowledge_index_outbox_item_failed",
                        item_id=item.id,
                        error=str(exc),
                    )
        return succeeded

    async def run_forever(self) -> None:
        self._stopping.clear()
        while not self._stopping.is_set():
            succeeded = await self.run_once()
            if succeeded:
                continue
            try:
                await asyncio.wait_for(
                    self._stopping.wait(),
                    timeout=self.idle_poll_seconds,
                )
            except TimeoutError:
                pass

    async def stop(self) -> None:
        self._stopping.set()
        async with self._batch_lock:
            pass


_worker: KnowledgeIndexOutboxWorker | None = None
_worker_task: asyncio.Task[None] | None = None


async def _resolve_collection(kb_id: str) -> str:
    from app.db.database import async_session
    from app.knowledge_base.models import KnowledgeBase

    async with async_session() as session:
        collection = await session.scalar(
            select(KnowledgeBase.qdrant_collection).where(KnowledgeBase.id == kb_id)
        )
    if not collection:
        raise LookupError(f"Knowledge base not found: {kb_id}")
    return str(collection)


async def start_index_outbox_worker() -> None:
    global _worker, _worker_task
    if _worker_task is not None and not _worker_task.done():
        return

    from app.db.database import async_session
    from app.knowledge_base import get_vector_store

    _worker = KnowledgeIndexOutboxWorker(
        repository=KnowledgeIndexOutboxRepository(async_session),
        vector_store=get_vector_store(),
        collection_resolver=_resolve_collection,
    )
    _worker_task = asyncio.create_task(
        _worker.run_forever(),
        name="knowledge-index-outbox-worker",
    )
    logger.info("knowledge_index_outbox_worker_started")


async def stop_index_outbox_worker() -> None:
    global _worker, _worker_task
    if _worker is None:
        return
    await _worker.stop()
    if _worker_task is not None:
        await _worker_task
    _worker = None
    _worker_task = None
    logger.info("knowledge_index_outbox_worker_stopped")
