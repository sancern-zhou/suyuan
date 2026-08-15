"""Unified incremental ingestion for document chunks and knowledge graphs."""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import structlog
from sqlalchemy import func, select

from app.knowledge_base.chunk_diff import build_chunk_drafts
from app.knowledge_base.chunk_repository import (
    KnowledgeChunkRepository,
    StaleContentGeneration,
)
from app.knowledge_base.extraction_run_repository import (
    ExtractionRunContext,
    ExtractionRunRepository,
)
from app.knowledge_base.graph_build_models import KnowledgeGraphBuildTask
from app.knowledge_base.graph_extraction.llm_factory import PROMPT_VERSION
from app.knowledge_base.graph_extraction.models import GraphExtractionSchema
from app.knowledge_base.graph_models import (
    KnowledgeChunk,
    KnowledgeGraphEntity,
    KnowledgeGraphRelation,
)
from app.knowledge_base.graph_repository import KnowledgeGraphRepository
from app.knowledge_base.index_outbox import KnowledgeIndexOutboxRepository
from app.knowledge_base.models import Document, DocumentStatus, KnowledgeBase
from app.knowledge_base.scene_models import KnowledgeBusinessRule

logger = structlog.get_logger()


@dataclass(frozen=True)
class IngestionResult:
    document_id: str
    content_generation: int
    added_chunks: int
    reused_chunks: int
    removed_chunks: int
    changed_entities: int
    changed_relations: int
    status: str


