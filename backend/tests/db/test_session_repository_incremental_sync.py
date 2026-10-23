"""sync_conversation_history_incremental 的持久化身份对账单元测试。

背景回归：
1. 旧实现按"长度+位置"对账，持久化视图过滤 thought 后长度短于数据库行数，
   被误判为"没有新消息"，整轮对话静默丢失。
2. 之后改为内容元组身份键对账，轻量加载视图（剥离 data）回存时身份不匹配，
   整批旧消息被误判为新消息重复插入，历史会话 AI 回复重复显示。

最终方案：以数据库行 id（"msg_<id>"）精确对账，新消息落库后把行 id 写回传入
字典；对账不再依赖任何内容表示。
"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.db.models_session import Base, SessionDB, SessionMessageDB

from app.db.session_repository import SessionRepository


def test_message_row_id_parses_persisted_ids():
    assert SessionRepository._message_row_id({"id": "msg_42"}) == 42
    assert SessionRepository._message_row_id({"id": "msg_0"}) == 0
    assert SessionRepository._message_row_id({"id": "frontend-uuid"}) is None
    assert SessionRepository._message_row_id({"id": "msg_x"}) is None
    assert SessionRepository._message_row_id({"id": 42}) is None
    assert SessionRepository._message_row_id({}) is None


def _sqlite_repository(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'messages.db'}")
    repository = SessionRepository()
    repository.engine = engine
    repository._pool_status = lambda: {}
    return engine, repository


async def _init_session(engine, session_id):
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda c: Base.metadata.create_all(c, tables=[SessionDB.__table__, SessionMessageDB.__table__])
        )
    async with AsyncSession(engine) as session:
        session.add(SessionDB(session_id=session_id, query="test"))
        await session.commit()


async def _rows(engine, session_id):
    async with AsyncSession(engine) as session:
        return (
            await session.execute(
                select(SessionMessageDB)
                .where(SessionMessageDB.session_id == session_id)
                .order_by(SessionMessageDB.sequence_number)
            )
        ).scalars().all()


TURN_ONE = [
    {"type": "user", "content": "查询数据", "timestamp": "2026-10-13T03:51:07.450000"},
    {
        "type": "tool_use",
        "content": "调用工具: xuchang_cube_metrics",
        "data": {"tool_use_id": "call_1", "tool_name": "xuchang_cube_metrics", "input": {"query": "q"}},
        "timestamp": "2026-10-13T03:51:08.000000",
    },
    {
        "type": "tool_result",
        "content": "查询 TownHour 返回 1 行(0.03s)",
        "data": {"tool_use_id": "call_1", "result": {"rows": 1}},
        "timestamp": "2026-10-13T03:51:08.100000",
    },
    {
        "type": "final",
        "content": "**查询结论**：数据如下",
        "data": {"answer": "**查询结论**：数据如下"},
        "timestamp": "2026-10-13T03:51:09.000000",
    },
]


@pytest.mark.asyncio
async def test_light_restored_history_does_not_duplicate(tmp_path):
    """回归：续问走 load_session_light，回存时按行 id 对账，不得重复插入旧消息。"""
    engine, repository = _sqlite_repository(tmp_path)
    session_id = "light-restore-test"
    try:
        await _init_session(engine, session_id)
        assert await repository.sync_conversation_history_incremental(session_id, TURN_ONE)

        restored = await repository.get_display_history_messages_light(session_id)
        assert len(restored) == len(TURN_ONE)
        assert all("data" not in msg for msg in restored)
        assert all(SessionRepository._message_row_id(msg) is not None for msg in restored)

        turn_two = restored + [
            {"type": "user", "content": "为什么查询这么多次", "timestamp": "2026-10-13T03:52:00.000000"},
            {"type": "final", "content": "这是问一次数，但底层多次取数", "timestamp": "2026-10-13T03:52:00.500000"},
        ]
        assert await repository.sync_conversation_history_incremental(session_id, turn_two)

        rows = await _rows(engine, session_id)
        assert len(rows) == len(turn_two)
        assert [row.msg_type for row in rows] == [msg["type"] for msg in turn_two]

        # 再次同步仍然幂等
        assert await repository.sync_conversation_history_incremental(session_id, turn_two)
        assert len(await _rows(engine, session_id)) == len(turn_two)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sync_stamps_row_ids_and_re_save_is_noop(tmp_path):
    """新消息落库后行 id 写回传入字典；同一批字典（或其副本）再次保存不重插。"""
    engine, repository = _sqlite_repository(tmp_path)
    session_id = "stamp-test"
    try:
        await _init_session(engine, session_id)
        history = [dict(msg) for msg in TURN_ONE]
        assert await repository.sync_conversation_history_incremental(session_id, history)

        rows = await _rows(engine, session_id)
        assert [msg["id"] for msg in history] == [f"msg_{row.id}" for msg, row in zip(history, rows)]

        # 同一批对象再次保存：全部按 id 命中，noop
        assert await repository.sync_conversation_history_incremental(session_id, history)
        # 深拷贝（不同对象、相同 id）再次保存：同样 noop
        copies = [dict(msg) for msg in history]
        assert await repository.sync_conversation_history_incremental(session_id, copies)
        assert len(await _rows(engine, session_id)) == len(TURN_ONE)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stale_row_id_is_appended_and_restamped(tmp_path):
    """id 不属于本会话（行已被全量重写删除）的消息按新消息追加，并改写为新行 id。"""
    engine, repository = _sqlite_repository(tmp_path)
    session_id = "stale-id-test"
    try:
        await _init_session(engine, session_id)
        stale = [{"type": "user", "content": "你好", "id": "msg_999999"}]
        assert await repository.sync_conversation_history_incremental(session_id, stale)

        rows = await _rows(engine, session_id)
        assert len(rows) == 1
        assert stale[0]["id"] == f"msg_{rows[0].id}"

        # 改写后的 id 生效：再次保存不重复
        assert await repository.sync_conversation_history_incremental(session_id, stale)
        assert len(await _rows(engine, session_id)) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("history", [
    [{"type": "user", "content": "好的"}],
    [{"type": "user", "content": "好的", "timestamp": "invalid"}],
    [{"type": "user", "content": "好的"}, {"type": "user", "content": "好的"}],
    [{"type": "user", "content": '"hello"', "timestamp": "2026-10-08T03:00:00"},
     {"type": "user", "content": "hello", "timestamp": "2026-10-08T03:00:00"}],
])
async def test_incremental_sync_preserves_occurrences_and_is_idempotent(tmp_path, history):
    engine, repository = _sqlite_repository(tmp_path)
    try:
        await _init_session(engine, "sync-test")
        for _ in range(2):
            assert await repository.sync_conversation_history_incremental("sync-test", history)
        rows = await _rows(engine, "sync-test")
        assert [row.content for row in rows] == [msg["content"] for msg in history]
        assert [row.sequence_number for row in rows] == list(range(len(history)))
        restored = [repository._msg_to_dict(row) for row in rows]
        assert [msg["content"] for msg in restored] == [msg["content"] for msg in history]
        assert await repository.sync_conversation_history_incremental("sync-test", restored)
        extended = [dict(msg) for msg in history] + [{"type": "final", "content": "new reply"}]
        assert await repository.sync_conversation_history_incremental("sync-test", extended)
        assert len(await _rows(engine, "sync-test")) == len(history) + 1
    finally:
        await engine.dispose()
