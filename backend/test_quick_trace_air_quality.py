"""
测试quick_trace_executor中的空气质量数据库查询功能
"""
import asyncio
import sys
sys.path.insert(0, 'D:\\溯源\\backend')

from app.agent.executors.quick_trace_executor import QuickTraceExecutor


async def test_air_quality_query():
    """测试空气质量查询"""
    executor = QuickTraceExecutor()

    print("=" * 80)
    print("测试快速溯源执行器 - 空气质量数据库查询")
    print("=" * 80)

    # 测试济宁市的空气质量查询
    city = "济宁市"
    print(f"\n查询城市: {city}")
    print(f"周边城市: {', '.join(executor.NEARBY_CITIES)}")

    result = await executor._get_air_quality_from_db(city)

    print("\n" + "=" * 80)
    print("查询结果")
    print("=" * 80)
    print(f"状态: {result['status']}")
    print(f"成功: {result['success']}")
    print(f"摘要: {result['summary']}")
    print(f"数据条数: {len(result.get('data', []))}")

    if result.get('data'):
        print("\n数据示例 (前5条):")
        for i, record in enumerate(result['data'][:5], 1):
            print(f"\n{i}. {record['timestamp']} - {record['station_name']}")
            print(f"   数据源: {record['metadata'].get('source', 'N/A')}")
            print(f"   数据类型: {record['metadata'].get('data_type', 'N/A')}")

            measurements = record.get('measurements', {})
            if measurements.get('AQI') is not None:
                print(f"   AQI: {measurements['AQI']}")

            # 显示六参数
            params = ['PM2.5', 'PM10', 'O3', 'NO2', 'SO2', 'CO']
            param_values = []
            for param in params:
                value = measurements.get(param)
                if value is not None:
                    param_values.append(f"{param}={value}")

            if param_values:
                print(f"   六参数: {', '.join(param_values)}")

            if measurements.get('primary_pollutant'):
                print(f"   首要污染物: {measurements['primary_pollutant']}")

            if measurements.get('quality'):
                print(f"   空气质量等级: {measurements['quality']}")

    # 统计数据来源
    if result.get('data'):
        forecast_count = sum(1 for r in result['data'] if r['metadata'].get('data_type') == 'forecast')
        history_count = sum(1 for r in result['data'] if r['metadata'].get('data_type') == 'history')

        print("\n" + "=" * 80)
        print("数据统计")
        print("=" * 80)
        print(f"预报数据: {forecast_count} 条")
        print(f"历史数据: {history_count} 条")

        # 按城市统计历史数据
        history_by_city = {}
        for record in result['data']:
            if record['metadata'].get('data_type') == 'history':
                city_name = record['station_name']
                history_by_city[city_name] = history_by_city.get(city_name, 0) + 1

        if history_by_city:
            print("\n历史数据按城市分布:")
            for city_name, count in sorted(history_by_city.items(), key=lambda x: x[1], reverse=True):
                print(f"  {city_name}: {count} 条")


if __name__ == "__main__":
    asyncio.run(test_air_quality_query())
