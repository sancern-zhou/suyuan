"""Shared helpers for stable, diverse knowledge retrieval results."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from app.knowledge_base.chunk_diff import normalize_chunk_text


def result_content_identity(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") or {}
    content_hash = item.get("content_hash") or metadata.get("content_hash")
    if content_hash:
        return str(content_hash)
    content = item.get("original_content") or item.get("content") or ""
    return sha256(normalize_chunk_text(str(content)).encode("utf-8")).hexdigest()


def _result_score(item: dict[str, Any]) -> float:
    return float(item.get("rrf_score") or item.get("score") or 0.0)


def deduplicate_results_by_content(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep the strongest hit for identical content and merge provenance."""
    deduplicated: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for item in results:
        kb = item.get("knowledge_base") or {}
        kb_id = str(item.get("knowledge_base_id") or kb.get("id") or "")
        key = (kb_id, result_content_identity(item))
        existing = deduplicated.get(key)
        if existing is None:
            deduplicated[key] = item
            order.append(key)
            continue

        for field in (
            "fusion_sources",
            "matched_entity_ids",
            "matched_relation_ids",
            "graph_paths",
            "retrieval_routes",
        ):
            merged = list(existing.get(field) or [])
            for value in item.get(field) or []:
                if value not in merged:
                    merged.append(value)
            if merged:
                existing[field] = merged

        if _result_score(item) > _result_score(existing):
            for field in (
                "fusion_sources",
                "matched_entity_ids",
                "matched_relation_ids",
                "graph_paths",
                "retrieval_routes",
            ):
                if field in existing:
                    item[field] = existing[field]
            deduplicated[key] = item

    return [deduplicated[key] for key in order]
