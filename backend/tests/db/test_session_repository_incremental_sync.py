"""sync_conversation_history_incremental 的身份键对账单元测试。

背景回归：旧实现按"长度+位置"对账，持久化视图过滤 thought 后长度短于
数据库行数，被误判为"没有新消息"，整轮对话静默丢失。
"""
from datetime import datetime

from app.db.session_repository import SessionRepository


def _make_row(message: dict, *, sequence_number: int = 0):
    role, msg_type = SessionRepository._resolve_role_and_type(message)
    return type(
        "Row",
        (),
        {
            "role": role,
            "msg_type": msg_type,
            "content": SessionRepository._serialize_content(message.get("content")),
            "data": SessionRepository._message_data(message),
            "timestamp": SessionRepository()._normalize_db_timestamp(message.get("timestamp")),
            "sequence_number": sequence_number,
        },
    )()


def test_incoming_key_matches_db_row_key():
    message = {
        "type": "tool_result",
        "role": "user",
        "content": "查询完成",
        "data": {"tool_use_id": "call_1", "tool_name": "execute_sql_query", "result": {"rows": 3}},
        "timestamp": "2026-10-08T03:01:22.410000",
    }

    row = _make_row(message)
    assert (
        SessionRepository()._incoming_message_identity_key(message)
        == SessionRepository()._db_message_identity_key(row)
    )


def test_restored_message_round_trip_keeps_identity():
    """DB 读回的消息（isoformat 时间戳 + 反序列化 content）再次保存时身份不变。"""
    message = {
        "type": "final",
        "role": "assistant",
        "content": [{"type": "text", "text": "结论：静稳天气"}],
        "data": {"run_id": "run-1", "partial": False},
        "timestamp": "2026-10-08T11:02:05.246117",
    }
    row = _make_row(message)
    # 模拟 _msg_to_dict 的还原表示
    restored = {
        "type": row.msg_type,
        "role": row.role,
        "content": SessionRepository._deserialize_content(row.content),
        "data": row.data,
        "timestamp": row.timestamp.isoformat(),
        "id": "msg_42",
        "sequence_number": row.sequence_number,
    }

    assert (
        SessionRepository()._incoming_message_identity_key(restored)
        == SessionRepository()._db_message_identity_key(row)
    )


def test_missing_timestamp_is_deterministic_not_now():
    message = {"type": "user", "content": "好的"}

    first = SessionRepository()._incoming_message_identity_key(message)
    second = SessionRepository()._incoming_message_identity_key(message)

    assert first == second


def test_timezone_equivalent_timestamps_collide():
    aware = {
        "type": "user",
        "content": "你好",
        "timestamp": "2026-10-08T11:00:00+08:00",
    }
    naive_utc = {
        "type": "user",
        "content": "你好",
        "timestamp": "2026-10-08T03:00:00",
    }

    assert (
        SessionRepository()._incoming_message_identity_key(aware)
        == SessionRepository()._incoming_message_identity_key(naive_utc)
    )


def test_distinct_messages_get_distinct_keys():
    base = {"type": "user", "content": "好的", "timestamp": "2026-10-08T03:00:00"}
    duplicate_text = {"type": "user", "content": "好的", "timestamp": "2026-10-08T03:00:05"}
    other_content = {"type": "user", "content": "继续", "timestamp": "2026-10-08T03:00:00"}

    keys = {
        SessionRepository()._incoming_message_identity_key(message)
        for message in (base, duplicate_text, other_content)
    }

    assert len(keys) == 3


def test_db_row_identity_handles_none_content_and_data():
    message = {"type": "thought", "content": None, "data": None}
    row = _make_row(message)

    key = SessionRepository()._db_message_identity_key(row)
    assert key[2] == "null" and key[3] == "null"
