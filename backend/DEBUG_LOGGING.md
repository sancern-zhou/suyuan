# 调试日志说明文档

## 概述

系统已添加详细的调试日志，帮助诊断超时和连接池问题。

## 新增日志事件

### 1. 数据库连接池监控

#### `db_connection_requested`
**级别**: DEBUG
**触发时机**: 每次请求数据库连接时
**字段**:
- `pool_status`: 连接池状态字符串
- `pool_size`: 当前连接池大小
- `checked_out`: 已签出的连接数
- `overflow`: 溢出连接数
- `queue_size`: 等待队列大小

**示例**:
```
db_connection_requested pool_status="Pool size: 20  Connections in pool: 15  Current Overflow: 3  Current Checked out connections: 5" pool_size=20 checked_out=5 overflow=3 queue_size=2
```

**诊断用途**:
- 如果 `checked_out` 接近 `pool_size + max_overflow`，说明连接池接近饱和
- 如果 `queue_size > 0`，说明有请求在等待连接

---

#### `db_connection_returned`
**级别**: DEBUG
**触发时机**: 连接归还到连接池时
**字段**:
- `pool_status`: 归还后的连接池状态

---

#### `db_session_error`
**级别**: ERROR
**触发时机**: 数据库会话发生错误
**字段**:
- `error`: 错误信息
- `error_type`: 错误类型
- `pool_status`: 错误时的连接池状态

**诊断用途**: 查看错误发生时的连接池状态

---

### 2. 工具执行监控

#### `tool_execution_start`
**级别**: INFO
**触发时机**: 工具开始执行前
**字段**:
- `tool`: 工具名称
- `index`: 工具索引
- `timeout`: 超时时间（秒）
- `attempt`: 当前尝试次数
- `max_retries`: 最大重试次数
- `has_upstream`: 是否有上游依赖
- `upstream_count`: 上游工具数量

**示例**:
```
tool_execution_start tool=get_weather_data index=0 timeout=120 attempt=1 max_retries=3 has_upstream=False upstream_count=0
```

---

#### `tool_timeout_detailed`
**级别**: ERROR
**触发时机**: 工具执行超时
**字段**:
- `tool`: 工具名称
- `attempt`: 尝试次数
- `timeout_seconds`: 超时阈值
- `error`: 错误信息
- `error_type`: 错误类型
- `bound_params`: 绑定的参数
- `upstream_tools`: 上游工具列表
- `diagnostic_hint`: 诊断提示

**示例**:
```
tool_timeout_detailed tool=get_weather_data attempt=1 timeout_seconds=120 error="TimeoutError" bound_params={'lat': 22.5431, 'lon': 114.0579, 'start_time': '2026-02-01 00:00:00', 'end_time': '2026-02-01 23:59:59'} upstream_tools=[] diagnostic_hint="工具执行超时。可能原因：1) 数据库连接池满 2) 外部API响应慢 3) 数据量过大 4) 网络延迟"
```

**诊断用途**:
- 查看超时时的参数配置
- 了解是否有上游依赖导致延迟
- 根据 `diagnostic_hint` 排查问题

---

### 3. 气象数据查询监控

#### `weather_query_start`
**级别**: INFO
**触发时机**: 开始查询气象数据
**字段**:
- `lat`: 纬度
- `lon`: 经度
- `start_time`: 开始时间
- `end_time`: 结束时间

---

#### `weather_query_success`
**级别**: INFO
**触发时机**: 气象数据查询成功
**字段**:
- `lat`: 纬度
- `lon`: 经度
- `record_count`: 返回记录数
- `query_duration_seconds`: 查询耗时（秒）

**示例**:
```
weather_query_success lat=22.5 lon=114.0 record_count=24 query_duration_seconds=0.92
```

**诊断用途**:
- 如果 `query_duration_seconds` 接近超时阈值，说明查询慢
- 如果 `record_count=0`，说明数据库中无数据

