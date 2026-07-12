from app.knowledge_base.graph_retrieval import reciprocal_rank_fusion


def test_rrf_fuses_chunk_and_graph_rankings():
    result = reciprocal_rank_fusion(
        {"chunk": ["c1", "c2"], "graph": ["c2", "c3"]},
        weights={"chunk": 1.0, "graph": 1.0},
        k=60,
    )
    assert result[0].chunk_id == "c2"
    assert set(result[0].sources) == {"chunk", "graph"}


def test_rrf_respects_source_weights():
    result = reciprocal_rank_fusion(
        {"chunk": ["c1"], "graph": ["c2"]},
        weights={"chunk": 1.0, "graph": 2.0},
    )
    assert result[0].chunk_id == "c2"
