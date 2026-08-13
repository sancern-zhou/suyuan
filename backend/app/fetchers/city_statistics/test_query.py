"""
测试修复后的城市查询
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.fetchers.city_statistics.city_statistics_fetcher import SQLServerClient


def test_query():
    """测试查询功能"""
    print("="*60)
    print("测试城市数据查询")
    print("="*60)

    client = SQLServerClient()

    # 测试查询几个城市
    test_cities = ['广州', '深圳', '北京', '上海']
    start_date = '2024-12-01'
    end_date = '2024-12-31'

    print(f"\n查询城市: {test_cities}")
    print(f"日期范围: {start_date} 至 {end_date}")

    city_data = client.query_city_data(test_cities, start_date, end_date)

    print(f"\n查询结果:")
    for city, records in city_data.items():
        print(f"  {city}: {len(records)} 条记录")
        if records:
            # 显示第一条记录
            record = records[0]
            print(f"    示例: {record['Area']}, PM2.5={record.get('PM2_5_24h')}, PM10={record.get('PM10_24h')}")

    print(f"\n✓ 查询测试完成")


if __name__ == "__main__":
    test_query()
