import inspect
import time

import httpx
import pytest

from app.knowledge_base.retrieval_service import KnowledgeRetrievalService
from app.knowledge_base.remote_reranker import RemoteReranker
from app.knowledge_base.retrieval_utils import deduplicate_results_by_content
from app.knowledge_base.schemas import SearchRequest
from app.knowledge_base.service import KnowledgeBaseService
from app.tools.workflow.knowledge_qa_workflow import KnowledgeQAWorkflow


def test_pure_retrieval_defaults_disable_reranking_and_graph_expansion():
    service_defaults = inspect.signature(KnowledgeBaseService.search).parameters
    retrieval_defaults = inspect.signature(KnowledgeRetrievalService.search).parameters
    request = SearchRequest(query="检查维护要求")

    assert service_defaults["use_reranker"].default == "never"
    assert service_defaults["use_graph_retrieval"].default is False
    assert retrieval_defaults["use_graph_retrieval"].default is False
    assert request.rerank_mode == "never"
    assert request.use_graph_retrieval is False


def test_knowledge_workflow_defaults_to_five_results_with_global_reranking():
    defaults = inspect.signature(KnowledgeQAWorkflow.execute).parameters

    assert defaults["top_k"].default == 5
    assert defaults["reranker"].default == "always"


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
    monkeypatch.setenv("KNOWLEDGE_RERANK_BACKEND", "local")
    monkeypatch.setattr(service, "_get_reranker", lambda: service._reranker)
    monkeypatch.setenv("KNOWLEDGE_RERANK_TIMEOUT_SECONDS", "0.1")
    candidates = [
        {"content": "first", "score": 0.8},
        {"content": "second", "score": 0.4},
    ]

    results = await service._rerank("query", candidates, top_k=1)

    assert results == [{"content": "first", "score": 0.8}]


def test_remote_reranker_does_not_reuse_bailian_token_plan_credentials(monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_RERANK_API_KEY", raising=False)
    monkeypatch.delenv("KNOWLEDGE_RERANK_API_URL", raising=False)
    monkeypatch.delenv("KNOWLEDGE_RERANK_MODEL", raising=False)
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    monkeypatch.setenv("BAILIAN_API_KEY", "bailian-key")

    reranker = RemoteReranker.from_env()

    assert reranker is None


@pytest.mark.asyncio
async def test_remote_reranker_maps_ranked_indices_to_scores():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.91},
                    {"index": 0, "relevance_score": 0.42},
                ]
            },
        )

    reranker = RemoteReranker(
        api_url="https://rerank.example/v1/rerank",
        api_key="test-key",
        model="test-model",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    result = await reranker.rerank("query", ["first", "second"], top_n=2)

    assert result == [(1, 0.91), (0, 0.42)]


@pytest.mark.asyncio
async def test_remote_reranker_accepts_dashscope_nested_response():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert b'"input"' in request.content
        assert b'"parameters"' in request.content
        return httpx.Response(
            200,
            json={
                "output": {
                    "results": [{"index": 0, "relevance_score": 0.87}]
                }
            },
        )

    reranker = RemoteReranker(
        api_url="https://dashscope.example/api/v1/services/rerank/text-rerank/text-rerank",
        api_key="test-key",
        model="qwen3-rerank",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    result = await reranker.rerank("query", ["document"], top_n=1)

    assert result == [(0, 0.87)]


@pytest.mark.asyncio
async def test_remote_reranker_uses_flat_payload_for_compatible_endpoint():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert b'"query"' in request.content
        assert b'"documents"' in request.content
        assert b'"input"' not in request.content
        return httpx.Response(
            200,
            json={"results": [{"index": 0, "relevance_score": 0.83}]},
        )

    reranker = RemoteReranker(
        api_url="https://workspace.example/compatible-api/v1/reranks",
        api_key="test-key",
        model="qwen3-rerank",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    result = await reranker.rerank("query", ["document"], top_n=1)

    assert result == [(0, 0.83)]


@pytest.mark.asyncio
async def test_remote_global_rerank_does_not_load_local_model(monkeypatch):
    class FakeRemoteReranker:
        async def rerank(self, _query, _documents, _top_k):
            return [(1, 0.9), (0, 0.2)]

    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    monkeypatch.setenv("KNOWLEDGE_RERANK_BACKEND", "remote")
    monkeypatch.setattr(
        "app.knowledge_base.service.get_remote_reranker",
        lambda: FakeRemoteReranker(),
    )
    monkeypatch.setattr(
        service,
        "_get_reranker",
        lambda: pytest.fail("local reranker must not be loaded"),
    )
    candidates = [
        {"content": "first", "score": 0.8},
        {"content": "second", "score": 0.4},
    ]

    results = await service._rerank("query", candidates, top_k=2)

    assert [item["content"] for item in results] == ["second", "first"]
    assert results[0]["original_score"] == 0.4
