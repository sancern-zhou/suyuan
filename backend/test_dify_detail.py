"""
Dify API 详细数据检查
"""
import asyncio
import sys
import os
import json
from datetime import datetime, timedelta

# 设置UTF-8编码输出
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(__file__))

from app.external_apis.dify_client import DifyClient
from app.schemas.dify_data_adapter import parse_dify_air_quality_data


async def test_detail():
    """详细数据检查"""
    print("=" * 80)
    print("Dify API 详细数据检查")
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

    print(f"\n查询问题:\n{question}\n")

    start = datetime.now()
    response = await client.chat_messages(query=question)
    elapsed = (datetime.now() - start).total_seconds()

    print(f"\n[OK] 请求成功! 耗时: {elapsed:.2f}秒")
    print(f"Conversation ID: {response.get('conversation_id')}")

    # 解析数据
    unified_data = parse_dify_air_quality_data(response)

    print(f"\n解析结果:")
    print(f"  - success: {unified_data.success}")
    print(f"  - status: {unified_data.status}")
    print(f"  - 记录数: {len(unified_data.data)}")
    print(f"  - 摘要: {unified_data.summary}")

    # 详细数据检查
    if unified_data.data:
        print(f"\n" + "=" * 80)
        print("前5条数据详情:")
        print("=" * 80)

        for i, record in enumerate(unified_data.data[:5]):
            print(f"\n记录 {i+1}:")
            print(f"  时间: {record.timestamp}")
            print(f"  站点: {record.station_name}")
            print(f"  坐标: ({record.lat}, {record.lon})")
            print(f"  测量值: {record.measurements}")

        # 按城市统计
        print(f"\n" + "=" * 80)
        print("按城市统计:")
        print("=" * 80)

        city_data = {}
        for record in unified_data.data:
            city = record.station_name or "未知"
            if city not in city_data:
                city_data[city] = {
                    "count": 0,
                    "pm25_values": [],
                    "timestamps": []
                }

            city_data[city]["count"] += 1
            city_data[city]["timestamps"].append(record.timestamp)

            pm25 = record.measurements.get('pm2_5')
            if pm25 is not None:
                city_data[city]["pm25_values"].append(pm25)

        # 打印统计
        for city in sorted(city_data.keys()):
            stats = city_data[city]
            print(f"\n{city}:")
            print(f"  记录数: {stats['count']}")

            if stats['pm25_values']:
                print(f"  PM2.5 范围: {min(stats['pm25_values']):.1f} - {max(stats['pm25_values']):.1f} μg/m³")
                print(f"  PM2.5 平均: {sum(stats['pm25_values'])/len(stats['pm25_values']):.1f} μg/m³")
            else:
                print(f"  PM2.5: 无有效数据")

            print(f"  时间范围: {min(stats['timestamps'])} ~ {max(stats['timestamps'])}")

        # 检查字段映射
        print(f"\n" + "=" * 80)
        print("字段映射检查:")
        print("=" * 80)

        if unified_data.data:
            first_record = unified_data.data[0]
            print(f"\n第一条记录的所有字段:")
            print(f"  时间: {first_record.timestamp}")
            print(f"  站点: {first_record.station_name}")
            print(f"  测量值字段数: {len(first_record.measurements)}")
            print(f"  测量值字段名: {list(first_record.measurements.keys())}")

    # 检查原始answer
    print(f"\n" + "=" * 80)
    print("原始响应数据检查:")
    print("=" * 80)

    answer = response.get('answer', '')
    print(f"\nAnswer长度: {len(answer)}")
    print(f"Answer前500字符:\n{answer[:500]}")

    # 尝试查找JSON
    import re
    json_match = re.search(r'\[[\s\S]*\]', answer)
    if json_match:
        json_str = json_match.group(0)
        print(f"\n找到JSON数组，长度: {len(json_str)}")

        try:
            data = json.loads(json_str)
            print(f"JSON解析成功，包含 {len(data)} 条记录")

            if data:
                print(f"\n第一条原始数据:")
                print(json.dumps(data[0], ensure_ascii=False, indent=2))
        except:
            print(f"JSON解析失败")

    print(f"\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_detail())
