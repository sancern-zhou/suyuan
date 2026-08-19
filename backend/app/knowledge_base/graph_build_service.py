"""Resumable knowledge graph build executor."""
from __future__ import annotations
import asyncio
from contextlib import suppress
from datetime import datetime, timedelta
from types import SimpleNamespace
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from .graph_build_models import KnowledgeGraphBuildTask
from .graph_models import KnowledgeChunk, KnowledgeGraphEntity, KnowledgeGraphRelation, KnowledgeGraphEntityMention, KnowledgeGraphRelationMention, KnowledgeIndexOutbox
from .models import Document, KnowledgeBase
from .ingestion_service import KnowledgeIngestionService
from .graph_extractor import KnowledgeGraphExtractor
from .index_outbox import KnowledgeIndexOutboxRepository
from .graph_revision import bump_graph_revision
from .scene_models import KnowledgeGraphExtractionRun

class GraphBuildService:
    def __init__(self, session_factory, *, extractor=None, batch_size=20, lease_seconds=300, concurrency=4):
        self.session_factory, self.extractor = session_factory, extractor
        self.batch_size, self.lease_seconds, self.concurrency = batch_size, lease_seconds, max(1, concurrency)

    def _session(self): return self.session_factory()

    async def _lease_heartbeat(self, task_id, owner_token, stop_event):
        """Keep a long-running LLM batch from losing its build lease.

        A single extraction request can take longer than the default lease when
        provider failover/retries are involved.  Renewing only between batches
        lets an otherwise healthy build get marked cancelled while a batch is
        still awaiting the model.  The heartbeat is deliberately independent
        of the extraction workers so it can renew during that wait.
        """
        interval = max(0.5, min(float(self.lease_seconds) / 3.0, 30.0))
        while True:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                if not await self._renew_lease(task_id, owner_token):
                    return

    async def create_task(self, kb_id, mode="pending", batch_size=None, user_id=None):
        async with self._session() as db:
            kb = await db.get(KnowledgeBase, kb_id)
            if kb is None:
                raise ValueError("knowledge base not found")
            if kb.scene_status != "ready" or int(kb.schema_version or 0) <= 0:
                raise ValueError("scene_confirmation_required")
            if not kb.graph_enabled:
                raise ValueError("knowledge graph is disabled")
            if mode != "reset_and_build":
                stale_entity = await db.scalar(
                    select(KnowledgeGraphEntity.id).where(
                        KnowledgeGraphEntity.kb_id == kb_id,
                        KnowledgeGraphEntity.source_type == "document_fact",
                        KnowledgeGraphEntity.schema_version != kb.schema_version,
                    ).limit(1)
                )
                stale_relation = await db.scalar(
                    select(KnowledgeGraphRelation.id).where(
                        KnowledgeGraphRelation.kb_id == kb_id,
                        KnowledgeGraphRelation.source_type == "document_fact",
                        KnowledgeGraphRelation.schema_version != kb.schema_version,
                    ).limit(1)
                )
                if stale_entity is not None or stale_relation is not None:
                    mode = "reset_and_build"
            active = await db.scalar(select(KnowledgeGraphBuildTask).where(KnowledgeGraphBuildTask.kb_id==kb_id, KnowledgeGraphBuildTask.status.in_(["queued","running"])))
            if active: raise ValueError("knowledge graph build already queued or running")
            chunk_query = select(KnowledgeChunk.id).where(KnowledgeChunk.kb_id == kb_id)
            if mode != "reset_and_build":
                chunk_query = chunk_query.where(KnowledgeChunk.graph_status != "completed")
            chunks = (await db.execute(chunk_query)).scalars().all()
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

    async def _renew_lease(self, tid, owner_token):
        deadline = datetime.utcnow() + timedelta(seconds=self.lease_seconds)
        async with self._session() as db:
            result = await db.execute(
                update(KnowledgeGraphBuildTask)
                .where(
                    KnowledgeGraphBuildTask.id == tid,
                    KnowledgeGraphBuildTask.status == "running",
                    KnowledgeGraphBuildTask.started_at == owner_token,
                )
                .values(lease_until=deadline)
            )
            await db.commit()
            return bool(result.rowcount)

    async def _finish_task(self, tid, owner_token, **values):
        async with self._session() as db:
            result = await db.execute(
                update(KnowledgeGraphBuildTask)
                .where(
                    KnowledgeGraphBuildTask.id == tid,
                    KnowledgeGraphBuildTask.status == "running",
                    KnowledgeGraphBuildTask.started_at == owner_token,
                )
                .values(**values)
            )
            await db.commit()
            return bool(result.rowcount)

    async def _mark_task_failed(self, tid, error):
        async with self._session() as db:
            result = await db.execute(
                update(KnowledgeGraphBuildTask)
                .where(KnowledgeGraphBuildTask.id == tid, KnowledgeGraphBuildTask.status.in_(["queued", "running"]))
                .values(status="failed", last_error=error, completed_at=datetime.utcnow(), lease_until=None)
            )
            await db.commit()
            return bool(result.rowcount)

    async def _claim_task(self, task_id, now):
        async with self._session() as db:
            result = await db.execute(
                update(KnowledgeGraphBuildTask)
                .where(
                    KnowledgeGraphBuildTask.id == task_id,
                    (KnowledgeGraphBuildTask.status == "queued")
                    | (
                        (KnowledgeGraphBuildTask.status == "running")
                        & (KnowledgeGraphBuildTask.lease_until < now)
                    ),
                )
                .values(
                    status="running",
                    started_at=now,
                    lease_until=now + timedelta(seconds=self.lease_seconds),
                )
            )
            await db.commit()
            return bool(result.rowcount)

    async def _owns_task(self, task_id, owner_token):
        current = await self.get_status(task_id=task_id)
        return bool(
            current
            and current.status == "running"
            and current.started_at == owner_token
            and current.lease_until
            and current.lease_until > datetime.utcnow()
        )

    async def run(self, task_id):
        task = await self.get_status(task_id=task_id)
        if not task: raise ValueError("task not found")
        now = datetime.utcnow()
        if task.status == "running" and task.lease_until and task.lease_until > now:
            raise ValueError("task already running")
        if task.status not in {"queued", "running"}:
            raise ValueError(f"task cannot run from status {task.status}")
        if not await self._claim_task(task_id, now):
            raise ValueError("task was claimed by another worker or is not runnable")
        task = await self.get_status(task_id=task_id)
        owner_token = now
        heartbeat_stop = asyncio.Event()
        heartbeat = asyncio.create_task(
            self._lease_heartbeat(task_id, owner_token, heartbeat_stop)
        )
        try:
            if task.mode == "reset_and_build": await self.reset_graph(task.kb_id, task_id=task_id)
            ids = list(task.failed_chunk_ids or [])
            async with self._session() as db:
                q=select(KnowledgeChunk).where(KnowledgeChunk.kb_id==task.kb_id, KnowledgeChunk.graph_status!="completed")
                if ids: q=q.where(KnowledgeChunk.id.in_(ids))
                chunks=(await db.execute(q)).scalars().all()
            total_chunks = max(int(task.total_chunks or 0), len(chunks))
            # A resumed task may already have committed some chunks before its
            # process died.  Count those completed chunks as the baseline so a
            # later batch cannot overwrite the durable cumulative counters.
            completed_before = max(0, total_chunks - len(chunks))
            await self._set_documents_graph_status(
                {chunk.document_id for chunk in chunks}, "processing"
            )
            succeeded=[]; failed=[]; errors=[]; cancelled=False
            async def one(c):
                try:
                    current = await self.get_status(task_id=task_id)
                    if (
                        current is None
                        or current.status != "running"
                        or current.started_at != owner_token
                        or not current.lease_until
                        or current.lease_until <= datetime.utcnow()
                        or current.cancel_requested
                    ):
                        return None, None
                    async with self._session() as db:
                        kb=await db.get(KnowledgeBase, task.kb_id)
                        schema=KnowledgeIngestionService._schema(kb.graph_schema)
                    extractor=self.extractor or KnowledgeGraphExtractor()
                    snap=SimpleNamespace(
                        kb_id=task.kb_id,
                        document_id=c.document_id,
                        content_generation=c.content_generation,
                        schema=schema,
                        rule_version=int(kb.rule_version or 0),
                    )
                    svc=KnowledgeIngestionService(session_factory=self.session_factory, processor=None, extractor=extractor)
                    extraction=await svc._extract_with_provenance(snap, c)
                    if not await self._owns_task(task_id, owner_token):
                        return None, None
                    await svc._persist_graph_extraction(
                        snap, c, extraction, task_id=task_id, owner_token=owner_token
                    ); return True,None
                except Exception as e:
                    if not await self._owns_task(task_id, owner_token):
                        return None, None
                    async with self._session() as db:
                        cc=await db.get(KnowledgeChunk,c.id)
                        if cc: cc.graph_status="failed"; cc.last_error=str(e); await db.commit()
                    return False,str(e)
            sem=asyncio.Semaphore(self.concurrency)
            async def guarded(c):
                async with sem: return await one(c)
            for i in range(0,len(chunks),self.batch_size):
                cur=await self.get_status(task_id=task_id)
                if (
                    cur is None
                    or cur.status != "running"
                    or cur.started_at != owner_token
                    or not await self._renew_lease(task_id, owner_token)
                ):
                    cancelled = True
                    break
                if cur.cancel_requested: cancelled=True; break
                for c,(ok,err) in zip(chunks[i:i+self.batch_size], await asyncio.gather(*(guarded(c) for c in chunks[i:i+self.batch_size]))):
                    if ok is None:
                        cancelled = True
                        continue
                    (succeeded if ok else failed).append(c.id)
                    if not ok and err:
                        errors.append(err)
                processed_count = min(total_chunks, completed_before + len(succeeded))
                await self._set_task(task_id, processed_chunks=processed_count, failed_chunks=len(failed), failed_chunk_ids=failed, remaining_chunks=max(0,total_chunks-processed_count-len(failed)), last_error=(errors[-1] if errors else None))
                if cancelled:
                    break
            status="cancelled" if cancelled else ("partial" if failed else "completed")
            processed_count = min(total_chunks, completed_before + len(succeeded))
            await self._finish_task(task_id, owner_token, status=status, completed_at=datetime.utcnow(), lease_until=None, failed_chunk_ids=failed, processed_chunks=processed_count, failed_chunks=len(failed), remaining_chunks=max(0,total_chunks-processed_count-len(failed)), last_error=(errors[-1] if errors else None))
            await self._sync_document_graph_statuses(task.kb_id)
            return await self.get_status(task_id=task_id)
        finally:
            heartbeat_stop.set()
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def _set_documents_graph_status(self, document_ids, status):
        if not document_ids:
            return
        async with self._session() as db:
            await db.execute(
                update(Document)
                .where(Document.id.in_(document_ids))
                .values(graph_status=status)
            )
            await db.commit()

    async def _sync_document_graph_statuses(self, kb_id):
        async with self._session() as db:
            kb = await db.get(KnowledgeBase, kb_id)
            documents = list(
                (await db.execute(select(Document).where(Document.knowledge_base_id == kb_id)))
                .scalars()
                .all()
            )
            chunks = list(
                (await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.kb_id == kb_id)))
                .scalars()
                .all()
            )
            statuses_by_document = {}
            for chunk in chunks:
                statuses_by_document.setdefault(chunk.document_id, []).append(chunk.graph_status)
            for document in documents:
                statuses = statuses_by_document.get(document.id, [])
                if kb is not None and not kb.graph_enabled:
                    document.graph_status = "disabled"
                elif any(status == "failed" for status in statuses):
                    document.graph_status = "failed"
                elif statuses and all(status == "completed" for status in statuses):
                    document.graph_status = "completed"
                else:
                    document.graph_status = "pending"
            await db.commit()

    async def recover_expired_tasks(self, kb_id=None):
        now=datetime.utcnow(); out=[]
        async with self._session() as db:
            query = select(KnowledgeGraphBuildTask).where(
                KnowledgeGraphBuildTask.status=="running",
                KnowledgeGraphBuildTask.lease_until < now,
            )
            if kb_id:
                query = query.where(KnowledgeGraphBuildTask.kb_id == kb_id)
            rows=(await db.execute(query.with_for_update())).scalars().all()
            for t in rows:
                # A process restart can leave a provenance row in ``running``
                # even though the build lease has expired.  Mark only rows
                # created before this task's lease deadline; newer rows belong
                # to the recovery run and must remain active.
                await db.execute(
                    update(KnowledgeGraphExtractionRun)
                    .where(
                        KnowledgeGraphExtractionRun.kb_id == t.kb_id,
                        KnowledgeGraphExtractionRun.status == "running",
                        KnowledgeGraphExtractionRun.created_at < t.lease_until,
                    )
                    .values(
                        status="failed",
                        validation_errors=["orphaned_after_graph_build_lease_expired"],
                    )
                )
                result = await db.execute(
                    update(KnowledgeGraphBuildTask)
                    .where(
                        KnowledgeGraphBuildTask.id == t.id,
                        KnowledgeGraphBuildTask.status == "running",
                        KnowledgeGraphBuildTask.lease_until < now,
                    )
                .values(status="queued", lease_until=None)
                )
                if result.rowcount:
                    out.append(t.id)
            await db.commit()
        return out

    async def retry(self, task_id=None, kb_id=None):
        old=await self.get_status(task_id=task_id,kb_id=kb_id)
        if not old: raise ValueError("task not found")
        if old.status not in {"failed", "partial"}:
            raise ValueError("only failed or partial graph builds can be retried")
        ids=list(old.failed_chunk_ids or [])
        if not ids:
            async with self._session() as db:
                ids=(await db.execute(select(KnowledgeChunk.id).where(KnowledgeChunk.kb_id==old.kb_id, KnowledgeChunk.graph_status=="failed"))).scalars().all()
        task=await self.create_task(old.kb_id, mode="pending", user_id="system")
        await self._set_task(task.id, failed_chunk_ids=ids, total_chunks=len(ids), remaining_chunks=len(ids))
        return await self.get_status(task_id=task.id)

    async def cancel(self, task_id):
        await self._set_task(task_id,cancel_requested=True)

    async def reset_graph(self, kb_id, *, task_id=None):
        async with self._session() as db:
            active = await db.scalar(select(KnowledgeGraphBuildTask).where(KnowledgeGraphBuildTask.kb_id == kb_id, KnowledgeGraphBuildTask.status.in_(["queued", "running"]), KnowledgeGraphBuildTask.id != task_id))
            if active:
                raise ValueError("task already running")
            outbox=KnowledgeIndexOutboxRepository.for_session(db)
            record_ids = {}
            for typ,model in (("entity",KnowledgeGraphEntity),("relation",KnowledgeGraphRelation)):
                for rid in (await db.execute(select(model.id).where(model.kb_id==kb_id))).scalars().all():
                    record_ids[(typ, rid)] = int(await db.scalar(select(func.max(KnowledgeIndexOutbox.payload_version)).where(KnowledgeIndexOutbox.kb_id == kb_id, KnowledgeIndexOutbox.record_type == typ, KnowledgeIndexOutbox.record_id == rid)) or 0) + 1
            for typ, rid in (
                await db.execute(
                    select(
                        KnowledgeIndexOutbox.record_type,
                        KnowledgeIndexOutbox.record_id,
                    )
                    .where(
                        KnowledgeIndexOutbox.kb_id == kb_id,
                        KnowledgeIndexOutbox.record_type.in_(["entity", "relation"]),
                    )
                    .distinct()
                )
            ).all():
                if (typ, rid) not in record_ids:
                    record_ids[(typ, rid)] = int(
                        await db.scalar(
                            select(func.max(KnowledgeIndexOutbox.payload_version)).where(
                                KnowledgeIndexOutbox.kb_id == kb_id,
                                KnowledgeIndexOutbox.record_type == typ,
                                KnowledgeIndexOutbox.record_id == rid,
                            )
                        )
                        or 0
                    ) + 1
            await db.execute(delete(KnowledgeIndexOutbox).where(KnowledgeIndexOutbox.kb_id == kb_id, KnowledgeIndexOutbox.record_type.in_(["entity", "relation"])))
            for (typ, rid), revision in record_ids.items():
                await outbox.enqueue_delete(kb_id, typ, rid, revision)
            for model in (KnowledgeGraphEntityMention,KnowledgeGraphRelationMention,KnowledgeGraphRelation,KnowledgeGraphEntity): await db.execute(delete(model).where(model.kb_id==kb_id))
            for c in (await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.kb_id==kb_id))).scalars(): c.graph_status="pending"; c.last_error=None
            await bump_graph_revision(db, kb_id)
            await db.commit()
        await self._sync_document_graph_statuses(kb_id)
