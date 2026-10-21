from app.knowledge_base.retrieval_service import KnowledgeRetrievalService


def test_rrf_fuses_chunk_and_graph_rankings():
    result = KnowledgeRetrievalService.reciprocal_rank_fusion(
        [{"chunk_id": "c1"}, {"chunk_id": "c2"}],
        [{"chunk_id": "c2"}, {"chunk_id": "c3"}], 1.0,
    )
    assert result[0]["chunk_id"] == "c2"
    assert set(result[0]["fusion_sources"]) == {"chunk", "graph"}


def test_rrf_respects_source_weights():
    result = KnowledgeRetrievalService.reciprocal_rank_fusion(
        [{"chunk_id": "c1"}], [{"chunk_id": "c2"}], 2.0,
    )
    assert result[0]["chunk_id"] == "c2"


def test_rrf_ignores_duplicate_ids_and_disabled_graph_source():
    result = KnowledgeRetrievalService.reciprocal_rank_fusion(
        [{"chunk_id": "c1"}, {"chunk_id": "c1"}], [{"chunk_id": "c2"}], 0.0,
    )
    assert len(result) == 1
    assert result[0]["score"] == 1 / 61
