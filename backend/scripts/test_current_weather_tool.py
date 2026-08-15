"""
测试当前天气工具

验证 GetCurrentWeatherTool 是否正常工作
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools.query.get_current_weather import GetCurrentWeatherTool
import json

async def test_current_weather_tool():
    """测试当前天气工具"""
    print("="*60)
    print("测试当前天气工具")
    print("="*60)

    tool = GetCurrentWeatherTool()

    # 测试1: 获取广州当前天气
    print("\n测试1: 广州天河当前天气")
    print("-"*60)

    result = await tool.execute(
        lat=23.1291,
        lon=113.3644,
        location_name="广州天河"
    )

    if result.get("success"):
        print("[OK] 调用成功")
        print(f"   位置: {result['location']['name']}")
        print(f"   观测时间: {result['observation_time']}")

        current = result.get("current", {})
        print(f"\n   当前天气:")
        print(f"     温度: {current.get('temperature_2m')} C")
        print(f"     体感温度: {current.get('apparent_temperature')} C")
        print(f"     湿度: {current.get('relative_humidity_2m')} %")
        print(f"     风速: {current.get('wind_speed_10m')} km/h")
        print(f"     风向: {current.get('wind_direction_10m')} deg")
        print(f"     气压: {current.get('surface_pressure')} hPa")
        print(f"     云量: {current.get('cloud_cover')} %")
        print(f"     降水: {current.get('precipitation')} mm")
        print(f"     天气代码: {current.get('weather_code')}")
        print(f"     是否白天: {current.get('is_day')}")
    else:
        print(f"[ERROR] 调用失败: {result.get('error')}")

    # 测试2: 获取深圳当前天气
    print("\n" + "="*60)
    print("测试2: 深圳南山当前天气")
    print("-"*60)

    result2 = await tool.execute(
        lat=22.5329,
        lon=113.9344,
        location_name="深圳南山"
    )

    if result2.get("success"):
        print("[OK] 调用成功")
        current = result2.get("current", {})
        print(f"   温度: {current.get('temperature_2m')} C")
        print(f"   风速: {current.get('wind_speed_10m')} km/h")
        print(f"   云量: {current.get('cloud_cover')} %")
    else:
        print(f"[ERROR] 调用失败: {result2.get('error')}")

    # 测试3: 获取北京当前天气
    print("\n" + "="*60)
    print("测试3: 北京当前天气")
    print("-"*60)

    result3 = await tool.execute(
        lat=39.9042,
        lon=116.4074,
        location_name="北京"
    )

    if result3.get("success"):
        print("[OK] 调用成功")
        current = result3.get("current", {})
        print(f"   温度: {current.get('temperature_2m')} C")
        print(f"   风速: {current.get('wind_speed_10m')} km/h")
        print(f"   降水: {current.get('precipitation')} mm")
    else:
        print(f"[ERROR] 调用失败: {result3.get('error')}")

    # 测试4: 获取Function Schema
    print("\n" + "="*60)
    print("测试4: Function Calling Schema")
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
    asyncio.run(test_current_weather_tool())
