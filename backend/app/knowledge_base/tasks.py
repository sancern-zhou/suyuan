"""Database-backed document jobs shared by web and background workers."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

import structlog
from sqlalchemy import select, update

from .models import Document, DocumentStatus

logger = structlog.get_logger()
TASK_METADATA_KEY = "_processing_task"


def queue_document(document, *, processing_options=None, user_id=None):
    """Publish the job in the same transaction as the document record."""
    metadata = dict(document.extra_metadata or {})
    metadata[TASK_METADATA_KEY] = {
        "options": dict(processing_options or {}),
        "user_id": user_id,
        "attempts": 0,
        "generation": document.content_generation or 1,
    }
    metadata["processing_phase"] = "queued"
    document.extra_metadata = metadata
    document.status = DocumentStatus.PROCESSING
    document.ingestion_status = "queued"
    document.error_message = None
    document.processing_error = None


@dataclass(frozen=True)
class DocumentTask:
    doc_id: str
    kb_id: str
    generation: int
    token: str
    processing_options: dict


class DocumentProcessingQueue:
    """Claim durable jobs using row locks and renewable ownership leases."""

    def __init__(self, max_workers=3, *, session_factory=None,
                 poll_interval=1.0, lease_seconds=300, max_retries=3):
        if session_factory is None:
            from app.db.knowledge_database import knowledge_async_session
            session_factory = knowledge_async_session
        self.session_factory = session_factory
        self._max_workers = max_workers
        self.poll_interval = poll_interval
        self.lease_seconds = lease_seconds
        self.max_retries = max_retries
        self._workers = []
        self._is_running = False

    async def start(self):
        if self._is_running:
            return
        await self.recover_interrupted()
        self._is_running = True
        self._workers = [asyncio.create_task(self._worker(i))
                         for i in range(self._max_workers)]

    async def stop(self):
        self._is_running = False
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def recover_interrupted(self):
        """Adopt pre-durable-queue jobs; modern jobs recover through leases."""
        recovered = 0
        async with self.session_factory() as db, db.begin():
            documents = await db.scalars(select(Document).where(
                Document.status == DocumentStatus.PROCESSING,
                Document.ingestion_status == "processing",
            ).with_for_update(skip_locked=True))
            for document in documents:
                if TASK_METADATA_KEY not in (document.extra_metadata or {}):
                    queue_document(document)
                    recovered += 1
        return recovered

    async def claim_next(self):
        now = datetime.utcnow()
        async with self.session_factory() as db, db.begin():
            # Exclude active leases in SQL so long jobs cannot starve new ones.
            lease = Document.extra_metadata[TASK_METADATA_KEY]["lease_until"].as_string()
            document = await db.scalar(select(Document).where(
                Document.status == DocumentStatus.PROCESSING,
                Document.ingestion_status.in_(["queued", "processing"]),
                (Document.ingestion_status == "queued") | (lease <= now.isoformat()),
            ).order_by(Document.created_at).limit(1).with_for_update(skip_locked=True))
            if document is None:
                return None
            metadata = dict(document.extra_metadata or {})
            job = dict(metadata.get(TASK_METADATA_KEY) or {})
            if int(job.get("attempts", 0)) >= self.max_retries:
                document.status = DocumentStatus.FAILED
                document.ingestion_status = "failed"
                document.error_message = "Document processing lease expired after maximum attempts"
                job.pop("token", None)
                job.pop("lease_until", None)
                metadata[TASK_METADATA_KEY] = job
                document.extra_metadata = metadata
                return None
            token = uuid4().hex
            job.update(token=token, generation=document.content_generation,
                       attempts=int(job.get("attempts", 0)) + 1,
                       lease_until=(now + timedelta(seconds=self.lease_seconds)).isoformat())
            metadata[TASK_METADATA_KEY] = job
            document.extra_metadata = metadata
            document.ingestion_status = "processing"
            return DocumentTask(document.id, document.knowledge_base_id,
                                document.content_generation, token,
                                dict(job.get("options") or {}))

    async def _update_owned(self, task, *, error=None, renew=False, cancelled=False):
        async with self.session_factory() as db, db.begin():
            document = await db.scalar(select(Document).where(
                Document.id == task.doc_id).with_for_update())
            if document is None or document.content_generation != task.generation:
                return False
            metadata = dict(document.extra_metadata or {})
            job = dict(metadata.get(TASK_METADATA_KEY) or {})
            if job.get("token") != task.token:
                return False
            if renew:
                job["lease_until"] = (datetime.utcnow() + timedelta(
                    seconds=self.lease_seconds)).isoformat()
            else:
                job.pop("token", None)
                job.pop("lease_until", None)
                if (error or cancelled) and document.ingestion_status != "completed":
                    retry = cancelled or job["attempts"] < self.max_retries
                    document.status = DocumentStatus.PROCESSING if retry else DocumentStatus.FAILED
                    document.ingestion_status = "queued" if retry else "failed"
                    if cancelled:
                        job["attempts"] = max(0, job["attempts"] - 1)
                    if error:
                        document.processing_error = str(error)[:2000]
                        document.error_message = str(error)[:500]
                # On success ingestion owns the final document statuses.
            metadata[TASK_METADATA_KEY] = job
            document.extra_metadata = metadata
            return True

    async def _heartbeat(self, task, processing):
        try:
            while True:
                await asyncio.sleep(max(0.05, self.lease_seconds / 3))
                if not await self._update_owned(task, renew=True):
                    processing.cancel()
                    return
        except Exception:
            # A disconnected worker cannot keep writing after its lease expires.
            logger.exception("document_task_heartbeat_failed", doc_id=task.doc_id)
            processing.cancel()

    async def _run_ingestion(self, task):
        from app.knowledge_base.service import KnowledgeBaseService
        from app.services.llm_service import llm_service
        from config.settings import settings

        if not await self._update_owned(task, renew=True):
            return
        service = KnowledgeBaseService(session_factory=self.session_factory)
        with llm_service.use_balanced_model_tier(settings.knowledge_base_llm_model_tier), \
                llm_service.use_opencode_session(f"kb-doc-{task.doc_id}"):
            await service.ingest_document(task.doc_id, **task.processing_options)

    async def _process_task(self, task, worker_id=0):
        processing = asyncio.create_task(self._run_ingestion(task))
        heartbeat = asyncio.create_task(self._heartbeat(task, processing))
        try:
            await processing
        except asyncio.CancelledError:
            await self._update_owned(task, cancelled=True)
            # Losing one document lease must not terminate the worker itself.
            if asyncio.current_task().cancelling():
                raise
        except Exception as error:
            logger.exception("document_task_failed", doc_id=task.doc_id, worker_id=worker_id)
            await self._update_owned(task, error=error)
        else:
            await self._update_owned(task)
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def _worker(self, worker_id):
        while self._is_running:
            try:
                task = await self.claim_next()
                if task is None:
                    await asyncio.sleep(self.poll_interval)
                else:
                    await self._process_task(task, worker_id)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("document_worker_error", worker_id=worker_id)
                await asyncio.sleep(self.poll_interval)


_processing_queue = None


def get_processing_queue():
    global _processing_queue
    if _processing_queue is None:
        _processing_queue = DocumentProcessingQueue()
    return _processing_queue


async def start_processing_queue():
    await normalize_database_original_paths()
    await get_processing_queue().start()


async def normalize_database_original_paths():
    """Clear obsolete staging paths once PostgreSQL owns the original file."""
    from app.db.knowledge_database import knowledge_async_session

    async with knowledge_async_session() as db, db.begin():
        result = await db.execute(update(Document).where(
            Document.file_storage_type == "database",
            Document.original_file_oid.is_not(None),
            Document.file_path.is_not(None),
        ).values(file_path=None))
    return int(result.rowcount or 0)


async def stop_processing_queue():
    global _processing_queue
    if _processing_queue:
        await _processing_queue.stop()
        _processing_queue = None
