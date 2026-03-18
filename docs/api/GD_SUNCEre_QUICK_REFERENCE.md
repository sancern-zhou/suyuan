# 广东省 Suncere API 快速参考

## 概述

广东省 Suncere API 数据查询工具，提供基于官方 API 的空气质量监测数据查询功能。

**已注册工具（可被 Agent 调用）：**
- `query_gd_suncere_city_hour` - 城市小时数据查询（priority: 32）
- `query_gd_suncere_regional_comparison` - 区域对比数据查询（priority: 33）

## 一分钟上手

### 导入

```python
from app.tools.query.query_gd_suncere import (
    execute_query_gd_suncere_station_hour,
    execute_query_gd_suncere_regional_comparison
)
from app.agent.context.execution_context import ExecutionContext
```

### 查询站点小时数据

```python
result = execute_query_gd_suncere_station_hour(
    cities=["广州", "深圳"],
    start_time="2024-12-01 00:00:00",
    end_time="2024-12-01 23:59:59",
    context=context
)
```

### 查询区域对比数据

```python
result = execute_query_gd_suncere_regional_comparison(
    target_city="韶关",
    nearby_cities=["广州", "深圳", "佛山", "东莞"],
    start_time="2024-12-01 00:00:00",
    end_time="2024-12-01 23:59:59",
    context=context
)
```

## 返回格式

```json
{
  "status": "success",
  "success": true,
  "data": [
    {
      "station_name": "广雅中学",
      "timestamp": "2024-12-01 00:00:00",
      "measurements": {
        "PM2_5": 35.2,
        "PM10": 58.7,
        "SO2": 8.3
      }
    }
  ],
  "metadata": {
    "data_id": "air_quality_unified:v1:abc123",
    "total_records": 48
  }
}
```

## 城市代码速查

| 城市 | 代码 | 城市 | 代码 |
|-----|------|-----|------|
| 广州 | 440100 | 惠州 | 441300 |
| 深圳 | 440300 | 梅州 | 441400 |
| 珠海 | 440400 | 汕尾 | 441500 |
| 汕头 | 440500 | 河源 | 441600 |
| 佛山 | 440600 | 阳江 | 441700 |
| 韶关 | 440200 | 清远 | 441800 |
| 湛江 | 440800 | 东莞 | 441900 |
| 肇庆 | 441200 | 中山 | 442000 |
| 江门 | 440700 | 潮州 | 445100 |
| 茂名 | 440900 | 揭阳 | 445200 |
| 云浮 | 445300 |  |  |

## 污染物代码

- `PM2.5` - 细颗粒物
- `PM10` - 可吸入颗粒物
- `SO2` - 二氧化硫
- `NO2` - 二氧化氮
- `O3` - 臭氧
- `CO` - 一氧化碳

## DataSource 参数自动修正

工具会根据查询的结束时间自动判断 `DataSource` 参数（参考 Vanna 项目实现）：

- **结束时间距离当前日期在 3 天内（含）**：使用 `DataSource=0`（原始实况）
- **结束时间距离当前日期超过 3 天**：使用 `DataSource=1`（审核实况）

### 示例

```python
# 查询昨天的数据 - 自动使用 DataSource=0（原始实况）
result = execute_query_gd_suncere_station_hour(
    cities=["广州"],
    start_time="2026-02-02 00:00:00",
    end_time="2026-02-02 23:59:59",
    context=context
)

# 查询一周前的数据 - 自动使用 DataSource=1（审核实况）
result = execute_query_gd_suncere_station_hour(
    cities=["深圳"],
    start_time="2026-01-27 00:00:00",
    end_time="2026-01-27 23:59:59",
    context=context
)
```

### 手动计算 DataSource

```python
from app.tools.query.query_gd_suncere import QueryGDSuncereDataTool

data_source = QueryGDSuncereDataTool.calculate_data_source("2026-02-02 23:59:59")
# 返回: 0 (原始实况) 或 1 (审核实况)
```

## API 配置

```yaml
base_url: "http://113.108.142.147:20161"
username: "ScGuanLy"
password: "Suncere$0717"
token_cache: 30 分钟
```

## 测试

```bash
cd backend

# API 基础测试
python tests/test_gd_suncere_api.py

# 代码映射测试
python tests/test_gd_suncere_mapping.py

# DataSource 自动修正测试
python tests/test_gd_suncere_datasource.py

# 集成测试
python tests/test_gd_suncere_integration.py
```

## 常见问题

**Q: Token 过期怎么办？**
A: 自动刷新，无需处理

**Q: 查询返回空数据？**
A: 检查时间范围，使用历史数据

**Q: 如何查询多个城市？**
A: 直接传入城市列表，自动批量查询

**Q: 数据格式是什么？**
A: UDF v2.0 标准，包含 measurements 字段

**Q: DataSource 参数如何设置？**
A: 工具会根据查询的结束时间自动判断，无需手动设置。3天内用原始实况，否则用审核实况

## 文档链接

- 使用指南: `docs/api/GD_SUNCEre_API_GUIDE.md`
- 集成指南: `docs/implementation/GD_SUNCEre_INTEGRATION.md`
- 实现总结: `docs/implementation/GD_SUNCEre_IMPLEMENTATION_SUMMARY.md`
