"""
省级统计数据抓取器测试脚本

功能：测试省级统计计算功能
使用方法：python test_province_fetcher.py

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
    calculate_province_statistics,
    validate_province_statistics
)
import structlog

logger = structlog.get_logger()


async def test_province_calculation():
    """测试省级统计计算功能"""
    print("="*80)
    print("省级统计数据抓取器测试")
    print("="*80)

    sql_client = ProvinceSQLServerClient()

    # 测试连接
    if not sql_client.test_connection():
        print("❌ 数据库连接失败")
        return False

    print("✅ 数据库连接成功\n")

    # 测试2024年3月的数据
    test_year = 2024
    test_month = 3

    first_day = datetime(test_year, test_month, 1)
    last_day = datetime(test_year, test_month + 1, 1) - timedelta(days=1) if test_month < 12 else datetime(test_year + 1, 1, 1) - timedelta(days=1)

    year_month = first_day.strftime('%Y-%m')
    start_date = first_day.strftime('%Y-%m-%d')
    end_date = last_day.strftime('%Y-%m-%d')

    print(f"测试数据：{year_month} ({start_date} 至 {end_date})")
    print("-"*80)

    # 查询数据
    from app.fetchers.city_statistics.province_statistics_fetcher import ALL_168_CITIES
    city_data = sql_client.query_city_data(ALL_168_CITIES, start_date, end_date)

    print(f"查询到 {len(city_data)} 个城市的数据")
    total_records = sum(len(records) for records in city_data.values())
    print(f"总记录数: {total_records}\n")

    # 创建fetcher实例
    fetcher = ProvinceStatisticsFetcher()

    # 按省份分组
    print("按省份分组...")
    province_groups, grouping_warnings = fetcher._group_by_province_enhanced(city_data)

    print(f"✅ 分组完成: {len(province_groups)} 个省份")
    if grouping_warnings:
        print(f"⚠️  分组警告: {len(grouping_warnings)} 个")
        for warning in grouping_warnings[:5]:
            print(f"   - {warning}")

    # 测试几个省份的统计计算
    print("\n测试省份统计计算:")
    print("-"*80)

    test_provinces = ['河北', '山西', '山东', '广东', '北京']

    for province in test_provinces:
        if province in province_groups:
            cities_data = province_groups[province]
            stat = calculate_province_statistics(cities_data)

            if stat:
                print(f"\n{province} ({stat['city_count']}个城市):")
                print(f"  - PM2.5: {stat.get('pm2_5_concentration')} μg/m³")
                print(f"  - 综合指数: {stat.get('comprehensive_index')}")
                print(f"  - 数据天数: {stat.get('data_days')} 天")
                print(f"  - 样本覆盖率: {stat.get('sample_coverage')}%")
                print(f"  - 城市列表: {stat.get('city_names')[:50]}...")

    # 计算所有省份的统计
    print("\n\n计算所有省份的统计数据...")
    print("-"*80)

    statistics = []
    for province, cities in province_groups.items():
        stat = calculate_province_statistics(cities)

        if stat:
            stat['province_name'] = province
            statistics.append(stat)

    print(f"✅ 计算完成: {len(statistics)} 个省份")

    # 计算排名（省份专用版本）
    from app.fetchers.city_statistics.province_statistics_fetcher import calculate_province_rankings
    statistics = calculate_province_rankings(statistics)

    print(f"\n排名前5的省份:")
    print("-"*80)
    for stat in sorted(statistics, key=lambda x: x.get('comprehensive_index_rank', 999))[:5]:
        rank = stat.get('comprehensive_index_rank', '?')
        province = stat.get('province_name', 'Unknown')
        index = stat.get('comprehensive_index', 'N/A')
        print(f"{rank:2d}. {province:6s} - 综合指数: {index}")

    # 验证数据
    stat_date = f"{year_month}-01"
    statistics, validation_warnings = validate_province_statistics(
        city_data, statistics, stat_date
    )

    print(f"\n验证结果:")
    print("-"*80)
    if validation_warnings:
        print(f"⚠️  发现 {len(validation_warnings)} 个警告:")
        for warning in validation_warnings[:10]:
            print(f"   - {warning}")
    else:
        print("✅ 验证通过，无警告")

    # 存储到数据库（可选）
    print("\n\n是否将测试数据存储到数据库？(y/n): ", end="")
    # For automated testing, we'll skip the interactive prompt
    # response = input().strip().lower()

    # Uncomment the following to enable storage:
    # if response == 'y':
    #     sql_client.insert_province_statistics(statistics, 'monthly', stat_date)
    #     print(f"✅ 数据已存储到数据库 (stat_date={stat_date})")

    print("\n" + "="*80)
    print("测试完成！")
    print("="*80)

    return True


if __name__ == "__main__":
    asyncio.run(test_province_calculation())
