"""Remote embedding client mirroring the SentenceTransformer.encode surface.

bge-m3 权重约 1G，此前每个 web/worker 进程各加载一份，把小内存机器上的
worker 数焊死在 3。把权重收敛到独立服务（app.services.embedding_server）
后，进程通过 EMBEDDING_SERVICE_URL 走 HTTP 调用；未配置该变量时保持原有
本地加载行为，开发机和旧部署无需任何改动。
"""

from __future__ import annotations

import os
from typing import Callable, Union

import httpx
import structlog
from pydantic import PrivateAttr

logger = structlog.get_logger()

EmbedInput = Union[str, list[str]]


class EmbeddingArray:
    """encode() 结果的最小列表仿真：单句为 1D 向量，批量行为 2D。

    vector_store 对返回值的使用面只有：len()、迭代、下标、tolist()，
    且批量场景会对每行单独调用 tolist()，因此行同样包装为本类型。
    """

    def __init__(self, vectors: list[list[float]], single: bool = False):
        self._vectors = vectors
        self._single = single

    def tolist(self) -> Union[list[float], list[list[float]]]:
        if self._single:
            return list(self._vectors[0])
        return [list(vector) for vector in self._vectors]

    def __len__(self) -> int:
        if self._single:
            return len(self._vectors[0])
        return len(self._vectors)

    def __iter__(self):
        if self._single:
            return iter(self._vectors[0])
        return (EmbeddingArray([vector], single=True) for vector in self._vectors)

    def __getitem__(self, index):
        if self._single:
            return self._vectors[0][index]
        return EmbeddingArray([self._vectors[index]], single=True)

    @property
    def shape(self) -> tuple[int, ...]:
        if self._single:
            return (len(self),)
        return (len(self._vectors), len(self._vectors[0]) if self._vectors else 0)


class RemoteEmbeddingModel:
    """SentenceTransformer.encode 的 HTTP 兼容客户端。

    调用方已在 asyncio.to_thread 中执行 encode，这里用同步 httpx 不会
    阻塞事件循环。
    """

    def __init__(
        self,
        api_url: str,
        timeout_seconds: float = 60.0,
        batch_size: int = 32,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.batch_size = max(1, batch_size)
        self.transport = transport

    @classmethod
    def from_env(cls) -> "RemoteEmbeddingModel | None":
        api_url = os.getenv("EMBEDDING_SERVICE_URL", "").strip()
        if not api_url:
            return None
        timeout_seconds = max(
            1.0, float(os.getenv("EMBEDDING_SERVICE_TIMEOUT_SECONDS", "60"))
        )
        return cls(api_url=api_url, timeout_seconds=timeout_seconds)

    def encode(
        self,
        sentences: EmbedInput,
        normalize_embeddings: bool = True,
        show_progress_bar: bool = False,
        **_ignored,
    ) -> EmbeddingArray:
        single = isinstance(sentences, str)
        texts = [sentences] if single else list(sentences)
        if not texts:
            raise ValueError("encode() requires at least one sentence")

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(
                self._post(texts[start : start + self.batch_size], normalize_embeddings)
            )
        logger.debug(
            "remote_embedding_encoded", count=len(texts), dim=len(vectors[0])
        )
        return EmbeddingArray(vectors, single=single)

    def _post(self, texts: list[str], normalize: bool) -> list[list[float]]:
        with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = client.post(
                f"{self.api_url}/embed",
                json={"texts": texts, "normalize": normalize},
            )
            response.raise_for_status()
        embeddings = response.json().get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise ValueError("embedding service returned mismatched embeddings")
        return embeddings


def build_llama_index_embedding(
    remote: RemoteEmbeddingModel,
    factory: Callable[[], type] | None = None,
):
    """把远程客户端包成 LlamaIndex BaseEmbedding，供语义分块解析器使用。"""
    if factory is not None:
        base_cls = factory()
    else:
        from llama_index.core.embeddings import BaseEmbedding as base_cls

    class RemoteHTTPEmbedding(base_cls):
        # BaseEmbedding 是 pydantic 模型，实例级属性必须经 PrivateAttr 声明
        _remote: PrivateAttr = PrivateAttr(default=None)

        def __init__(self, client: RemoteEmbeddingModel, **kwargs):
            super().__init__(model_name="remote-bge-m3", **kwargs)
            self._remote = client

        @classmethod
        def class_name(cls) -> str:
            return "RemoteHTTPEmbedding"

        def _get_query_embedding(self, query: str) -> list[float]:
            return self._remote.encode(query).tolist()

        def _get_text_embedding(self, text: str) -> list[float]:
            return self._remote.encode(text).tolist()

        def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
            return self._remote.encode(texts).tolist()

        async def _aget_query_embedding(self, query: str) -> list[float]:
            return self._get_query_embedding(query)

        async def _aget_text_embedding(self, text: str) -> list[float]:
            return self._get_text_embedding(text)

        async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
            return self._get_text_embeddings(texts)

    return RemoteHTTPEmbedding(remote)
