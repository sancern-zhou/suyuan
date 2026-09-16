# XcAiDb城市历史数据查询工具 - 实现总结

## 实现日期
2026-03-29

## 功能说明

查询全国城市历史空气质量数据（SQL Server XcAiDb数据库）

### 支持的数据表
- **小时数据表**：CityAQIPublishHistory（2017-01-01 至今）
- **日数据表**：CityDayAQIPublishHistory（2021-06-25 至今）

### 支持的功能
- 多城市查询
- 自定义时间范围
- 小时数据和日数据两种粒度
- 返回UDF v2.0标准格式
- 自动字段映射和标准化
- 数据存储并返回data_id

## 文件结构

```
backend/app/tools/query/query_xcai_city_history/
├── __init__.py           # 包导出
├── tool.py               # 主工具实现（QueryXcAiCityHistoryTool）
├── sql_client.py         # SQL Server客户端（SQLServerClient）
├── README.md             # 工具使用文档
└── IMPLEMENTATION_SUMMARY.md  # 本文件
```

## 工具参数

```json
{
  "name": "query_xcai_city_history",
  "parameters": {
    "cities": ["城市名称数组"],
    "data_type": "hour | day",
    "start_time": "YYYY-MM-DD HH:MM:SS",
    "end_time": "YYYY-MM-DD HH:MM:SS"
  }
}
```

## 核心特性

### 1. 参数化SQL查询
- 使用pyodbc参数化查询防止SQL注入
- 支持多城市批量查询（IN子句）
- 查询超时控制（30秒）

### 2. 字段映射
通过 `data_standardizer` 自动映射字段：
- TimePoint → timestamp
- Area → city
- CityCode → city_code
- PM2_5, PM10, O3, NO2, SO2, CO → measurements.*
- PrimaryPollutant → primary_pollutant
- Quality → air_quality_level

### 3. 数据标准化
- 使用 `get_data_standardizer().standardize()` 标准化
- 符合UDF v2.0标准
- 自动应用字段映射

### 4. 数据存储
- 使用 `context.data_manager.save_data()` 保存
- schema="air_quality_unified"
- 返回data_id供下游工具使用
- 返回前24条记录供LLM预览

## 返回格式

```python
{
    "status": "success",
    "success": True,
    "data": [...],  # 前24条标准化记录
    "metadata": {
        "tool_name": "query_xcai_city_history",
        "data_id": "air_quality_unified:xxx",
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
```

## 工具注册

- 注册位置：`backend/app/tools/__init__.py`
- 优先级：43
- 类别：ToolCategory.QUERY
- 需要Context：True

## 数据库配置

```python
# SQL Server XcAiDb Configuration
host: 180.184.30.94
port: 1433
database: XcAiDb
user: sa
password: #Ph981,6J2bOkWYT7p?5slH$I~g_0itR
```

## 测试状态

✓ 模块导入成功
✓ 工具实例创建成功
✓ Schema检查通过
✓ SQL客户端创建成功
✓ 工具已注册到全局注册表（priority=43）

## 依赖项

- pyodbc: SQL Server数据库连接
- app.utils.data_standardizer: 字段标准化
- app.agent.context.execution_context: 执行上下文
- app.tools.base.tool_interface: LLMTool基类

## 注意事项

1. 数据库连接需要网络访问180.184.30.94:1433
2. 密码包含特殊字符，连接字符串中需要用大括号包裹
3. 时间格式必须严格：YYYY-MM-DD HH:MM:SS
4. 城市名称必须与数据库中的Area字段匹配
5. 返回的data_id可用于下游分析工具获取完整数据

## 后续扩展

- [ ] 添加查询结果缓存
- [ ] 支持导出为CSV/Excel
- [ ] 添加数据质量检查
- [ ] 支持周/月/年聚合
- [ ] 优化大数据量查询性能
