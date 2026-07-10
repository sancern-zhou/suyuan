"""Fusion retrieval across chunk vectors and trusted knowledge graphs."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select

from app.knowledge_base.graph_models import KnowledgeChunk
from app.knowledge_base.graph_repository import KnowledgeGraphRepository
from app.knowledge_base.graph_schemas import TRUSTED_REVIEW_STATUSES
from app.knowledge_base.models import KnowledgeBase


class KnowledgeRetrievalService:
    def __init__(
        self,
        *,
        session_factory,
        vector_store,
        reranker: Callable[[str, list[dict[str, Any]], int], Awaitable[list[dict[str, Any]]]]
        | None = None,
    ):
        self.session_factory = session_factory
        self.vector_store = vector_store
        self.reranker = reranker

    async def search(
        self,
        *,
        query: str,
        kb_ids: list[str],
        top_k: int,
        use_graph_retrieval: bool = True,
        graph_depth: int = 2,
        graph_seed_top_k: int = 10,
        graph_chunk_top_k: int = 20,
        graph_weight: float = 1.0,
    ) -> list[dict[str, Any]]:
        results_by_kb = await asyncio.gather(
            *(
                self._search_one_kb(
                    kb_id=kb_id,
                    query=query,
                    top_k=top_k,
                    use_graph_retrieval=use_graph_retrieval,
                    graph_depth=graph_depth,
                    graph_seed_top_k=graph_seed_top_k,
                    graph_chunk_top_k=graph_chunk_top_k,
                    graph_weight=graph_weight,
                )
                for kb_id in kb_ids
            )
        )
        results = [item for kb_results in results_by_kb for item in kb_results]
        results.sort(key=lambda item: item.get("rrf_score", 0.0), reverse=True)
        candidate_limit = min(max(top_k * 4, top_k), 60)
        results = results[:candidate_limit]
        if self.reranker is not None and len(results) > top_k:
            return await self.reranker(query, results, top_k)
        return results[:top_k]

    async def _search_one_kb(
        self,
        *,
        kb_id: str,
        query: str,
        top_k: int,
        use_graph_retrieval: bool,
        graph_depth: int,
        graph_seed_top_k: int,
        graph_chunk_top_k: int,
        graph_weight: float,
    ) -> list[dict[str, Any]]:
        if self.session_factory is None:
            return []
        async with self.session_factory() as session:
            kb = await session.get(KnowledgeBase, kb_id)
            if kb is None:
                return []
            recall = min(max(top_k * 3, 8), 30)
            chunk_results = await self.vector_store.hybrid_search(
                collection_name=kb.qdrant_collection,
                query=query,
                top_k=recall,
                score_threshold=0.0,
                alpha=0.7,
                filters=None,
            )
            for item in chunk_results:
                item["chunk_id"] = item.get("chunk_id") or (item.get("metadata") or {}).get(
                    "chunk_id"
                )
                item["knowledge_base_id"] = kb_id
                item["knowledge_base"] = {
                    "id": kb.id,
                    "name": kb.name,
                    "type": kb.kb_type.value,
                }

            # Qdrant is a rebuildable projection. Never return a point whose
            # PostgreSQL fact was deleted/replaced or has not been acknowledged.
            hit_chunk_ids = [item["chunk_id"] for item in chunk_results if item["chunk_id"]]
            current_chunk_ids = set(
                (
                    await session.execute(
                        select(KnowledgeChunk.id).where(
                            KnowledgeChunk.kb_id == kb_id,
                            KnowledgeChunk.id.in_(hit_chunk_ids),
                            KnowledgeChunk.vector_status == "indexed",
                        )
                    )
                )
                .scalars()
                .all()
            )
            chunk_results = [
                item for item in chunk_results if item["chunk_id"] in current_chunk_ids
            ]

            if not use_graph_retrieval or not kb.graph_enabled:
                return self.reciprocal_rank_fusion(chunk_results, [], graph_weight)

            seed_hits = await self.vector_store.search_records(
                kb.qdrant_collection,
                query,
                record_types={"entity", "relation"},
                review_statuses=set(TRUSTED_REVIEW_STATUSES),
                top_k=graph_seed_top_k,
            )
            seed_entity_ids: list[str] = []
            seed_relation_ids: list[str] = []
            for hit in seed_hits:
                if hit["record_type"] == "entity" and hit.get("record_id"):
                    seed_entity_ids.append(hit["record_id"])
                elif hit["record_type"] == "relation":
                    if hit.get("record_id"):
                        seed_relation_ids.append(hit["record_id"])
                    payload = hit.get("payload") or {}
                    seed_entity_ids.extend(
                        entity_id
                        for entity_id in (
                            payload.get("source_entity_id"),
                            payload.get("target_entity_id"),
                        )
                        if entity_id
                    )

            repository = KnowledgeGraphRepository(session)
            ordinary_chunk_ids = [item["chunk_id"] for item in chunk_results if item["chunk_id"]]
            seed_entity_ids.extend(
                await repository.entity_ids_for_chunk_ids(
                    kb_id=kb_id,
                    chunk_ids=ordinary_chunk_ids,
                    statuses=set(TRUSTED_REVIEW_STATUSES),
                )
            )
            seed_entity_ids = list(dict.fromkeys(seed_entity_ids))
            entities, relations = await repository.traverse(
                kb_id=kb_id,
                seed_entity_ids=seed_entity_ids,
                statuses=set(TRUSTED_REVIEW_STATUSES),
                depth=graph_depth,
                limit=max(graph_chunk_top_k, graph_seed_top_k),
            )
            entity_ids = [entity.id for entity in entities]
            relation_ids = list(
                dict.fromkeys([*seed_relation_ids, *(relation.id for relation in relations)])
            )
            graph_chunk_ids = await repository.chunk_ids_for_graph_records(
                kb_id=kb_id,
                entity_ids=entity_ids,
                relation_ids=relation_ids,
            )
            graph_chunks = list(
                (
                    await session.execute(
                        select(KnowledgeChunk).where(
                            KnowledgeChunk.kb_id == kb_id,
                            KnowledgeChunk.id.in_(graph_chunk_ids[:graph_chunk_top_k]),
                            KnowledgeChunk.vector_status == "indexed",
                        )
                    )
                ).scalars()
            )
            paths = [
                {
                    "kb_id": kb_id,
                    "relation_id": relation.id,
                    "source_entity_id": relation.source_entity_id,
                    "target_entity_id": relation.target_entity_id,
                    "relation_type": relation.relation_type,
                }
                for relation in relations[:10]
            ]
            graph_results = [
                {
                    "chunk_id": chunk.id,
                    "content": chunk.content,
                    "original_content": chunk.content,
                    "embedding_text": chunk.embedding_text,
                    "document_id": chunk.document_id,
                    "chunk_index": chunk.chunk_index,
                    "knowledge_base_id": kb_id,
                    "knowledge_base": {
                        "id": kb.id,
                        "name": kb.name,
                        "type": kb.kb_type.value,
                    },
                    "matched_entity_ids": entity_ids,
                    "matched_relation_ids": relation_ids,
                    "graph_paths": paths,
                }
                for chunk in sorted(graph_chunks, key=lambda item: graph_chunk_ids.index(item.id))
            ]
            return self.reciprocal_rank_fusion(chunk_results, graph_results, graph_weight)

    @staticmethod
    def reciprocal_rank_fusion(
        chunk_results: list[dict[str, Any]],
        graph_results: list[dict[str, Any]],
        graph_weight: float,
        k: float = 60.0,
    ) -> list[dict[str, Any]]:
        fused: dict[str, dict[str, Any]] = {}
        scores: dict[str, float] = {}

        def add(results, source: str, weight: float) -> None:
            for rank, item in enumerate(results, start=1):
                chunk_id = item.get("chunk_id") or (item.get("metadata") or {}).get("chunk_id")
                if not chunk_id:
                    continue
                current = fused.setdefault(chunk_id, {"chunk_id": chunk_id})
                current.update({key: value for key, value in item.items() if value is not None})
                sources = current.setdefault("fusion_sources", [])
                if source not in sources:
                    sources.append(source)
                scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (k + rank)

        add(chunk_results, "chunk", 1.0)
        add(graph_results, "graph", graph_weight)
        for chunk_id, item in fused.items():
            item["rrf_score"] = scores[chunk_id]
            if item.get("score") is not None:
                item.setdefault("original_score", item["score"])
            item["score"] = scores[chunk_id]
            item.setdefault("metadata", {})
            item.setdefault("matched_entity_ids", [])
            item.setdefault("matched_relation_ids", [])
            item.setdefault("graph_paths", [])
            item["graph_paths"] = item["graph_paths"][:10]
        return sorted(fused.values(), key=lambda item: item["rrf_score"], reverse=True)
