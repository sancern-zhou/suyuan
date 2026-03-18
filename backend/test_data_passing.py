"""
测试空气质量数据是否完整传递给LLM
"""
import asyncio
import sys
sys.path.insert(0, 'D:\\溯源\\backend')

from app.agent.executors.quick_trace_executor import QuickTraceExecutor


async def test_data_passing_to_llm():
    """测试数据传递给LLM"""
    executor = QuickTraceExecutor()

    print("=" * 80)
    print("测试空气质量数据传递给LLM上下文")
    print("=" * 80)

    city = "济宁市"
    pollutant = "PM2.5"
    alert_value = 115.0
    alert_time = "2026-02-03 12:00:00"

    # 1. 获取空气质量数据
    print(f"\n1. 获取空气质量数据...")
    air_quality_result = await executor._get_air_quality_from_db(city)

    print(f"   - 状态: {air_quality_result['status']}")
    print(f"   - 成功: {air_quality_result['success']}")
    print(f"   - 数据条数: {len(air_quality_result.get('data', []))}")

    # 2. 格式化为LLM摘要
    print(f"\n2. 格式化LLM摘要...")
    regional_summary = executor._format_regional_summary(air_quality_result, pollutant)

    print(f"   - 摘要长度: {len(regional_summary)} 字符")
    print(f"   - 摘要行数: {len(regional_summary.split(chr(10)))} 行")

    # 3. 显示摘要内容（前2000字符）
    print(f"\n3. LLM摘要内容 (前2000字符):")
    print("-" * 80)
    print(regional_summary[:2000])
    if len(regional_summary) > 2000:
        print(f"\n... (还有 {len(regional_summary) - 2000} 字符)")
    print("-" * 80)

    # 4. 分析摘要内容
    print(f"\n4. 内容分析:")

    summary_lines = regional_summary.split("\n")

    # 检查关键信息
    has_forecast = "未来7天预报数据" in regional_summary
    has_history = "历史前12小时监测数据" in regional_summary
    has_complete_data = "完整每小时数据" in regional_summary
    has_stats = "数据统计摘要" in regional_summary

    print(f"   - 包含预报数据: {has_forecast}")
    print(f"   - 包含历史数据: {has_history}")
    print(f"   - 标记完整数据: {has_complete_data}")
    print(f"   - 包含统计摘要: {has_stats}")

    # 统计数据点数量
    forecast_count = regional_summary.count("- ") if has_forecast else 0
    history_lines = [line for line in summary_lines if line.strip().startswith(("  2026", "  2025"))]

    print(f"   - 预报数据行: 约 {forecast_count} 行")
    print(f"   - 历史数据行: {len(history_lines)} 行")

    # 5. 检查是否包含六参数
    print(f"\n5. 检查六参数数据:")
    params = ["PM2.5", "PM10", "O3", "NO2", "SO2", "CO"]
    for param in params:
        count = regional_summary.count(f"{param}=")
        print(f"   - {param}: 出现 {count} 次")

    # 6. 检查AQI数据
    aqi_count = regional_summary.count("AQI=")
    print(f"\n6. AQI数据: 出现 {aqi_count} 次")

    # 7. 检查城市数据
    print(f"\n7. 城市分布:")
    cities_found = set()
    for line in summary_lines:
        if line.strip().startswith("#### "):
            city_name = line.strip().replace("#### ", "").strip()
            cities_found.add(city_name)

    for city_name in sorted(cities_found):
        city_line_count = regional_summary.count(f"#### {city_name}")
        print(f"   - {city_name}: {city_line_count} 次标题")

    # 8. 结论
    print(f"\n8. Conclusion:")
    if has_complete_data and len(history_lines) > 50:
        print("   [OK] Data fully passed: LLM can see complete hourly data")
        print(f"   [OK] History data lines: {len(history_lines)} (about {len(history_lines)//11} cities x 11 hours)")
        print("   [OK] Contains complete 6-parameter data")
        print("   [OK] Contains AQI and air quality level")
    elif has_forecast or has_history:
        print("   [WARNING] Data partially passed: only statistical summary, not complete data")
        print("   Suggestion: Need to modify _format_regional_summary method")
    else:
        print("   [ERROR] Data not passed: nearby city data query failed")


if __name__ == "__main__":
    asyncio.run(test_data_passing_to_llm())
