"""Remote embedding client mirroring the SentenceTransformer.encode surface.

bge-m3 权重约 1G，此前每个 web/worker 进程各加载一份，把小内存机器上的
worker 数焊死在 3。把权重收敛到独立服务（app.services.embedding_server）
后，进程通过 EMBEDDING_SERVICE_URL 走 HTTP 调用；未配置该变量时保持原有
本地加载行为，开发机和旧部署无需任何改动。

EMBEDDING_SERVICE_FORMAT 选择协议：
- native：app.services.embedding_server 的 /embed（默认探测）
- openai：OpenAI 兼容网关的 /api/v1/embeddings（body 为 model/input，
  支持 EMBEDDING_SERVICE_API_KEY + EMBEDDING_SERVICE_API_KEY_HEADER，
  例如 jcmp-token）
"""

from __future__ import annotations

import math
import os
from typing import Callable, Union

import httpx
import structlog
from pydantic import PrivateAttr

logger = structlog.get_logger()

EmbedInput = Union[str, list[str]]

_DEFAULT_API_KEY_HEADER = "Authorization"
_DEFAULT_API_KEY_PREFIX = "Bearer "


def resolve_api_key_prefix(header: str, prefix: str | None) -> str:
    """Authorization 默认带 Bearer 前缀，自定义认证头（如 jcmp-token）默认裸值。

    空字符串等同于未配置，避免 .env 里留空的模板值把 Bearer 前缀吃掉。
    """
    if prefix:
        return prefix
    return (
        _DEFAULT_API_KEY_PREFIX
        if header.strip().lower() == _DEFAULT_API_KEY_HEADER.lower()
        else ""
    )


def build_auth_headers(
    api_key: str | None,
    header: str = _DEFAULT_API_KEY_HEADER,
    prefix: str | None = None,
) -> dict[str, str]:
    if not api_key:
        return {}
    return {header: f"{resolve_api_key_prefix(header, prefix)}{api_key}"}


def configured_embedding_model_name() -> str:
    """知识库元数据里记录的嵌入模型名，跟随实际生效的配置而不是写死 bge-m3。"""
    model = os.getenv("EMBEDDING_SERVICE_MODEL", "").strip()
    if model:
        return model
    return "BAAI/bge-m3"


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
        api_format: str = "native",
        model: str | None = None,
        api_key: str | None = None,
        api_key_header: str = _DEFAULT_API_KEY_HEADER,
        api_key_prefix: str | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.batch_size = max(1, batch_size)
        self.transport = transport
        self.api_format = api_format.strip().lower() or "native"
        if self.api_format not in {"native", "openai"}:
            raise ValueError(f"Unsupported embedding api format: {self.api_format}")
        self.model = model
        self.api_key = api_key
        self.api_key_header = api_key_header
        self.api_key_prefix = api_key_prefix

    @classmethod
    def from_env(cls) -> "RemoteEmbeddingModel | None":
        api_url = os.getenv("EMBEDDING_SERVICE_URL", "").strip()
        if not api_url:
            return None
        timeout_seconds = max(
            1.0, float(os.getenv("EMBEDDING_SERVICE_TIMEOUT_SECONDS", "60"))
        )
        return cls(
            api_url=api_url,
            timeout_seconds=timeout_seconds,
            batch_size=int(os.getenv("EMBEDDING_SERVICE_BATCH_SIZE", "32")),
            api_format=os.getenv("EMBEDDING_SERVICE_FORMAT", "native"),
            model=os.getenv("EMBEDDING_SERVICE_MODEL", "").strip() or None,
            api_key=os.getenv("EMBEDDING_SERVICE_API_KEY", "").strip() or None,
            api_key_header=os.getenv(
                "EMBEDDING_SERVICE_API_KEY_HEADER", _DEFAULT_API_KEY_HEADER
            ).strip()
            or _DEFAULT_API_KEY_HEADER,
            api_key_prefix=os.environ.get("EMBEDDING_SERVICE_API_KEY_PREFIX"),
        )

    @property
    def endpoint(self) -> str:
        if self.api_format == "openai":
            if self.api_url.endswith("/embeddings"):
                return self.api_url
            return f"{self.api_url}/embeddings"
        if self.api_url.endswith("/embed"):
            return self.api_url
        return f"{self.api_url}/embed"

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
        headers = {"Content-Type": "application/json"}
        headers.update(
            build_auth_headers(self.api_key, self.api_key_header, self.api_key_prefix)
        )
        if self.api_format == "openai":
            if not self.model:
                raise ValueError(
                    "EMBEDDING_SERVICE_MODEL is required when "
                    "EMBEDDING_SERVICE_FORMAT=openai"
                )
            payload: dict = {"model": self.model, "input": texts}
        else:
            payload = {"texts": texts, "normalize": normalize}

        with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
        body = response.json()

        embeddings = self._extract_embeddings(body, len(texts))
        # native 服务端已按 normalize 归一化；OpenAI 兼容网关不保证，
        # 这里统一补齐，保证与 bge-m3 的余弦检索语义一致。
        if normalize and self.api_format == "openai":
            embeddings = [self._l2_normalize(vector) for vector in embeddings]
        return embeddings

    @staticmethod
    def _extract_embeddings(body: dict, expected: int) -> list[list[float]]:
        if isinstance(body.get("embeddings"), list):
            embeddings = body["embeddings"]
        elif isinstance(body.get("data"), list):
            items = sorted(
                (item for item in body["data"] if isinstance(item, dict)),
                key=lambda item: item.get("index", 0),
            )
            embeddings = [item.get("embedding") for item in items]
        else:
            raise ValueError("embedding service response is missing embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != expected:
            raise ValueError("embedding service returned mismatched embeddings")
        return embeddings

    @staticmethod
    def _l2_normalize(vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 1e-12:
            return list(vector)
        return [value / norm for value in vector]


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
            super().__init__(model_name=client.model or "remote-embedding", **kwargs)
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
