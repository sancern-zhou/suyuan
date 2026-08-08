"""
新标准统计报表查询工具测试

验证工具的基本功能和数据格式
"""

import asyncio
from datetime import datetime, timedelta


async def test_query_new_standard_report():
    """测试新标准统计报表查询工具"""
    import sys
    sys.path.insert(0, '/home/xckj/suyuan/backend')

    from app.tools.query.query_new_standard_report.tool import execute_query_new_standard_report

    # 测试参数
    cities = ["广州"]
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)

    print(f"Testing query_new_standard_report:")
    print(f"  Cities: {cities}")
    print(f"  Date range: {start_date} to {end_date}")
    print()

    try:
        result = await execute_query_new_standard_report(
            cities=cities,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            context=None  # 不使用context进行基本测试
        )

        # 验证返回格式
        assert "status" in result, "Missing 'status' field"
        assert "success" in result, "Missing 'success' field"
        assert "metadata" in result, "Missing 'metadata' field"
        assert "summary" in result, "Missing 'summary' field"

        print(f"Status: {result['status']}")
        print(f"Success: {result['success']}")
        print(f"Summary: {result['summary']}")
        print()

        # 检查元数据
        metadata = result["metadata"]
        assert metadata["schema_version"] == "v2.0", "Schema version should be v2.0"
        assert metadata["tool_name"] == "query_new_standard_report", "Tool name mismatch"
        print("Metadata validation passed")
        print()

        # 检查数据
        if result.get("data"):
            for city, stats in result["data"].items():
                print(f"City: {city}")
                print(f"  Composite Index: {stats.get('composite_index')}")
                print(f"  Exceed Days: {stats.get('exceed_days')}")
                print(f"  Compliance Rate: {stats.get('compliance_rate')}%")
                print(f"  PM2.5: {stats.get('PM2_5')}")
                print(f"  PM2.5_P95: {stats.get('PM2_5_P95')}")
                print(f"  O3_8h_P90: {stats.get('O3_8h_P90')}")
                print(f"  SO2_P98: {stats.get('SO2_P98')}")
                print(f"  NO2_P98: {stats.get('NO2_P98')}")
                print(f"  PM10_P95: {stats.get('PM10_P95')}")
                print(f"  CO_P95: {stats.get('CO_P95')}")
                print()

                # 验证必需字段
                required_fields = [
                    "composite_index", "exceed_days", "valid_days",
                    "exceed_rate", "compliance_rate", "total_days",
                    "SO2", "SO2_P98", "NO2", "NO2_P98",
                    "PM10", "PM10_P95", "PM2_5", "PM2_5_P95",
                    "CO_P95", "O3_8h_P90",
                    "single_indexes", "primary_pollutant_days",
                    "primary_pollutant_ratio", "exceed_days_by_pollutant",
                    "exceed_rate_by_pollutant"
                ]

                for field in required_fields:
                    assert field in stats, f"Missing field: {field}"

                print("All required fields present")
        else:
            print("No data returned (may be expected for recent dates)")

        print()
        print("Test PASSED!")
        return True

    except Exception as e:
        print(f"Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_query_new_standard_report())
    exit(0 if success else 1)
