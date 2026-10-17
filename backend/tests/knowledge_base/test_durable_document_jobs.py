import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import Base
from app.knowledge_base.models import Document, DocumentStatus, KnowledgeBase
from app.knowledge_base.service import KnowledgeBaseService
from app.knowledge_base.tasks import DocumentProcessingQueue, TASK_METADATA_KEY, queue_document


@pytest.fixture
async def jobs(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'jobs.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(
            conn, tables=[KnowledgeBase.__table__, Document.__table__]))
    async with factory() as db, db.begin():
        db.add(KnowledgeBase(id="kb", name="KB", owner_id="user", qdrant_collection="kb"))
    monkeypatch.setattr("app.knowledge_base.service.get_document_processor", lambda: SimpleNamespace(
        get_file_type=lambda path: "md"))
    yield factory, tmp_path
    await engine.dispose()


async def upload(jobs):
    factory, tmp_path = jobs
    path = tmp_path / "document.md"
    path.write_text("document", encoding="utf-8")
    async with factory() as db:
        service = KnowledgeBaseService(db=db, vector_store=SimpleNamespace(), session_factory=factory)
        return await service.upload_document(
            "kb", str(path), "document.md", user_id="user", is_admin=True, defer_processing=True,
            chunking_strategy="sentence", chunk_size=640, chunk_overlap=40)


@pytest.mark.asyncio
async def test_separate_worker_claims_committed_upload_with_options(jobs):
    document = await upload(jobs)
    worker = DocumentProcessingQueue(session_factory=jobs[0])
    task = await worker.claim_next()
    assert task.doc_id == document.id
    assert task.processing_options == {
        "chunking_strategy": "sentence", "chunk_size": 640,
        "chunk_overlap": 40, "llm_mode": "online"}
    assert await DocumentProcessingQueue(session_factory=jobs[0]).claim_next() is None


@pytest.mark.asyncio
async def test_worker_running_before_upload_continuously_picks_up_new_jobs(jobs, monkeypatch):
    worker = DocumentProcessingQueue(max_workers=1, session_factory=jobs[0], poll_interval=0.01)
    completed = asyncio.Event()

    async def ingest(task):
        async with jobs[0]() as db, db.begin():
            doc = await db.get(Document, task.doc_id)
            doc.status = DocumentStatus.COMPLETED
            doc.ingestion_status = "completed"
        completed.set()

    monkeypatch.setattr(worker, "_run_ingestion", ingest)
    await worker.start()
    try:
        await upload(jobs)
        await asyncio.wait_for(completed.wait(), timeout=3)
    finally:
        await worker.stop()
    assert await worker.claim_next() is None


@pytest.mark.asyncio
async def test_expired_lease_recovers_and_old_owner_cannot_update(jobs):
    await upload(jobs)
    worker = DocumentProcessingQueue(session_factory=jobs[0])
    old = await worker.claim_next()
    async with jobs[0]() as db, db.begin():
        doc = await db.get(Document, old.doc_id)
        metadata = dict(doc.extra_metadata)
        metadata[TASK_METADATA_KEY] = {**metadata[TASK_METADATA_KEY],
            "lease_until": (datetime.utcnow() - timedelta(seconds=1)).isoformat()}
        doc.extra_metadata = metadata
    new = await DocumentProcessingQueue(session_factory=jobs[0]).claim_next()
    assert new.doc_id == old.doc_id and new.token != old.token
    assert not await worker._update_owned(old, error="obsolete")


@pytest.mark.asyncio
async def test_retry_budget_and_options_survive_worker_recreation(jobs, monkeypatch):
    doc = await upload(jobs)
    for attempt in range(3):
        worker = DocumentProcessingQueue(session_factory=jobs[0])
        task = await worker.claim_next()
        assert task.processing_options["chunk_size"] == 640
        async def fail(task):
            raise RuntimeError("provider unavailable")
        monkeypatch.setattr(worker, "_run_ingestion", fail)
        await worker._process_task(task)
    assert await worker.claim_next() is None
    async with jobs[0]() as db:
        doc = await db.get(Document, doc.id)
        assert doc.status == DocumentStatus.FAILED
        assert doc.ingestion_status == "failed"
        assert doc.extra_metadata[TASK_METADATA_KEY]["attempts"] == 3
        assert doc.error_message == "provider unavailable"


@pytest.mark.asyncio
async def test_heartbeat_prevents_other_worker_reclaiming_slow_job(jobs, monkeypatch):
    await upload(jobs)
    worker = DocumentProcessingQueue(session_factory=jobs[0], lease_seconds=0.3)
    task = await worker.claim_next()
    async def slow(task):
        await asyncio.sleep(0.65)
        assert await DocumentProcessingQueue(session_factory=jobs[0]).claim_next() is None
    monkeypatch.setattr(worker, "_run_ingestion", slow)
    await worker._process_task(task)


@pytest.mark.asyncio
async def test_cancelled_job_is_durable_and_generation_fences_old_updates(jobs):
    await upload(jobs)
    worker = DocumentProcessingQueue(session_factory=jobs[0])
    task = await worker.claim_next()
    assert await worker._update_owned(task, cancelled=True)
    new = await worker.claim_next()
    assert new.token != task.token
    async with jobs[0]() as db, db.begin():
        doc = await db.get(Document, new.doc_id)
        doc.content_generation += 1
    assert not await worker._update_owned(new, error="old generation")


@pytest.mark.asyncio
async def test_rolled_back_upload_publishes_no_job(jobs):
    with pytest.raises(RuntimeError):
        async with jobs[0]() as db, db.begin():
            doc = Document(id="rolled-back", knowledge_base_id="kb", filename="x.md")
            queue_document(doc, processing_options={"chunk_size": 200})
            db.add(doc)
            await db.flush()
            raise RuntimeError("rollback")
    assert await DocumentProcessingQueue(session_factory=jobs[0]).claim_next() is None



@pytest.mark.asyncio
async def test_repeated_crashes_exhaust_budget_and_invalidate_old_owner(jobs):
    await upload(jobs)
    worker = DocumentProcessingQueue(session_factory=jobs[0], max_retries=1)
    task = await worker.claim_next()
    async with jobs[0]() as db, db.begin():
        doc = await db.get(Document, task.doc_id)
        metadata = dict(doc.extra_metadata)
        metadata[TASK_METADATA_KEY] = {**metadata[TASK_METADATA_KEY],
            "lease_until": (datetime.utcnow() - timedelta(seconds=1)).isoformat()}
        doc.extra_metadata = metadata
    assert await worker.claim_next() is None
    assert not await worker._update_owned(task, renew=True)
    async with jobs[0]() as db:
        assert (await db.get(Document, task.doc_id)).status == DocumentStatus.FAILED


@pytest.mark.asyncio
async def test_lost_job_does_not_cancel_its_worker(jobs, monkeypatch):
    await upload(jobs)
    worker = DocumentProcessingQueue(session_factory=jobs[0])
    task = await worker.claim_next()
    async def cancelled(task):
        raise asyncio.CancelledError
    monkeypatch.setattr(worker, "_run_ingestion", cancelled)
    await worker._process_task(task)
    assert (await worker.claim_next()).doc_id == task.doc_id
