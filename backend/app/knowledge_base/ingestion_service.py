"""Unified incremental ingestion for document chunks and knowledge graphs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import structlog
from sqlalchemy import func, select

from app.agent.cognition.models import CognitiveSchema
from app.knowledge_base.chunk_diff import build_chunk_drafts
from app.knowledge_base.chunk_repository import (
    KnowledgeChunkRepository,
    StaleContentGeneration,
)
from app.knowledge_base.graph_models import (
    KnowledgeChunk,
    KnowledgeGraphEntity,
    KnowledgeGraphRelation,
)
from app.knowledge_base.graph_repository import KnowledgeGraphRepository
from app.knowledge_base.index_outbox import KnowledgeIndexOutboxRepository
from app.knowledge_base.models import Document, DocumentStatus, KnowledgeBase

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
        try:
            content = await self.processor.parse(snapshot.file_path)
            chunks = await self.processor.chunk(
                content=content,
                strategy=self.processing_options.get("chunking_strategy", "llm"),
                chunk_size=self.processing_options.get("chunk_size", 800),
                chunk_overlap=self.processing_options.get("chunk_overlap", 100),
                filename=snapshot.filename,
                llm_mode=self.processing_options.get("llm_mode", "online"),
            )
        except Exception as exc:
            await self._mark_document_failed(
                document_id,
                str(exc),
                expected_generation=snapshot.content_generation,
            )
            raise

        drafts = build_chunk_drafts(chunks)
        persisted = await self._persist_chunks_and_outbox(snapshot, drafts)
        await self._store_original_file(snapshot)

        graph_errors: list[str] = []
        changed_entity_ids: set[str] = set()
        changed_relation_ids: set[str] = set()
        if snapshot.graph_enabled:
            semaphore = asyncio.Semaphore(self.max_graph_concurrency)
            graph_chunks = [
                *persisted.added,
                *(chunk for chunk in persisted.reused if chunk.graph_status != "completed"),
            ]

            async def process_chunk(chunk):
                async with semaphore:
                    extraction = await self.extractor.extract_chunk(
                        kb_id=snapshot.kb_id,
                        chunk=chunk,
                        schema=snapshot.schema,
                    )
                return await self._persist_graph_extraction(snapshot, chunk, extraction)

            results = await asyncio.gather(
                *(process_chunk(chunk) for chunk in graph_chunks),
                return_exceptions=True,
            )
            for chunk, result in zip(
                graph_chunks,
                results,
                strict=True,
            ):
                if isinstance(result, BaseException):
                    error = str(result)
                    graph_errors.append(error)
                    await self._mark_chunk_graph_failed(
                        chunk.id,
                        error,
                        expected_generation=snapshot.content_generation,
                    )
                    continue
                changed_entity_ids.update(result.changed_entity_ids)
                changed_relation_ids.update(result.changed_relation_ids)

        status = "partial" if graph_errors else "completed"
        await self._finalize_document(
            snapshot=snapshot,
            content=content,
            chunk_count=len(drafts),
            status=status,
            graph_errors=graph_errors,
        )
        return IngestionResult(
            document_id=document_id,
            content_generation=snapshot.content_generation,
            added_chunks=len(persisted.added),
            reused_chunks=len(persisted.reused),
            removed_chunks=len(persisted.removed),
            changed_entities=len(changed_entity_ids),
            changed_relations=len(changed_relation_ids),
            status=status,
        )

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
        await self._delete_original_file(old_snapshot)
        try:
            return await self.ingest_document(document_id)
        except Exception:
            await self._purge_document_derivatives(
                kb_id=old_snapshot.kb_id,
                document_id=document_id,
                payload_version=old_snapshot.content_generation + 1,
                expected_generation=old_snapshot.content_generation + 1,
            )
            raise

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
            document.graph_status = "processing" if kb.graph_enabled else "disabled"
            document.processing_error = None
            return _DocumentSnapshot(
                document_id=document.id,
                kb_id=kb.id,
                content_generation=document.content_generation,
                filename=document.filename,
                file_path=document.file_path,
                file_size=document.file_size or 0,
                graph_enabled=bool(kb.graph_enabled),
                schema=self._schema(kb.graph_schema),
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

    async def _persist_graph_extraction(self, snapshot, chunk, extraction):
        async with self.session_factory() as session, session.begin():
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
                extraction_run_id=str(uuid4()),
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
        graph_errors: list[str],
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
            document.graph_status = "failed" if graph_errors else "completed"
            document.processing_error = "; ".join(dict.fromkeys(graph_errors))[:2000] or None
            document.error_message = None
            document.chunk_count = chunk_count
            document.file_preview_text = content[:500] if content else None
            document.processed_at = datetime.utcnow()

            await self._recalculate_kb_stats(session, snapshot.kb_id)

    async def _store_original_file(self, snapshot) -> None:
        if self.file_storage is None:
            return
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
                if info:
                    document.file_storage_type = info.get("storage_type", "none")
                    document.file_mime_type = info.get("mime_type")
                    document.file_checksum = info.get("checksum")
                    document.storage_size = info.get("size", 0)
                    if info.get("storage_type") == "database" and info.get("loid"):
                        document.original_file_oid = int(info["loid"])
                    elif info.get("storage_type") == "local":
                        document.file_path = info.get("storage_path", snapshot.file_path)
        except StaleContentGeneration:
            raise
        except Exception as exc:
            logger.warning(
                "original_file_storage_failed",
                document_id=snapshot.document_id,
                error=str(exc),
            )

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
        return _DocumentSnapshot(
            document_id=document.id,
            kb_id=kb.id,
            content_generation=document.content_generation,
            filename=document.filename,
            file_path=document.file_path,
            file_size=document.file_size or 0,
            graph_enabled=bool(kb.graph_enabled),
            schema=self._schema(kb.graph_schema),
            original_file_oid=document.original_file_oid,
            file_storage_type=document.file_storage_type,
        )

    @staticmethod
    def _schema(raw_schema: dict | None) -> CognitiveSchema:
        return (
            CognitiveSchema.model_validate(raw_schema)
            if raw_schema
            else CognitiveSchema.default_air_quality_schema()
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
    file_path: str
    file_size: int
    graph_enabled: bool
    schema: CognitiveSchema
    original_file_oid: int | None = None
    file_storage_type: str | None = None
