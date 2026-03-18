"""
手动运行数据采集器脚本

用法:
    python run_fetcher_manual.py <fetcher_name>
    python run_fetcher_manual.py all

可用的采集器:
    era5      - ERA5历史气象数据
    observed  - 观测站气象数据
    fire      - NASA FIRMS火点数据
    dust      - CAMS沙尘AOD数据
    all       - 运行所有采集器
"""
import asyncio
from app.fetchers.weather.era5_fetcher import ERA5Fetcher
from app.fetchers.weather.observed_fetcher import ObservedWeatherFetcher
from app.fetchers.satellite.nasa_firms_fetcher import NASAFirmsFetcher
from app.fetchers.dust.cams_dust_fetcher import CAMSDustFetcher
from app.db.database import init_db, close_db
import structlog
import os
import sys

# 配置日志
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()


async def run_single_fetcher(fetcher_name: str):
    """
    运行单个采集器

    Args:
        fetcher_name: 采集器名称
            - era5: ERA5历史数据
            - observed: 观测数据
            - fire: 火点数据
            - dust: 沙尘数据
    """
    # 检查数据库配置
    if not os.getenv("DATABASE_URL"):
        logger.error("DATABASE_URL未配置，无法运行采集器")
        logger.info("请在.env文件中配置DATABASE_URL")
        return

    # 初始化数据库
    try:
        await init_db()
        logger.info("database_initialized", status="success")
    except Exception as e:
        logger.error("database_init_failed", error=str(e))
        return

    try:
        # 选择采集器
        fetcher = None
        if fetcher_name == "era5":
            fetcher = ERA5Fetcher()
        elif fetcher_name == "observed":
            fetcher = ObservedWeatherFetcher()
        elif fetcher_name == "fire":
            fetcher = NASAFirmsFetcher()
        elif fetcher_name == "dust":
            fetcher = CAMSDustFetcher()
        else:
            logger.error("unknown_fetcher", fetcher=fetcher_name)
            print(f"\n错误: 未知的采集器 '{fetcher_name}'")
            print("可用的采集器: era5, observed, fire, dust, all")
            return

        logger.info(
            "fetcher_starting",
            name=fetcher.name,
            description=fetcher.description,
            schedule=fetcher.schedule
        )

        # 运行采集器
        await fetcher.run()

        logger.info("fetcher_completed", name=fetcher.name, status="success")

    except Exception as e:
        logger.error(
            "fetcher_failed",
            fetcher=fetcher_name,
            error=str(e),
            exc_info=True
        )

    finally:
        # 关闭数据库连接
        try:
            await close_db()
            logger.info("database_closed")
        except Exception as e:
            logger.error("database_close_failed", error=str(e))


async def run_all_fetchers():
    """运行所有采集器（用于批量回填历史数据）"""
    if not os.getenv("DATABASE_URL"):
        logger.error("DATABASE_URL未配置")
        return

    try:
        await init_db()
        logger.info("database_initialized")
    except Exception as e:
        logger.error("database_init_failed", error=str(e))
        return

    fetchers = [
        ERA5Fetcher(),
        ObservedWeatherFetcher(),
        NASAFirmsFetcher(),
        CAMSDustFetcher(),
    ]

    success_count = 0
    failed_count = 0

    for fetcher in fetchers:
        try:
            logger.info("fetcher_starting", name=fetcher.name)
            await fetcher.run()
            logger.info("fetcher_completed", name=fetcher.name)
            success_count += 1
        except Exception as e:
            logger.error(
                "fetcher_failed",
                name=fetcher.name,
                error=str(e),
                exc_info=True
            )
            failed_count += 1

    logger.info(
        "all_fetchers_completed",
        total=len(fetchers),
        success=success_count,
        failed=failed_count
    )

    await close_db()


def print_usage():
    """打印使用说明"""
    print(__doc__)
    print("\n示例:")
    print("  # 运行ERA5采集器")
    print("  python run_fetcher_manual.py era5")
    print()
    print("  # 运行观测数据采集器")
    print("  python run_fetcher_manual.py observed")
    print()
    print("  # 运行所有采集器")
    print("  python run_fetcher_manual.py all")
    print()
    print("注意:")
    print("  - 需要在.env文件中配置DATABASE_URL")
    print("  - 某些采集器可能需要配置API密钥")
    print("  - 建议先测试单个采集器，确认无误后再运行全部")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    fetcher_name = sys.argv[1]

    if fetcher_name == "all":
        print("\n正在运行所有采集器...\n")
        asyncio.run(run_all_fetchers())
    else:
        print(f"\n正在运行采集器: {fetcher_name}\n")
        asyncio.run(run_single_fetcher(fetcher_name))

    print("\n完成！")
