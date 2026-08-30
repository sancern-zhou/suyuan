#!/usr/bin/env python3
"""Remove stale knowledge-vector chunk points whose documents no longer exist."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
import sys
from pathlib import Path

from sqlalchemy import select

PROJECT_BACKEND = Path(__file__).resolve().parents[1]
if str(PROJECT_BACKEND) not in sys.path:
    sys.path.insert(0, str(PROJECT_BACKEND))

from app.knowledge_base import get_vector_store
from app.knowledge_base.models import Document, KnowledgeBase
from app.knowledge_base.shared_metadata import knowledge_base_read_session


async def _inspect_kb(kb_id: str):
    async with knowledge_base_read_session(kb_id) as db:
        kb = await db.scalar(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
        if kb is None:
            raise ValueError(f"Knowledge base not found: {kb_id}")
        document_ids = set(
            (await db.execute(
                select(Document.id).where(Document.knowledge_base_id == kb_id)
            )).scalars().all()
        )

    store = get_vector_store().for_scope(kb.vector_store_scope)
    client = store.qdrant_client
    if client is None:
        raise RuntimeError("Qdrant client is not available")

    orphan_counts: Counter[str] = Counter()
    orphan_chunk_ids: dict[str, list[str]] = defaultdict(list)
    total_points = 0
    offset = None

    while True:
        batch, offset = await asyncio.to_thread(
            client.scroll,
            collection_name=kb.qdrant_collection,
            offset=offset,
            limit=256,
            with_payload=True,
            with_vectors=False,
        )
        if not batch:
            if offset is None:
                break
            continue

        total_points += len(batch)
        for point in batch:
            payload = point.payload or {}
            document_id = str(payload.get("document_id") or "")
            if not document_id or document_id in document_ids:
                continue
            orphan_counts[document_id] += 1
            chunk_id = payload.get("chunk_id") or payload.get("record_id")
            if chunk_id:
                orphan_chunk_ids[document_id].append(str(chunk_id))

        if offset is None:
            break

    return kb, store, total_points, orphan_counts, orphan_chunk_ids


async def _cleanup_kb(kb_id: str, *, apply: bool) -> int:
    kb, store, total_points, orphan_counts, orphan_chunk_ids = await _inspect_kb(kb_id)

    print(
        {
            "kb_id": kb.id,
            "collection": kb.qdrant_collection,
            "scope": kb.vector_store_scope.value,
            "total_points": total_points,
            "orphan_document_ids": dict(orphan_counts),
        }
    )

    if not orphan_counts:
        return 0

    if not apply:
        return 0

    deleted = 0
    for document_id, count in sorted(orphan_counts.items()):
        ok = await store.delete_by_document(kb.qdrant_collection, document_id)
        if ok:
            deleted += count
            print(
                {
                    "document_id": document_id,
                    "chunk_ids": orphan_chunk_ids.get(document_id, []),
                    "deleted": count,
                }
            )
        else:
            raise RuntimeError(f"Failed to delete orphan vectors for document {document_id}")

    remaining = await _inspect_kb(kb_id)
    remaining_orphans = dict(remaining[3])
    if remaining_orphans:
        raise RuntimeError(
            f"Cleanup incomplete for {kb_id}: remaining orphan documents {remaining_orphans}"
        )
    return deleted


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb-id", required=True, help="Knowledge base id to inspect")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete orphan vector points instead of only reporting them",
    )
    args = parser.parse_args()

    deleted = await _cleanup_kb(args.kb_id, apply=args.apply)
    if args.apply:
        print({"status": "completed", "deleted_points": deleted})
    else:
        print({"status": "dry_run"})
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
