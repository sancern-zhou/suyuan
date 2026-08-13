"""Lazy routing for shared and project-local Qdrant stores."""

from __future__ import annotations

from typing import Any

from .models import KnowledgeBaseStorageScope
from .vector_store import KnowledgeVectorStore


class KnowledgeVectorStoreRouter:
    """Create a store only when its scope is actually used.

    ``QDRANT_*`` remains the legacy/central shared configuration.  A local
    knowledge base uses ``LOCAL_QDRANT_*`` and defaults to localhost:6333.
    """

    def __init__(self) -> None:
        self._stores: dict[str, KnowledgeVectorStore] = {}

    def for_scope(self, scope: KnowledgeBaseStorageScope | str) -> KnowledgeVectorStore:
        value = getattr(scope, "value", scope)
        if value not in {"shared", "local"}:
            raise ValueError(f"Unsupported vector store scope: {value}")
        if value not in self._stores:
            if value == "shared":
                self._stores[value] = KnowledgeVectorStore(
                    env_prefix="SHARED_QDRANT", fallback_prefix="QDRANT"
                )
            else:
                self._stores[value] = KnowledgeVectorStore(
                    env_prefix="LOCAL_QDRANT", default_port=6334
                )
        return self._stores[value]

    def for_knowledge_base(self, kb: Any) -> KnowledgeVectorStore:
        return self.for_scope(getattr(kb, "vector_store_scope", "shared"))
