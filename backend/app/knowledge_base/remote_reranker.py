"""Remote reranker client for globally ordering cross-knowledge-base hits."""

from __future__ import annotations

import os
from typing import Any

import httpx


class RemoteReranker:
    def __init__(
        self,
        *,
        api_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    @classmethod
    def from_env(cls) -> RemoteReranker | None:
        api_url = os.getenv(
            "KNOWLEDGE_RERANK_API_URL",
            "https://api.siliconflow.cn/v1/rerank",
        ).strip()
        api_key = (
            os.getenv("KNOWLEDGE_RERANK_API_KEY", "").strip()
            or os.getenv("SILICONFLOW_API_KEY", "").strip()
        )
        if not api_url or not api_key:
            return None
        return cls(
            api_url=api_url,
            api_key=api_key,
            model=os.getenv(
                "KNOWLEDGE_RERANK_MODEL", "BAAI/bge-reranker-v2-m3"
            ).strip(),
            timeout_seconds=max(
                0.1,
                float(os.getenv("KNOWLEDGE_RERANK_TIMEOUT_SECONDS", "8")),
            ),
        )

    async def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[tuple[int, float]]:
        top_n = min(top_n, len(documents))
        if "/api/v1/services/rerank/" in self.api_url:
            payload = {
                "model": self.model,
                "input": {"query": query, "documents": documents},
                "parameters": {
                    "top_n": top_n,
                    "return_documents": False,
                    "instruct": (
                        "Given a knowledge-base question, retrieve passages that "
                        "directly answer the question or identify the requested document."
                    ),
                },
            }
        else:
            payload = {
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": top_n,
                "instruct": (
                    "Given a knowledge-base question, retrieve passages that directly "
                    "answer the question or identify the requested document."
                ),
            }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(self.timeout_seconds)
        async with httpx.AsyncClient(
            timeout=timeout,
            transport=self.transport,
        ) as client:
            response = await client.post(self.api_url, headers=headers, json=payload)
            response.raise_for_status()
        body: dict[str, Any] = response.json()
        output = body.get("output")
        results = body.get("results")
        if not isinstance(results, list) and isinstance(output, dict):
            results = output.get("results")
        if not isinstance(results, list):
            raise ValueError("Remote reranker response is missing results")

        ranked: list[tuple[int, float]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            score = item.get("relevance_score", item.get("score"))
            if isinstance(index, int) and 0 <= index < len(documents) and score is not None:
                ranked.append((index, float(score)))
        if not ranked:
            raise ValueError("Remote reranker response contains no valid rankings")
        return ranked
