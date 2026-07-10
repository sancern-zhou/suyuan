from app.knowledge_base.chunk_diff import build_chunk_drafts, diff_chunks


def test_duplicate_text_gets_distinct_stable_keys():
    drafts = build_chunk_drafts(
        [
            {"content": "同一段", "embedding_text": "同一段"},
            {"content": "同一段", "embedding_text": "同一段"},
        ]
    )

    assert drafts[0].content_hash == drafts[1].content_hash
    assert drafts[0].chunk_key != drafts[1].chunk_key


def test_diff_reuses_unchanged_and_replaces_changed_chunks():
    old = build_chunk_drafts([{"content": "A"}, {"content": "B"}])
    new = build_chunk_drafts([{"content": "A"}, {"content": "C"}])

    result = diff_chunks(old, new)

    assert [item.content for item in result.reused] == ["A"]
    assert [item.content for item in result.added] == ["C"]
    assert [item.content for item in result.removed] == ["B"]


def test_diff_replaces_chunk_when_embedding_text_changes():
    old = build_chunk_drafts([{"content": "A", "embedding_text": "old context A"}])
    new = build_chunk_drafts([{"content": "A", "embedding_text": "new context A"}])

    result = diff_chunks(old, new)

    assert result.reused == []
    assert result.added == new
    assert result.removed == old


def test_content_normalization_stabilizes_hash_and_preserves_display_text():
    drafts = build_chunk_drafts([{"content": "Ｏ3\r\n  污染   过程"}])
    normalized = build_chunk_drafts([{"content": "O3\n污染 过程"}])

    assert drafts[0].content_hash == normalized[0].content_hash
    assert drafts[0].content == "Ｏ3\r\n  污染   过程"
