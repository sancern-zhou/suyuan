from types import SimpleNamespace

import numpy as np
import pytest

from app.knowledge_base.vector_store import KnowledgeVectorStore


class FakeEmbeddingModel:
    def encode(self, texts, **_kwargs):
        if isinstance(texts, str):
            return np.array([0.1, 0.2], dtype=float)
        return np.array([[0.1, 0.2] for _ in texts], dtype=float)


class FakeQdrantClient:
    def __init__(self):
        self.upsert_calls = []
        self.delete_calls = []
        self.search_calls = []
        self.search_hits = []

    def upsert(self, **kwargs):
        self.upsert_calls.append(kwargs)

    def delete(self, **kwargs):
        self.delete_calls.append(kwargs)

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return self.search_hits


def make_store() -> KnowledgeVectorStore:
    store = KnowledgeVectorStore.__new__(KnowledgeVectorStore)
    store.qdrant_client = FakeQdrantClient()
    store.embedding_model = FakeEmbeddingModel()
    store._jieba_initialized = True
    store._get_collection_vector_config = lambda _name: {
        "has_named_vectors": True,
        "has_sparse": True,
        "vectors_type": "dict",
    }
    store._compute_sparse_vector = lambda _text: {1: 0.5}
    return store


def test_typed_point_id_is_stable_and_namespaced():
    store = make_store()

    entity_id = store.typed_point_id("entity", "record-1")

    assert entity_id == store.typed_point_id("entity", "record-1")
    assert entity_id != store.typed_point_id("relation", "record-1")


@pytest.mark.asyncio
async def test_upsert_records_writes_typed_payload_and_deterministic_id():
    store = make_store()

    count = await store.upsert_records(
        "kb1",
        [
            {
                "record_type": "entity",
                "record_id": "entity-1",
                "content": "臭氧",
                "embedding_text": "污染物 臭氧 O3",
                "payload": {"review_status": "confirmed", "kb_id": "kb1"},
            }
        ],
    )

    assert count == 1
    point = store.qdrant_client.upsert_calls[0]["points"][0]
    assert point.id == store.typed_point_id("entity", "entity-1")
    assert point.payload["record_type"] == "entity"
    assert point.payload["record_id"] == "entity-1"
    assert point.payload["review_status"] == "confirmed"


@pytest.mark.asyncio
async def test_search_records_filters_type_and_review_status_and_rejects_untyped_hits():
    store = make_store()
    store.qdrant_client.search_hits = [
        SimpleNamespace(payload={"content": "legacy chunk"}, score=0.9),
        SimpleNamespace(
            payload={
                "record_type": "entity",
                "record_id": "entity-1",
                "content": "臭氧",
                "review_status": "confirmed",
            },
            score=0.8,
        ),
    ]

    results = await store.search_records(
        "kb1",
        "臭氧",
        record_types={"entity"},
        review_statuses={"confirmed"},
        top_k=10,
    )

    assert [result["record_id"] for result in results] == ["entity-1"]
    query_filter = store.qdrant_client.search_calls[0]["query_filter"]
    assert {condition.key for condition in query_filter.must} == {
        "record_type",
        "review_status",
    }


@pytest.mark.asyncio
async def test_delete_records_uses_typed_point_ids():
    store = make_store()

    await store.delete_records("kb1", "relation", ["relation-1"])

    selector = store.qdrant_client.delete_calls[0]["points_selector"]
    assert selector.points == [store.typed_point_id("relation", "relation-1")]
