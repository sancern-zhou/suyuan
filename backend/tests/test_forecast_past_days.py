"""
测试 GetWeatherForecastTool 的 past_days 参数

验证 past_days=1 是否能获取今天00:00~当前时刻的完整数据
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.tools.query.get_weather_forecast.tool import GetWeatherForecastTool


async def test_forecast_past_days():
    """测试天气预报工具的 past_days 参数"""

    print("=" * 80)
    print("测试 GetWeatherForecastTool - past_days 参数")
    print("=" * 80)

    # 创建工具实例
    tool = GetWeatherForecastTool()

    # 测试参数
    lat = 35.4154  # 济宁市
    lon = 116.5875

    print(f"\n测试地点: 济宁市 ({lat}, {lon})")
    print(f"测试参数:")
    print(f"  - forecast_days: 7")
    print(f"  - past_days: 1 (获取昨天 + 今天 + 未来7天)")
    print(f"\n{'-' * 80}")

    try:
        # 调用工具（不使用 context）
        result = await tool.execute(
            lat=lat,
            lon=lon,
            location_name="济宁市",
            forecast_days=7,
            past_days=1,
            hourly=True,
            daily=True
        )

        # 检查结果
        if result.get("success"):
            print(f"\n[OK] 工具调用成功")

            # 分析数据时间范围
            data = result.get("data", [])
            if data:
                from datetime import datetime

                # 按天分组
                daily_data = {}
                for record in data:
                    if isinstance(record, dict):
                        ts = record.get("timestamp")
                        if ts:
                            if isinstance(ts, str):
                                date_str = ts[:10]
                            else:
                                date_str = str(ts)[:10]
                            if date_str not in daily_data:
                                daily_data[date_str] = []
                            daily_data[date_str].append(record)

                today = datetime.now().strftime("%Y-%m-%d")

                print(f"\n[INFO] 数据覆盖情况:")
                print(f"  总小时数: {len(data)}")
                print(f"  覆盖天数: {len(daily_data)}")

                # 显示每天的数据点数
                for date in sorted(daily_data.keys()):
                    count = len(daily_data[date])
                    print(f"  - {date}: {count} 小时")

                # 检查今天数据
                if today in daily_data:
                    today_count = len(daily_data[today])
                    print(f"\n[OK] 今天 ({today}) 数据: {today_count} 小时")

                    # 检查是否从00:00开始
                    today_records = sorted(daily_data[today],
                                         key=lambda x: str(x.get("timestamp", "")))
                    first_time = str(today_records[0].get("timestamp", ""))

                    if "T00:00" in first_time or " 00:00" in first_time:
                        print(f"[OK] 今天数据从 00:00 开始")
                    else:
                        print(f"[WARNING] 今天起始时间: {first_time}")

                else:
                    print(f"\n[FAILED] 缺少今天 ({today}) 的数据")

                # 显示数据样本
                print(f"\n[INFO] 今天数据样本 (前3个小时):")
                if today in daily_data:
                    for i, rec in enumerate(today_records[:3]):
                        ts = rec.get("timestamp")
                        meas = rec.get("measurements", {})
                        temp = meas.get("temperature") or meas.get("temperature_2m")
                        pblh = meas.get("boundary_layer_height")
                        print(f"  {ts}: 温度={temp}°C, 边界层高度={pblh}m")

            else:
                print(f"\n[FAILED] 数据为空")

        else:
            print(f"\n[FAILED] 工具调用失败")
            print(f"错误: {result.get('summary', 'Unknown error')}")

    except Exception as e:
        print(f"\n[FAILED] 测试失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_forecast_past_days())
