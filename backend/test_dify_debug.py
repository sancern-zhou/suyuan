"""
Dify API 调试脚本

诊断问题:
1. 连接问题
2. 超时问题
3. 解析问题
"""
import asyncio
import sys
import os
import json
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from app.external_apis.dify_client import DifyClient
from app.schemas.dify_data_adapter import parse_dify_air_quality_data


async def test_dify_basic_connection():
    """测试基本连接"""
    print("=" * 60)
    print("测试1: Dify API 基本连接")
    print("=" * 60)

    client = DifyClient()

    print(f"API地址: {client.base_url}")
    print(f"超时时间: {client.timeout}秒")

    # 简单查询
    question = "查询济宁市今日空气质量"
    print(f"\n查询问题: {question}")
    print("开始请求...")

    start_time = datetime.now()

    try:
        response = await client.chat_messages(
            query=question,
            response_mode="blocking"
        )

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n[OK] 请求成功! 耗时: {elapsed:.2f}秒")
        print(f"Conversation ID: {response.get('conversation_id')}")
        print(f"Answer长度: {len(response.get('answer', ''))}")

        # 打印answer前500字符
        answer = response.get('answer', '')
        print(f"\nAnswer内容预览:\n{answer[:500]}")

        return response

    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n❌ 请求失败! 耗时: {elapsed:.2f}秒")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        return None


async def test_dify_data_parsing(response):
    """测试数据解析"""
    print("\n" + "=" * 60)
    print("测试2: Dify 数据解析")
    print("=" * 60)

    if not response:
        print("⚠️  无响应数据，跳过解析测试")
        return

    print("\n开始解析数据...")
    unified_data = parse_dify_air_quality_data(response)

    print(f"\n解析结果:")
    print(f"  - 成功标志: {unified_data.success}")
    print(f"  - 状态: {unified_data.status}")
    print(f"  - 数据记录数: {len(unified_data.data)}")
    print(f"  - 摘要: {unified_data.summary}")

    if unified_data.data:
        print(f"\n第一条数据示例:")
        first_record = unified_data.data[0]
        print(f"  - 时间: {first_record.timestamp}")
        print(f"  - 站点: {first_record.station_name}")
        print(f"  - 测量值: {first_record.measurements}")
    else:
        print("\n⚠️  未解析到数据")

        # 打印原始answer用于调试
        answer = response.get('answer', '')
        print(f"\n原始Answer内容:")
        print(answer[:1000])


async def test_dify_regional_query():
    """测试区域对比查询（模拟快速溯源场景）"""
    print("\n" + "=" * 60)
    print("测试3: 区域对比查询（快速溯源场景）")
    print("=" * 60)

    client = DifyClient()

    # 模拟快速溯源的查询
    alert_time = datetime.now()
    query_start = alert_time - timedelta(hours=12)

    cities = ["济宁市", "菏泽市", "枣庄市", "临沂市", "泰安市", "徐州市", "商丘市", "开封市"]
    cities_str = "、".join(cities)

    question = f"""查询{cities_str}的PM2.5浓度数据，
StartTime={query_start.strftime('%Y-%m-%d %H:%M:%S')}，
EndTime={alert_time.strftime('%Y-%m-%d %H:%M:%S')}，
时间粒度为小时数据，请返回各城市的PM2.5小时浓度数据。"""

    print(f"\n查询问题:\n{question}")
    print(f"\n涉及城市数: {len(cities)}")
    print(f"时间范围: 12小时")
    print(f"预计数据量: ~{len(cities) * 12}条")
    print("\n开始请求...")

    start_time = datetime.now()

    try:
        response = await client.chat_messages(
            query=question,
            response_mode="blocking"
        )

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n✅ 请求成功! 耗时: {elapsed:.2f}秒")

        # 解析数据
        unified_data = parse_dify_air_quality_data(response)

        print(f"\n解析结果:")
        print(f"  - 成功标志: {unified_data.success}")
        print(f"  - 数据记录数: {len(unified_data.data)}")
        print(f"  - 摘要: {unified_data.summary}")

        # 按城市统计
        city_data = {}
        for record in unified_data.data:
            city = record.station_name or "未知"
            if city not in city_data:
                city_data[city] = []
            city_data[city].append(record)

        print(f"\n按城市统计:")
        for city, records in sorted(city_data.items()):
            pm25_values = [r.measurements.get('pm2_5') for r in records if r.measurements.get('pm2_5')]
            if pm25_values:
                print(f"  - {city}: {len(records)}条记录, PM2.5范围: {min(pm25_values):.1f}-{max(pm25_values):.1f} μg/m³")

        return response

    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n❌ 请求失败! 耗时: {elapsed:.2f}秒")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")

        if elapsed >= client.timeout:
            print(f"\n⚠️  请求超时! 超时时间: {client.timeout}秒")
            print("建议: 增加 timeout 参数或简化查询")

        return None


async def test_dify_timeout_analysis():
    """分析不同超时设置的影响"""
    print("\n" + "=" * 60)
    print("测试4: 超时时间分析")
    print("=" * 60)

    client = DifyClient()

    # 测试不同复杂度的查询
    test_cases = [
        ("简单查询", "查询济宁今日空气质量", 30),
        ("中等查询", "查询济宁、菏泽、枣庄今日空气质量", 60),
        ("复杂查询", f"查询济宁市、菏泽市、枣庄市过去12小时PM2.5浓度数据", 120),
    ]

    for name, question, expected_timeout in test_cases:
        print(f"\n{name}:")
        print(f"  问题: {question}")
        print(f"  预计超时: {expected_timeout}秒")

        start_time = datetime.now()

        try:
            response = await client.chat_messages(
                query=question,
                response_mode="blocking"
            )

            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"  ✅ 成功! 实际耗时: {elapsed:.2f}秒")

            # 解析检查
            unified_data = parse_dify_air_quality_data(response)
            print(f"  解析记录数: {len(unified_data.data)}")

        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"  ❌ 失败! 耗时: {elapsed:.2f}秒")
            print(f"  错误: {str(e)[:100]}")


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("Dify API 诊断测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 测试1: 基本连接
    response = await test_dify_basic_connection()

    # 测试2: 数据解析
    await test_dify_data_parsing(response)

    # 测试3: 区域对比查询（快速溯源场景）
    await test_dify_regional_query()

    # 测试4: 超时分析
    await test_dify_timeout_analysis()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
