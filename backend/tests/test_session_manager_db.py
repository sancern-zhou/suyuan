from datetime import datetime

import pytest

from app.agent.session.session_manager_db import SessionManagerDB


class FakeSessionRepository:
    def __init__(self):
        self.session_id = "assistant_session_1"
        self.full_messages = [
            {
                "type": "user",
                "role": "user",
                "content": f"message {index}",
                "timestamp": datetime(2026, 1, 1).isoformat(),
                "sequence_number": index,
            }
            for index in range(4)
        ]

    def _session_dict(self, include_messages):
        return {
            "session_id": self.session_id,
            "query": "test query",
            "created_at": datetime(2026, 1, 1).isoformat(),
            "updated_at": datetime(2026, 1, 1).isoformat(),
            "data_ids": [],
            "visual_ids": [],
            "office_documents": [],
            "metadata": {"mode": "assistant"},
            "error": None,
            "current_step": None,
            "current_expert": None,
            "conversation_history": self.full_messages[:] if include_messages else [],
        }

    async def get_session_with_messages(
        self,
        session_id,
        include_messages=True,
        include_artifacts=True,
    ):
        assert session_id == self.session_id
        return self._session_dict(include_messages)

    async def get_message_count(self, session_id):
        assert session_id == self.session_id
        return len(self.full_messages)

    async def get_messages_before(
        self,
        session_id,
        before_sequence=None,
        limit=30,
        include_data=True,
    ):
        assert session_id == self.session_id
        messages = self.full_messages[-limit:]
        return {
            "messages": messages,
            "has_more": True,
            "oldest_sequence": messages[0]["sequence_number"],
            "total_count": len(self.full_messages),
        }


def make_session_manager(repository):
    manager = SessionManagerDB.__new__(SessionManagerDB)
    manager.auto_save = True
    manager.retention_days = 30
    manager.enable_cache = True
    manager.sessions = {}
    manager.repository = repository
    return manager


@pytest.mark.asyncio
async def test_paginated_restore_does_not_cache_truncated_session():
    repository = FakeSessionRepository()
    manager = make_session_manager(repository)

    paginated = await manager.load_session_with_pagination(
        repository.session_id,
        message_limit=2,
    )

    assert paginated is not None
    assert len(paginated["session"].conversation_history) == 2

    full_session = await manager.load_session(repository.session_id)

    assert full_session is not None
    assert len(full_session.conversation_history) == 4
