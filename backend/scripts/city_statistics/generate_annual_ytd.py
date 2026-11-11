"""
生成年度累计统计数据

手动生成2024-2026年的年度累计数据（annual_ytd）
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


async def generate_annual_ytd(year: int, sql_client: SQLServerClient):
    """
    生成指定年份的年度累计数据

    Args:
        year: 年份
        sql_client: SQL Server客户端
    """
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    logger.info(
        "generating_annual_ytd",
        year=year,
        start_date=start_date,
        end_date=end_date
    )

    try:
        # 查询全年数据
        city_data = sql_client.query_city_data(ALL_168_CITIES, start_date, end_date)

        # 计算统计
        statistics = []
        for city in ALL_168_CITIES:
            if city not in city_data or not city_data[city]:
                logger.warning("city_no_data", city=city, year=year)
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

        # 存储数据库（stat_type='annual_ytd', stat_date为年份首日）
        stat_date = f"{year}-01-01"
        sql_client.insert_statistics(statistics, 'annual_ytd', stat_date)

        logger.info(
            "annual_ytd_generated",
            year=year,
            cities_processed=len(statistics),
            total_cities=len(ALL_168_CITIES)
        )

        return len(statistics)

    except Exception as e:
        logger.error(
            "annual_ytd_generation_failed",
            year=year,
            error=str(e),
            exc_info=True
        )
        return 0


async def main():
    """主函数"""
    logger.info("annual_ytd_generation_started")

    sql_client = SQLServerClient()

    # 测试连接
    if not sql_client.test_connection():
        logger.error("sql_server_connection_failed")
        return

    logger.info("sql_server_connection_success")

    # 生成2024-2026年的年度累计数据
    years = [2024, 2025, 2026]

    total_cities = 0
    for year in years:
        logger.info(f"Generating annual YTD for {year}...")
        try:
            cities_count = await generate_annual_ytd(year, sql_client)
            total_cities += cities_count
        except Exception as e:
            logger.error(f"Failed to generate {year} annual YTD: {str(e)}")

    logger.info(f"annual_ytd_generation_completed: {total_cities} total records")

    print("\n" + "="*60)
    print("年度累计数据生成完成！")
    print(f"生成年份: {', '.join(str(y) for y in years)}")
    print(f"总记录数: {total_cities}")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
