"""
删除并重新创建 quick_trace_analysis 表

Drop and Recreate quick_trace_analysis Table
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from app.db.database import engine
from app.db.models.quick_trace_models import QuickTraceAnalysis
import structlog

logger = structlog.get_logger()


async def drop_and_recreate():
    """删除并重新创建表"""
    try:
        logger.info("删除现有的 quick_trace_analysis 表...")

        # 删除表
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS quick_trace_analysis CASCADE"))

        logger.info("✓ 表删除成功")

        # 重新创建表
        logger.info("重新创建 quick_trace_analysis 表...")

        async with engine.begin() as conn:
            await conn.run_sync(QuickTraceAnalysis.metadata.create_all)

        logger.info("✓ 表创建成功")

        # 验证表结构
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT
                    column_name,
                    data_type,
                    is_nullable
                FROM information_schema.columns
                WHERE table_name = 'quick_trace_analysis'
                ORDER BY ordinal_position
            """))
            columns = result.fetchall()

            logger.info("新表结构:")
            logger.info("-" * 80)
            for col in columns:
                logger.info(f"  {col[0]:<30} {col[1]:<20} NULL={col[2]}")
            logger.info("-" * 80)

        logger.info("✓ 表重建完成！")

    except Exception as e:
        logger.error(f"✗ 操作失败: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(drop_and_recreate())
