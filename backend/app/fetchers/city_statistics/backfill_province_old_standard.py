#!/usr/bin/env python3
"""
省级统计旧标准历史数据回填脚本

回填2024年至今的旧标准数据
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.fetchers.city_statistics.province_statistics_old_standard_fetcher import (
    ProvinceStatisticsOldStandardFetcher
)
import structlog

logger = structlog.get_logger()


async def backfill_year(year: int):
    """
    回填指定年份的旧标准数据

    Args:
        year: 年份
    """
    fetcher = ProvinceStatisticsOldStandardFetcher()

    print(f"\n{'='*60}")
    print(f"开始回填 {year} 年旧标准数据")
    print(f"{'='*60}")

    # 遍历该年的每个月
    for month in range(1, 13):
        # 计算该月的日期范围
        month_start = datetime(year, month, 1)

        # 获取该月最后一天
        if month == 12:
            month_end = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = datetime(year, month + 1, 1) - timedelta(days=1)

        stat_date = month_start.strftime('%Y-%m-%d')

        print(f"\n处理 {year}年{month}月...")
        print(f"  日期范围: {month_start.strftime('%Y-%m-%d')} 到 {month_end.strftime('%Y-%m-%d')}")

        try:
            # 执行月度统计计算
            await fetcher._run_calculation(
                month_start.strftime('%Y-%m-%d'),
                month_end.strftime('%Y-%m-%d'),
                stat_date,
                'monthly'
            )
            print(f"  ✓ {year}年{month}月 完成")

        except Exception as e:
            print(f"  ✗ {year}年{month}月 失败: {str(e)}")
            logger.error("backfill_month_failed", year=year, month=month, error=str(e))

    print(f"\n{'='*60}")
    print(f"✓ {year} 年回填完成")
    print(f"{'='*60}")


async def backfill_range(start_year: int, end_year: int):
    """
    回填指定年份范围的旧标准数据

    Args:
        start_year: 起始年份
        end_year: 结束年份
    """
    print(f"\n{'='*60}")
    print(f"省级统计旧标准历史数据回填")
    print(f"回填范围: {start_year}年 至 {end_year}年")
    print(f"{'='*60}")

    for year in range(start_year, end_year + 1):
        await backfill_year(year)

    print(f"\n{'='*60}")
    print(f"✓ 所有年份回填完成！")
    print(f"{'='*60}")


async def backfill_specific_months(year: int, months: list):
    """
    回填指定年份的特定月份

    Args:
        year: 年份
        months: 月份列表，如 [1, 2, 3]
    """
    fetcher = ProvinceStatisticsOldStandardFetcher()

    print(f"\n{'='*60}")
    print(f"回填 {year} 年指定月份: {months}")
    print(f"{'='*60}")

    for month in months:
        if month < 1 or month > 12:
            print(f"  ✗ 无效月份: {month}")
            continue

        # 计算该月的日期范围
        month_start = datetime(year, month, 1)

        # 获取该月最后一天
        if month == 12:
            month_end = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = datetime(year, month + 1, 1) - timedelta(days=1)

        stat_date = month_start.strftime('%Y-%m-%d')

        print(f"\n处理 {year}年{month}月...")

        try:
            await fetcher._run_calculation(
                month_start.strftime('%Y-%m-%d'),
                month_end.strftime('%Y-%m-%d'),
                stat_date,
                'monthly'
            )
            print(f"  ✓ {year}年{month}月 完成")

        except Exception as e:
            print(f"  ✗ {year}年{month}月 失败: {str(e)}")


# 使用示例
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='省级统计旧标准历史数据回填')
    parser.add_argument('--year', type=int, help='指定年份（如2024）')
    parser.add_argument('--start-year', type=int, default=2024, help='起始年份（默认2024）')
    parser.add_argument('--end-year', type=int, default=2024, help='结束年份（默认2024）')
    parser.add_argument('--months', type=str, help='指定月份，逗号分隔（如1,2,3）')

    args = parser.parse_args()

    if args.year:
        # 回填指定年份
        asyncio.run(backfill_year(args.year))
    elif args.months:
        # 回填指定月份
        year = args.year or datetime.now().year
        months = [int(m.strip()) for m in args.months.split(',')]
        asyncio.run(backfill_specific_months(year, months))
    else:
        # 回填年份范围
        asyncio.run(backfill_range(args.start_year, args.end_year))
