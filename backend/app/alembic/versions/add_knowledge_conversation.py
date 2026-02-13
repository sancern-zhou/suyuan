"""
知识问答对话表迁移脚本

执行方式：
    cd backend
    python -m app.alembic.versions.add_knowledge_conversation

此脚本创建知识问答连续对话所需的两张表：
- knowledge_conversation_sessions: 对话会话表
- knowledge_conversation_turns: 对话轮次表
"""

import os
import sys
import asyncio

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text
from app.db.database import engine
import structlog

logger = structlog.get_logger()


async def create_conversation_tables():
    """创建知识问答对话表"""

    # 会话表
    create_sessions_table = text("""
    CREATE TABLE IF NOT EXISTS knowledge_conversation_sessions (
        id VARCHAR(36) PRIMARY KEY,
        title VARCHAR(256) NOT NULL DEFAULT '新对话',
        status VARCHAR(20) NOT NULL DEFAULT 'active',
        knowledge_base_ids JSON DEFAULT '[]'::json,
        total_turns INTEGER DEFAULT 0,
        last_query TEXT DEFAULT '',
        user_id VARCHAR(36),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP,

        CONSTRAINT ck_session_status CHECK (status IN ('active', 'archived', 'expired'))
    )
    """)

    # 轮次表
    create_turns_table = text("""
    CREATE TABLE IF NOT EXISTS knowledge_conversation_turns (
        id VARCHAR(36) PRIMARY KEY,
        session_id VARCHAR(36) NOT NULL,
        turn_index INTEGER NOT NULL,
        role VARCHAR(20) NOT NULL,
        content TEXT NOT NULL,
        sources JSON DEFAULT '[]'::json,
        sources_count INTEGER DEFAULT 0,
        query_metadata JSON DEFAULT '{}'::json,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT fk_turn_session FOREIGN KEY (session_id)
            REFERENCES knowledge_conversation_sessions(id) ON DELETE CASCADE,
        CONSTRAINT ck_turn_role CHECK (role IN ('user', 'assistant')),
        CONSTRAINT ck_turn_index CHECK (turn_index >= 1)
    )
    """)

    # 索引
    create_indexes = [
        text("CREATE INDEX IF NOT EXISTS idx_kcs_user_time ON knowledge_conversation_sessions(user_id, created_at DESC)"),
        text("CREATE INDEX IF NOT EXISTS idx_kcs_status_time ON knowledge_conversation_sessions(status, updated_at DESC)"),
        text("CREATE INDEX IF NOT EXISTS idx_kcs_expires ON knowledge_conversation_sessions(expires_at)"),
        text("CREATE INDEX IF NOT EXISTS idx_kct_session_index ON knowledge_conversation_turns(session_id, turn_index)"),
        text("CREATE INDEX IF NOT EXISTS idx_kct_created_at ON knowledge_conversation_turns(created_at DESC)"),
    ]

    async with engine.begin() as conn:
        # 创建表
        await conn.execute(create_sessions_table)
        logger.info("knowledge_conversation_sessions table created")

        await conn.execute(create_turns_table)
        logger.info("knowledge_conversation_turns table created")

        # 创建索引
        for idx in create_indexes:
            await conn.execute(idx)
            logger.debug("index created", sql=str(idx))

    logger.info("all conversation tables and indexes created successfully")


async def drop_conversation_tables():
    """删除知识问答对话表（回滚用）"""

    drop_turns = text("DROP TABLE IF EXISTS knowledge_conversation_turns CASCADE")
    drop_sessions = text("DROP TABLE IF EXISTS knowledge_conversation_sessions CASCADE")

    async with engine.begin() as conn:
        await conn.execute(drop_turns)
        logger.info("knowledge_conversation_turns table dropped")

        await conn.execute(drop_sessions)
        logger.info("knowledge_conversation_sessions table dropped")

    logger.info("all conversation tables dropped successfully")


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="知识问答对话表迁移脚本")
    parser.add_argument("--drop", action="store_true", help="删除表（回滚）")
    args = parser.parse_args()

    if args.drop:
        await drop_conversation_tables()
    else:
        await create_conversation_tables()

    # 关闭引擎
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
