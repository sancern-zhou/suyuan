from datetime import datetime
from types import SimpleNamespace

from app.conversations.adapters import knowledge_session_to_payload
from app.conversations.schemas import ConversationCatalogRecord, ConversationSource


def test_knowledge_session_is_normalized_for_unified_read_only_restore():
    now = datetime(2026, 7, 14, 10, 0, 0)
    session = SimpleNamespace(
        id="kqa-1",
        title="知识问答",
        created_at=now,
        updated_at=now,
        turns=[
            SimpleNamespace(
                role="user",
                content="问题",
                created_at=now,
                sources=None,
                sources_count=0,
            ),
            SimpleNamespace(
                role="assistant",
                content="回答",
                created_at=now,
                sources=[{"document": "a.pdf"}],
                sources_count=1,
            ),
        ],
    )
    row = ConversationCatalogRecord(
        session_id="kqa-1",
        owner_user_id="u1",
        owner_username="alice",
        owner_display_name="Alice",
        source=ConversationSource.KNOWLEDGE_QA,
        mode="knowledge_qa",
        title="知识问答",
    )

    payload = knowledge_session_to_payload(session, row)

    assert payload["session_id"] == "kqa-1"
    assert payload["source"] == "knowledge_qa"
    assert [message["content"] for message in payload["conversation_history"]] == [
        "问题",
        "回答",
    ]
    assert payload["has_more_messages"] is False
    assert payload["total_message_count"] == 2
