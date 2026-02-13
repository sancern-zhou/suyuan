"""
测试 Open-Meteo API 能否获取当天00:00~当前时刻的气象数据

测试方案：
1. 使用 forecast API 的 past_days 参数
2. 查看返回的数据是否包含今天00:00到现在的数据
"""

import asyncio
import httpx
from datetime import datetime, timedelta


async def test_openmeteo_past_days():
    """测试 Open-Meteo API 的 past_days 参数"""

    # 测试坐标：济宁市
    lat = 35.4154
    lon = 116.5875

    api_url = "https://api.open-meteo.com/v1/forecast"

    print("=" * 80)
    print("测试 Open-Meteo API 获取当天气象数据")
    print(f"测试地点: 济宁市 ({lat}, {lon})")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 测试方案1: 使用 past_days=1 参数
    print("\n【方案1】使用 past_days=1 获取过去1天 + 今天 + 未来7天数据")
    print("-" * 80)

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation,boundary_layer_height",
        "past_days": 1,  # 关键参数：获取过去1天
        "forecast_days": 7,
        "timezone": "UTC",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(api_url, params=params)
            if response.status_code == 200:
                data = response.json()

                # 分析时间范围
                hourly_times = data.get("hourly", {}).get("time", [])

                if hourly_times:
                    first_time = hourly_times[0]
                    last_time = hourly_times[-1]
                    total_hours = len(hourly_times)

                    print(f"[OK] API 调用成功")
                    print(f"\n数据时间范围:")
                    print(f"  起始时间: {first_time}")
                    print(f"  结束时间: {last_time}")
                    print(f"  总小时数: {total_hours}")

                    # 分析今天的数据覆盖情况
                    today = datetime.now().strftime("%Y-%m-%d")
                    today_hours = [t for t in hourly_times if t.startswith(today)]

                    print(f"\n今天 ({today}) 的数据覆盖:")
                    print(f"  今天的小时数据点数: {len(today_hours)}")
                    if today_hours:
                        print(f"  今天起始时间: {today_hours[0]}")
                        print(f"  今天结束时间: {today_hours[-1]}")

                        # 判断是否从00:00开始
                        if "T00:00" in today_hours[0]:
                            print(f"  [OK] 包含今天 00:00 起始数据")
                        else:
                            print(f"  [WARNING]  今天起始时间不是 00:00")

                    # 样本数据展示
                    print(f"\n样本数据 (今天的前5个小时):")
                    hourly_temp = data.get("hourly", {}).get("temperature_2m", [])
                    for i in range(min(5, len(today_hours))):
                        idx = hourly_times.index(today_hours[i])
                        print(f"  {today_hours[i]}: 温度={hourly_temp[idx]}°C")

                    return {
                        "success": True,
                        "total_hours": total_hours,
                        "today_hours_count": len(today_hours),
                        "first_time": first_time,
                        "last_time": last_time,
                        "today_start": today_hours[0] if today_hours else None,
                        "today_end": today_hours[-1] if today_hours else None,
                    }
            else:
                print(f"[FAILED] API 调用失败: {response.status_code}")
                return {"success": False, "error": f"HTTP {response.status_code}"}

    except Exception as e:
        print(f"[FAILED] 测试失败: {e}")
        return {"success": False, "error": str(e)}


async def test_current_weather_api():
    """测试 current_weather API 的返回内容"""
    print("\n" + "=" * 80)
    print("【对比】测试 current_weather API (只用 current 参数)")
    print("-" * 80)

    lat = 35.4154
    lon = 116.5875
    api_url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,is_day,precipitation",
        "timezone": "UTC",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(api_url, params=params)
            if response.status_code == 200:
                data = response.json()
                current = data.get("current", {})

                print(f"[OK] API 调用成功")
                print(f"\n返回内容:")
                print(f"  观测时间: {current.get('time')}")
                print(f"  温度: {current.get('temperature_2m')}°C")
                print(f"  湿度: {current.get('relative_humidity_2m')}%")
                print(f"  风速: {current.get('wind_speed_10m')} km/h")
                print(f"  风向: {current.get('wind_direction_10m')}°")
                print(f"  是否白天: {current.get('is_day')}")
                print(f"  降水: {current.get('precipitation')} mm")

                print(f"\n[WARNING]  结论: current_weather 只返回单个时刻的数据，不是时序数据")

                return {"success": True, "is_single_point": True}
            else:
                print(f"[FAILED] API 调用失败: {response.status_code}")
                return {"success": False}

    except Exception as e:
        print(f"[FAILED] 测试失败: {e}")
        return {"success": False, "error": str(e)}


async def main():
    """主测试函数"""
    print("\n" + "=" * 80)
    print("Open-Meteo API 当天数据获取能力测试")
    print("=" * 80 + "\n")

    # 测试1: past_days 方案
    result1 = await test_openmeteo_past_days()

    # 测试2: current_weather 对比
    result2 = await test_current_weather_api()

    # 总结
    print("\n" + "=" * 80)
    print("【测试总结】")
    print("=" * 80)

    if result1.get("success"):
        print(f"\n[OK] 使用 past_days=1 参数可以获取:")
        print(f"   - 总小时数: {result1['total_hours']} 小时")
        print(f"   - 今天的小时数: {result1['today_hours_count']} 小时")
        print(f"   - 今天起始时间: {result1['today_start']}")
        print(f"   - 今天结束时间: {result1['today_end']}")

        if result1['today_start'] and "T00:00" in result1['today_start']:
            print(f"\n[OK] 结论: 可以获取今天 00:00 到当前时刻的完整小时数据")
            print(f"   建议: 修改 get_weather_forecast 工具，添加 past_days 参数")
        else:
            print(f"\n[WARNING]  警告: 今天起始时间不是 00:00，可能存在数据缺失")
    else:
        print(f"\n[FAILED] past_days 测试失败: {result1.get('error')}")

    if result2.get("success") and result2.get("is_single_point"):
        print(f"\n[WARNING]  current_weather 只返回单个时刻，无法获取今天00:00~现在的时序数据")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
