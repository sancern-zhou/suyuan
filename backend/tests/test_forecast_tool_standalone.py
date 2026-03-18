"""
独立测试天气预报工具

验证 GetWeatherForecastTool 是否能正常返回数据
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tools.query.get_weather_forecast.tool import GetWeatherForecastTool


async def test_forecast_tool():
    """测试天气预报工具"""
    print("=" * 60)
    print("独立测试: GetWeatherForecastTool")
    print("=" * 60)

    # 创建工具实例
    tool = GetWeatherForecastTool()

    # 测试参数（广州）
    test_cases = [
        {
            "name": "广州（7天预报）",
            "params": {
                "lat": 23.1291,
                "lon": 113.2644,
                "location_name": "广州",
                "forecast_days": 7,
                "hourly": True,
                "daily": True
            }
        },
        {
            "name": "北京（3天预报）",
            "params": {
                "lat": 39.9042,
                "lon": 116.4074,
                "location_name": "北京",
                "forecast_days": 3,
                "hourly": True,
                "daily": True
            }
        }
    ]

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n测试 {i}: {test_case['name']}")
        print("-" * 60)

        try:
            result = await tool.execute(**test_case['params'])

            # 检查返回结果 (UDF v2.0 格式)
            if isinstance(result, dict):
                success = result.get("success", False)
                status = result.get("status", "")

                print(f"  status: {status}")
                print(f"  success: {success}")

                if success:
                    print(f"  [PASS] 工具执行成功")

                    # 检查 UDF v2.0 数据结构
                    metadata = result.get("metadata", {})
                    if isinstance(metadata, dict):
                        print(f"  data_id: {metadata.get('data_id', 'N/A')}")
                        print(f"  data_type: {metadata.get('data_type', 'N/A')}")
                        print(f"  schema_version: {metadata.get('schema_version', 'N/A')}")
                        print(f"  record_count: {metadata.get('record_count', 0)}")

                        # 检查参数
                        parameters = metadata.get("parameters", {})
                        if isinstance(parameters, dict):
                            print(f"  forecast_days (param): {parameters.get('forecast_days', 'N/A')}")

                    # 检查 data 列表
                    data = result.get("data", [])
                    if isinstance(data, list) and len(data) > 0:
                        print(f"  data 记录数: {len(data)}")
                        # 显示第一条记录示例
                        first_record = data[0]
                        if isinstance(first_record, dict):
                            measurements = first_record.get("measurements", {})
                            print(f"  示例记录: timestamp={first_record.get('timestamp')}")
                            print(f"    temperature={measurements.get('temperature')}")
                            print(f"    boundary_layer_height={measurements.get('boundary_layer_height')}")
                            print(f"    wind_speed={measurements.get('wind_speed')}")

                    # 检查 summary
                    summary = result.get("summary", "")
                    if summary:
                        print(f"  摘要: {summary[:100]}...")

                else:
                    error = result.get("error", "未知错误")
                    print(f"  [FAIL] 工具执行失败: {error}")

            else:
                print(f"  [FAIL] 返回结果不是字典: {type(result)}")

        except Exception as e:
            print(f"  [ERROR] 异常: {e}")
            import traceback
            traceback.print_exc()

        print()

    print("=" * 60)


async def test_openmeteo_client_directly():
    """直接测试 OpenMeteoClient"""
    print("\n直接测试: OpenMeteoClient.fetch_forecast()")
    print("=" * 60)

    from app.external_apis.openmeteo_client import OpenMeteoClient

    client = OpenMeteoClient()

    try:
        print("调用 fetch_forecast API...")
        result = await client.fetch_forecast(
            lat=23.1291,
            lon=113.2644,
            forecast_days=7,
            hourly=True,
            daily=True
        )

        print(f"[PASS] API 调用成功")
        print(f"  返回类型: {type(result)}")
        print(f"  顶层键: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")

        if isinstance(result, dict):
            if "daily" in result:
                daily = result["daily"]
                print(f"  daily 数据包含: {list(daily.keys()) if isinstance(daily, dict) else 'N/A'}")
                if isinstance(daily, dict) and "time" in daily:
                    print(f"  预报天数: {len(daily['time'])}")

            if "hourly" in result:
                hourly = result["hourly"]
                if isinstance(hourly, dict) and "time" in hourly:
                    print(f"  小时数据点数: {len(hourly['time'])}")

    except Exception as e:
        print(f"[ERROR] API 调用失败: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 60)


async def main():
    """运行所有测试"""
    try:
        # 测试工具
        await test_forecast_tool()

        # 测试底层客户端
        await test_openmeteo_client_directly()

        print("\n所有测试完成")

    except Exception as e:
        print(f"\n测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
