"""Persistence operations for canonical knowledge-base chunks."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge_base.chunk_diff import ChunkDraft, normalize_chunk_text
from app.knowledge_base.graph_models import KnowledgeChunk
from app.knowledge_base.models import Document


class StaleContentGeneration(RuntimeError):
    """Raised when an obsolete ingestion task attempts to write chunks."""


@dataclass(frozen=True)
class PersistedChunkDiff:
    reused: list[KnowledgeChunk]
    added: list[KnowledgeChunk]
    removed: list[KnowledgeChunk]


class KnowledgeChunkRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_document(self, document_id: str) -> list[KnowledgeChunk]:
        result = await self.session.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def get_by_ids(
        self,
        kb_id: str,
        chunk_ids: list[str],
    ) -> list[KnowledgeChunk]:
        if not chunk_ids:
            return []
        result = await self.session.execute(
            select(KnowledgeChunk).where(
                KnowledgeChunk.kb_id == kb_id,
                KnowledgeChunk.id.in_(chunk_ids),
            )
        )
        return list(result.scalars().all())

    async def replace_document_chunks(
        self,
        *,
        kb_id: str,
        document_id: str,
        content_generation: int,
        drafts: list[ChunkDraft],
    ) -> PersistedChunkDiff:
        document = await self.session.scalar(
            select(Document)
            .where(
                Document.id == document_id,
                Document.knowledge_base_id == kb_id,
            )
            .with_for_update()
        )
        if document is None:
            raise ValueError(f"Document not found: {document_id}")
        if document.content_generation != content_generation:
            raise StaleContentGeneration(
                f"expected generation {content_generation}, "
                f"current is {document.content_generation}"
            )

        existing = await self.list_by_document(document_id)
        existing_by_key = {chunk.chunk_key: chunk for chunk in existing}
        draft_keys = {draft.chunk_key for draft in drafts}
        reused: list[KnowledgeChunk] = []
        added: list[KnowledgeChunk] = []

        for draft in drafts:
            current = existing_by_key.get(draft.chunk_key)
            if current is not None:
                has_same_index_text = self._has_same_index_text(current, draft)
                self._apply_draft(
                    current,
                    draft,
                    content_generation=content_generation,
                )
                if not has_same_index_text:
                    current.vector_status = "pending"
                reused.append(current)
                continue

            chunk = KnowledgeChunk(
                kb_id=kb_id,
                document_id=document_id,
                content_generation=content_generation,
                chunk_key=draft.chunk_key,
                content_hash=draft.content_hash,
                chunk_index=draft.chunk_index,
                content=draft.content,
                embedding_text=draft.embedding_text,
                context_prefix=draft.context_prefix,
                start_char=draft.start_char,
                end_char=draft.end_char,
                page_number=draft.page_number,
                section_path=list(draft.section_path),
                chunk_metadata=dict(draft.metadata),
            )
            self.session.add(chunk)
            added.append(chunk)

        removed = [chunk for chunk in existing if chunk.chunk_key not in draft_keys]
        await self.session.flush()
        return PersistedChunkDiff(reused=reused, added=added, removed=removed)

    async def mark_vector_status(
        self,
        chunk_ids: list[str],
        status: str,
        error: str | None = None,
    ) -> None:
        await self._mark_status("vector_status", chunk_ids, status, error)

    async def mark_graph_status(
        self,
        chunk_ids: list[str],
        status: str,
        error: str | None = None,
    ) -> None:
        await self._mark_status("graph_status", chunk_ids, status, error)

    async def _mark_status(
        self,
        field: str,
        chunk_ids: list[str],
        status: str,
        error: str | None,
    ) -> None:
        if not chunk_ids:
            return
        values: dict[str, str | None] = {field: status}
        if error is not None:
            values["last_error"] = error
        await self.session.execute(
            update(KnowledgeChunk).where(KnowledgeChunk.id.in_(chunk_ids)).values(**values)
        )

    @staticmethod
    def _has_same_index_text(chunk: KnowledgeChunk, draft: ChunkDraft) -> bool:
        return normalize_chunk_text(chunk.embedding_text) == normalize_chunk_text(
            draft.embedding_text
        ) and normalize_chunk_text(chunk.context_prefix) == normalize_chunk_text(
            draft.context_prefix
        )

    @staticmethod
    def _apply_draft(
        chunk: KnowledgeChunk,
        draft: ChunkDraft,
        *,
        content_generation: int,
    ) -> None:
        chunk.content_generation = content_generation
        chunk.content_hash = draft.content_hash
        chunk.chunk_index = draft.chunk_index
        chunk.content = draft.content
        chunk.embedding_text = draft.embedding_text
        chunk.context_prefix = draft.context_prefix
        chunk.start_char = draft.start_char
        chunk.end_char = draft.end_char
        chunk.page_number = draft.page_number
        chunk.section_path = list(draft.section_path)
        chunk.chunk_metadata = dict(draft.metadata)
