from app.knowledge_base.retrieval_service import KnowledgeRetrievalService


def test_graph_path_summary_is_bounded_to_ten():
    fused = KnowledgeRetrievalService.reciprocal_rank_fusion(
        [],
        [{"chunk_id": "c1", "graph_paths": [{"relation_id": str(i)} for i in range(25)]}],
        graph_weight=1.0,
    )

    assert len(fused[0]["graph_paths"]) == 10
