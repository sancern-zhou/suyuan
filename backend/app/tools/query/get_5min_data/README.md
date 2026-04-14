# 5分钟数据查询工具

## 概述

`get_5min_data` 工具用于查询站点的5分钟污染物浓度和气象数据。

## 功能特性

- 查询站点5分钟污染物浓度数据（PM2.5、PM10、SO2、NO2、O3、CO等）
- 查询站点5分钟气象数据（风速、风向、温度、湿度、气压）
- 自动数据透视（长表 → 宽表转换）
- 返回 UDF v2.0 标准格式
- 支持站点名称和站点代码输入

## 数据来源

- **数据库**: air_quality_db (SQL Server)
- **表名格式**: `Air_5m_{年份}_{站点代码}_Src`
- **示例**: `Air_5m_2026_1001A_Src`

## 使用方法

### 基本查询

```python
# 查询万寿西宫站点2026年1月1日的5分钟数据
get_5min_data(
    station="万寿西宫",
    start_time="2026-01-01T00:00:00",
    end_time="2026-01-02T00:00:00"
)
```

### 查询特定污染物

```python
# 查询PM2.5、O3和风数据
get_5min_data(
    station="万寿西宫",
    start_time="2026-01-01T00:00:00",
    end_time="2026-01-02T00:00:00",
    pollutants=["PM2.5", "O3", "WS", "WD"]
)
```

## 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| station | string | 是 | 站点名称或站点代码（如"万寿西宫"或"1001A"） |
| start_time | string | 是 | 开始时间（ISO 8601格式） |
| end_time | string | 是 | 结束时间（ISO 8601格式） |
| pollutants | array | 否 | 污染物列表（默认查询所有） |

## 支持的污染物

### 污染物代码

| 代码 | 名称 | 说明 |
|------|------|------|
| 100 | PM2_5 | PM2.5 |
| 101 | PM10 | PM10 |
| 102 | SO2 | 二氧化硫 |
| 103 | NO2 | 二氧化氮 |
| 104 | O3 | 臭氧 |
| 105 | CO | 一氧化碳 |
| 106 | NO | 一氧化氮 |
| 107 | NOx | 氮氧化物 |

### 气象参数

| 代码 | 名称 | 单位 |
|------|------|------|
| 108 | WS | 风速 (m/s) |
| 109 | WD | 风向 (度) |
| 110 | PRESSURE | 气压 (hPa) |
| 111 | TEMP | 温度 (℃) |
| 112 | RH | 湿度 (%) |

## 返回格式

```python
{
    "status": "success",
    "success": True,
    "data": [
        {
            "timestamp": "2026-01-01 00:05:00",
            "station_code": "1001A",
            "PM2_5": 35.5,
            "PM10": 45.2,
            "SO2": 8.5,
            "NO2": 32.1,
            "O3": 56.8,
            "CO": 0.8,
            "WS": 2.3,
            "WD": 135,
            "TEMP": 25.0,
            "RH": 65.0,
            "PRESSURE": 1013.5
        },
        # ... 更多记录
    ],
    "metadata": {
        "schema_version": "v2.0",
        "field_mapping_applied": True,
        "generator": "get_5min_data",
        "scenario": "5min_pollutant_weather",
        "record_count": 288,
        "data_id": "air_quality_5min:xxx"
    },
    "summary": "查询到288条5分钟数据"
}
```

## 限制

1. **不支持跨年查询**: 时间段必须在单一年内，如需跨年数据请分段查询
2. **表必须存在**: 需要站点代码对应的5分钟数据表存在
3. **站点代码验证**: 使用 GeoMappingResolver 解析站点名称

## 图表模式集成

### 风玫瑰图生成流程

1. 查询5分钟风数据：
   ```python
   get_5min_data(
       station="万寿西宫",
       start_time="2026-01-01T00:00:00",
       end_time="2026-01-02T00:00:00",
       pollutants=["WS", "WD"]
   )
   ```

2. 加载数据：
   ```python
   read_data_registry(data_id, list_fields=true)
   ```

3. LLM 生成 Python 代码处理数据并生成 ECharts 配置

## 错误处理

| 错误 | 原因 | 解决方法 |
|------|------|----------|
| 未找到站点 | 站点名称或代码错误 | 使用正确的站点名称或代码 |
| 表不存在 | 年份或站点代码错误 | 检查表名格式和站点代码 |
| 跨年查询 | 时间范围跨年 | 分段查询不同年份的数据 |

## 相关文件

- 工具实现: `tool.py`
- 站点解析: `query_gd_suncere/tool.py` (GeoMappingResolver)
- 数据标准化: `utils/data_standardizer.py` (DataStandardizer)
- 上下文管理: `agent/context/execution_context.py` (ExecutionContext)
