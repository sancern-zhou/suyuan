# -*- coding: utf-8 -*-
"""网关式重排接口（Qwen3-Reranker + jcmp-token）测试。"""
from __future__ import annotations

import json

import httpx
import pytest

from app.knowledge_base.remote_reranker import RemoteReranker

GATEWAY_URL = "http://<llm-gateway>:41080/api/v1/rerank"


def _reranker(transport, **kwargs):
    options = {
        "api_url": GATEWAY_URL,
        "api_key": "gw-key",
        "model": "Qwen3-Reranker-8B",
        "timeout_seconds": 5,
        "transport": transport,
    }
    options.update(kwargs)
    return RemoteReranker(**options)


@pytest.mark.asyncio
async def test_gateway_payload_and_custom_header():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            {
                "auth": request.headers.get("jcmp-token"),
                "bearer": request.headers.get("authorization"),
                "body": json.loads(request.content),
            }
        )
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "index": 2,
                        "document": {"text": "c"},
                        "relevance_score": 0.96,
                    },
                    {
                        "index": 0,
                        "document": {"text": "a"},
                        "relevance_score": 0.94,
                    },
                ]
            },
        )

    reranker = _reranker(
        httpx.MockTransport(handler), api_key_header="jcmp-token"
    )
    ranked = await reranker.rerank("q", ["a", "b", "c"], top_n=2)

    assert ranked == [(2, 0.96), (0, 0.94)]
    assert calls[0]["auth"] == "gw-key"
    assert calls[0]["bearer"] is None
    body = calls[0]["body"]
    assert body["model"] == "Qwen3-Reranker-8B"
    assert body["query"] == "q"
    assert body["documents"] == ["a", "b", "c"]
    assert body["top_n"] == 2


@pytest.mark.asyncio
async def test_default_authorization_keeps_bearer_prefix():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200, json={"results": [{"index": 0, "relevance_score": 0.5}]}
        )

    reranker = _reranker(httpx.MockTransport(handler), api_key="gw-key")
    await reranker.rerank("q", ["a"], top_n=1)

    assert seen["authorization"] == "Bearer gw-key"


@pytest.mark.asyncio
async def test_empty_results_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    reranker = _reranker(httpx.MockTransport(handler))
    with pytest.raises(ValueError):
        await reranker.rerank("q", ["a"], top_n=1)


def test_from_env_reads_gateway_settings(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_RERANK_API_URL", GATEWAY_URL)
    monkeypatch.setenv("KNOWLEDGE_RERANK_API_KEY", "gw-key")
    monkeypatch.setenv("KNOWLEDGE_RERANK_API_KEY_HEADER", "jcmp-token")
    monkeypatch.setenv("KNOWLEDGE_RERANK_API_KEY_PREFIX", "")
    monkeypatch.setenv("KNOWLEDGE_RERANK_MODEL", "Qwen3-Reranker-8B")

    reranker = RemoteReranker.from_env()

    assert reranker is not None
    assert reranker.api_url == GATEWAY_URL
    assert reranker.model == "Qwen3-Reranker-8B"
    assert reranker.api_key_header == "jcmp-token"