class KnowledgeIngestionService:
    """Coordinate fact transactions and independently retryable graph work."""

    def __init__(
        self,
        *,
        session_factory,
        processor,
        chunk_repository_factory=KnowledgeChunkRepository,
        graph_repository_factory=KnowledgeGraphRepository,
        extractor,
        outbox_factory=KnowledgeIndexOutboxRepository.for_session,
        file_storage=None,
        processing_options: dict | None = None,
        max_graph_concurrency: int = 4,
    ):
        self.session_factory = session_factory
        self.processor = processor
        self.chunk_repository_factory = chunk_repository_factory
        self.graph_repository_factory = graph_repository_factory
        self.extractor = extractor
        self.outbox_factory = outbox_factory
        self.file_storage = file_storage
        self.processing_options = dict(processing_options or {})
        self.max_graph_concurrency = max(1, max_graph_concurrency)

    async def ingest_document(self, document_id: str) -> IngestionResult:
        snapshot = await self._load_and_mark_processing(document_id)
        staging_path = snapshot.file_path
        stored_now = False
        try:
            await self._set_processing_phase(document_id, "storing", snapshot.content_generation)
            snapshot, stored_now = await self._store_original_file(snapshot)
            await self._set_processing_phase(document_id, "parsing", snapshot.content_generation)
            content = await self._parse_original(snapshot)
            await self._set_processing_phase(document_id, "chunking", snapshot.content_generation)
            chunks = await self.processor.chunk(
                content=content,
                strategy=self.processing_options.get("chunking_strategy", "llm"),
                chunk_size=self.processing_options.get("chunk_size", 1200),
                chunk_overlap=self.processing_options.get("chunk_overlap", 100),
                filename=snapshot.filename,
                llm_mode=self.processing_options.get("llm_mode", "online"),
            )
            if not chunks:
                raise ValueError("文档解析后未生成任何分块，不能标记为已完成，请检查目录识别或解析结果")
        except Exception as exc:
            await self._mark_document_failed(
                document_id,
                str(exc),
                expected_generation=snapshot.content_generation,
            )
            raise
        finally:
            if stored_now and staging_path and staging_path != snapshot.file_path:
                Path(staging_path).unlink(missing_ok=True)

        drafts = build_chunk_drafts(chunks)
        await self._set_processing_phase(document_id, "indexing", snapshot.content_generation)
        persisted = await self._persist_chunks_and_outbox(snapshot, drafts)

        current_chunks = [*persisted.added, *persisted.reused]
        graph_status = (
            "disabled"
            if not snapshot.graph_enabled
            else (
                "completed"
                if current_chunks
                and all(chunk.graph_status == "completed" for chunk in current_chunks)
                else "pending"
            )
        )
        status = "completed"
        await self._finalize_document(
            snapshot=snapshot,
            content=content,
            chunk_count=len(drafts),
            status=status,
            graph_status=graph_status,
        )
        return IngestionResult(
            document_id=document_id,
            content_generation=snapshot.content_generation,
            added_chunks=len(persisted.added),
            reused_chunks=len(persisted.reused),
            removed_chunks=len(persisted.removed),
            changed_entities=0,
            changed_relations=0,
            status=status,
        )

    async def _set_processing_phase(self, document_id: str, phase: str, generation: int) -> None:
        """Expose a lightweight progress phase without requiring a schema migration."""
        async with self.session_factory() as session, session.begin():
            document = await session.scalar(
                select(Document).where(Document.id == document_id).with_for_update()
            )
            if document is None or document.content_generation != generation:
                return
            metadata = dict(document.extra_metadata or {})
            metadata["processing_phase"] = phase
            metadata["processing_phase_updated_at"] = datetime.utcnow().isoformat()
            document.extra_metadata = metadata

    async def replace_document(
        self,
        document_id: str,
        new_file_path: str,
        file_metadata: dict,
    ) -> IngestionResult:
        old_snapshot = await self._begin_replacement(
            document_id=document_id,
            new_file_path=new_file_path,
            file_metadata=file_metadata,
        )
        try:
            result = await self.ingest_document(document_id)
        except Exception:
            failed_snapshot = await self._get_current_snapshot(document_id)
            if failed_snapshot is not None:
                await self._delete_original_file(failed_snapshot)
            await self._restore_replacement(old_snapshot)
            raise
        await self._delete_original_file(old_snapshot)
        return result

    async def _get_current_snapshot(self, document_id: str) -> _DocumentSnapshot | None:
        async with self.session_factory() as session:
            document = await session.get(Document, document_id)
            if document is None:
                return None
            kb = await session.get(KnowledgeBase, document.knowledge_base_id)
            return self._snapshot(document, kb) if kb is not None else None

    async def _restore_replacement(self, snapshot: _DocumentSnapshot) -> None:
        async with self.session_factory() as session, session.begin():
            document = await session.scalar(
                select(Document).where(Document.id == snapshot.document_id).with_for_update()
            )
            if document is None or document.content_generation != snapshot.content_generation + 1:
                return
            document.content_generation = snapshot.content_generation
            document.filename = snapshot.filename
            document.file_path = snapshot.file_path
            document.file_type = snapshot.file_type
            document.file_size = snapshot.file_size
            document.file_hash = snapshot.file_hash
            document.extra_metadata = dict(snapshot.extra_metadata or {})
            document.original_file_oid = snapshot.original_file_oid
            document.file_storage_type = snapshot.file_storage_type
            document.file_mime_type = snapshot.file_mime_type
            document.file_checksum = snapshot.file_checksum
            document.storage_size = snapshot.storage_size
            document.status = snapshot.status
            document.ingestion_status = snapshot.ingestion_status
            document.graph_status = snapshot.graph_status
            document.processing_error = snapshot.processing_error
            document.error_message = snapshot.error_message

    async def delete_document(self, kb_id: str, document_id: str) -> None:
        snapshot = await self._begin_delete(kb_id, document_id)
        await self._purge_document_derivatives(
            kb_id=kb_id,
            document_id=document_id,
            payload_version=snapshot.content_generation,
            expected_generation=snapshot.content_generation,
        )
        await self._delete_original_file(snapshot)
        async with self.session_factory() as session, session.begin():
            document = await session.get(Document, document_id)
            if document is not None:
                await session.delete(document)
                await session.flush()
            await self._recalculate_kb_stats(session, kb_id)

    async def _load_and_mark_processing(self, document_id: str):
        async with self.session_factory() as session, session.begin():
            document = await session.scalar(
                select(Document).where(Document.id == document_id).with_for_update()
            )
            if document is None:
                raise ValueError(f"Document not found: {document_id}")
            kb = await session.get(KnowledgeBase, document.knowledge_base_id)
            if kb is None:
                raise ValueError(f"Knowledge base not found: {document.knowledge_base_id}")
            document.status = DocumentStatus.PROCESSING
            document.ingestion_status = "processing"
            document.graph_status = "pending" if kb.graph_enabled else "disabled"
            document.processing_error = None
            metadata = dict(document.extra_metadata or {})
            metadata["processing_phase"] = "queued"
            document.extra_metadata = metadata
            schema = self._schema(kb.graph_schema)
            rules = []
            if int(kb.rule_version or 0) > 0:
                rules = list(
                    (
                        await session.scalars(
                            select(KnowledgeBusinessRule).where(
                                KnowledgeBusinessRule.kb_id == kb.id,
                                KnowledgeBusinessRule.status == "confirmed",
                            )
                        )
                    ).all()
                )
            schema.normalization_rules = {
                **(schema.normalization_rules or {}),
                "business_rules": [dict(item.structured_rule or {}) for item in rules],
            }
            return _DocumentSnapshot(
                document_id=document.id,
                kb_id=kb.id,
                content_generation=document.content_generation,
                filename=document.filename,
                file_path=document.file_path,
                file_size=document.file_size or 0,
                graph_enabled=bool(kb.graph_enabled),
                schema=schema,
                rule_version=int(kb.rule_version or 0),
                original_file_oid=document.original_file_oid,
                file_storage_type=document.file_storage_type,
                file_type=document.file_type,
                file_hash=document.file_hash,
                file_mime_type=document.file_mime_type,
                file_checksum=document.file_checksum,
                storage_size=document.storage_size or 0,
                extra_metadata=dict(document.extra_metadata or {}),
                status=document.status,
                ingestion_status=document.ingestion_status,
                graph_status=document.graph_status,
                processing_error=document.processing_error,
                error_message=document.error_message,
            )

    async def _persist_chunks_and_outbox(self, snapshot, drafts):
        async with self.session_factory() as session, session.begin():
            repository = self.chunk_repository_factory(session)
            persisted = await repository.replace_document_chunks(
                kb_id=snapshot.kb_id,
                document_id=snapshot.document_id,
                content_generation=snapshot.content_generation,
                drafts=drafts,
            )
            outbox = self.outbox_factory(session)
            removed_ids = [chunk.id for chunk in persisted.removed]
            if removed_ids:
                deactivated_entities, deactivated_relations = await self.graph_repository_factory(
                    session
                ).remove_chunk_contributions(
                    kb_id=snapshot.kb_id,
                    chunk_ids=removed_ids,
                )
                for chunk in persisted.removed:
                    await outbox.enqueue_delete(
                        kb_id=snapshot.kb_id,
                        record_type="chunk",
                        record_id=chunk.id,
                        payload_version=snapshot.content_generation,
                    )
                    await session.delete(chunk)
                for entity_id in deactivated_entities:
                    revision = await outbox.next_payload_version(
                        snapshot.kb_id, "entity", entity_id
                    )
                    await outbox.enqueue_delete(
                        kb_id=snapshot.kb_id,
                        record_type="entity",
                        record_id=entity_id,
                        payload_version=revision,
                    )
                for relation_id in deactivated_relations:
                    revision = await outbox.next_payload_version(
                        snapshot.kb_id, "relation", relation_id
                    )
                    await outbox.enqueue_delete(
                        kb_id=snapshot.kb_id,
                        record_type="relation",
                        record_id=relation_id,
                        payload_version=revision,
                    )
            chunks_to_index = [
                *persisted.added,
                *(chunk for chunk in persisted.reused if chunk.vector_status != "indexed"),
            ]
            for chunk in chunks_to_index:
                await outbox.enqueue_upsert(
                    kb_id=snapshot.kb_id,
                    record_type="chunk",
                    record_id=chunk.id,
                    payload_version=snapshot.content_generation,
                    payload=self._chunk_payload(chunk),
                )
            await repository.mark_vector_status(
                [chunk.id for chunk in chunks_to_index],
                "pending",
            )
            return persisted

    async def _persist_graph_extraction(
        self, snapshot, chunk, extraction, *, task_id=None, owner_token=None
    ):
        async with self.session_factory() as session, session.begin():
            if task_id is not None:
                task = await session.scalar(
                    select(KnowledgeGraphBuildTask)
                    .where(KnowledgeGraphBuildTask.id == task_id)
                    .with_for_update()
                )
                if (
                    task is None
                    or task.status != "running"
                    or task.started_at != owner_token
                    or task.cancel_requested
                    or task.lease_until is None
                    or task.lease_until <= datetime.utcnow()
                ):
                    raise StaleContentGeneration(
                        f"graph build task {task_id} lease is no longer owned"
                    )
            current_document = await session.scalar(
                select(Document).where(Document.id == snapshot.document_id).with_for_update()
            )
            if (
                current_document is None
                or current_document.content_generation != snapshot.content_generation
            ):
                raise StaleContentGeneration(
                    f"document {snapshot.document_id} no longer belongs to generation "
                    f"{snapshot.content_generation}"
                )
            current_chunk = await session.get(KnowledgeChunk, chunk.id)
            if (
                current_chunk is None
                or current_chunk.content_generation != snapshot.content_generation
            ):
                raise StaleContentGeneration(
                    f"chunk {chunk.id} no longer belongs to generation "
                    f"{snapshot.content_generation}"
                )
            repository = self.graph_repository_factory(session)
            result = await repository.upsert_chunk_extraction(
                kb_id=snapshot.kb_id,
                document_id=snapshot.document_id,
                extraction=extraction,
                extraction_run_id=extraction.extraction_run_id or str(uuid4()),
                source_type="document_fact",
                scene_profile_version=getattr(
                    getattr(snapshot, "schema", None), "scene_profile_version", 0
                ),
                schema_version=getattr(getattr(snapshot, "schema", None), "schema_version", 0),
                rule_version=getattr(snapshot, "rule_version", 0),
            )
            outbox = self.outbox_factory(session)
            for entity_id in result.changed_entity_ids:
                entity = await session.get(KnowledgeGraphEntity, entity_id)
                if entity is not None:
                    revision = await outbox.next_payload_version(
                        snapshot.kb_id, "entity", entity.id
                    )
                    await outbox.enqueue_upsert(
                        kb_id=snapshot.kb_id,
                        record_type="entity",
                        record_id=entity.id,
                        payload_version=revision,
                        payload=self._entity_payload(entity),
                    )
            for relation_id in result.changed_relation_ids:
                relation = await session.get(KnowledgeGraphRelation, relation_id)
                if relation is not None:
                    source = await session.get(KnowledgeGraphEntity, relation.source_entity_id)
                    target = await session.get(KnowledgeGraphEntity, relation.target_entity_id)
                    revision = await outbox.next_payload_version(
                        snapshot.kb_id, "relation", relation.id
                    )
                    await outbox.enqueue_upsert(
                        kb_id=snapshot.kb_id,
                        record_type="relation",
                        record_id=relation.id,
                        payload_version=revision,
                        payload=self._relation_payload(relation, source, target),
                    )
            await self.chunk_repository_factory(session).mark_graph_status(
                [chunk.id],
                "completed",
            )
            return result

    async def _extract_with_provenance(self, snapshot, chunk):
        if snapshot.schema.schema_version <= 0:
            return await self.extractor.extract_chunk(
                kb_id=snapshot.kb_id, chunk=chunk, schema=snapshot.schema
            )
        provider = getattr(self.extractor, "provider", None)
        llm = getattr(provider, "llm", None)
        model_name = str(getattr(llm, "model_name", "project-configured-model"))
        context = ExtractionRunContext(
            kb_id=snapshot.kb_id,
            document_id=snapshot.document_id,
            chunk_id=chunk.id,
            content_generation=snapshot.content_generation,
            scene_profile_version=snapshot.schema.scene_profile_version,
            schema_version=snapshot.schema.schema_version,
            prompt_version=PROMPT_VERSION,
            model_name=model_name,
            model_params={"temperature": getattr(llm, "temperature", None)},
        )
        async with self.session_factory() as session:
            repository = ExtractionRunRepository(session)
            run_id = await repository.start(context)
            started = time.perf_counter()
            try:
                extraction = await self.extractor.extract_chunk(
                    kb_id=snapshot.kb_id, chunk=chunk, schema=snapshot.schema
                )
                extraction.extraction_run_id = run_id
                raw = getattr(llm, "last_structured_payload", None) or {}
                await repository.complete(
                    run_id,
                    raw_response=dict(raw),
                    parsed_response=extraction.model_dump(mode="json"),
                    token_usage={},
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
                return extraction
            except Exception as exc:
                raw = getattr(llm, "last_structured_payload", None) or {}
                await repository.fail(
                    run_id,
                    raw_response=dict(raw),
                    validation_errors=[str(exc)],
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
                raise

    async def _mark_chunk_graph_failed(
        self,
        chunk_id: str,
        error: str,
        *,
        expected_generation: int,
    ) -> None:
        async with self.session_factory() as session, session.begin():
            chunk = await session.scalar(
                select(KnowledgeChunk).where(KnowledgeChunk.id == chunk_id).with_for_update()
            )
            if chunk is None or chunk.content_generation != expected_generation:
                return
            await self.chunk_repository_factory(session).mark_graph_status(
                [chunk_id],
                "failed",
                error[:1000],
            )

    async def _mark_document_failed(
        self,
        document_id: str,
        error: str,
        *,
        expected_generation: int,
    ) -> None:
        async with self.session_factory() as session, session.begin():
            document = await session.scalar(
                select(Document).where(Document.id == document_id).with_for_update()
            )
            if document is None or document.content_generation != expected_generation:
                return
            document.status = DocumentStatus.FAILED
            document.ingestion_status = "failed"
            document.graph_status = "failed"
            document.processing_error = error[:2000]
            document.error_message = error[:500]
            document.retry_count += 1

    async def _finalize_document(
        self,
        *,
        snapshot,
        content: str,
        chunk_count: int,
        status: str,
        graph_status: str,
    ) -> None:
        async with self.session_factory() as session, session.begin():
            document = await session.scalar(
                select(Document).where(Document.id == snapshot.document_id).with_for_update()
            )
            kb = await session.get(KnowledgeBase, snapshot.kb_id)
            if document is None or kb is None:
                raise ValueError("Document or knowledge base disappeared during ingestion")
            if document.content_generation != snapshot.content_generation:
                raise StaleContentGeneration(
                    f"document {snapshot.document_id} advanced from generation "
                    f"{snapshot.content_generation} to {document.content_generation}"
                )
            document.status = DocumentStatus.COMPLETED
            document.ingestion_status = status
            document.graph_status = graph_status
            document.processing_error = None
            document.error_message = None
            metadata = dict(document.extra_metadata or {})
            metadata["processing_phase"] = "completed"
            document.extra_metadata = metadata
            document.chunk_count = chunk_count
            document.file_preview_text = content[:500] if content else None
            document.processed_at = datetime.utcnow()
            if document.file_storage_type == "database" and document.original_file_oid:
                document.file_path = None

            await self._recalculate_kb_stats(session, snapshot.kb_id)

    async def _store_original_file(self, snapshot) -> tuple[_DocumentSnapshot, bool]:
        if self.file_storage is None:
            return snapshot, False
        if snapshot.file_storage_type == "database" and snapshot.original_file_oid:
            return replace(snapshot, file_path=None), False
        if snapshot.file_storage_type == "local" and snapshot.file_path:
            return snapshot, False
        if not snapshot.file_path:
            raise FileNotFoundError("document has no staging file or durable original")

        info = None
        try:
            async with self.session_factory() as session, session.begin():
                document = await session.scalar(
                    select(Document).where(Document.id == snapshot.document_id).with_for_update()
                )
                if document is None or document.content_generation != snapshot.content_generation:
                    raise StaleContentGeneration(
                        f"document {snapshot.document_id} no longer belongs to generation "
                        f"{snapshot.content_generation}"
                    )
                storage = (
                    self.file_storage(session) if callable(self.file_storage) else self.file_storage
                )
                info = await storage.store_file(
                    temp_file_path=snapshot.file_path,
                    original_filename=snapshot.filename,
                    document_id=snapshot.document_id,
                    knowledge_base_id=snapshot.kb_id,
                )
                if not info:
                    raise RuntimeError("original file storage returned no durable reference")
                storage_type = info.get("storage_type", "none")
                document.file_storage_type = storage_type
                document.file_mime_type = info.get("mime_type")
                document.file_checksum = info.get("checksum")
                document.storage_size = info.get("size", 0)
                if storage_type == "database" and info.get("loid"):
                    document.original_file_oid = int(info["loid"])
                    document.file_path = None
                elif storage_type == "local" and info.get("storage_path"):
                    document.original_file_oid = None
                    document.file_path = str(info["storage_path"])
                else:
                    raise RuntimeError("original file storage returned an invalid durable reference")
                updated = replace(
                    snapshot,
                    file_path=document.file_path,
                    original_file_oid=document.original_file_oid,
                    file_storage_type=document.file_storage_type,
                )
        except Exception:
            if info and info.get("storage_type") == "local" and info.get("storage_path"):
                Path(str(info["storage_path"])).unlink(missing_ok=True)
            raise
        return updated, True

    async def _parse_original(self, snapshot: _DocumentSnapshot) -> str:
        if snapshot.file_path:
            return await self.processor.parse(snapshot.file_path)
        if snapshot.file_storage_type != "database" or not snapshot.original_file_oid:
            raise FileNotFoundError("durable original file is unavailable")

        from app.knowledge_base.file_storage import DatabaseFileStorageService

        async with self.session_factory() as session:
            file_bytes, _ = await DatabaseFileStorageService(session).retrieve_file(
                int(snapshot.original_file_oid)
            )
        suffix = Path(snapshot.filename).suffix
        with tempfile.NamedTemporaryFile(prefix="kb-parse-", suffix=suffix, delete=False) as handle:
            handle.write(file_bytes)
            materialized_path = Path(handle.name)
        try:
            return await self.processor.parse(str(materialized_path))
        finally:
            materialized_path.unlink(missing_ok=True)

    async def _begin_replacement(
        self,
        *,
        document_id: str,
        new_file_path: str,
        file_metadata: dict,
    ) -> _DocumentSnapshot:
        async with self.session_factory() as session, session.begin():
            document = await session.scalar(
                select(Document).where(Document.id == document_id).with_for_update()
            )
            if document is None:
                raise ValueError(f"Document not found: {document_id}")
            kb = await session.get(KnowledgeBase, document.knowledge_base_id)
            if kb is None:
                raise ValueError(f"Knowledge base not found: {document.knowledge_base_id}")
            old_snapshot = self._snapshot(document, kb)
            document.content_generation += 1
            document.filename = str(file_metadata.get("filename") or document.filename)
            document.file_path = new_file_path
            document.file_type = file_metadata.get("file_type")
            document.file_size = int(file_metadata.get("file_size") or 0)
            document.file_hash = file_metadata.get("file_hash")
            document.extra_metadata = dict(file_metadata.get("metadata") or {})
            document.original_file_oid = None
            document.file_storage_type = "none"
            document.file_mime_type = file_metadata.get("mime_type")
            document.file_checksum = None
            document.storage_size = 0
            document.file_preview_text = None
            document.status = DocumentStatus.PROCESSING
            document.ingestion_status = "processing"
            document.graph_status = "processing"
            document.processing_error = None
            document.error_message = None
            return old_snapshot

    async def _begin_delete(self, kb_id: str, document_id: str) -> _DocumentSnapshot:
        async with self.session_factory() as session, session.begin():
            document = await session.scalar(
                select(Document)
                .where(
                    Document.id == document_id,
                    Document.knowledge_base_id == kb_id,
                )
                .with_for_update()
            )
            if document is None:
                raise ValueError(f"Document not found: {document_id}")
            kb = await session.get(KnowledgeBase, kb_id)
            if kb is None:
                raise ValueError(f"Knowledge base not found: {kb_id}")
            document.content_generation += 1
            document.status = DocumentStatus.DELETING
            document.ingestion_status = "deleting"
            document.graph_status = "deleting"
            return self._snapshot(document, kb)

    async def _purge_document_derivatives(
        self,
        *,
        kb_id: str,
        document_id: str,
        payload_version: int,
        expected_generation: int,
    ) -> None:
        async with self.session_factory() as session, session.begin():
            document = await session.scalar(
                select(Document)
                .where(
                    Document.id == document_id,
                    Document.knowledge_base_id == kb_id,
                )
                .with_for_update()
            )
            if document is None or document.content_generation != expected_generation:
                return
            chunks = list(
                (
                    await session.execute(
                        select(KnowledgeChunk).where(
                            KnowledgeChunk.kb_id == kb_id,
                            KnowledgeChunk.document_id == document_id,
                        )
                    )
                ).scalars()
            )
            chunk_ids = [chunk.id for chunk in chunks]
            deactivated_entities, deactivated_relations = await self.graph_repository_factory(
                session
            ).remove_chunk_contributions(
                kb_id=kb_id,
                chunk_ids=chunk_ids,
            )
            outbox = self.outbox_factory(session)
            for chunk in chunks:
                await outbox.enqueue_delete(
                    kb_id=kb_id,
                    record_type="chunk",
                    record_id=chunk.id,
                    payload_version=payload_version,
                )
                await session.delete(chunk)
            for entity_id in deactivated_entities:
                revision = await outbox.next_payload_version(kb_id, "entity", entity_id)
                await outbox.enqueue_delete(
                    kb_id=kb_id,
                    record_type="entity",
                    record_id=entity_id,
                    payload_version=revision,
                )
            for relation_id in deactivated_relations:
                revision = await outbox.next_payload_version(kb_id, "relation", relation_id)
                await outbox.enqueue_delete(
                    kb_id=kb_id,
                    record_type="relation",
                    record_id=relation_id,
                    payload_version=revision,
                )
            await self._recalculate_kb_stats(session, kb_id)

    async def _delete_original_file(self, snapshot: _DocumentSnapshot) -> None:
        reference = snapshot.original_file_oid or (
            snapshot.file_path if snapshot.file_storage_type == "local" else None
        )
        if reference is None:
            return
        try:
            if self.file_storage is not None and not callable(self.file_storage):
                await self.file_storage.delete_file(reference)
                return
            async with self.session_factory() as session, session.begin():
                if snapshot.original_file_oid:
                    from app.knowledge_base.file_storage import DatabaseFileStorageService

                    storage = DatabaseFileStorageService(session)
                    await storage.delete_file(int(snapshot.original_file_oid))
                else:
                    from app.knowledge_base.file_storage import LocalFileStorageService

                    await LocalFileStorageService().delete_file(str(reference))
        except Exception as exc:
            logger.warning(
                "original_file_delete_failed",
                document_id=snapshot.document_id,
                error=str(exc),
            )

    @staticmethod
    async def _recalculate_kb_stats(session, kb_id: str) -> None:
        kb = await session.get(KnowledgeBase, kb_id)
        if kb is None:
            return
        kb.document_count = int(
            await session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.knowledge_base_id == kb_id)
            )
            or 0
        )
        kb.chunk_count = int(
            await session.scalar(
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(KnowledgeChunk.kb_id == kb_id)
            )
            or 0
        )
        kb.total_size = int(
            await session.scalar(
                select(func.coalesce(func.sum(Document.file_size), 0)).where(
                    Document.knowledge_base_id == kb_id
                )
            )
            or 0
        )

    def _snapshot(self, document: Document, kb: KnowledgeBase) -> _DocumentSnapshot:
        file_path = document.file_path
        if document.file_storage_type == "database" and document.original_file_oid:
            file_path = None
        return _DocumentSnapshot(
            document_id=document.id,
            kb_id=kb.id,
            content_generation=document.content_generation,
            filename=document.filename,
            file_path=file_path,
            file_size=document.file_size or 0,
            graph_enabled=bool(kb.graph_enabled),
            schema=self._schema(kb.graph_schema),
            rule_version=int(kb.rule_version or 0),
            original_file_oid=document.original_file_oid,
            file_storage_type=document.file_storage_type,
            file_type=document.file_type,
            file_hash=document.file_hash,
            file_mime_type=document.file_mime_type,
            file_checksum=document.file_checksum,
            storage_size=document.storage_size or 0,
            extra_metadata=dict(document.extra_metadata or {}),
            status=document.status,
            ingestion_status=document.ingestion_status,
            graph_status=document.graph_status,
            processing_error=document.processing_error,
            error_message=document.error_message,
        )

    @staticmethod
    def _schema(raw_schema: dict | None) -> GraphExtractionSchema:
        return (
            GraphExtractionSchema.model_validate(raw_schema)
            if raw_schema
            else GraphExtractionSchema.default_air_quality_schema()
        )

    @staticmethod
    def _chunk_payload(chunk) -> dict:
        return {
            "record_type": "chunk",
            "record_id": chunk.id,
            "content": chunk.content,
            "embedding_text": chunk.embedding_text,
            "payload": {
                "knowledge_base_id": chunk.kb_id,
                "document_id": chunk.document_id,
                "chunk_index": chunk.chunk_index,
                "chunk_id": chunk.id,
                "content_hash": chunk.content_hash,
            },
        }

    @staticmethod
    def _entity_payload(entity) -> dict:
        text = " ".join(part for part in [entity.name, entity.description] if part)
        return {
            "record_type": "entity",
            "record_id": entity.id,
            "content": text,
            "embedding_text": text,
            "payload": {
                "knowledge_base_id": entity.kb_id,
                "entity_type": entity.entity_type,
                "name": entity.name,
                "review_status": entity.review_status,
            },
        }

    @staticmethod
    def _relation_payload(relation, source, target) -> dict:
        source_name = source.name if source is not None else relation.source_entity_id
        target_name = target.name if target is not None else relation.target_entity_id
        text = " ".join(
            part
            for part in [source_name, relation.relation_type, target_name, relation.description]
            if part
        )
        return {
            "record_type": "relation",
            "record_id": relation.id,
            "content": text,
            "embedding_text": text,
            "payload": {
                "knowledge_base_id": relation.kb_id,
                "source_entity_id": relation.source_entity_id,
                "target_entity_id": relation.target_entity_id,
                "relation_type": relation.relation_type,
                "review_status": relation.review_status,
            },
        }


@dataclass(frozen=True)
class _DocumentSnapshot:
    document_id: str
    kb_id: str
    content_generation: int
    filename: str
    file_path: str | None
    file_size: int
    graph_enabled: bool
    schema: GraphExtractionSchema
    rule_version: int = 0
    original_file_oid: int | None = None
    file_storage_type: str | None = None
    file_type: str | None = None
    file_hash: str | None = None
    file_mime_type: str | None = None
    file_checksum: str | None = None
    storage_size: int = 0
    extra_metadata: dict | None = None
    status: DocumentStatus = DocumentStatus.PROCESSING
    ingestion_status: str = "processing"
    graph_status: str = "pending"
    processing_error: str | None = None
    error_message: str | None = None
