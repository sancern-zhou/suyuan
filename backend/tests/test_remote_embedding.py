# -*- coding: utf-8 -*-
"""远程嵌入客户端与嵌入服务接口测试。

不加载真实 bge-m3 权重：HTTP 层用 httpx.MockTransport 桩，服务层用
stub 模型替身。
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.knowledge_base.remote_embedding import (
    EmbeddingArray,
    RemoteEmbeddingModel,
    build_llama_index_embedding,
)


class TestEmbeddingArray:
    def test_single_vector_behaves_1d(self):
        arr = EmbeddingArray([[0.1, 0.2, 0.3]], single=True)
        assert len(arr) == 3
        assert arr.tolist() == [0.1, 0.2, 0.3]
        assert list(arr) == [0.1, 0.2, 0.3]
        assert arr[1] == 0.2
        assert arr.shape == (3,)

    def test_batch_behaves_2d_with_row_tolist(self):
        arr = EmbeddingArray([[0.1, 0.2], [0.3, 0.4]])
        assert len(arr) == 2
        assert arr.tolist() == [[0.1, 0.2], [0.3, 0.4]]
        rows = list(arr)
        assert len(rows) == 2
        # vector_store 对每行单独调用 tolist()
        assert [row.tolist() for row in rows] == [[0.1, 0.2], [0.3, 0.4]]
        assert arr.shape == (2, 2)

    def test_zip_strict_iteration(self):
        arr = EmbeddingArray([[1.0], [2.0]])
        records = ["a", "b"]
        pairs = list(zip(records, arr, strict=True))
        assert pairs[1][1].tolist() == [2.0]


def _stub_service(responses: list[list[list[float]]] | None = None):
    """返回 (transport, 收到的请求体列表)；每次请求回一页 embeddings。"""
    calls: list[dict] = []
    pages = iter(responses) if responses is not None else None

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if pages is not None:
            return httpx.Response(200, json={"embeddings": next(pages), "dim": 2})
        return httpx.Response(
            200,
            json={"embeddings": [[0.1, 0.2] for _ in body["texts"]], "dim": 2},
        )

    return httpx.MockTransport(handler), calls


class TestRemoteEmbeddingModel:
    def test_from_env_returns_none_without_url(self, monkeypatch):
        monkeypatch.delenv("EMBEDDING_SERVICE_URL", raising=False)
        assert RemoteEmbeddingModel.from_env() is None

    def test_from_env_reads_url_and_timeout(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_SERVICE_URL", "http://127.0.0.1:8020")
        monkeypatch.setenv("EMBEDDING_SERVICE_TIMEOUT_SECONDS", "5")
        client = RemoteEmbeddingModel.from_env()
        assert client is not None
        assert client.api_url == "http://127.0.0.1:8020"
        assert client.timeout_seconds == 5.0

    def test_encode_single_sentence_returns_1d(self):
        transport, calls = _stub_service()
        client = RemoteEmbeddingModel("http://svc", transport=transport)
        result = client.encode("hello", normalize_embeddings=True)
        assert result.tolist() == [0.1, 0.2]
        assert len(result) == 2
        assert calls[0] == {"texts": ["hello"], "normalize": True}

    def test_encode_batch_returns_2d(self):
        transport, _ = _stub_service()
        client = RemoteEmbeddingModel("http://svc", transport=transport)
        result = client.encode(["a", "b", "c"])
        assert result.tolist() == [[0.1, 0.2]] * 3
        assert len(result) == 3

    def test_encode_splits_batches(self):
        transport, calls = _stub_service()
        client = RemoteEmbeddingModel("http://svc", batch_size=2, transport=transport)
        result = client.encode(["a", "b", "c"])
        assert len(result) == 3
        assert [len(call["texts"]) for call in calls] == [2, 1]

    def test_encode_mismatched_response_raises(self):
        transport, _ = _stub_service(responses=[[[0.1, 0.2]]])
        client = RemoteEmbeddingModel("http://svc", transport=transport)
        with pytest.raises(ValueError):
            client.encode(["a", "b"])

    def test_encode_empty_batch_raises(self):
        client = RemoteEmbeddingModel("http://svc")
        with pytest.raises(ValueError):
            client.encode([])


class TestLlamaIndexAdapter:
    def test_adapter_delegates_encode(self):
        transport, calls = _stub_service()
        client = RemoteEmbeddingModel("http://svc", transport=transport)

        class _FakeBase:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        embedding = build_llama_index_embedding(
            client, factory=lambda: _FakeBase
        )
        vector = embedding._get_text_embedding("hello")
        assert vector == [0.1, 0.2]
        assert embedding._get_text_embeddings(["a", "b"]) == [[0.1, 0.2]] * 2
        assert calls[1]["texts"] == ["a", "b"]


class TestEmbeddingServerEndpoint:
    def test_embed_endpoint_shape(self, monkeypatch):
        fastapi_testclient = pytest.importorskip("fastapi.testclient")
        from app.services import embedding_server

        class _StubModel:
            def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
                return EmbeddingArray([[0.1, 0.2] for _ in texts])

        monkeypatch.setattr(embedding_server, "get_model", lambda: _StubModel())
        with fastapi_testclient.TestClient(embedding_server.app) as http:
            health = http.get("/health").json()
            assert health["status"] == "ok"
            body = http.post("/embed", json={"texts": ["x", "y"]}).json()
        assert body["dim"] == 2
        assert body["embeddings"] == [[0.1, 0.2], [0.1, 0.2]]

    def test_embed_endpoint_rejects_empty(self, monkeypatch):
        fastapi_testclient = pytest.importorskip("fastapi.testclient")
        from app.services import embedding_server

        monkeypatch.setattr(
            embedding_server, "get_model", lambda: (_ for _ in ()).throw(AssertionError("不应加载模型"))
        )
        with fastapi_testclient.TestClient(embedding_server.app) as http:
            response = http.post("/embed", json={"texts": []})
        assert response.status_code == 400
