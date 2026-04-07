"""
省级空气质量统计数据回填脚本（2024-2026年）

功能：回填2024年1月至2026年3月的月度统计数据
使用方法：python backfill_province_historical.py

作者：Claude Code
版本：1.0.0
日期：2026-04-05
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.fetchers.city_statistics.province_statistics_fetcher import (
    ProvinceStatisticsFetcher,
    ProvinceSQLServerClient,
    ALL_168_CITIES,
    calculate_province_statistics,
    calculate_province_rankings,
    validate_province_statistics
)
import structlog

logger = structlog.get_logger()


async def backfill_month(year: int, month: int, sql_client: ProvinceSQLServerClient):
    """
    回填指定月份的省级数据

    Args:
        year: 年份
        month: 月份（1-12）
        sql_client: SQL Server客户端
    """
    # 计算月份的起止日期
    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)

    year_month = first_day.strftime('%Y-%m')
    start_date = first_day.strftime('%Y-%m-%d')
    end_date = last_day.strftime('%Y-%m-%d')

    logger.info(
        "backfill_province_month_started",
        year_month=year_month,
        start_date=start_date,
        end_date=end_date
    )

    try:
        # 查询数据
        city_data = sql_client.query_city_data(ALL_168_CITIES, start_date, end_date)

        # 创建fetcher实例用于分组
        fetcher = ProvinceStatisticsFetcher()

        # 按省份分组
        province_groups, grouping_warnings = fetcher._group_by_province_enhanced(city_data)

        # 计算统计
        statistics = []
        for province, cities in province_groups.items():
            stat = calculate_province_statistics(cities)

            if stat:
                stat['province_name'] = province
                statistics.append(stat)

        # 计算排名
        statistics = calculate_province_rankings(statistics)

        # 验证
        stat_date = f"{year_month}-01"
        statistics, validation_warnings = validate_province_statistics(
            city_data, statistics, stat_date
        )

        # 存储数据库
        sql_client.insert_province_statistics(statistics, 'monthly', stat_date)

        logger.info(
            "backfill_province_month_completed",
            year_month=year_month,
            provinces_processed=len(statistics),
            grouping_warnings=len(grouping_warnings),
            validation_warnings=len(validation_warnings)
        )

        return len(statistics)

    except Exception as e:
        logger.error(
            "backfill_province_month_failed",
            year_month=year_month,
            error=str(e),
            exc_info=True
        )
        return 0


async def main():
    """主函数"""
    logger.info("backfill_province_historical_started")

    sql_client = ProvinceSQLServerClient()

    # 测试连接
    if not sql_client.test_connection():
        logger.error("sql_server_connection_failed")
        print("数据库连接失败，请检查连接配置")
        return

    logger.info("sql_server_connection_success")
    print("数据库连接成功\n")

    # 回填范围：2024-01至2026-03
    backfill_periods = []

    # 2024年（12个月）
    for month in range(1, 13):
        backfill_periods.append((2024, month))

    # 2025年（12个月）
    for month in range(1, 13):
        backfill_periods.append((2025, month))

    # 2026年（3个月）
    for month in range(1, 4):
        backfill_periods.append((2026, month))

    total_months = len(backfill_periods)
    success_months = 0
    total_provinces_processed = 0

    print(f"开始回填 {total_months} 个月的数据...")
    print("="*60)

    for i, (year, month) in enumerate(backfill_periods, 1):
        year_month = f"{year}-{month:02d}"
        print(f"[{i}/{total_months}] 处理 {year_month}...", end=" ")

        try:
            provinces_count = await backfill_month(year, month, sql_client)
            if provinces_count > 0:
                success_months += 1
                total_provinces_processed += provinces_count
                print(f"完成 ({provinces_count}个省)")
            else:
                print("失败（无数据）")
        except Exception as e:
            print(f"错误: {str(e)}")

    print("="*60)
    logger.info(
        "backfill_province_historical_completed",
        total_months=total_months,
        success_months=success_months,
        total_provinces_processed=total_provinces_processed,
        average_provinces_per_month=total_provinces_processed / success_months if success_months > 0 else 0
    )

    print("\n省级历史数据回填完成！")
    print(f"总月份数：{total_months}")
    print(f"成功月份数：{success_months}")
    print(f"总处理省份数：{total_provinces_processed}")
    if success_months > 0:
        print(f"平均每月处理省份数：{total_provinces_processed / success_months:.0f}")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
