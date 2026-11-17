# -*- coding: utf-8 -*-
"""嵌入模型切换后的稠密维度校验测试。"""
from __future__ import annotations

import threading

import pytest

from app.knowledge_base.vector_store import KnowledgeVectorStore


def _store(dim: int, config: dict) -> KnowledgeVectorStore:
    store = KnowledgeVectorStore.__new__(KnowledgeVectorStore)
    store._embedding_dim = dim
    store._collection_config_cache = {}
    store._collection_config_lock = threading.RLock()
    store._get_collection_vector_config = lambda _name: dict(config)
    return store


def test_matching_dim_passes():
    store = _store(4096, {"dense_size": 4096, "has_named_vectors": True})
    store._ensure_collection_dim_matches(
        "kb1", store._get_collection_vector_config("kb1")
    )


def test_mismatched_dim_raises_actionable_error():
    store = _store(4096, {"dense_size": 1024, "has_named_vectors": True})
    with pytest.raises(RuntimeError) as excinfo:
        store._ensure_collection_dim_matches(
            "kb1", store._get_collection_vector_config("kb1")
        )

    message = str(excinfo.value)
    assert "1024" in message
    assert "4096" in message
    assert "Re-index" in message


def test_unknown_dim_is_tolerated():
    store = _store(4096, {"has_named_vectors": True})
    store._ensure_collection_dim_matches(
        "kb1", store._get_collection_vector_config("kb1")
    )
