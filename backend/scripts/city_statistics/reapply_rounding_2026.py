"""
重新应用修约规则（2026年3月）

由于修复了CO浓度的修约规则（从1位改为2位小数），需要重新计算并存储2026年3月数据
"""
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.fetchers.city_statistics.city_statistics_fetcher import (
    ALL_168_CITIES,
    CITY_REGION_MAP,
    calculate_statistics,
    calculate_rankings,
    SQLServerClient,
    CityStatisticsFetcher
)
import structlog

logger = structlog.get_logger()


async def reapply_rounding_month(year: int, month: int, sql_client: SQLServerClient):
    """
    重新计算并存储指定月份的数据（应用修正后的修约规则）

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
        "reapply_rounding_month_started",
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

        # 存储数据库（覆盖旧数据）
        stat_date = f"{year_month}-01"
        sql_client.insert_statistics(statistics, 'monthly', stat_date)

        logger.info(
            "reapply_rounding_month_completed",
            year_month=year_month,
            cities_processed=len(statistics),
            total_cities=len(ALL_168_CITIES)
        )

        return len(statistics)

    except Exception as e:
        logger.error(
            "reapply_rounding_month_failed",
            year_month=year_month,
            error=str(e),
            exc_info=True
        )
        return 0


async def main():
    """主函数"""
    logger.info("reapply_rounding_2026_started")

    sql_client = SQLServerClient()

    # 测试连接
    if not sql_client.test_connection():
        logger.error("sql_server_connection_failed")
        return

    logger.info("sql_server_connection_success")

    # 只重新计算2026年3月（包含修约规则修正）
    year = 2026
    month = 3

    logger.info(f"Reapplying rounding rules for {year}-{month:02d}...")

    cities_count = 0
    try:
        cities_count = await reapply_rounding_month(year, month, sql_client)
        logger.info(f"Completed: {cities_count} cities processed")
    except Exception as e:
        logger.error(f"Failed: {str(e)}")

    logger.info("reapply_rounding_2026_completed")

    print("\n" + "="*60)
    print("修约规则重新应用完成！")
    print(f"重新计算月份: {year}-{month:02d}")
    print(f"处理城市数: {cities_count}")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
