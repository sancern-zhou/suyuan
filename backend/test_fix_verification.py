"""
验证区域对比数据修复
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

# 设置UTF-8编码输出
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(__file__))

from app.external_apis.dify_client import DifyClient
from app.schemas.dify_data_adapter import parse_dify_air_quality_data


async def test_regional_data():
    """测试区域对比数据"""
    print("=" * 80)
    print("测试区域对比数据格式化")
    print("=" * 80)

    client = DifyClient()

    # 区域对比查询
    alert_time = datetime.now()
    query_start = alert_time - timedelta(hours=12)
    cities = ["济宁市", "菏泽市", "枣庄市", "临沂市", "泰安市", "徐州市", "商丘市", "开封市"]
    cities_str = "、".join(cities)

    question = f"""查询{cities_str}的PM2.5浓度数据，
StartTime={query_start.strftime('%Y-%m-%d %H:%M:%S')}，
EndTime={alert_time.strftime('%Y-%m-%d %H:%M:%S')}，
时间粒度为小时数据，请返回各城市的PM2.5小时浓度数据。"""

    print(f"\n查询: {cities_str} PM2.5浓度 (前12小时)\n")

    response = await client.chat_messages(query=question)
    unified_data = parse_dify_air_quality_data(response)

    print(f"[OK] 获取数据: {len(unified_data.data)}条\n")

    # 转换为字典格式（模拟快速溯源的数据格式）
    data_list = []
    for record in unified_data.data:
        data_list.append({
            "timestamp": str(record.timestamp),
            "station_name": record.station_name,
            "lat": record.lat,
            "lon": record.lon,
            "measurements": record.measurements
        })

    # 模拟 _format_regional_summary 函数
    regional_data = {
        "success": True,
        "data": data_list
    }

    pollutant = "PM2.5"

    # 使用修复后的格式化逻辑
    from app.utils.data_standardizer import get_data_standardizer
    standardizer = get_data_standardizer()

    possible_keys = [
        pollutant.lower(),  # pm2.5
        pollutant.upper(),  # PM2.5
        pollutant,  # 原始输入
        pollutant.replace(".", "_"),  # PM2_5
        pollutant.lower().replace(".", "_"),  # pm2_5
    ]

    standard_key = standardizer._get_standard_field_name(pollutant)
    if standard_key and standard_key not in possible_keys:
        possible_keys.insert(0, standard_key)

    print(f"尝试的字段名: {possible_keys}")
    print(f"标准化器推荐字段: {standard_key}\n")

    # 按城市分组统计
    city_data = {}
    for record in data_list:
        if isinstance(record, dict):
            # 尝试多个字段名获取浓度
            concentration = None
            measurements = record.get("measurements", {})

            for key in possible_keys:
                if key in measurements and measurements[key] is not None:
                    concentration = measurements[key]
                    break

            city_name = record.get("station_name") or record.get("city_name") or record.get("name", "未知")

            if city_name not in city_data:
                city_data[city_name] = []

            if concentration is not None:
                city_data[city_name].append(concentration)

    # 打印结果
    print("=" * 80)
    print("按城市统计 (修复后):")
    print("=" * 80)

    if city_data:
        for city_name, concentrations in sorted(city_data.items()):
            if concentrations:
                min_conc = min(concentrations)
                max_conc = max(concentrations)
                avg_conc = sum(concentrations) / len(concentrations)
                print(f"{city_name}: {min_conc:.1f}-{max_conc:.1f} μg/m³ (平均{avg_conc:.1f} μg/m³, {len(concentrations)}条)")
            else:
                print(f"{city_name}: 无有效数据")
    else:
        print("[错误] 未找到任何有效浓度数据")

    # 详细检查第一条记录
    print(f"\n" + "=" * 80)
    print("详细数据检查:")
    print("=" * 80)

    if data_list:
        first = data_list[0]
        print(f"\n第一条记录:")
        print(f"  城市: {first['station_name']}")
        print(f"  时间: {first['timestamp']}")
        print(f"  测量值字段: {list(first['measurements'].keys())}")
        print(f"  测量值内容: {first['measurements']}")

        # 检查字段匹配
        print(f"\n字段匹配测试:")
        for key in possible_keys:
            found = key in first['measurements']
            value = first['measurements'].get(key)
            print(f"  '{key}': {'找到' if found else '未找到'} (值={value})")

    print(f"\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_regional_data())
