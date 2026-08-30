"""
数据库初始化脚本

执行此脚本创建会话相关的数据库表
"""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import structlog

from app.db.database import SESSION_DATABASE_URL
from app.db.models_session import Base
from app.conversations.models import ConversationCatalogDB

logger = structlog.get_logger()


async def init_session_tables():
    """初始化会话数据库表"""
    engine = create_async_engine(SESSION_DATABASE_URL, echo=True)

    try:
        # 创建所有表
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(
                lambda sync_conn: ConversationCatalogDB.__table__.create(
                    sync_conn, checkfirst=True
                )
            )

        logger.info("session_tables_created_successfully")

        # 验证表是否创建成功
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN (
                    'sessions',
                    'session_messages',
                    'session_resources',
                    'session_resource_versions',
                    'conversation_catalog'
                )
            """))
            tables = [row[0] for row in result]

            logger.info("tables_verified", tables=tables)

            expected_tables = {
                "sessions",
                "session_messages",
                "session_resources",
                "session_resource_versions",
                "conversation_catalog",
            }
            if expected_tables.issubset(tables):
                logger.info("✅ 所有表创建成功")
            else:
                logger.error("❌ 部分表创建失败", created_tables=tables)

    except Exception as e:
        logger.error("failed_to_create_tables", error=str(e))
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_session_tables())
