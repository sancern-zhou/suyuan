from app.agent.session.conversation_persistence import ConversationPersistenceService
from app.agent.session.models import Session


def test_conversation_persistence_does_not_store_thought_events():
    session = Session(
        session_id="social_session_existing",
        query="old query",
        conversation_history=[
            {"type": "user", "content": "旧问题", "timestamp": "2026-07-08T16:00:00"},
            {"type": "thought", "content": "旧思考不应保留", "timestamp": "2026-07-08T16:00:01"},
        ],
    )

    ConversationPersistenceService().append_complete(
        session,
        display_history=[
            {"type": "user", "content": "新问题", "timestamp": "2026-07-08T16:01:00"},
            {"type": "thought", "content": "运行时思考不应持久化", "timestamp": "2026-07-08T16:01:01"},
            {"type": "final", "content": "最终回答", "timestamp": "2026-07-08T16:01:02"},
        ],
        collected_data_ids=[],
        collected_visuals=[],
    )

    assert [message["type"] for message in session.conversation_history] == [
        "user",
        "user",
        "final",
    ]
    assert "运行时思考不应持久化" not in str(session.conversation_history)
    assert "旧思考不应保留" not in str(session.conversation_history)
