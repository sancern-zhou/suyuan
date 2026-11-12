"""
测试新旧标准综合指数计算

验证HJ 663-2013（旧标准）和HJ 663-2021（新标准）的计算差异
"""

import asyncio
import sys
from datetime import datetime

sys.path.insert(0, '/home/xckj/suyuan/backend')

from app.fetchers.city_statistics.city_statistics_fetcher import (
    CityStatisticsFetcher,
    ALL_168_CITIES,
    CITY_REGION_MAP,
    calculate_statistics,
    calculate_rankings,
    ANNUAL_STANDARD_LIMITS_2013,
    ANNUAL_STANDARD_LIMITS_2026
)


async def test_dual_standard_calculation():
    """
    测试双标准计算
    """
    fetcher = CityStatisticsFetcher()

    print('=== 标准限值对比 ===')
    print('污染物 | HJ 663-2013（旧标准） | HJ 663-2026（新标准） | 差异')
    print('-' * 70)
    for pollutant in ['SO2', 'NO2', 'PM10', 'PM2_5', 'CO', 'O3_8h']:
        old = ANNUAL_STANDARD_LIMITS_2013[pollutant]
        new = ANNUAL_STANDARD_LIMITS_2026[pollutant]
        diff = '✓ 相同' if old == new else f'{old - new:+d}'
        print(f'{pollutant:6} | {old:20} | {new:20} | {diff}')

    print('\n=== 测试数据计算（以2025年深圳为例）===')

    # 查询深圳2025年数据
    year = 2025
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    city_data = fetcher.sql_client.query_city_data(['深圳'], start_date, end_date)

    if '深圳' not in city_data or not city_data['深圳']:
        print('✗ 未找到深圳数据')
        return

    records = city_data['深圳']
    print(f'数据天数: {len(records)}')

    # 计算统计
    stat = calculate_statistics(records)

    if stat:
        print('\n--- 浓度值 ---')
        print(f"SO2:   {stat.get('so2_concentration')} μg/m³")
        print(f"NO2:   {stat.get('no2_concentration')} μg/m³")
        print(f"PM10:  {stat.get('pm10_concentration')} μg/m³")
        print(f"PM2.5: {stat.get('pm2_5_concentration')} μg/m³")
        print(f"CO:    {stat.get('co_concentration')} mg/m³")
        print(f"O3:    {stat.get('o3_8h_concentration')} μg/m³")

        print('\n--- 新标准（HJ 663-2026）---')
        print(f"PM10指数:    {stat.get('pm10_index'):.3f} (标准限值: 60)")
        print(f"PM2.5指数:  {stat.get('pm2_5_index'):.3f} (标准限值: 30)")
        print(f"综合指数:    {stat.get('comprehensive_index'):.3f}")
        print(f"排名:        {stat.get('comprehensive_index_rank')}")

        print('\n--- 旧标准（HJ 663-2013）---')
        print(f"PM10指数:    {stat.get('pm10_index_old'):.3f} (标准限值: 70)")
        print(f"PM2.5指数:  {stat.get('pm2_5_index_old'):.3f} (标准限值: 35)")
        print(f"综合指数:    {stat.get('comprehensive_index_old'):.3f}")
        print(f"排名:        {stat.get('comprehensive_index_rank_old')}")

        print('\n--- 差异分析 ---')
        diff_pm10 = (stat.get('pm10_index_old') or 0) - (stat.get('pm10_index') or 0)
        diff_pm25 = (stat.get('pm2_5_index_old') or 0) - (stat.get('pm2_5_index') or 0)
        diff_comp = (stat.get('comprehensive_index_old') or 0) - (stat.get('comprehensive_index') or 0)

        print(f"PM10指数差异:    {diff_pm10:+.3f}")
        print(f"PM2.5指数差异:  {diff_pm25:+.3f}")
        print(f"综合指数差异:    {diff_comp:+.3f}")

        if diff_comp > 0:
            print(f'\n结论: 旧标准综合指数更高 {diff_comp:.3f}，排名更严格')
        elif diff_comp < 0:
            print(f'\n结论: 新标准综合指数更高 {-diff_comp:.3f}，排名更严格')
        else:
            print(f'\n结论: 两个标准综合指数相同')


if __name__ == "__main__":
    asyncio.run(test_dual_standard_calculation())
