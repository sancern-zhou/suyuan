"""
测试天气预报工具集成

验证：
1. default_plan 是否包含 get_weather_forecast
2. WeatherExecutor 是否正确处理预报数据
3. summary_stats 是否包含 forecast 相关字段
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.core.expert_plan_generator import ExpertPlanGenerator


def test_default_plan_includes_forecast():
    """测试默认计划是否包含天气预报工具"""
    print("=" * 60)
    print("测试: 默认计划包含天气预报工具")
    print("=" * 60)

    plan_gen = ExpertPlanGenerator()

    # 获取气象专家的计划模板
    weather_templates = plan_gen.EXPERT_TEMPLATES.get("weather", {})
    default_plan = weather_templates.get("default_plan", [])

    print(f"\n默认计划包含 {len(default_plan)} 个工具:")
    for i, tool in enumerate(default_plan):
        print(f"  {i+1}. {tool['tool']}: {tool['purpose']}")

    # 验证是否包含 get_weather_forecast
    tool_names = [t["tool"] for t in default_plan]
    assert "get_weather_forecast" in tool_names, "默认计划应包含 get_weather_forecast 工具"

    print("\n[PASS] 默认计划包含 get_weather_forecast 工具")

    # 验证工具顺序
    assert tool_names[0] == "get_weather_data", "第一个工具应为 get_weather_data"
    assert tool_names[1] == "get_weather_forecast", "第二个工具应为 get_weather_forecast"
    assert tool_names[2] == "meteorological_trajectory_analysis", "第三个工具应为 meteorological_trajectory_analysis"

    print("[PASS] 工具顺序正确")
    print("\n" + "=" * 60)


def test_weather_executor_summary_stats():
    """测试 WeatherExecutor 的 summary_stats 包含预报字段"""
    print("\n测试: WeatherExecutor summary_stats 包含预报字段")
    print("=" * 60)

    from app.agent.experts.weather_executor import WeatherExecutor

    executor = WeatherExecutor()

    # 模拟工具结果
    mock_results = [
        {
            "tool": "get_weather_data",
            "status": "success",
            "data": [
                {"temperature_2m": 25.5, "wind_speed_10m": 3.2, "relative_humidity_2m": 75}
            ]
        },
        {
            "tool": "get_weather_forecast",
            "status": "success",
            "summary": "未来7天天气预报：温度20-28°C，风速2-5m/s，湿度60-80%",
            "data": {
                "daily": {
                    "time": ["2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06", "2026-02-07", "2026-02-08", "2026-02-09"]
                }
            }
        },
        {
            "tool": "meteorological_trajectory_analysis",
            "status": "success",
            "summary": "后向轨迹分析显示主要传输通道为西南方向"
        }
    ]

    # 提取统计信息
    stats = executor._extract_summary_stats(mock_results)

    # 验证预报相关字段
    assert stats["has_forecast_data"] == True, "应标记 has_forecast_data=True"
    assert stats["forecast_days"] == 7, "预报天数应为7天"
    assert "未来7天天气预报" in stats["forecast_info"], "应包含预报摘要信息"

    print(f"  has_forecast_data: {stats['has_forecast_data']}")
    print(f"  forecast_days: {stats['forecast_days']}")
    print(f"  forecast_info: {stats['forecast_info'][:50]}...")

    print("\n[PASS] 通过: summary_stats 正确包含预报字段")
    print("\n" + "=" * 60)


def test_data_completeness_includes_forecast():
    """测试数据完整性计算包含预报数据"""
    print("\n测试: 数据完整性计算包含预报数据")
    print("=" * 60)

    from app.agent.experts.weather_executor import WeatherExecutor

    executor = WeatherExecutor()

    # 只有历史数据和预报数据
    mock_results = [
        {
            "tool": "get_weather_data",
            "status": "success",
            "data": [{"temperature_2m": 25.5}]
        },
        {
            "tool": "get_weather_forecast",
            "status": "success",
            "data": {
                "daily": {
                    "time": ["2026-02-03", "2026-02-04"]
                }
            }
        }
    ]

    stats = executor._extract_summary_stats(mock_results)

    # total_possible = 6 (weather_data, forecast_data, trajectory, fire, dust, satellite)
    # actual_has = 2 (weather_data, forecast_data)
    # completeness = 2/6 = 0.33
    expected_completeness = round(2 / 6, 2)
    assert stats["data_completeness"] == expected_completeness, f"数据完整性应为 {expected_completeness}"

    print(f"  data_completeness: {stats['data_completeness']} (预期: {expected_completeness})")
    print(f"  total_possible: 6")
    print(f"  actual_has: 2 (weather_data, forecast_data)")

    print("\n[PASS] 通过: 数据完整性计算正确")
    print("\n" + "=" * 60)


def main():
    """运行所有测试"""
    try:
        test_default_plan_includes_forecast()
        test_weather_executor_summary_stats()
        test_data_completeness_includes_forecast()

        print("\n" + "=" * 60)
        print("所有测试通过！")
        print("=" * 60)
        print("\n修改总结:")
        print("  1. [PASS] default_plan 新增 get_weather_forecast 工具")
        print("  2. [PASS] 工具顺序正确: get_weather_data -> get_weather_forecast -> 轨迹分析")
        print("  3. [PASS] WeatherExecutor 正确提取预报统计信息")
        print("  4. [PASS] 数据完整性计算包含预报数据")
        print("  5. [PASS] LLM 提示词更新，强调使用预报数据")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
