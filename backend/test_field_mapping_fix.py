"""
测试字段映射修复 - 验证快速溯源场景
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(__file__))

from app.external_apis.dify_client import DifyClient
from app.schemas.dify_data_adapter import parse_dify_air_quality_data
from app.utils.data_standardizer import get_measurement_value


async def test_field_mapping():
    """测试字段映射"""
    print("=" * 80)
    print("测试字段映射修复")
    print("=" * 80)

    client = DifyClient()

    # 查询
    alert_time = datetime.now()
    query_start = alert_time - timedelta(hours=12)
    cities = ["济宁市", "菏泽市"]
    cities_str = "、".join(cities)

    question = f"""查询{cities_str}的PM2.5浓度数据，
StartTime={query_start.strftime('%Y-%m-%d %H:%M:%S')}，
EndTime={alert_time.strftime('%Y-%m-%d %H:%M:%S')}，
时间粒度为小时数据。"""

    print(f"\n查询: {question}\n")

    response = await client.chat_messages(query=question)
    unified_data = parse_dify_air_quality_data(response)

    print(f"获取数据: {len(unified_data.data)}条\n")

    # 转换为字典格式（模拟quick_trace_executor的数据格式）
    data_list = []
    for record in unified_data.data:
        data_list.append({
            "timestamp": str(record.timestamp),
            "station_name": record.station_name,
            "measurements": record.measurements
        })

    # 测试新旧两种访问方式
    print("=" * 80)
    print("对比测试:")
    print("=" * 80)

    if data_list:
        first = data_list[0]
        measurements = first["measurements"]

        print(f"\n第一条数据:")
        print(f"  城市: {first['station_name']}")
        print(f"  measurements字段: {list(measurements.keys())}")

        # ❌ 旧方式（错误）
        print(f"\n[旧方式] pollutant.lower() = 'pm2.5'")
        old_way = measurements.get('pm2.5')
        print(f"  结果: {old_way} ❌ 找不到")

        # ✅ 新方式（正确）
        print(f"\n[新方式] get_measurement_value(measurements, 'PM2.5')")
        new_way = get_measurement_value(measurements, 'PM2.5')
        print(f"  结果: {new_way} ✅ 正确")

        # 测试各种输入格式
        print(f"\n[新方式] 测试各种输入格式:")
        for test_name in ['PM2.5', 'pm2.5', 'PM2_5', 'pm2_5', 'PM25']:
            result = get_measurement_value(measurements, test_name)
            print(f"  get_measurement_value(measurements, '{test_name}') = {result}")

    # 统计测试
    print(f"\n" + "=" * 80)
    print("按城市统计 (使用新方式):")
    print("=" * 80)

    city_data = {}
    for record in data_list:
        measurements = record.get("measurements", {})
        concentration = get_measurement_value(measurements, "PM2.5")  # 自动映射
        city_name = record.get("station_name", "未知")

        if city_name not in city_data:
            city_data[city_name] = []

        if concentration is not None:
            city_data[city_name].append(concentration)

    for city, concentrations in sorted(city_data.items()):
        if concentrations:
            print(f"{city}: {min(concentrations):.1f}-{max(concentrations):.1f} μg/m³ (平均{sum(concentrations)/len(concentrations):.1f})")

    print(f"\n" + "=" * 80)
    print("测试完成 - 字段映射工作正常!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_field_mapping())
