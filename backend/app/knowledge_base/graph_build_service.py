"""Resumable knowledge graph build executor."""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from .graph_build_models import KnowledgeGraphBuildTask
from .graph_models import KnowledgeChunk, KnowledgeGraphEntity, KnowledgeGraphRelation, KnowledgeGraphEntityMention, KnowledgeGraphRelationMention, KnowledgeIndexOutbox
from .models import KnowledgeBase
from .ingestion_service import KnowledgeIngestionService
from .graph_extractor import KnowledgeGraphExtractor

class GraphBuildService:
    def __init__(self, session_factory, *, extractor=None, batch_size=20, lease_seconds=300, concurrency=4):
        self.session_factory, self.extractor = session_factory, extractor
        self.batch_size, self.lease_seconds, self.concurrency = batch_size, lease_seconds, max(1, concurrency)

    def _session(self): return self.session_factory()

    async def create_task(self, kb_id, mode="pending", batch_size=None, user_id=None):
        async with self._session() as db:
            active = await db.scalar(select(KnowledgeGraphBuildTask).where(KnowledgeGraphBuildTask.kb_id==kb_id, KnowledgeGraphBuildTask.status.in_(["queued","running"])))
            if active: raise ValueError("knowledge graph build already queued or running")
            n = await db.scalar(select(KnowledgeChunk.id).where(KnowledgeChunk.kb_id==kb_id, KnowledgeChunk.graph_status!="completed"))
            chunks = (await db.execute(select(KnowledgeChunk.id).where(KnowledgeChunk.kb_id==kb_id, KnowledgeChunk.graph_status!="completed"))).scalars().all()
            task = KnowledgeGraphBuildTask(kb_id=kb_id, mode=mode, created_by=user_id or "system", total_chunks=len(chunks), remaining_chunks=len(chunks))
            db.add(task)
            try: await db.commit()
            except IntegrityError: await db.rollback(); raise ValueError("knowledge graph build already queued or running")
            await db.refresh(task); return task

    async def get_status(self, kb_id=None, task_id=None):
        async with self._session() as db:
            q = select(KnowledgeGraphBuildTask).where(KnowledgeGraphBuildTask.id==task_id) if task_id else select(KnowledgeGraphBuildTask).where(KnowledgeGraphBuildTask.kb_id==kb_id).order_by(KnowledgeGraphBuildTask.created_at.desc())
            return await db.scalar(q)

    async def _set_task(self, tid, **vals):
        async with self._session() as db:
            t=await db.get(KnowledgeGraphBuildTask, tid)
            if t:
                for k,v in vals.items(): setattr(t,k,v)
                await db.commit()

    async def run(self, task_id):
        task = await self.get_status(task_id=task_id)
        if not task: raise ValueError("task not found")
        await self._set_task(task_id, status="running", started_at=datetime.utcnow(), lease_until=datetime.utcnow()+timedelta(seconds=self.lease_seconds))
        ids = list(task.failed_chunk_ids or [])
        async with self._session() as db:
            q=select(KnowledgeChunk).where(KnowledgeChunk.kb_id==task.kb_id, KnowledgeChunk.graph_status!="completed")
            if ids: q=q.where(KnowledgeChunk.id.in_(ids))
            chunks=(await db.execute(q)).scalars().all()
        succeeded=[]; failed=[]; cancelled=False
        async def one(c):
            try:
                async with self._session() as db: kb=await db.get(KnowledgeBase, task.kb_id); schema=kb.graph_schema or {}
                extractor=self.extractor or KnowledgeGraphExtractor()
                extraction=await extractor.extract_chunk(kb_id=task.kb_id, chunk=c, schema=schema)
                snap=SimpleNamespace(kb_id=task.kb_id, document_id=c.document_id, content_generation=c.content_generation)
                svc=KnowledgeIngestionService(session_factory=self.session_factory, processor=None, extractor=extractor)
                await svc._persist_graph_extraction(snap,c,extraction); return True,None
            except Exception as e:
                async with self._session() as db:
                    cc=await db.get(KnowledgeChunk,c.id)
                    if cc: cc.graph_status="failed"; cc.last_error=str(e); await db.commit()
                return False,str(e)
        for i in range(0,len(chunks),self.batch_size):
            cur=await self.get_status(task_id=task_id)
            if cur and cur.cancel_requested: cancelled=True; break
            for c,(ok,err) in zip(chunks[i:i+self.batch_size], await asyncio.gather(*(one(c) for c in chunks[i:i+self.batch_size]))):
                (succeeded if ok else failed).append(c.id)
            await self._set_task(task_id, processed_chunks=len(succeeded), failed_chunks=len(failed), failed_chunk_ids=failed, remaining_chunks=max(0,len(chunks)-len(succeeded)-len(failed)))
        status="cancelled" if cancelled else ("partial" if failed else "completed")
        await self._set_task(task_id,status=status,completed_at=datetime.utcnow(),lease_until=None,failed_chunk_ids=failed,processed_chunks=len(succeeded),failed_chunks=len(failed),remaining_chunks=max(0,len(chunks)-len(succeeded)-len(failed)))
        return await self.get_status(task_id=task_id)

    async def retry(self, task_id=None, kb_id=None):
        old=await self.get_status(task_id=task_id,kb_id=kb_id)
        if not old: raise ValueError("task not found")
        ids=list(old.failed_chunk_ids or [])
        if not ids:
            async with self._session() as db:
                ids=(await db.execute(select(KnowledgeChunk.id).where(KnowledgeChunk.kb_id==old.kb_id, KnowledgeChunk.graph_status=="failed"))).scalars().all()
        task=await self.create_task(old.kb_id, user_id="system")
        await self._set_task(task.id, failed_chunk_ids=ids, total_chunks=len(ids), remaining_chunks=len(ids))
        return await self.get_status(task_id=task.id)

    async def cancel(self, task_id):
        await self._set_task(task_id,cancel_requested=True)

    async def reset_graph(self, kb_id):
        async with self._session() as db:
            for model in (KnowledgeGraphEntityMention,KnowledgeGraphRelationMention,KnowledgeGraphRelation,KnowledgeGraphEntity,KnowledgeIndexOutbox): await db.execute(delete(model).where(model.kb_id==kb_id))
            for c in (await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.kb_id==kb_id))).scalars(): c.graph_status="pending"; c.last_error=None
            await db.commit()
