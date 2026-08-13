from __future__ import annotations

import pytest

from app.lifecycle.knowledge_base import warmup_knowledge_base_models


@pytest.mark.asyncio
async def test_warmup_resolves_shared_store_from_router(monkeypatch):
    calls: list[object] = []

    class EmbeddingModel:
        def encode(self, values, **kwargs):
            calls.append((values, kwargs))

    class SharedStore:
        embedding_model = EmbeddingModel()

    class Router:
        def for_scope(self, scope):
            calls.append(scope)
            return SharedStore()

    monkeypatch.setattr("app.knowledge_base.get_vector_store", lambda: Router())
    monkeypatch.setenv("KNOWLEDGE_BASE_RERANKER_WARMUP_ON_STARTUP", "false")

    await warmup_knowledge_base_models()

    assert calls[0] == "shared"
    assert calls[1] == (["预热测试"], {"show_progress_bar": False})
