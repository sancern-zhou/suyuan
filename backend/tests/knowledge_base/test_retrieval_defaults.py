import inspect
import time

import pytest

from app.knowledge_base.retrieval_service import KnowledgeRetrievalService
from app.knowledge_base.retrieval_utils import deduplicate_results_by_content
from app.knowledge_base.schemas import SearchRequest
from app.knowledge_base.service import KnowledgeBaseService


def test_pure_retrieval_defaults_disable_reranking_and_graph_expansion():
    service_defaults = inspect.signature(KnowledgeBaseService.search).parameters
    retrieval_defaults = inspect.signature(KnowledgeRetrievalService.search).parameters
    request = SearchRequest(query="检查维护要求")

    assert service_defaults["use_reranker"].default == "never"
    assert service_defaults["use_graph_retrieval"].default is False
    assert retrieval_defaults["use_graph_retrieval"].default is False
    assert request.rerank_mode == "never"
    assert request.use_graph_retrieval is False


def test_content_deduplication_keeps_strongest_hit_and_merges_provenance():
    results = [
        {
            "knowledge_base_id": "kb1",
            "chunk_id": "chunk-old",
            "content_hash": "same-content",
            "content": "重复内容",
            "score": 0.4,
            "fusion_sources": ["chunk"],
            "retrieval_routes": ["original"],
        },
        {
            "knowledge_base_id": "kb1",
            "chunk_id": "chunk-strong",
            "content_hash": "same-content",
            "content": "重复内容",
            "score": 0.8,
            "fusion_sources": ["graph"],
            "retrieval_routes": ["hyde"],
        },
        {
            "knowledge_base_id": "kb2",
            "chunk_id": "chunk-other-kb",
            "content_hash": "same-content",
            "content": "重复内容",
            "score": 0.9,
        },
    ]

    deduplicated = deduplicate_results_by_content(results)

    assert len(deduplicated) == 2
    assert deduplicated[0]["chunk_id"] == "chunk-strong"
    assert deduplicated[0]["fusion_sources"] == ["chunk", "graph"]
    assert deduplicated[0]["retrieval_routes"] == ["original", "hyde"]
    assert deduplicated[1]["knowledge_base_id"] == "kb2"


@pytest.mark.asyncio
async def test_rerank_timeout_falls_back_to_recall_scores(monkeypatch):
    class SlowReranker:
        def predict(self, _pairs):
            time.sleep(0.2)
            return [0.1, 0.9]

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    service._reranker = SlowReranker()
    monkeypatch.setattr(service, "_get_reranker", lambda: service._reranker)
    monkeypatch.setenv("KNOWLEDGE_RERANK_TIMEOUT_SECONDS", "0.1")
    candidates = [
        {"content": "first", "score": 0.8},
        {"content": "second", "score": 0.4},
    ]

    results = await service._rerank("query", candidates, top_k=1)

    assert results == [{"content": "first", "score": 0.8}]
