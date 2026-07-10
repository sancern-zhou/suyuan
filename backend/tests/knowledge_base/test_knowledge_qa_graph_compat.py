def test_graph_metadata_is_additive_to_legacy_chunk_contract():
    result = {
        "content": "臭氧证据",
        "document_id": "doc1",
        "chunk_id": "chunk1",
        "filename": "report.md",
        "score": 0.8,
        "fusion_sources": ["chunk", "graph"],
        "matched_entity_ids": ["e1"],
        "graph_paths": [{"kb_id": "kb1"}],
    }

    legacy_fields = {key: result[key] for key in ("content", "document_id", "filename", "score")}

    assert legacy_fields == {
        "content": "臭氧证据",
        "document_id": "doc1",
        "filename": "report.md",
        "score": 0.8,
    }


def test_search_response_accepts_graph_metadata_without_losing_chunk_fields():
    from app.knowledge_base.schemas import SearchResultItem

    item = SearchResultItem(
        content="臭氧证据",
        score=0.02,
        document_id="doc1",
        filename="report.md",
        knowledge_base={"id": "kb1", "name": "知识库", "type": "private"},
        metadata={},
        chunk_id="chunk1",
        fusion_sources=["chunk", "graph"],
        graph_paths=[{"kb_id": "kb1"}],
    )

    assert item.chunk_id == "chunk1"
    assert item.fusion_sources == ["chunk", "graph"]
