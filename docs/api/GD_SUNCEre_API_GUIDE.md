# 广东省 Suncere API 使用指南

## 概述

广东省 Suncere API 是官方提供的空气质量数据查询接口，支持 token 认证和多种查询方式。

## API 认证

### Token 获取

```python
from app.services.gd_suncere_api_client import get_gd_suncere_api_client

# 获取客户端实例
api_client = get_gd_suncere_api_client()

# 获取访问令牌（自动缓存30分钟）
token = api_client.get_token()
```

### 认证机制

1. **Basic Auth**: 使用用户名和密码获取 token
2. **Bearer Token**: 后续请求使用 token 认证
3. **自动刷新**: Token 过期后自动重新获取

## 数据查询接口

### 1. 城市日报数据查询

```python
from app.tools.query.query_gd_suncere import execute_query_gd_suncere_city_day
from app.agent.context.execution_context import ExecutionContext

# 创建上下文
context = ExecutionContext(...)

# 查询广州、深圳的日报数据
result = execute_query_gd_suncere_city_day(
    cities=["广州", "深圳"],
    start_date="2024-12-01",
    end_date="2024-12-31",
    context=context
)

# 返回格式
{
    "status": "success",
    "success": True,
    "data": [...],  # 标准化后的数据记录
    "metadata": {
        "tool_name": "query_gd_suncere_city_day",
        "data_id": "air_quality_unified:v1:abc123",
        "total_records": 62,
        "cities": ["广州", "深圳"]
    }
}
```

### 2. 站点小时数据查询（推荐用于时序对比）

```python
from app.tools.query.query_gd_suncere import execute_query_gd_suncere_station_hour

result = execute_query_gd_suncere_station_hour(
    cities=["韶关", "广州", "深圳", "佛山", "东莞"],
    start_time="2024-12-01 00:00:00",
    end_time="2024-12-01 23:59:59",
    context=context
)
```

### 3. 区域对比数据查询（自动用于区域时序对比）

```python
from app.tools.query.query_gd_suncere import execute_query_gd_suncere_regional_comparison

result = execute_query_gd_suncere_regional_comparison(
    target_city="韶关",
    nearby_cities=["广州", "深圳", "佛山", "东莞"],
    start_time="2024-12-01 00:00:00",
    end_time="2024-12-01 23:59:59",
    context=context
)
```

## 数据格式

### API 原始响应格式

```json
{
    "status": "success",
    "success": true,
    "data": [
        {
            "stationName": "广雅中学",
            "stationCode": "440100051",
            "cityName": "广州市",
            "districtName": "荔湾区",
            "latitude": 23.1422,
            "longitude": 113.2347,
            "timestamp": "2024-12-01 00:00:00",
            "PM2.5": 35.2,
            "PM10": 58.7,
            "SO2": 8.3,
            "NO2": 45.6,
            "O3": 89.2,
            "CO": 0.8,
            "AQI": 68
        }
    ]
}
```

### 标准化后的数据格式（UDF v2.0）

```json
{
    "station_name": "广雅中学",
    "station_code": "440100051",
    "city": "广州市",
    "timestamp": "2024-12-01 00:00:00",
    "measurements": {
        "PM2_5": 35.2,
        "PM10": 58.7,
        "SO2": 45.6,
        "NO2": 45.6,
        "O3": 89.2,
        "CO": 0.8
    },
    "metadata": {
        "schema_version": "v2.0",
        "field_mapping_applied": true
    }
}
```

## 城市代码映射

| 城市名称 | 城市代码 |
|---------|---------|
| 广州 | 440100 |
| 深圳 | 440300 |
| 珠海 | 440400 |
| 汕头 | 440500 |
| 佛山 | 440600 |
| 韶关 | 440200 |
| 东莞 | 441900 |
| 中山 | 442000 |
| ... | ... |

完整映射见 `CITY_CODE_MAP` 常量。

## 污染物代码

支持的标准污染物代码：
- `PM2.5`: 细颗粒物
- `PM10`: 可吸入颗粒物
- `SO2`: 二氧化硫
- `NO2`: 二氧化氮
- `O3`: 臭氧
- `CO`: 一氧化碳

## 错误处理

### 常见错误

1. **Token 过期 (401)**
   - 自动刷新 token 并重试
   - 无需手动处理

2. **城市代码不存在**
   - 返回警告并跳过该城市
   - 继续查询其他城市

3. **无数据**
   - 返回空结果
   - 检查时间范围是否正确

4. **网络超时**
   - 默认超时 30 秒
   - 可配置超时时间

### 错误响应格式

```json
{
    "status": "failed",
    "success": false,
    "error": "错误信息",
    "data": null
}
```

## 集成到 ReAct Agent

### 在 Expert Plan Generator 中使用

```python
# expert_plan_generator.py

def generate_regional_comparison_plan(target_city, pollutants):
    """生成区域对比分析计划"""

    # 使用 Suncere API 查询周边城市数据
    nearby_cities = ["广州", "深圳", "佛山", "东莞"]

    plan = {
        "tool": "query_gd_suncere_regional_comparison",
        "params": {
            "target_city": target_city,
            "nearby_cities": nearby_cities,
            "start_time": "...",
            "end_time": "..."
        },
        "purpose": "获取目标城市与周边城市的污染物时序数据"
    }

    return plan
```

### 在 Component Executor 中使用

```python
# component_executor.py

async def execute_regional_analysis(self, task_description):
    """执行区域对比分析"""

    # 自动查询周边城市数据
    result = execute_query_gd_suncere_regional_comparison(
        target_city="韶关",
        nearby_cities=["广州", "深圳", "佛山", "东莞"],
        start_time=start_time,
        end_time=end_time,
        context=self.context
    )

    # 数据自动包含 measurements 字段
    # LLM 可以直接进行时序对比分析
    return result
```

## 性能优化

1. **Token 缓存**: 默认缓存 30 分钟，减少认证请求
2. **批量查询**: 支持一次查询多个城市
3. **数据标准化**: 自动转换为 UDF v2.0 格式
4. **增量查询**: 支持分页获取大量数据

## 配置文件

配置文件位置: `backend/config/gd_suncere_api_config.yaml`

可配置项：
- API 基础 URL
- 用户名和密码
- Token 缓存时间
- 查询超时时间
- 默认分页大小

## 测试

```bash
# 运行测试脚本
cd backend
python tests/test_gd_suncere_api.py
```

## 监控和日志

关键日志：
- `gd_suncere_api_client_initialized`: 客户端初始化
- `token_refreshed_success`: Token 刷新成功
- `query_gd_suncere_station_hour_start`: 开始查询
- `gd_suncere_data_saved`: 数据保存成功

## 注意事项

1. **时间范围**: 查询时间不宜过长，建议单次查询不超过 7 天
2. **数据可用性**: 确认 API 是否有该时间段的数据
3. **并发限制**: 避免同时发起大量请求
4. **错误重试**: 实现了自动 token 刷新和重试机制
5. **数据质量**: API 返回的数据已经过质量检查
