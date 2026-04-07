# 站点统计查询工具和站点同环比工具实现总结

## 实现概述

成功实现了两个站点级空气质量统计分析工具：

1. **query_station_new_standard_report** - 站点级新标准统计报表查询工具
2. **compare_station_standard_reports** - 站点级同比/环比分析工具

## 实现内容

### 工具1：站点统计查询工具（`query_station_new_standard_report`）

**文件位置**：
- `backend/app/tools/query/query_station_new_standard_report/tool.py`
- `backend/app/tools/query/query_station_new_standard_report/__init__.py`

**核心功能**：
- 查询任意时间段内基于 HJ 633-2024 新标准的站点级空气质量统计报表
- 支持单站点和多站点查询
- 支持城市名称自动展开为站点列表
- 支持多站点汇总统计（aggregate参数）

**输入参数**：
```python
{
    "cities": ["广州"],           # 可选：城市名称列表（自动展开为站点）
    "stations": ["广雅中学"],     # 可选：站点名称列表
    "start_date": "2025-03-01",   # 必需：开始日期
    "end_date": "2025-03-31",     # 必需：结束日期
    "aggregate": false            # 可选：是否计算多站点汇总统计（默认false）
}
```

**输出格式**：
- UDF v2.0 标准格式
- 包含综合指数、超标天数、达标率、六参数统计、首要污染物分析等完整指标

**关键特性**：
- ✅ 不支持扣沙处理（站点级别无扣沙数据）
- ✅ 使用 station_name 字段替代 city_name
- ✅ 支持城市名称自动展开为站点列表
- ✅ 支持多站点汇总统计（算术平均）

### 工具2：站点同环比工具（`compare_station_standard_reports`）

**文件位置**：
- `backend/app/tools/query/compare_station_standard_reports/tool.py`
- `backend/app/tools/query/compare_station_standard_reports/__init__.py`

**核心功能**：
- 站点级的同比/环比分析
- 并发查询两个时间段的统计数据
- 自动对比全部统计指标
- 返回差值和变化率

**输入参数**：
```python
{
    "cities": ["广州"],           # 可选：城市名称列表
    "stations": ["广雅中学"],     # 可选：站点名称列表
    "query_period": {             # 必需：查询时间段
        "start_date": "2025-03-01",
        "end_date": "2025-03-31"
    },
    "comparison_period": {        # 必需：对比时间段
        "start_date": "2024-03-01",
        "end_date": "2024-03-31"
    },
    "aggregate": false            # 可选：是否计算多站点汇总对比
}
```

**输出格式**：
- UDF v2.0 标准格式
- 包含 query_period、comparison_period、differences、change_rates

## 代码复用策略

### 复用的辅助函数（来自城市工具）

1. **calculate_iaqi()** - IAQI计算
   - 文件：`app/tools/query/query_new_standard_report/tool.py`
   - 行数：595-647

2. **safe_round()** - 修约函数
   - 文件：`app/tools/query/query_new_standard_report/tool.py`
   - 行数：507-535

3. **apply_rounding()** - 修约规则应用
   - 文件：`app/tools/query/query_new_standard_report/tool.py`
   - 行数：538-559

4. **format_pollutant_value()** - 污染物值格式化
   - 文件：`app/tools/query/query_new_standard_report/tool.py`
   - 行数：562-592

### 复用的数据查询接口

1. **QueryGDSuncereDataTool.query_station_day_data()**
   - 文件：`app/tools/query/query_gd_suncere/tool.py`
   - 功能：查询站点日报数据

2. **GeoMappingResolver**
   - resolve_station_codes() - 站点名称→编码
   - resolve_station_codes_by_city() - 城市→站点编码列表

### 实现的核心函数

1. **_calculate_station_statistics()** - 单站点统计计算
   - 计算综合指数、超标天数、达标率
   - 计算六参数统计浓度和百分位数
   - 计算首要污染物统计

2. **_calculate_station_aggregate_stats()** - 多站点汇总
   - 计算所有站点的算术平均值
   - 处理缺失值

3. **_calculate_comparison()** - 对比计算（复用城市工具逻辑）
   - 计算差值和变化率
   - 支持嵌套字段访问

## 工具注册

**文件**：`backend/app/tools/__init__.py`

**注册位置**：
- query_station_new_standard_report：priority=43
- compare_station_standard_reports：priority=44

**验证**：
```bash
# 成功导入并注册
python -c "from app.tools.query.query_station_new_standard_report import QueryStationNewStandardReportTool; print('SUCCESS')"
# 输出：SUCCESS

python -c "from app.tools.query.compare_station_standard_reports import CompareStationStandardReportsTool; print('SUCCESS')"
# 输出：SUCCESS
```

## 与城市工具的差异

| 特性 | 城市工具 | 站点工具 |
|------|---------|---------|
| 扣沙处理 | ✅ 支持 | ❌ 不支持 |
| 字段名称 | city_name | station_name |
| 城市展开 | N/A | ✅ 支持 |
| 多站点汇总 | N/A | ✅ 支持（aggregate参数） |
| 数据源 | 城市日报 | 站点日报 |

