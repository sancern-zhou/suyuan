from types import SimpleNamespace

import pytest

from app.knowledge_base.retrieval_service import KnowledgeRetrievalService


def test_rrf_promotes_chunk_supported_by_both_retrievers():
    chunk_results = [
        {"chunk_id": "plain", "content": "普通命中"},
        {"chunk_id": "supported", "content": "图支持命中"},
    ]
    graph_results = [
        {
            "chunk_id": "supported",
            "matched_entity_ids": ["e1"],
            "graph_paths": [{"kb_id": "kb1"}],
        }
    ]

    fused = KnowledgeRetrievalService.reciprocal_rank_fusion(
        chunk_results,
        graph_results,
        graph_weight=1.0,
    )

    assert fused[0]["chunk_id"] == "supported"
    assert fused[0]["fusion_sources"] == ["chunk", "graph"]
    assert fused[0]["matched_entity_ids"] == ["e1"]


class _CrossKbService(KnowledgeRetrievalService):
    async def _search_one_kb(self, *, kb_id, **kwargs):
        return [
            {
                "chunk_id": f"{kb_id}-chunk",
                "knowledge_base_id": kb_id,
                "content": kb_id,
                "fusion_sources": ["graph"],
                "graph_paths": [{"kb_id": kb_id}],
                "rrf_score": 1.0,
            }
        ]


@pytest.mark.asyncio
async def test_cross_kb_search_never_mixes_graph_paths():
    service = _CrossKbService(session_factory=None, vector_store=SimpleNamespace())

    results = await service.search(query="臭氧", kb_ids=["kb1", "kb2"], top_k=10)

    assert {item["knowledge_base_id"] for item in results} == {"kb1", "kb2"}
    assert all(
        path["kb_id"] == item["knowledge_base_id"]
        for item in results
        for path in item["graph_paths"]
    )
