"""
清理会话中的重复 final 消息

对于每个会话，只保留最新的一个 final 消息，删除其他的。
"""
import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session_repository import get_session_repository
from structlog import get_logger

logger = get_logger()


async def clean_duplicate_final_messages():
    """清理所有会话中的重复 final 消息"""
    repo = get_session_repository()

    # 获取所有会话
    sessions = await repo.list_sessions(limit=None)

    logger.info("开始清理重复 final 消息", total_sessions=len(sessions))

    cleaned_count = 0
    removed_count = 0

    for session_summary in sessions:
        session_id = session_summary["session_id"]

        try:
            # 获取会话的所有消息
            result = await repo.get_messages_before(session_id, before_sequence=None, limit=10000)
            messages = result.get("messages", [])

            if not messages:
                continue

            # 找到所有 final 消息
            final_messages = []
            for msg in messages:
                msg_type = msg.get("type") or (msg.get("role") if msg.get("role") == "user" else None)
                if msg_type in ["final", "assistant"]:
                    final_messages.append(msg)

            if len(final_messages) <= 1:
                continue

            # 获取需要删除的 final 消息（除了最后一个）
            final_messages = []
            for msg in messages:
                msg_type = msg.get("type") or msg.get("role")
                if msg_type in ["final", "assistant"]:
                    final_messages.append(msg)

            if len(final_messages) <= 1:
                continue

            # 获取需要删除的 final 消息的 sequence_number（除了最后一个）
            sequence_numbers = [msg.get("sequence_number") for msg in final_messages[:-1]]

            logger.info(
                "cleaning_session",
                session_id=session_id,
                total_finals=len(final_messages),
                removing=len(sequence_numbers),
                keeping_sequence=final_messages[-1].get("sequence_number")
            )

            # 删除重复的 final 消息（使用 sequence_number）
            from sqlalchemy import delete, table, text

            async with repo.engine.begin() as conn:
                # 构建IN子句
                seq_str = ', '.join([str(sn) for sn in sequence_numbers])
                sql = text(f"""
                    DELETE FROM session_messages
                    WHERE session_id = :session_id
                    AND sequence_number IN ({seq_str})
                """)
                await conn.execute(sql, {"session_id": session_id})

            removed_count += len(ids_to_remove)
            cleaned_count += 1

        except Exception as e:
            logger.error(
                "cleaning_session_failed",
                session_id=session_id,
                error=str(e)
            )

    logger.info(
        "清理完成",
        cleaned_sessions=cleaned_count,
        total_removed_messages=removed_count
    )


if __name__ == "__main__":
    asyncio.run(clean_duplicate_final_messages())
