"""Asynchronous, resumable knowledge graph build executor."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select

from .graph_build_models import KnowledgeGraphBuildTask
from .graph_models import KnowledgeChunk, KnowledgeGraphEntity, KnowledgeGraphRelation, KnowledgeGraphEntityMention, KnowledgeGraphRelationMention, KnowledgeIndexOutbox
from .graph_extractor import KnowledgeGraphExtractor
from .graph_repository import KnowledgeGraphRepository
from .chunk_repository import KnowledgeChunkRepository
from .models import KnowledgeBase


class GraphBuildService:
    def __init__(self, session_factory, *, extractor=None, batch_size=20, lease_seconds=300, concurrency=4):
        self.session_factory = session_factory
        self.extractor = extractor
        self.batch_size = batch_size
        self.lease_seconds = lease_seconds
        self.concurrency = concurrency
        self._cancelled: set[str] = set()

    def _session(self):
        return self.session_factory()

    async def create_task(self, kb_id, mode="pending", batch_size=None, user_id=None):
        async with self._session() as db:
            active = await db.scalar(select(KnowledgeGraphBuildTask).where(KnowledgeGraphBuildTask.kb_id == kb_id, KnowledgeGraphBuildTask.status.in_(["queued", "running"])))
            if active:
                raise ValueError("knowledge graph build already queued or running")
            chunks = (await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.kb_id == kb_id, KnowledgeChunk.graph_status != "completed"))).scalars().all()
            task = KnowledgeGraphBuildTask(kb_id=kb_id, mode=mode, created_by=user_id or "system", total_chunks=len(chunks), remaining_chunks=len(chunks))
            db.add(task); await db.commit(); await db.refresh(task)
            return task

    async def get_status(self, kb_id=None, task_id=None):
        async with self._session() as db:
            q = select(KnowledgeGraphBuildTask).where(KnowledgeGraphBuildTask.id == task_id) if task_id else select(KnowledgeGraphBuildTask).where(KnowledgeGraphBuildTask.kb_id == kb_id).order_by(KnowledgeGraphBuildTask.created_at.desc())
            return await db.scalar(q)

    async def run(self, task_id):
        async with self._session() as db:
            task = await db.get(KnowledgeGraphBuildTask, task_id)
            if not task: raise ValueError("task not found")
            task.status = "running"; task.started_at = datetime.utcnow(); task.lease_until = datetime.utcnow() + timedelta(seconds=self.lease_seconds); await db.commit()
            chunks = (await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.kb_id == task.kb_id, KnowledgeChunk.graph_status != "completed"))).scalars().all()
        sem = asyncio.Semaphore(self.concurrency)
        async def one(chunk):
            async with sem:
                if task_id in self._cancelled: return False, None
                try:
                    async with self._session() as db:
                        schema = (await db.get(KnowledgeBase, task.kb_id)).graph_schema or {}
                        extractor = self.extractor or KnowledgeGraphExtractor()
                        extraction = await extractor.extract_chunk(kb_id=task.kb_id, chunk=chunk, schema=schema)
                        await KnowledgeGraphRepository(db).upsert_chunk_extraction(kb_id=task.kb_id, document_id=chunk.document_id, extraction=extraction, extraction_run_id=str(uuid4()))
                        chunk = await db.get(KnowledgeChunk, chunk.id); chunk.graph_status = "completed"; await db.commit()
                    return True, None
                except Exception as exc:
                    async with self._session() as db:
                        c = await db.get(KnowledgeChunk, chunk.id)
                        if c: c.graph_status = "failed"; c.last_error = str(exc); await db.commit()
                    return False, str(exc)
        results = []
        for i in range(0, len(chunks), self.batch_size):
            if task_id in self._cancelled: break
            results.extend(await asyncio.gather(*(one(c) for c in chunks[i:i+self.batch_size])))
        async with self._session() as db:
            task = await db.get(KnowledgeGraphBuildTask, task_id)
            task.processed_chunks = sum(1 for ok, _ in results if ok); task.failed_chunks = sum(1 for ok, _ in results if not ok); task.remaining_chunks = max(0, len(chunks)-len(results)); task.status = "cancelled" if task_id in self._cancelled else ("partial" if task.failed_chunks else "completed"); task.completed_at = datetime.utcnow(); await db.commit()
        return await self.get_status(task_id=task_id)

    async def retry(self, task_id=None, kb_id=None):
        return await self.create_task(kb_id or (await self.get_status(task_id=task_id)).kb_id, "pending", self.batch_size, "system")

    async def cancel(self, task_id):
        self._cancelled.add(task_id)
        async with self._session() as db:
            task = await db.get(KnowledgeGraphBuildTask, task_id)
            if task: task.cancel_requested = True; await db.commit()

    async def reset_graph(self, kb_id):
        async with self._session() as db:
            await db.execute(delete(KnowledgeGraphEntityMention).where(KnowledgeGraphEntityMention.kb_id == kb_id)); await db.execute(delete(KnowledgeGraphRelationMention).where(KnowledgeGraphRelationMention.kb_id == kb_id)); await db.execute(delete(KnowledgeGraphRelation).where(KnowledgeGraphRelation.kb_id == kb_id)); await db.execute(delete(KnowledgeGraphEntity).where(KnowledgeGraphEntity.kb_id == kb_id)); await db.execute(delete(KnowledgeIndexOutbox).where(KnowledgeIndexOutbox.kb_id == kb_id)); await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.kb_id == kb_id));
            for c in (await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.kb_id == kb_id))).scalars(): c.graph_status = "pending"; c.last_error = None
            await db.commit()
