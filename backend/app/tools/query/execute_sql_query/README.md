# execute_sql_query 工具

## 概述

`execute_sql_query` 是一个通用的SQL执行工具，允许Agent直接执行SQL查询语句访问SQL Server历史数据库。

**特点**：
- 支持任意复杂的SELECT查询
- 复用现有的安全验证机制（`SQLValidator`）
- 自动处理LIMIT限制
- 统一的错误处理和日志记录

## 使用场景

### 1. 直接执行SQL查询

当用户需要执行复杂的SQL查询时，可以使用此工具：

```
用户：查询广州站所有未完成的工单数量
Agent调用：execute_sql_query(sql="SELECT COUNT(*) as cnt FROM working_orders WHERE STATIONID = '1' AND DDWORKINGORDERSTATUS != N'Finish'")
```

### 2. 多表关联查询

```
用户：统计各城市钼转换效率低于95%的质控记录数量
Agent调用：execute_sql_query(sql="SELECT city, COUNT(*) as cnt FROM quality_control_records WHERE molybdenum_efficiency < 95 GROUP BY city")
```

### 3. 聚合统计

```
用户：按工单类型统计工单数量
Agent调用：execute_sql_query(sql="SELECT DDWORKINGORDERTYPE, COUNT(*) as cnt FROM working_orders GROUP BY DDWORKINGORDERTYPE")
```

## 安全机制

工具继承了`SQLValidator`的所有安全特性：

### 1. SQL验证
- 只允许SELECT查询
- 禁止危险操作（DROP/DELETE/INSERT/UPDATE等）
- 禁止SQL注释（防止SQL注入）
- 禁止多语句执行

### 2. 表名白名单
当前允许的表：
- `quality_control_records`: 质控例行检查记录
- `working_orders`: 运维工单记录
- 以及`SQLValidator`中定义的其他表

### 3. LIMIT限制
- 默认限制1000条
- 最大限制10000条
- 自动添加或调整LIMIT子句

## 可用数据表

### quality_control_records (质控记录)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 记录ID |
| province | nvarchar | 省份 |
| city | nvarchar | 城市 |
| operation_unit | nvarchar | 运维单位 |
| station | nvarchar | 站点名称 |
| start_time | datetime | 开始时间 |
| end_time | datetime | 结束时间 |
| task_group | nvarchar | 任务组 |
| qc_item | nvarchar | 质控项目 |
| qc_result | nvarchar | 质控结果 |
| response_value | float | 响应值 |
| target_value | float | 目标值 |
| error_value | float | 误差值 |
| molybdenum_efficiency | float | 钼转换效率 |
| warning_limit | float | 警告限 |
| control_limit | float | 控制限 |

### working_orders (运维工单)

| 字段 | 类型 | 说明 |
|------|------|------|
| WORKINGORDERID | - | 工单ID |
| STATIONID | - | 站点ID |
| DEVICEID | - | 设备ID |
| WORKINGORDERCODE | - | 工单编号 |
| CREATETIME | datetime | 创建时间 |
| UPDATETIME | datetime | 更新时间 |
| FINISHTIME | datetime | 完成时间 |
| DDORDERCREATETYPE | - | 工单创建类型 |
| DDWORKINGORDERTYPE | - | 工单类型 |
| DDURGENCYTYPE | - | 紧急程度 |
| DDWORKINGORDERSTATUS | - | 工单状态 |
| ORDERTITLE | - | 工单标题 |
| ORDERCONTENT | - | 工单内容 |
| CURRENTWORKFLOWSTATUS | - | 当前工作流状态 |
| CURRENTWORKFLOWPOINT | - | 当前工作流节点 |
| MAINTENANCETYPE | - | 维护周期 |
| PLANFINISHTIME | datetime | 计划完成时间 |
| TOTALOVERTIME | - | 总超时时间 |
| TOTALEXPENSE | - | 总费用 |

## 工具参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| sql | string | 是 | - | SQL查询语句 |
| limit | integer | 否 | 1000 | 返回记录数限制（最大10000） |

## 返回格式

```json
{
    "success": true,
    "data": [
        {
            "列名1": "值1",
            "列名2": "值2",
            ...
        }
    ],
    "summary": "查询到10条记录"
}
```

## 使用示例

### 示例1：查询未完成工单

```python
from app.tools.query.execute_sql_query.tool import ExecuteSQLQueryTool

tool = ExecuteSQLQueryTool()
result = await tool.execute(
    sql="SELECT * FROM working_orders WHERE DDWORKINGORDERSTATUS = N'Doing'"
)
print(result["summary"])  # 输出: "查询到5条记录"
```

### 示例2：统计质控结果

```python
result = await tool.execute(
    sql="SELECT qc_result, COUNT(*) as cnt FROM quality_control_records GROUP BY qc_result"
)
print(result["data"])
# 输出: [{'qc_result': '合格', 'cnt': 100}, {'qc_result': '超控制限', 'cnt': 5}]
```

### 示例3：带LIMIT的查询

```python
result = await tool.execute(
    sql="SELECT * FROM quality_control_records WHERE city = N'广州市'",
    limit=100
)
```

## 与现有工具的关系

| 工具 | 用途 | 推荐场景 |
|------|------|----------|
| `get_quality_control_records` | 专用质控记录查询 | 简单的质控记录查询 |
| `get_working_orders` | 专用工单查询 | 简单的工单查询 |
| `execute_sql_query` | 通用SQL执行 | 复杂查询、JOIN、聚合等 |

**选择建议**：
- 简单查询：使用专用工具（参数化、更安全）
- 复杂查询：使用`execute_sql_query`（更灵活）

## 错误处理

工具会捕获并返回所有错误：

```json
{
    "success": false,
    "data": [],
    "summary": "SQL验证失败: 包含危险关键词: DROP"
}
```

常见错误：
- SQL语法错误
- 表名不在白名单
- 包含危险关键词
- LIMIT超过最大值
- 数据库连接失败

## 文件位置

- 工具实现：`backend/app/tools/query/execute_sql_query/tool.py`
- 模块导出：`backend/app/tools/query/execute_sql_query/__init__.py`
- 工具注册：`backend/app/tools/__init__.py` (priority=47)
- 安全验证：`backend/app/utils/sql_validator.py`
