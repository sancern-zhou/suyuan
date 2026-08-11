from datetime import date, datetime, time, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.agent.session.models import Session
from app.agent.session.session_manager_db import SessionManagerDB
from app.db.database import Base
from app.db.models_session import SessionDB, SessionMessageDB
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


@pytest.mark.asyncio
async def test_lightweight_restore_keeps_complete_long_unicode_content(tmp_path):
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    async with test_engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[SessionDB.__table__, SessionMessageDB.__table__],
            )
        )

    async with AsyncSession(test_engine) as db_session:
        db_session.add(SessionDB(session_id="session_partial", query="分析气象条件"))
        await db_session.commit()

    repository = SessionRepository()
    repository.engine = test_engine
    repository._pool_status = lambda: {}
    final_content = "一、总体形势\n" + ("气象条件分析。" * 400) + "\n二、分阶段气象机制分析\n完整结论"
    history = [
        {"type": "user", "content": "分析气象条件"},
        {"type": "final", "content": final_content, "data": {"large": "x" * 5000}},
    ]
    assert await repository.sync_conversation_history_incremental(
        "session_partial", history
    ) is True
    restored = await repository.get_messages_before(
        "session_partial", limit=100, include_data=False
    )

    assert len(restored["messages"]) == 2
    assert restored["messages"][-1]["content"] == final_content
    assert restored["messages"][-1]["content"].endswith("完整结论")
    assert "data" not in restored["messages"][-1]
    await test_engine.dispose()