---

#### `weather_query_failed`
**级别**: ERROR
**触发时机**: 气象数据查询失败
**字段**:
- `lat`: 纬度
- `lon`: 经度
- `error`: 错误信息
- `error_type`: 错误类型
- `query_duration_seconds`: 查询耗时

**诊断用途**: 查看查询失败的具体原因

---

## 常见问题诊断

### 问题1: 工具执行超时

**日志特征**:
```
tool_timeout_detailed tool=get_weather_data timeout_seconds=120
```

**排查步骤**:
1. 查看 `db_connection_requested` 日志，检查连接池状态
   - 如果 `checked_out` 接近最大值（50），说明连接池饱和
   - 如果 `queue_size > 0`，说明有请求在等待

2. 查看 `weather_query_start` 和 `weather_query_success` 之间的时间差
   - 如果超过60秒，说明数据库查询慢

3. 查看 `upstream_tools` 字段
   - 如果有多个上游工具，可能是并发查询导致

**解决方案**:
- 增加连接池大小（已修改为 pool_size=20, max_overflow=30）
- 增加工具超时时间（已修改为 120-180秒）
- 优化数据库查询（添加索引）

---

### 问题2: 数据库连接池耗尽

**日志特征**:
```
db_connection_requested pool_size=20 checked_out=18 overflow=30 queue_size=5
db_session_error error="QueuePool limit of size 20 overflow 30 reached"
```

**排查步骤**:
1. 统计同时执行的工具数量
2. 检查是否有连接泄漏（连接未正确释放）
3. 查看 `db_connection_returned` 日志，确认连接正常归还

**解决方案**:
- 增加 `pool_size` 和 `max_overflow`
- 增加 `pool_timeout`
- 检查代码中是否有未关闭的连接

---

### 问题3: 外部API响应慢

**日志特征**:
```
tool_execution_start tool=get_guangdong_regular_stations timeout=180
tool_timeout_detailed tool=get_guangdong_regular_stations timeout_seconds=180
```

**排查步骤**:
1. 查看 `http_request_detail` 日志（如果有）
2. 检查网络连接
3. 测试外部API响应时间

**解决方案**:
- 增加工具超时时间
- 添加缓存机制
- 使用重试策略

---

## 启用调试日志

### 方法1: 环境变量
```bash
export LOG_LEVEL=DEBUG
```

### 方法2: 修改配置文件
编辑 `backend/config/settings.py`:
```python
LOG_LEVEL = "DEBUG"
```

### 方法3: 运行时修改
```python
import structlog
import logging

logging.basicConfig(level=logging.DEBUG)
```

---

## 日志过滤

### 只查看超时错误
```bash
grep "tool_timeout_detailed" logs/app.log
```

### 只查看连接池状态
```bash
grep "db_connection_requested\|db_connection_returned" logs/app.log
```

### 只查看气象数据查询
```bash
grep "weather_query" logs/app.log
```

---

## 性能监控指标

### 关键指标

| 指标 | 正常范围 | 警告阈值 | 说明 |
|------|----------|----------|------|
| `query_duration_seconds` | < 5秒 | > 30秒 | 数据库查询耗时 |
| `checked_out` | < 15 | > 40 | 已签出连接数 |
| `queue_size` | 0 | > 5 | 等待队列大小 |
| `tool_execution_time` | < 60秒 | > 100秒 | 工具执行耗时 |

---

## 修改记录

| 日期 | 修改内容 | 文件 |
|------|----------|------|
| 2026-02-02 | 添加连接池监控日志 | `database.py` |
| 2026-02-02 | 添加工具超时详细日志 | `tool_dependency_graph.py` |
| 2026-02-02 | 添加气象查询监控日志 | `weather_repo.py` |
| 2026-02-02 | 增加连接池配置 | `database.py` |
| 2026-02-02 | 增加工具超时配置 | `tool_dependencies.py` |
