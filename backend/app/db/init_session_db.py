"""
数据库初始化脚本

执行此脚本在 SESSION_DATABASE_URL（未设置时回退 DATABASE_URL）指向的库中
创建会话历史与定时任务执行记录相关的表。
"""

import asyncio
from sqlalchemy import text
import structlog

from app.db.session_database import SESSION_DATABASE_URL, session_engine
from app.db.models_session import Base

logger = structlog.get_logger()


async def init_session_tables():
    """初始化会话数据库表"""
    engine = session_engine

    # 以下模型定义在应用主 Base 上，但数据与会话历史同库存储
    from app.boards.models import Board, BoardVersion
    from app.conversations.models import ConversationCatalogDB
    from app.db.models.scheduled_task_execution_db import (
        ScheduledTaskExecutionDB,
    )
    from app.social.models import (
        SocialSessionMapping,
        SocialUser,
        WeixinScanTask,
    )
    from app.social.report_models import SocialReportResult

    session_scoped_tables = [
        ScheduledTaskExecutionDB.__table__,
        ConversationCatalogDB.__table__,
        Board.__table__,
        BoardVersion.__table__,  # 依赖 drawio_boards
        SocialUser.__table__,
        SocialSessionMapping.__table__,
        WeixinScanTask.__table__,
        SocialReportResult.__table__,
    ]

    try:
        # 创建所有表
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            for table in session_scoped_tables:
                await conn.run_sync(
                    lambda sync_conn, t=table: t.create(sync_conn, checkfirst=True)
                )

        logger.info("session_tables_created_successfully")

        # 验证表是否创建成功
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN (
                    'sessions', 'session_messages', 'session_resources',
                    'session_resource_versions', 'scheduled_task_executions',
                    'conversation_catalog', 'drawio_boards',
                    'drawio_board_versions', 'social_users',
                    'social_session_mappings', 'weixin_scan_tasks',
                    'social_report_results'
                )
            """))
            tables = [row[0] for row in result]

            logger.info("tables_verified", tables=tables)

            expected = {
                "sessions",
                "session_messages",
                "session_resources",
                "session_resource_versions",
                "scheduled_task_executions",
                "conversation_catalog",
                "drawio_boards",
                "drawio_board_versions",
                "social_users",
                "social_session_mappings",
                "weixin_scan_tasks",
                "social_report_results",
            }
            if expected.issubset(set(tables)):
                logger.info("✅ 所有表创建成功")
            else:
                logger.error(
                    "❌ 部分表创建失败",
                    created_tables=tables,
                    missing=sorted(expected - set(tables)),
                )

    except Exception as e:
        logger.error("failed_to_create_tables", error=str(e))
        raise


if __name__ == "__main__":
    logger.info("session_db_target", url=SESSION_DATABASE_URL)

    async def _main():
        try:
            await init_session_tables()
        finally:
            await session_engine.dispose()

    asyncio.run(_main())
