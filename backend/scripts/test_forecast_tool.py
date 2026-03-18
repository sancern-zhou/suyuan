"""
测试天气预报工具 (UDF v2.0)

验证 GetWeatherForecastTool 是否正常工作
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools.query.get_weather_forecast import GetWeatherForecastTool
import json

async def test_forecast_tool():
    """测试天气预报工具 (UDF v2.0 格式)"""
    print("="*60)
    print("测试天气预报工具 (UDF v2.0)")
    print("="*60)

    tool = GetWeatherForecastTool()

    # 测试1: 获取广州7天预报（逐小时+每日）
    print("\n测试1: 广州7天预报（逐小时+每日）")
    print("-"*60)

    result = await tool.execute(
        lat=23.1291,
        lon=113.3644,
        location_name="广州天河",
        forecast_days=7,
        hourly=True,
        daily=True
    )

    if result.get("success"):
        print("[OK] 调用成功")
        print(f"   status: {result.get('status')}")
        print(f"   schema_version: {result.get('metadata', {}).get('schema_version')}")
        print(f"   data_type: {result.get('metadata', {}).get('data_type')}")
        print(f"   record_count: {result.get('metadata', {}).get('record_count')}")

        # 检查 data 列表
        data = result.get("data", [])
        if isinstance(data, list) and len(data) > 0:
            print(f"   data 记录数: {len(data)}")

            # 显示第一个小时的记录
            first_record = data[0]
            measurements = first_record.get("measurements", {})
            print(f"\n   第一小时预报:")
            print(f"     时间: {first_record.get('timestamp')}")
            print(f"     温度: {measurements.get('temperature')}°C")
            print(f"     风速: {measurements.get('wind_speed')} km/h")
            print(f"     降水概率: {measurements.get('precipitation_probability')}%")
            print(f"     边界层高度: {measurements.get('boundary_layer_height')} m")

        # 检查参数
        parameters = result.get('metadata', {}).get('parameters', {})
        print(f"\n   查询参数:")
        print(f"     forecast_days: {parameters.get('forecast_days')}")
        print(f"     hourly: {parameters.get('hourly')}")
        print(f"     daily: {parameters.get('daily')}")

        # 检查摘要
        summary = result.get('summary', '')
        print(f"\n   摘要: {summary}")

    else:
        print(f"[ERROR] 调用失败: {result.get('error')}")

    # 测试2: 只获取逐小时预报（3天）
    print("\n" + "="*60)
    print("测试2: 深圳3天预报（仅逐小时）")
    print("-"*60)

    result2 = await tool.execute(
        lat=22.5329,
        lon=113.9344,
        location_name="深圳南山",
        forecast_days=3,
        hourly=True,
        daily=False
    )

    if result2.get("success"):
        print("[OK] 调用成功")
        data = result2.get("data", [])
        if isinstance(data, list):
            print(f"   data 记录数: {len(data)}")
            print(f"   预期数据点: {3 * 24} (3天 × 24小时)")

        # 检查边界层高度
        has_blh = any(
            r.get("measurements", {}).get("boundary_layer_height") is not None
            for r in data if isinstance(r, dict)
        )
        print(f"   包含边界层高度: {'[OK]' if has_blh else '[MISSING]'}")
    else:
        print(f"[ERROR] 调用失败: {result2.get('error')}")

    # 测试3: 获取Function Schema
    print("\n" + "="*60)
    print("测试3: Function Calling Schema")
    print("-"*60)

    schema = tool.get_function_schema()
    print("[OK] Function Schema:")
    print(f"   Name: {schema['name']}")
    print(f"   Description: {schema['description']}")
    print(f"   Parameters: {list(schema['parameters']['properties'].keys())}")
    print(f"   Required: {schema['parameters']['required']}")

    print("\n" + "="*60)
    print("测试完成")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(test_forecast_tool())
