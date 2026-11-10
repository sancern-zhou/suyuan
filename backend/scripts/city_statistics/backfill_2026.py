"""
168城市空气质量统计数据回填脚本（2026年）

功能：回填2026年1月至当前月前一个月的月度统计数据
使用方法：python backfill_2026.py

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

from app.fetchers.city_statistics.city_statistics_fetcher import (
    CityStatisticsFetcher,
    ALL_168_CITIES,
    CITY_REGION_MAP,
    calculate_statistics,
    calculate_rankings,
    SQLServerClient
)
import structlog

logger = structlog.get_logger()


async def backfill_month(year: int, month: int, sql_client: SQLServerClient):
    """
    回填指定月份的数据

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
        "backfill_month_started",
        year_month=year_month,
        start_date=start_date,
        end_date=end_date
    )

    try:
        # 查询数据
        city_data = sql_client.query_city_data(ALL_168_CITIES, start_date, end_date)

        # 计算统计
        statistics = []
        for city in ALL_168_CITIES:
            if city not in city_data or not city_data[city]:
                logger.warning("city_no_data", city=city, year_month=year_month)
                continue

            records = city_data[city]
            stat = calculate_statistics(records)

            if stat:
                stat['city_name'] = city
                stat['city_code'] = records[0].get('CityCode') if records else None
                stat['region'] = CITY_REGION_MAP.get(city, '其他')
                stat['province'] = CityStatisticsFetcher()._extract_province(city)
                statistics.append(stat)

        # 计算排名
        statistics = calculate_rankings(statistics)

        # 存储数据库
        stat_date = f"{year_month}-01"
        sql_client.insert_statistics(statistics, 'monthly', stat_date)

        logger.info(
            "backfill_month_completed",
            year_month=year_month,
            cities_processed=len(statistics),
            total_cities=len(ALL_168_CITIES)
        )

        return len(statistics)

    except Exception as e:
        logger.error(
            "backfill_month_failed",
            year_month=year_month,
            error=str(e),
            exc_info=True
        )
        return 0


async def main():
    """主函数"""
    logger.info("backfill_2026_started")

    sql_client = SQLServerClient()

    # 测试连接
    if not sql_client.test_connection():
        logger.error("sql_server_connection_failed")
        return

    logger.info("sql_server_connection_success")

    # 获取当前日期
    today = datetime.now()
    current_year = today.year
    current_month = today.month

    # 回填2026年1月至上个月
    year = 2026

    # 只回填已经过去的完整月份
    if current_year == 2026:
        # 当前是2026年，回填1月到上个月
        if current_month == 1:
            # 现在是1月，没有完整月份可以回填
            months = []
        else:
            # 回填1月到上个月
            months = list(range(1, current_month))
    else:
        # 已经不是2026年了，回填全年
        months = list(range(1, 13))

    if not months:
        print("没有需要回填的月份")
        return

    total_months = len(months)
    success_months = 0
    total_cities_processed = 0

    for month in months:
        logger.info(f"Processing {year}-{month:02d}...")

        try:
            cities_count = await backfill_month(year, month, sql_client)
            if cities_count > 0:
                success_months += 1
                total_cities_processed += cities_count
        except Exception as e:
            logger.error(f"Failed to process {year}-{month:02d}: {str(e)}")

    logger.info(
        "backfill_2026_completed",
        total_months=total_months,
        success_months=success_months,
        total_cities_processed=total_cities_processed,
        average_cities_per_month=total_cities_processed / success_months if success_months > 0 else 0
    )

    print("\n" + "="*60)
    print(f"2026年数据回填完成！")
    print(f"总月份数：{total_months}")
    print(f"成功月份数：{success_months}")
    print(f"总处理城市数：{total_cities_processed}")
    print(f"平均每月处理城市数：{total_cities_processed / success_months:.0f}" if success_months > 0 else "平均每月处理城市数：0")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
