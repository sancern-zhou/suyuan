# 广东省 Suncere API 快速集成指南

## 概述

基于 Vanna 项目实现的广东省 Suncere API 客户端，提供 token 认证、自动刷新和多种数据查询功能。

## 文件清单

### 核心文件

1. **API 客户端**: `backend/app/services/gd_suncere_api_client.py`
   - Token 认证和自动刷新
   - HTTP 请求封装
   - 错误处理和重试

2. **查询工具**: `backend/app/tools/query/query_gd_suncere/tool.py`
   - 城市日报数据查询
   - 站点小时数据查询
   - 区域对比数据查询

3. **配置文件**: `backend/config/gd_suncere_api_config.yaml`
   - API 连接配置
   - 城市代码映射
   - 查询参数配置

### 文档和测试

4. **使用指南**: `docs/api/GD_SUNCEre_API_GUIDE.md`
5. **测试脚本**: `backend/tests/test_gd_suncere_api.py`

## 快速开始

### 1. 测试 API 连接

```bash
cd backend
python tests/test_gd_suncere_api.py
```

预期输出：
```
[PASS] Token 认证
[PASS] 城市日报查询
[PASS] 站点小时查询
[PASS] 区域对比查询
```

### 2. 在 Expert Plan Generator 中集成

修改 `backend/app/agent/core/expert_plan_generator.py`:

```python
def generate_regional_city_comparison_params(self, target, pollutants, start_time, end_time):
    """生成区域对比查询参数"""
    from app.tools.query.query_gd_suncere import QueryGDSuncereDataTool

    # 获取周边城市
    target_city = self._extract_city(target)
    nearby_cities = ["广州", "深圳", "佛山", "东莞"]  # 可配置

    return {
        "cities": [target_city] + nearby_cities,
        "start_time": start_time,
        "end_time": end_time,
        "query_type": "regional_comparison"
    }
```

### 3. 在 Component Executor 中使用

修改 `backend/app/agent/experts/component_executor.py`:

```python
async def execute_regional_comparison_analysis(self, task, start_time, end_time):
    """执行区域对比分析"""
    from app.tools.query.query_gd_suncere import execute_query_gd_suncere_regional_comparison

    result = execute_query_gd_suncere_regional_comparison(
        target_city="韶关",
        nearby_cities=["广州", "深圳", "佛山", "东莞"],
        start_time=start_time,
        end_time=end_time,
        context=self.context
    )

    if result.get("success"):
        # 数据自动包含 measurements 字段
        # 可以直接用于时序对比分析和可视化
        return result
    else:
        raise Exception(f"查询失败: {result.get('error')}")
```

## 关键特性

### 1. Token 自动管理

```python
# Token 自动缓存 30 分钟
api_client = get_gd_suncere_api_client()
token = api_client.get_token()  # 自动刷新，无需手动管理
```

### 2. 数据自动标准化

```python
# API 数据自动转换为 UDF v2.0 格式
result = execute_query_gd_suncere_station_hour(...)

# 结果包含 measurements 字段
{
    "station_name": "广雅中学",
    "measurements": {
        "PM2_5": 35.2,  # ✅ 标准字段名
        "PM10": 58.7,
        ...
    }
}
```

### 3. 多城市批量查询

```python
# 一次查询多个城市
result = execute_query_gd_suncere_station_hour(
    cities=["韶关", "广州", "深圳", "佛山", "东莞"],
    start_time="2024-12-01 00:00:00",
    end_time="2024-12-01 23:59:59",
    context=context
)

# 返回所有城市的合并数据
total_records = result['metadata']['total_records']
```

### 4. 错误自动重试

```python
# Token 过期自动刷新
# 网络超时自动重试
# 无需手动处理
```

## 与现有工具的对比

| 特性 | 现有工具 (get_guangdong_regular_stations) | 新工具 (query_gd_suncere) |
|-----|----------------------------------------|---------------------------|
| 数据源 | 9091 端口 (UQP 查询接口) | 官方 Suncere API |
| 认证方式 | 无 | Token + 自动刷新 |
| 数据格式 | 自然语言解析 | 结构化参数 |
| 数据质量 | 可能返回 `'—'` 缺失值 | 经过质量检查 |
| 查询方式 | 单一 question 参数 | 多种专用接口 |
| 标准化 | 需要手动处理 | 自动 UDF v2.0 |
| 错误处理 | 基础 | 完善的重试机制 |

## 推荐使用场景

### 使用现有工具 (get_guangdong_regular_stations)

- ✅ 快速原型验证
- ✅ 灵活的自然语言查询
- ✅ 不需要认证的场景

### 使用新工具 (query_gd_suncere)

- ✅ 生产环境部署
- ✅ 需要可靠数据质量
- ✅ 区域对比分析
- ✅ 大批量数据查询
- ✅ 需要标准化格式

## 迁移建议

### 阶段1: 并行运行

```python
# 同时使用两个工具，对比结果
old_result = get_guangdong_regular_stations(...)
new_result = execute_query_gd_suncere_station_hour(...)

# 验证数据一致性
assert old_result['total_records'] == new_result['total_records']
```

### 阶段2: 逐步切换

```python
# 优先使用新工具，失败时回退到旧工具
try:
    result = execute_query_gd_suncere_station_hour(...)
except Exception as e:
    logger.warning("suncere_api_failed", error=e)
    result = get_guangdong_regular_stations(...)
```

### 阶段3: 完全切换

```python
# 在 Expert Plan Generator 中直接使用新工具
def generate_plan(task):
    return {
        "tool": "query_gd_suncere_regional_comparison",
        "params": {...}
    }
```

## 监控和日志

### 关键日志

```python
# Token 管理
gd_suncere_api_client_initialized
token_refreshed_success

# 查询执行
query_gd_suncere_station_hour_start
station_hour_data_extracted

# 数据保存
gd_suncere_data_saved
gd_suncere_station_hour_saved
```

### 性能指标

- Token 获取: ~1 秒（首次），后续使用缓存
- 城市日报查询: ~2-5 秒
- 站点小时查询: ~5-10 秒
- 区域对比查询: ~10-20 秒

## 故障排查

### 常见问题

**1. Token 获取失败**
```
检查: 网络连接、用户名密码
解决: 确认 API 服务可用
```

**2. 查询返回空数据**
```
检查: 时间范围、城市代码
解决: 使用有数据的时间范围
```

**3. 数据不包含 measurements**
```
检查: 标准化器是否工作
解决: 查看 UDF v2.0 转换日志
```

## 后续优化

1. **缓存策略**: 缓存常用查询结果
2. **异步查询**: 支持异步批量查询
3. **数据预取**: 预先加载常用时间段数据
4. **监控告警**: API 性能和可用性监控

## 总结

广东省 Suncere API 提供了：
- ✅ 可靠的数据质量
- ✅ 完善的认证机制
- ✅ 自动数据标准化
- ✅ 多种查询方式
- ✅ 良好的错误处理

建议在生产环境中优先使用，确保数据查询的稳定性和可靠性。
