"""
快速溯源分析数据库表初始化脚本

Quick Trace Analysis Database Table Initialization Script

使用方法:
    python init_quick_trace_db.py

功能:
    1. 连接到 weather_db 数据库 (180.184.30.94:5432)
    2. 创建 quick_trace_analysis 表（如果不存在）
    3. 创建必要的索引
    4. 验证表创建成功
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from app.db.database import init_db, engine
from app.db.models.quick_trace_models import QuickTraceAnalysis
import structlog

logger = structlog.get_logger()


async def create_table():
    """创建 quick_trace_analysis 表"""
    try:
        logger.info("开始创建 quick_trace_analysis 表...")

        # 使用 SQLAlchemy 自动创建表
        async with engine.begin() as conn:
            await conn.run_sync(QuickTraceAnalysis.metadata.create_all)

        logger.info("✓ quick_trace_analysis 表创建成功")

        # 验证表是否存在
        async with engine.begin() as conn:
            result = await conn.execute(
                text("SELECT EXISTS (SELECT FROM information_schema.tables "
                     "WHERE table_name = 'quick_trace_analysis')")
            )
            exists = result.scalar()

            if exists:
                logger.info("✓ 表存在性验证通过")
            else:
                logger.error("✗ 表存在性验证失败")
                return False

        # 查询表结构
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_name = 'quick_trace_analysis'
                ORDER BY ordinal_position
            """))
            columns = result.fetchall()

            logger.info("表结构:")
            logger.info("-" * 80)
            for col in columns:
                logger.info(
                    f"  {col[0]:<30} {col[1]:<20} NULL={col[2]} DEFAULT={col[3]}"
                )
            logger.info("-" * 80)

        return True

    except Exception as e:
        logger.error(f"✗ 表创建失败: {str(e)}", exc_info=True)
        return False


async def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("快速溯源分析数据库表初始化")
    logger.info("=" * 80)
    logger.info(f"数据库: {engine.url}")
    logger.info("")

    try:
        # 创建表
        success = await create_table()

        if success:
            logger.info("")
            logger.info("=" * 80)
            logger.info("✓ 初始化完成！")
            logger.info("=" * 80)
            logger.info("")
            logger.info("下一步:")
            logger.info("  1. 使用 API 触发快速溯源分析")
            logger.info("  2. 分析结果将自动保存到数据库")
            logger.info("")
            logger.info("查询命令:")
            logger.info("  SELECT * FROM quick_trace_analysis ORDER BY alert_time DESC LIMIT 10;")
            logger.info("")
        else:
            logger.error("")
            logger.error("=" * 80)
            logger.error("✗ 初始化失败")
            logger.error("=" * 80)
            sys.exit(1)

    except Exception as e:
        logger.error(f"初始化过程出错: {str(e)}", exc_info=True)
        sys.exit(1)

    finally:
        # 关闭数据库连接
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
