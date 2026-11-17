# -*- coding: utf-8 -*-
"""OpenAI 兼容嵌入网关（Qwen3-Embedding）与自定义认证头测试。"""
from __future__ import annotations

import json

import httpx
import pytest

from app.knowledge_base.remote_embedding import (
    RemoteEmbeddingModel,
    build_auth_headers,
)


def _client(transport, **kwargs):
    return RemoteEmbeddingModel(
        "http://gateway:41080/api/v1",
        api_format="openai",
        model="Qwen3-Embedding-8B",
        transport=transport,
        **kwargs,
    )


def test_custom_header_sends_bare_key():
    expected = {"jcmp-token": "gw-key"}
    assert build_auth_headers("gw-key", "jcmp-token", None) == expected
    assert build_auth_headers("gw-key", "jcmp-token", "") == expected
    assert build_auth_headers("k", "Authorization", None) == {
        "Authorization": "Bearer k"
    }
    assert build_auth_headers(None, "Authorization", None) == {}


def test_posts_openai_payload_and_normalizes():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            {
                "url": str(request.url),
                "auth": request.headers.get("jcmp-token"),
                "bearer": request.headers.get("authorization"),
                "body": json.loads(request.content),
            }
        )
        payload = {"data": [{"index": 0, "embedding": [3.0, 4.0]}]}
        return httpx.Response(200, json=payload)

    client = _client(
        httpx.MockTransport(handler),
        api_key="gw-key",
        api_key_header="jcmp-token",
    )
    result = client.encode("hello")

    assert calls[0]["url"] == "http://gateway:41080/api/v1/embeddings"
    assert calls[0]["auth"] == "gw-key"
    assert calls[0]["bearer"] is None
    assert calls[0]["body"] == {
        "model": "Qwen3-Embedding-8B",
        "input": ["hello"],
    }
    assert result.tolist() == pytest.approx([0.6, 0.8])


def test_data_items_are_ordered_by_index():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 2.0]},
                    {"index": 0, "embedding": [2.0, 0.0]},
                ]
            },
        )

    client = _client(httpx.MockTransport(handler), api_key="k")
    rows = client.encode(["a", "b"]).tolist()
    assert rows[0] == pytest.approx([1.0, 0.0])
    assert rows[1] == pytest.approx([0.0, 1.0])


def test_default_authorization_uses_bearer_prefix():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]}
        )

    client = _client(httpx.MockTransport(handler), api_key="gw-key")
    client.encode("hello")

    assert seen["authorization"] == "Bearer gw-key"


def test_missing_model_raises_before_request():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call the gateway without a model")

    client = RemoteEmbeddingModel(
        "http://gateway:41080/api/v1",
        api_format="openai",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ValueError, match="EMBEDDING_SERVICE_MODEL"):
        client.encode("hello")


def test_from_env_reads_openai_gateway_settings(monkeypatch):
    monkeypatch.setenv("EMBEDDING_SERVICE_URL", "http://<llm-gateway>:41080/api/v1")
    monkeypatch.setenv("EMBEDDING_SERVICE_FORMAT", "openai")
    monkeypatch.setenv("EMBEDDING_SERVICE_MODEL", "Qwen3-Embedding-8B")
    monkeypatch.setenv("EMBEDDING_SERVICE_API_KEY", "gw-key")
    monkeypatch.setenv("EMBEDDING_SERVICE_API_KEY_HEADER", "jcmp-token")
    monkeypatch.setenv("EMBEDDING_SERVICE_API_KEY_PREFIX", "")

    client = RemoteEmbeddingModel.from_env()

    assert client is not None
    assert client.endpoint == "http://<llm-gateway>:41080/api/v1/embeddings"
    assert client.model == "Qwen3-Embedding-8B"
    assert client.api_key_header == "jcmp-token"
    assert build_auth_headers(
        client.api_key, client.api_key_header, client.api_key_prefix
    ) == {"jcmp-token": "gw-key"}


def test_native_format_keeps_legacy_endpoint():
    client = RemoteEmbeddingModel("http://127.0.0.1:8020")
    assert client.endpoint == "http://127.0.0.1:8020/embed"


def test_configured_model_name_follows_env(monkeypatch):
    from app.knowledge_base.remote_embedding import configured_embedding_model_name

    monkeypatch.delenv("EMBEDDING_SERVICE_MODEL", raising=False)
    assert configured_embedding_model_name() == "BAAI/bge-m3"

    monkeypatch.setenv("EMBEDDING_SERVICE_MODEL", "Qwen3-Embedding-8B")
    assert configured_embedding_model_name() == "Qwen3-Embedding-8B"

