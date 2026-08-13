"""
168城市空气质量统计系统测试脚本

功能：测试系统各组件是否正常工作
使用方法：python test_system.py

作者：Claude Code
版本：1.0.0
日期：2026-04-05
"""

import sys
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


def test_city_list():
    """测试168城市名单"""
    print("="*60)
    print("测试1: 168城市名单")
    print("="*60)

    print(f"总城市数: {len(ALL_168_CITIES)}")

    region_counts = {}
    for city in ALL_168_CITIES:
        region = CITY_REGION_MAP.get(city, '其他')
        region_counts[region] = region_counts.get(region, 0) + 1

    print("\n各地区城市数:")
    for region, count in region_counts.items():
        print(f"  {region}: {count}个")

    # 验证总数
    total = sum(region_counts.values())
    assert total == 168, f"城市总数应为168，实际为{total}"
    print("\n✓ 城市名单验证通过")


def test_calculation_functions():
    """测试统计计算函数"""
    print("\n" + "="*60)
    print("测试2: 统计计算函数")
    print("="*60)

    # 模拟数据
    mock_records = [
        {'PM2_5_24h': 35.0, 'PM10_24h': 65.0, 'SO2_24h': 10.0, 'NO2_24h': 40.0, 'CO_24h': 1.0, 'O3_8h_24h': 120.0},
        {'PM2_5_24h': 45.0, 'PM10_24h': 75.0, 'SO2_24h': 15.0, 'NO2_24h': 45.0, 'CO_24h': 1.2, 'O3_8h_24h': 130.0},
        {'PM2_5_24h': 55.0, 'PM10_24h': 85.0, 'SO2_24h': 20.0, 'NO2_24h': 50.0, 'CO_24h': 1.5, 'O3_8h_24h': 140.0},
    ]

    result = calculate_statistics(mock_records)

    print(f"PM2.5浓度: {result.get('pm2_5_concentration')} μg/m³")
    print(f"PM10浓度: {result.get('pm10_concentration')} μg/m³")
    print(f"SO2浓度: {result.get('so2_concentration')} μg/m³")
    print(f"NO2浓度: {result.get('no2_concentration')} μg/m³")
    print(f"CO浓度: {result.get('co_concentration')} mg/m³")
    print(f"O3_8h浓度: {result.get('o3_8h_concentration')} μg/m³")
    print(f"综合指数: {result.get('comprehensive_index')}")
    print(f"数据天数: {result.get('data_days')}")

    # 验证结果
    assert result is not None, "计算结果不应为None"
    assert result.get('pm2_5_concentration') == 45.0, "PM2.5平均值应为45.0"
    assert result.get('comprehensive_index') is not None, "综合指数不应为None"

    print("\n✓ 统计计算函数验证通过")


def test_ranking_function():
    """测试排名计算函数"""
    print("\n" + "="*60)
    print("测试3: 排名计算函数")
    print("="*60)

    # 模拟统计数据
    mock_statistics = [
        {'city_name': '北京', 'comprehensive_index': 5.5},
        {'city_name': '上海', 'comprehensive_index': 4.5},
        {'city_name': '广州', 'comprehensive_index': 3.5},
        {'city_name': '深圳', 'comprehensive_index': 3.2},
    ]

    ranked = calculate_rankings(mock_statistics)

    print("排名结果:")
    for stat in ranked:
        print(f"  {stat['city_name']}: 综合指数={stat['comprehensive_index']}, 排名={stat.get('comprehensive_index_rank')}")

    # 验证排名（通过查找深圳的记录）
    shenzhen_rank = next((s for s in ranked if s['city_name'] == '深圳'), None)
    assert shenzhen_rank is not None, "深圳应在排名列表中"
    assert shenzhen_rank['comprehensive_index_rank'] == 1, "深圳排名应为1"

    # 验证所有排名都是唯一的
    ranks = [s['comprehensive_index_rank'] for s in ranked if s.get('comprehensive_index_rank') is not None]
    assert len(ranks) == len(set(ranks)), "所有排名应该是唯一的"

    print("\n✓ 排名计算函数验证通过")


def test_sql_client():
    """测试SQL Server客户端"""
    print("\n" + "="*60)
    print("测试4: SQL Server客户端连接")
    print("="*60)

    try:
        client = SQLServerClient()
        success = client.test_connection()

        if success:
            print("✓ SQL Server连接成功")

            # 测试查询
            print("\n测试查询功能...")
            cities = ['北京', '上海', '广州']
            start_date = '2024-03-01'
            end_date = '2024-03-31'

            city_data = client.query_city_data(cities, start_date, end_date)

            print(f"查询结果:")
            for city, records in city_data.items():
                print(f"  {city}: {len(records)}条记录")

            print("\n✓ SQL Server查询功能正常")

        else:
            print("✗ SQL Server连接失败")
            print("请检查数据库连接配置")

    except Exception as e:
        print(f"✗ SQL Server测试失败: {str(e)}")
        print("请检查数据库连接配置和网络连接")


def test_fetcher():
    """测试Fetcher"""
    print("\n" + "="*60)
    print("测试5: CityStatisticsFetcher")
    print("="*60)

    try:
        fetcher = CityStatisticsFetcher()

        print(f"Fetcher名称: {fetcher.name}")
        print(f"Fetcher描述: {fetcher.description}")
        print(f"调度时间: {fetcher.schedule}")
        print(f"版本: {fetcher.version}")
        print(f"状态: {fetcher.status.value}")

        print("\n✓ CityStatisticsFetcher创建成功")

    except Exception as e:
        print(f"✗ CityStatisticsFetcher测试失败: {str(e)}")


def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("168城市空气质量统计系统测试")
    print("="*60)

    try:
        # 运行所有测试
        test_city_list()
        test_calculation_functions()
        test_ranking_function()
        test_fetcher()
        test_sql_client()

        print("\n" + "="*60)
        print("测试完成！")
        print("="*60)

    except AssertionError as e:
        print(f"\n✗ 测试失败: {str(e)}")
        return 1
    except Exception as e:
        print(f"\n✗ 测试异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
