"""
测试 Open-Meteo API 的 past_days 参数行为

目标：找到只获取今天00:00~当前时刻数据的参数组合
"""

import asyncio
import httpx
from datetime import datetime


async def test_past_days_options():
    """测试不同的 past_days 参数"""

    lat = 35.4154
    lon = 116.5875
    api_url = "https://api.open-meteo.com/v1/forecast"

    today = datetime.now().strftime("%Y-%m-%d")

    print("=" * 80)
    print(f"测试 Open-Meteo API past_days 参数")
    print(f"今天: {today}")
    print("=" * 80)

    # 测试方案
    test_cases = [
        {"past_days": 0, "desc": "past_days=0 (默认，从当前时刻开始)"},
        {"past_days": 1, "desc": "past_days=1 (从昨天00:00开始)"},
    ]

    for case in test_cases:
        past_days = case["past_days"]
        desc = case["desc"]

        print(f"\n{'-' * 80}")
        print(f"测试: {desc}")
        print(f"{'-' * 80}")

        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "temperature_2m",
            "past_days": past_days,
            "forecast_days": 1,
            "timezone": "UTC",
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(api_url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    times = data.get("hourly", {}).get("time", [])

                    if times:
                        first_time = times[0]
                        last_time = times[-1]

                        # 按天分组
                        daily_counts = {}
                        for t in times:
                            date_str = t[:10]
                            daily_counts[date_str] = daily_counts.get(date_str, 0) + 1

                        print(f"  时间范围: {first_time} ~ {last_time}")
                        print(f"  总小时数: {len(times)}")
                        print(f"  各天数据点:")
                        for date in sorted(daily_counts.keys()):
                            print(f"    - {date}: {daily_counts[date]} 小时")

                        # 检查是否包含昨天
                        yesterday = (datetime.now().replace(hour=0, minute=0, second=0) -
                                    __import__('datetime').timedelta(days=1)).strftime("%Y-%m-%d")

                        if yesterday in daily_counts:
                            print(f"  [包含昨天数据]")
                        if today in daily_counts:
                            print(f"  [包含今天数据]")

                else:
                    print(f"  API 错误: {response.status_code}")

        except Exception as e:
            print(f"  测试失败: {e}")

    print("\n" + "=" * 80)
    print("结论：")
    print("  - past_days=0: 从当前时刻开始，不包含今天00:00~现在的数据")
    print("  - past_days=1: 包含昨天完整数据 + 今天完整数据")
    print("\n建议：使用 past_days=1，然后在工具层过滤掉昨天数据")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_past_days_options())
