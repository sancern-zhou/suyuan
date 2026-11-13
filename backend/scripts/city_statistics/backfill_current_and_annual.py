"""
省级统计数据补充回填脚本

功能：补充current_month（当月累计）和annual_ytd（年度累计）的历史数据
回填范围：2024-01至2026-03

作者：Claude Code
版本：2.0.0（优化版）
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


async def backfill_current_month(year: int, month: int, day: int, sql_client: ProvinceSQLServerClient):
    """
    回填指定日期的当月累计数据

    Args:
        year: 年份
        month: 月份
        day: 日期
        sql_client: SQL Server客户端
    """
    target_date = datetime(year, month, day)
    year_month = target_date.strftime('%Y-%m')
    start_date = f"{year_month}-01"
    end_date = target_date.strftime('%Y-%m-%d')
    stat_date = f"{year_month}-01"

    logger.info(
        "backfill_current_month_started",
        target_date=target_date.isoformat(),
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
        statistics, validation_warnings = validate_province_statistics(
            city_data, statistics, stat_date
        )

        # 存储数据库
        sql_client.insert_province_statistics(statistics, 'current_month', stat_date)

        logger.info(
            "backfill_current_month_completed",
            target_date=target_date.isoformat(),
            provinces_processed=len(statistics),
            grouping_warnings=len(grouping_warnings),
            validation_warnings=len(validation_warnings)
        )

        return len(statistics)

    except Exception as e:
        logger.error(
            "backfill_current_month_failed",
            target_date=target_date.isoformat(),
            error=str(e),
            exc_info=True
        )
        return 0


async def backfill_annual_ytd(year: int, month: int, day: int, sql_client: ProvinceSQLServerClient):
    """
    回填指定日期的年度累计数据

    Args:
        year: 年份
        month: 月份
        day: 日期
        sql_client: SQL Server客户端
    """
    target_date = datetime(year, month, day)
    stat_date = f"{year}-01-01"
    start_date = f"{year}-01-01"
    end_date = target_date.strftime('%Y-%m-%d')

    logger.info(
        "backfill_annual_ytd_started",
        target_date=target_date.isoformat(),
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
        statistics, validation_warnings = validate_province_statistics(
            city_data, statistics, stat_date
        )

        # 存储数据库
        sql_client.insert_province_statistics(statistics, 'annual_ytd', stat_date)

        logger.info(
            "backfill_annual_ytd_completed",
            target_date=target_date.isoformat(),
            stat_date=stat_date,
            provinces_processed=len(statistics),
            grouping_warnings=len(grouping_warnings),
            validation_warnings=len(validation_warnings)
        )

        return len(statistics)

    except Exception as e:
        logger.error(
            "backfill_annual_ytd_failed",
            target_date=target_date.isoformat(),
            error=str(e),
            exc_info=True
        )
        return 0


async def main():
    """主函数"""
    logger.info("backfill_current_and_annual_started")

    sql_client = ProvinceSQLServerClient()

    # 测试连接
    if not sql_client.test_connection():
        logger.error("sql_server_connection_failed")
        print("数据库连接失败，请检查连接配置")
        return

    logger.info("sql_server_connection_success")
    print("数据库连接成功\n")

    print("="*80)
    print("省级统计数据补充回填（优化方案）")
    print("="*80)
    print("\n回填策略：")
    print("1. current_month（当月累计）：每月最后一天的数据")
    print("2. annual_ytd（年度累计）：每年最后一天的数据")
    print("="*80)

    # 回填current_month：每月最后一天
    print("\n【第一阶段】回填当月累计数据（current_month）")
    print("-"*80)

    backfill_periods = []

    # 2024年（每月最后一天）
    for month in range(1, 13):
        if month == 12:
            last_day = 31
        else:
            last_day = (datetime(2024, month + 1, 1) - timedelta(days=1)).day
        backfill_periods.append(('current_month', 2024, month, last_day))

    # 2025年（每月最后一天）
    for month in range(1, 13):
        if month == 12:
            last_day = 31
        else:
            last_day = (datetime(2025, month + 1, 1) - timedelta(days=1)).day
        backfill_periods.append(('current_month', 2025, month, last_day))

    # 2026年（1-3月，使用3月31日作为当前最新数据）
    for month in range(1, 4):
        if month == 3:
            last_day = 31  # 使用3月31日
        else:
            last_day = (datetime(2026, month + 1, 1) - timedelta(days=1)).day
        backfill_periods.append(('current_month', 2026, month, last_day))

    current_months = [p for p in backfill_periods if p[0] == 'current_month']
    success_count = 0
    total_provinces = 0

    for i, (stat_type, year, month, day) in enumerate(current_months, 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        print(f"[{i}/{len(current_months)}] 处理 {date_str}...", end=" ")

        try:
            provinces_count = await backfill_current_month(year, month, day, sql_client)
            if provinces_count > 0:
                success_count += 1
                total_provinces += provinces_count
                print(f"完成 ({provinces_count}个省)")
            else:
                print("失败（无数据）")
        except Exception as e:
            print(f"错误: {str(e)}")

    print(f"\n当月累计回填完成：{success_count}/{len(current_months)}个月，总处理省份数：{total_provinces}")

    # 回填annual_ytd：每年最后一天
    print("\n\n【第二阶段】回填年度累计数据（annual_ytd）")
    print("-"*80)

    # 2024年最后一天
    print("[1/3] 处理 2024-12-31...", end=" ")
    try:
        count = await backfill_annual_ytd(2024, 12, 31, sql_client)
        print(f"完成 ({count}个省)")
    except Exception as e:
        print(f"错误: {str(e)}")

    # 2025年最后一天
    print("[2/3] 处理 2025-12-31...", end=" ")
    try:
        count = await backfill_annual_ytd(2025, 12, 31, sql_client)
        print(f"完成 ({count}个省)")
    except Exception as e:
        print(f"错误: {str(e)}")

    # 2026年当前最新（使用3月31日）
    print("[3/3] 处理 2026-03-31...", end=" ")
    try:
        count = await backfill_annual_ytd(2026, 3, 31, sql_client)
        print(f"完成 ({count}个省)")
    except Exception as e:
        print(f"错误: {str(e)}")

    print("\n" + "="*80)
    print("补充回填完成！")
    print("="*80)

    # 验证结果
    print("\n【数据验证】")
    print("-"*80)

    import pyodbc
    conn = pyodbc.connect(sql_client.connection_string, timeout=30)
    cursor = conn.cursor()

    # 检查各类型的记录数
    for stat_type in ['monthly', 'current_month', 'annual_ytd']:
        sql = 'SELECT COUNT(*) as cnt FROM province_statistics WHERE stat_type = ?'
        cursor.execute(sql, [stat_type])
        count = cursor.fetchone().cnt
        print(f"{stat_type}: {count}条记录")

    cursor.close()
    conn.close()

    logger.info("backfill_current_and_annual_completed")


if __name__ == "__main__":
    asyncio.run(main())
