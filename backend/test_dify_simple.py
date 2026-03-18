"""
Dify API 调试脚本 - 简化版
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


async def test_simple():
    """简单测试"""
    print("=" * 60)
    print("Dify API 测试")
    print("=" * 60)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    client = DifyClient()
    print(f"\nAPI地址: {client.base_url}")
    print(f"超时时间: {client.timeout}秒")

    # 测试1: 简单查询
    print("\n" + "-" * 60)
    print("测试1: 简单查询")
    print("-" * 60)
    question = "查询济宁市今日空气质量"
    print(f"问题: {question}")

    start = datetime.now()
    try:
        response = await client.chat_messages(query=question)
        elapsed = (datetime.now() - start).total_seconds()
        print(f"[OK] 成功! 耗时: {elapsed:.2f}秒")

        # 解析数据
        unified_data = parse_dify_air_quality_data(response)
        print(f"解析结果: success={unified_data.success}, 记录数={len(unified_data.data)}")

        if unified_data.data:
            print(f"第一条数据: 时间={unified_data.data[0].timestamp}, 站点={unified_data.data[0].station_name}")
    except Exception as e:
        elapsed = (datetime.now() - start).total_seconds()
        print(f"[FAIL] 失败! 耗时: {elapsed:.2f}秒")
        print(f"错误: {str(e)}")

    # 测试2: 区域查询
    print("\n" + "-" * 60)
    print("测试2: 区域对比查询（快速溯源场景）")
    print("-" * 60)

    alert_time = datetime.now()
    query_start = alert_time - timedelta(hours=12)
    cities = ["济宁市", "菏泽市", "枣庄市", "临沂市", "泰安市", "徐州市", "商丘市", "开封市"]
    cities_str = "、".join(cities)

    question = f"""查询{cities_str}的PM2.5浓度数据，
StartTime={query_start.strftime('%Y-%m-%d %H:%M:%S')}，
EndTime={alert_time.strftime('%Y-%m-%d %H:%M:%S')}，
时间粒度为小时数据，请返回各城市的PM2.5小时浓度数据。"""

    print(f"问题: {question}")
    print(f"涉及城市: {len(cities)}个")
    print(f"时间范围: 12小时")
    print(f"预计数据量: ~{len(cities) * 12}条")

    start = datetime.now()
    try:
        response = await client.chat_messages(query=question)
        elapsed = (datetime.now() - start).total_seconds()
        print(f"\n[OK] 成功! 耗时: {elapsed:.2f}秒")

        # 解析数据
        unified_data = parse_dify_air_quality_data(response)
        print(f"解析结果: success={unified_data.success}, 记录数={len(unified_data.data)}")
        print(f"摘要: {unified_data.summary}")

        # 按城市统计
        city_stats = {}
        for record in unified_data.data:
            city = record.station_name or "未知"
            if city not in city_stats:
                city_stats[city] = []
            pm25 = record.measurements.get('pm2_5')
            if pm25:
                city_stats[city].append(pm25)

        print(f"\n按城市统计:")
        for city, values in sorted(city_stats.items()):
            if values:
                print(f"  {city}: {len(values)}条, PM2.5范围 {min(values):.1f}-{max(values):.1f} μg/m³")

    except Exception as e:
        elapsed = (datetime.now() - start).total_seconds()
        print(f"\n[FAIL] 失败! 耗时: {elapsed:.2f}秒")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")

        if "Timeout" in str(e) or elapsed >= client.timeout:
            print(f"\n[警告] 请求超时! 超时设置: {client.timeout}秒")
            print("建议: 查询量太大，建议简化查询或增加超时时间")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_simple())
