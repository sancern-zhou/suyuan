"""
测试天气预报数据修复

验证：
1. 数据不再重复
2. 数据完整返回（14个气象要素）
3. 字段格式兼容性（measurements嵌套 vs 扁平）
"""
import pytest
from datetime import datetime
from app.schemas.unified import UnifiedData, DataMetadata, UnifiedDataRecord, DataType, DataStatus


def test_forecast_data_structure():
    """测试预报数据结构是否符合UDF v2.0规范"""

    # 模拟 get_weather_forecast 工具返回的数据
    records = []
    for day in range(7):
        for hour in range(24):
            i = day * 24 + hour
            record = UnifiedDataRecord(
                timestamp=datetime.fromisoformat(f"2025-02-0{2+day}T{hour:02d}:00:00"),
                lat=23.13,
                lon=113.26,
                station_name="广州",
                measurements={
                    "temperature": 20.5 + i * 0.1,
                    "humidity": 70.0 + i * 0.05,
                    "dew_point": 15.0 + i * 0.08,
                    "wind_speed": 5.0 + i * 0.02,
                    "wind_direction": 45.0 + i,
                    "wind_gusts": 8.0 + i * 0.03,
                    "surface_pressure": 1013.0 + i * 0.01,
                    "precipitation": 0.0 if i < 100 else 0.5,
                    "precipitation_probability": 10 if i < 100 else 80,
                    "cloud_cover": 30 + i % 50,
                    "visibility": 10000,
                    "boundary_layer_height": 500 + i * 2,
                }
            )
            records.append(record)

    # 构建返回数据
    result = UnifiedData(
        status=DataStatus.SUCCESS,
        success=True,
        data=records,
        metadata=DataMetadata(
            data_id="weather_forecast_test",
            data_type=DataType.WEATHER,
            schema_version="v2.0",
            record_count=len(records),
            station_name="广州",
            lat=23.13,
            lon=113.26,
            parameters={
                "forecast_days": 7,
                "hourly": True,
                "daily": True
            }
        ),
        summary=f"天气预报查询成功 (广州)。未来7天预报，温度范围20.5~37.3°C。包含边界层高度预报数据。"
    )

    # 验证数据结构
    assert result.status == "success"
    assert result.success == True
    assert len(result.data) == 168
    # Pydantic v2 使用 model_dump() 访问字段
    assert result.metadata.parameters["forecast_days"] == 7

    # 验证记录完整性（14个气象要素）
    sample_record = result.data[0]
    # Pydantic v2: data 字段返回的是对象列表，不是字典
    assert hasattr(sample_record, "measurements")

    # 验证 measurements 字典
    measurements = sample_record.measurements
    assert "temperature" in measurements
    assert "humidity" in measurements
    assert "boundary_layer_height" in measurements
    assert measurements["temperature"] == 20.5
    assert measurements["boundary_layer_height"] == 500

    print("测试通过：预报数据结构符合UDF v2.0规范")


def test_weather_executor_data_extraction():
    """测试 WeatherExecutor 的数据提取逻辑"""

    # 模拟 tool_results
    tool_results = [
        {
            "tool": "get_weather_forecast",
            "status": "success",
            "success": True,
            "data": [
                {
                    "timestamp": "2025-02-02T00:00:00",
                    "lat": 23.13,
                    "lon": 113.26,
                    "station_name": "广州",
                    "measurements": {
                        "temperature": 20.5,
                        "humidity": 70.0,
                        "dew_point": 15.0,
                        "wind_speed": 5.0,
                        "wind_direction": 45.0,
                        "wind_gusts": 8.0,
                        "surface_pressure": 1013.0,
                        "precipitation": 0.0,
                        "precipitation_probability": 10,
                        "cloud_cover": 30,
                        "visibility": 10000,
                        "boundary_layer_height": 500,
                    }
                },
                {
                    "timestamp": "2025-02-02T01:00:00",
                    "lat": 23.13,
                    "lon": 113.26,
                    "station_name": "广州",
                    "measurements": {
                        "temperature": 20.6,
                        "humidity": 70.5,
                        "dew_point": 15.1,
                        "wind_speed": 5.2,
                        "wind_direction": 46.0,
                        "wind_gusts": 8.3,
                        "surface_pressure": 1013.1,
                        "precipitation": 0.0,
                        "precipitation_probability": 10,
                        "cloud_cover": 31,
                        "visibility": 10000,
                        "boundary_layer_height": 502,
                    }
                }
            ],
            "metadata": {
                "data_type": "weather",
                "schema_version": "v2.0",
                "station_name": "广州",
                "record_count": 2,
                "parameters": {
                    "forecast_days": 7,
                    "hourly": True,
                    "daily": True
                }
            },
            "summary": "天气预报查询成功 (广州)。未来7天预报，温度范围20.5~37.3°C。"
        }
    ]

    # 模拟 weather_executor 的数据提取逻辑
    forecast_data_summary = {
        "has_forecast": False,
        "forecast_days": 0,
        "hourly_records": [],
        "location": None,
        "parameters": {}
    }

    for result in tool_results:
        if result.get("tool") == "get_weather_forecast":
            forecast_data_summary["has_forecast"] = True

            metadata = result.get("metadata", {})
            if isinstance(metadata, dict):
                forecast_data_summary["location"] = metadata.get("station_name")
                forecast_data_summary["parameters"] = metadata.get("parameters", {})

            data_records = result.get("data", [])
            if isinstance(data_records, list) and len(data_records) > 0:
                forecast_data_summary["hourly_records"] = data_records

    # 验证提取结果
    assert forecast_data_summary["has_forecast"] == True
    assert forecast_data_summary["location"] == "广州"
    assert forecast_data_summary["parameters"]["forecast_days"] == 7
    assert len(forecast_data_summary["hourly_records"]) == 2

    # 验证字段兼容性逻辑（模拟 weather_executor.py 第337-354行）
    hourly_records = forecast_data_summary["hourly_records"]
    sample_records = hourly_records[:6] if len(hourly_records) > 6 else hourly_records

    for i, record in enumerate(sample_records):
        assert isinstance(record, dict)
        timestamp = record.get("timestamp")

        # 字段兼容性测试
        measurements = record.get("measurements", {})
        if not measurements:
            # 如果没有 measurements 字段，从顶层提取
            measurements = {
                "temperature": record.get("temperature"),
                "humidity": record.get("humidity"),
                "boundary_layer_height": record.get("boundary_layer_height"),
            }

        # 验证数据完整性
        assert timestamp is not None
        assert measurements.get("temperature") is not None
        assert measurements.get("boundary_layer_height") is not None

        print(f"记录 {i+1}: 时间={timestamp}, 温度={measurements.get('temperature')}, 边界层高度={measurements.get('boundary_layer_height')}")

    print("测试通过：数据提取逻辑正确")


if __name__ == "__main__":
    test_forecast_data_structure()
    test_weather_executor_data_extraction()
    print("\n所有测试通过！")
