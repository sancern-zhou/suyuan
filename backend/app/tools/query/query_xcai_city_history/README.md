# XcAiDb城市历史数据查询工具

## 功能说明

查询全国城市历史空气质量数据（SQL Server XcAiDb数据库）

## 数据表

### CityAQIPublishHistory（小时数据）
- **时间范围**：2017-01-01 至今
- **字段**：TimePoint, Area, CityCode, PM2_5, PM10, O3, NO2, SO2, CO, AQI, PrimaryPollutant, Quality

### CityDayAQIPublishHistory（日数据）
- **时间范围**：2021-06-25 至今
- **字段**：TimePoint, Area, CityCode, PM2_5_24h, PM10_24h, O3_8h_24h, NO2_24h, SO2_24h, CO_24h, AQI, PrimaryPollutant, Quality

## 使用示例

```python
# 查询广州2025年3月小时数据
query_xcai_city_history(
    cities=["广州市"],
    data_type="hour",
    start_time="2025-03-01 00:00:00",
    end_time="2025-03-31 23:00:00"
)

# 查询深圳、东莞近7天日数据
query_xcai_city_history(
    cities=["深圳市", "东莞市"],
    data_type="day",
    start_time="2025-03-22 00:00:00",
    end_time="2025-03-29 00:00:00"
)

# 查询北京2024年全年日数据
query_xcai_city_history(
    cities=["北京市"],
    data_type="day",
    start_time="2024-01-01 00:00:00",
    end_time="2024-12-31 00:00:00"
)
```

## 返回格式（UDF v2.0）

```python
{
    "status": "success",
    "success": True,
    "data": [...],  # 前24条标准化记录
    "metadata": {
        "tool_name": "query_xcai_city_history",
        "data_id": "air_quality_unified:xxx",  # 下游工具通过此ID获取完整数据
        "total_records": 744,
        "returned_records": 24,
        "cities": ["广州市"],
        "data_type": "hour",
        "table": "CityAQIPublishHistory",
        "time_range": "2025-03-01 00:00:00 to 2025-03-31 23:00:00",
        "schema_version": "v2.0",
        "source": "xcai_sql_server",
        "field_mapping_applied": True
    },
    "summary": "成功查询 广州市 的hour数据共 744 条，已保存为 air_quality_unified:xxx"
}
```

## 数据标准化

工具会自动将原始字段映射为标准字段：

| 原始字段（小时表） | 标准字段 |
|------------------|---------|
| TimePoint | timestamp |
| Area | city |
| CityCode | city_code |
| PM2_5 | measurements.pm2_5 |
| PM10 | measurements.pm10 |
| O3 | measurements.o3 |
| NO2 | measurements.no2 |
| SO2 | measurements.so2 |
| CO | measurements.co |
| AQI | measurements.aqi |
| PrimaryPollutant | primary_pollutant |
| Quality | air_quality_level |

## 配置

数据库连接配置在 `config/settings.py`：

```python
sqlserver_host = "180.184.30.94"
sqlserver_port = 1433
sqlserver_database = "XcAiDb"
sqlserver_user = "sa"
sqlserver_password = "#Ph981,6J2bOkWYT7p?5slH$I~g_0itR"
```
