from datetime import date, datetime, time, timezone
from decimal import Decimal

import pytest

from app.agent.session.models import Session
from app.agent.session.session_manager_db import SessionManagerDB
from app.db.session_repository import SessionRepository


def test_message_json_values_normalize_nested_dates_and_decimals():
    timestamp = datetime(2026, 8, 11, 14, 53, 37, tzinfo=timezone.utc)

    assert SessionRepository._convert_json_value({
        "observed_at": timestamp,
        "window": [date(2026, 8, 11), time(14, 53, 37)],
        "value": Decimal("25.4"),
    }) == {
        "observed_at": "2026-08-11T14:53:37+00:00",
        "window": ["2026-08-11", "14:53:37"],
        "value": 25.4,
    }


class _FailingMessageRepository:
    async def get_session(self, session_id):
        return None

    async def create_session(self, **kwargs):
        return object()

    async def sync_conversation_history_incremental(self, session_id, history):
        return False


@pytest.mark.asyncio
async def test_session_save_fails_when_transcript_persistence_fails():
    manager = SessionManagerDB(enable_cache=False)
    manager.repository = _FailingMessageRepository()
    session = Session(
        session_id="expert_session_test",
        query="分析天气条件",
        conversation_history=[{"type": "user", "content": "分析天气条件"}],
    )

    assert await manager.save_session(session) is False
