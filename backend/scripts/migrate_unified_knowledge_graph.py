#!/usr/bin/env python3
"""Backfill legacy Qdrant chunk payloads into PostgreSQL fact rows."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict

from sqlalchemy import func, select

from app.knowledge_base.chunk_diff import build_chunk_drafts
from app.knowledge_base.chunk_repository import KnowledgeChunkRepository
from app.knowledge_base.graph_models import KnowledgeChunk
from app.knowledge_base.models import Document, KnowledgeBase


class ChunkBackfillMigrator:
    def __init__(self, session_factory, qdrant_client):
        self.session_factory = session_factory
        self.qdrant_client = qdrant_client

    def _scroll(self, collection_name: str) -> list:
        points = []
        offset = None
        while True:
            batch, offset = self.qdrant_client.scroll(
                collection_name=collection_name,
                offset=offset,
                limit=256,
                with_payload=True,
            )
            points.extend(batch)
            if offset is None:
                return points

    async def migrate_kb(self, kb_id: str, *, apply: bool) -> dict:
        async with self.session_factory() as session:
            kb = await session.get(KnowledgeBase, kb_id)
            if kb is None:
                raise ValueError(f"Knowledge base not found: {kb_id}")
            collection_name = kb.qdrant_collection
        points = await asyncio.to_thread(self._scroll, collection_name)
        grouped: dict[str, list[dict]] = defaultdict(list)
        missing_documents = 0
        unrecovered_metadata = 0
        for point in points:
            payload = dict(point.payload or {})
            if payload.get("record_type") in {"entity", "relation"}:
                continue
            document_id = str(payload.get("document_id") or "")
            if not document_id:
                missing_documents += 1
                continue
            recovered = (
                payload.get("start_char") is not None and payload.get("end_char") is not None
            )
            if not recovered:
                unrecovered_metadata += 1
            grouped[document_id].append(
                {
                    "content": payload.get("original_content") or payload.get("content") or "",
                    "embedding_text": payload.get("embedding_text") or payload.get("content") or "",
                    "context_prefix": payload.get("context_prefix") or "",
                    "start_char": payload.get("start_char"),
                    "end_char": payload.get("end_char"),
                    "page_number": payload.get("page_number"),
                    "section_path": payload.get("section_path") or [],
                    "metadata": {
                        **dict(payload.get("chunk_metadata") or payload.get("metadata") or {}),
                        "metadata_recovered": recovered,
                        "legacy_chunk_id": payload.get("chunk_id"),
                    },
                    "chunk_index": int(payload.get("chunk_index") or 0),
                }
            )

        if apply:
            async with self.session_factory() as session, session.begin():
                repository = KnowledgeChunkRepository(session)
                for document_id, raw_chunks in grouped.items():
                    document = await session.get(Document, document_id)
                    if document is None or document.knowledge_base_id != kb_id:
                        missing_documents += 1
                        continue
                    raw_chunks.sort(key=lambda item: item["chunk_index"])
                    await repository.replace_document_chunks(
                        kb_id=kb_id,
                        document_id=document_id,
                        content_generation=document.content_generation,
                        drafts=build_chunk_drafts(raw_chunks),
                    )

        async with self.session_factory() as session:
            postgres_chunks = int(
                await session.scalar(
                    select(func.count())
                    .select_from(KnowledgeChunk)
                    .where(KnowledgeChunk.kb_id == kb_id)
                )
                or 0
            )
        return {
            "kb_id": kb_id,
            "mode": "apply" if apply else "dry-run",
            "qdrant_points": sum(len(items) for items in grouped.values()),
            "postgres_chunks": postgres_chunks,
            "missing_documents": missing_documents,
            "unrecovered_metadata": unrecovered_metadata,
        }


async def _run(args) -> int:
    from app.db.database import async_session
    from app.knowledge_base import get_vector_store

    migrator = ChunkBackfillMigrator(async_session, get_vector_store().qdrant_client)
    async with async_session() as session:
        query = select(KnowledgeBase.id)
        if args.kb_id:
            query = query.where(KnowledgeBase.id == args.kb_id)
        kb_ids = list((await session.execute(query)).scalars())
    failed = False
    for kb_id in kb_ids:
        result = await migrator.migrate_kb(kb_id, apply=args.apply)
        if args.verify and result["qdrant_points"] != result["postgres_chunks"]:
            failed = True
        print(json.dumps(result, ensure_ascii=False))
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview only (default)")
    mode.add_argument("--apply", action="store_true", help="Write PostgreSQL chunk facts")
    mode.add_argument("--verify", action="store_true", help="Compare Qdrant and PostgreSQL counts")
    parser.add_argument("--kb-id", help="Limit operation to one knowledge base")
    return parser


def main() -> int:
    return asyncio.run(_run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