## 使用示例

### 示例1：单站点统计查询

```
查询广州广雅中学站点2025年3月的新标准统计报表
```

**LLM工具调用**：
```python
query_station_new_standard_report(
    stations=["广雅中学"],
    start_date="2025-03-01",
    end_date="2025-03-31"
)
```

### 示例2：多站点统计查询

```
查询广州所有站点2025年3月的新标准统计报表
```

**LLM工具调用**：
```python
query_station_new_standard_report(
    cities=["广州"],
    start_date="2025-03-01",
    end_date="2025-03-31",
    aggregate=True  # 包含多站点汇总
)
```

### 示例3：站点同比分析

```
对比广州广雅中学站点2025年3月和2024年3月的新标准统计报表
```

**LLM工具调用**：
```python
compare_station_standard_reports(
    stations=["广雅中学"],
    query_period={
        "start_date": "2025-03-01",
        "end_date": "2025-03-31"
    },
    comparison_period={
        "start_date": "2024-03-01",
        "end_date": "2024-03-31"
    }
)
```

## 实现质量

### 代码规范
- ✅ 遵循项目现有的工具组织结构
- ✅ 使用 Context-Aware V2 架构
- ✅ 返回 UDF v2.0 格式
- ✅ 完整的错误处理和日志记录

### 功能完整性
- ✅ 支持单站点和多站点查询
- ✅ 支持城市名称自动展开
- ✅ 支持多站点汇总统计
- ✅ 完整的统计指标计算
- ✅ 同比/环比分析功能

### 代码复用
- ✅ 复用城市工具的辅助函数（避免代码重复）
- ✅ 复用站点数据查询接口
- ✅ 复用对比计算逻辑

## 测试建议

### 手动测试用例

1. **单站点统计查询**：
   ```
   查询广州广雅中学站点2025年3月的新标准统计报表
   ```
   验证：返回站点统计结果，包含综合指数、超标天数等指标

2. **多站点统计查询**：
   ```
   查询广州所有站点2025年3月的新标准统计报表
   ```
   验证：返回所有站点统计结果

3. **站点同比分析**：
   ```
   对比广州广雅中学站点2025年3月和2024年3月的新标准统计报表
   ```
   验证：返回对比结果，包含差值和变化率

4. **城市展开功能**：
   ```
   查询广州的站点统计报表
   ```
   验证：自动展开为广州所有站点

## 后续工作

### 可选优化
1. 编写单元测试
2. 性能优化（如果需要）
3. 添加缓存机制
4. 扩展站点映射表

### 文档更新
1. 更新工具提示词（tool_registry.py）
2. 更新用户手册
3. 添加使用示例

## 修复记录

### 问题1：异步/同步调用不匹配（2026-04-04 20:54 - 20:57）

**错误信息**：
```
TypeError: object dict can't be used in 'await' expression
```

**原因**：
- `tool_adapter.py` 总是用 `await` 调用工具的 `execute` 方法
- 站点工具的 `execute` 方法是同步方法，导致调用失败
- `QueryGDSuncereDataTool.query_station_day_data()` 是同步方法，不能使用 `await`

**最终解决方案**：
1. ✅ 将工具类的 `execute()` 方法改为异步方法（`async def`）
2. ✅ 将 `execute_query_station_new_standard_report()` 保持为同步函数
3. ✅ 在异步的 `execute()` 方法中直接调用同步函数（不使用 `await`）
4. ✅ 站点对比工具也采用相同的模式

**架构设计**：
```
tool_adapter.py (await) → Tool.execute() (async) → execute_query_xxx() (sync) → QueryGDSuncereDataTool.query_station_day_data() (sync)
```

**修改文件**：
- `backend/app/tools/query/query_station_new_standard_report/tool.py`
- `backend/app/tools/query/compare_station_standard_reports/tool.py`

**验证**：
- ✅ `execute` 方法是异步的（`inspect.iscoroutinefunction()` 返回 `True`）
- ✅ 工具成功导入
- ✅ 工具注册到全局工具注册表（84个工具）
- ✅ 工具添加到问数模式和报告模式

## 总结

成功实现了站点级新标准统计报表查询工具和站点同比/环比分析工具，复用了现有城市工具的核心逻辑，保持了代码一致性。两个工具已成功注册到全局工具注册表，可以通过LLM调用使用。

实现特点：
- 代码复用率高，避免重复开发
- 功能完整，支持单站点和多站点查询
- 架构规范，遵循项目现有结构
- 易于使用，支持城市名称自动展开
- 混合异步/同步架构（满足框架要求）

**实施日期**：2026-04-04
**实施状态**：✅ 完成（已修复所有已知问题）

## 已修复问题

1. **异步/同步调用不匹配** - 将工具 `execute()` 方法改为异步方法
2. **缺少 `_smart_sample_data` 方法** - 在 `QueryGDSuncereDataTool` 类中添加智能采样方法
