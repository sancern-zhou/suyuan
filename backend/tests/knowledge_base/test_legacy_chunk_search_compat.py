from types import SimpleNamespace

from app.knowledge_base.vector_store import KnowledgeVectorStore
from tests.knowledge_base.test_typed_vector_store import make_store


def test_legacy_untyped_points_remain_visible_to_ordinary_chunk_search():
    store = make_store()
    store.qdrant_client.search_hits = [
        SimpleNamespace(
            payload={
                "content": "legacy chunk",
                "document_id": "doc1",
                "chunk_id": "legacy-1",
            },
            score=0.9,
        )
    ]

    results = store._search_sync("kb1", "legacy", 5, 0.1, None)

    assert results[0]["content"] == "legacy chunk"
    assert results[0]["metadata"]["chunk_id"] == "legacy-1"
    query_filter = store.qdrant_client.search_calls[0]["query_filter"]
    assert [condition.key for condition in query_filter.must_not] == ["record_type"]


def test_ordinary_chunk_search_excludes_explicit_graph_record_types():
    store = make_store()
    store.qdrant_client.search_hits = []

    KnowledgeVectorStore._search_sync(store, "kb1", "臭氧", 5, 0.1, {})

    query_filter = store.qdrant_client.search_calls[0]["query_filter"]
    excluded = query_filter.must_not[0].match.any
    assert set(excluded) == {"entity", "relation"}
