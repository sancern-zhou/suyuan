from app.knowledge_base.chunk_diff import build_chunk_drafts


def test_duplicate_text_gets_distinct_stable_keys():
    drafts = build_chunk_drafts(
        [
            {"content": "同一段", "embedding_text": "同一段"},
            {"content": "同一段", "embedding_text": "同一段"},
        ]
    )

    assert drafts[0].content_hash == drafts[1].content_hash
    assert drafts[0].chunk_key != drafts[1].chunk_key






def test_content_normalization_stabilizes_hash_and_preserves_display_text():
    drafts = build_chunk_drafts([{"content": "Ｏ3\r\n  污染   过程"}])
    normalized = build_chunk_drafts([{"content": "O3\n污染 过程"}])

    assert drafts[0].content_hash == normalized[0].content_hash
    assert drafts[0].content == "Ｏ3\r\n  污染   过程"
