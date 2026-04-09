# complex_query_planner 工具 Schema 完整性分析报告

生成时间：2026-04-04

## 1. 分析概述

`complex_query_planner` 工具负责为复杂查询生成执行计划，它涉及 8 个查询工具。本次检查了这些工具的 schema 描述完整性，特别关注返回字段说明。

## 2. 涉及的查询工具列表

### 2.1 新标准相关工具（4个）
1. `query_gd_suncere_city_day_new` - 城市日数据（新标准 HJ 633-2026）
2. `query_new_standard_report` - 新标准统计报表
3. `query_old_standard_report` - 旧标准统计报表
4. `query_standard_comparison` - 新旧标准对比

### 2.2 对比分析工具（1个）
5. `compare_standard_reports` - 新标准报表对比分析

### 2.3 历史数据工具（2个）
6. `query_xcai_city_history` - XcAiDb 城市历史数据
7. `query_gd_suncere_city_day` - 城市日数据（旧标准）

### 2.4 通用工具（1个）
8. `execute_sql_query` - 通用SQL执行

## 3. 实际工具实现的返回字段描述情况

### 3.1 ✅ query_new_standard_report (完整描述)

**返回数据结构**：
```python
{
    "result": {
        # 单城市查询时直接返回城市统计数据
        # 多城市查询时返回各城市统计数据 + province_wide

        # 综合指标
        "composite_index": float,      # 综合指数
        "exceed_days": int,            # 超标天数
        "valid_days": int,             # 有效天数
        "exceed_rate": float,          # 超标率（%）
        "compliance_rate": float,      # 达标率（%）
        "total_days": int,             # 总天数

        # 六参数统计
        "SO2": float, "SO2_P98": float,
        "NO2": float, "NO2_P98": float,
        "PM10": float, "PM10_P95": float,
        "PM2_5": float, "PM2_5_P95": float,
        "CO_P95": float, "O3_8h_P90": float,

        # 加权单项质量指数
        "single_indexes": {
            "SO2": float, "NO2": float, "PM10": float,
            "CO": float, "PM2_5": float, "O3_8h": float
        },

        # 首要污染物统计
        "primary_pollutant_days": {
            "PM2_5": int, "PM10": int, "SO2": int,
            "NO2": int, "CO": int, "O3_8h": int
        },
        "primary_pollutant_ratio": {
            "PM2_5": float, "PM10": float, "SO2": float,
            "NO2": float, "CO": float, "O3_8h": float
        },
        "total_primary_days": int,
        "PM2_5_primary_dates": List[str],  # PM2.5作为首要污染物的日期列表

        # 超标统计
        "exceed_days_by_pollutant": {
            "PM2_5": int, "PM10": int, "SO2": int,
            "NO2": int, "CO": int, "O3_8h": int
        },
        "exceed_rate_by_pollutant": {
            "PM2_5": float, "PM10": float, "SO2": float,
            "NO2": float, "CO": float, "O3_8h": float
        },
        "primary_pollutant_exceed_days": {
            "PM2_5": int, "PM10": int, "SO2": int,
            "NO2": int, "CO": int, "O3_8h": int
        },

        # 全省汇总（多城市查询时）
        "province_wide": {
            # 结构同上，包含 _indicator_types 说明各指标是"平均值"还是"累计值"
            "_indicator_types": {...}
        }
    },
    "data_id": "air_quality_unified:v1:xxx"  # 完整日报数据（不含统计指标）
}
```

**说明文档位置**：`backend/app/tools/query/query_new_standard_report/tool.py:1895-1920`

### 3.2 ✅ compare_standard_reports (完整描述)

**返回数据结构**：
```python
{
    "result": {
        "<城市名>": {
            "query_period": {...},        # 查询时间段统计数据
            "comparison_period": {...},   # 对比时间段统计数据
            "differences": {              # 差值（query - comparison）
                "composite_index": float,
                "exceed_days": int,
                # ... 所有对比指标
            },
            "change_rates": {             # 变化率（%）
                "composite_index": float,
                "exceed_days": float,
                # ... 所有对比指标
            }
        },
        "province_wide": {                # 全省汇总对比（多城市时）
            # 结构同上
        }
    },
    "metadata": {
        "source_data_ids": [...]  # 两个时间段的原始数据ID
    }
}
```

**对比指标列表**（34个）：
- 综合指标：composite_index, exceed_days, exceed_rate, compliance_rate, total_days, valid_days
- 六参数统计：SO2, SO2_P98, NO2, NO2_P98, PM10, PM10_P95, PM2_5, PM2_5_P95, CO_P95, O3_8h_P90
- 单项质量指数：single_indexes.*
- 首要污染物天数：primary_pollutant_days.*, total_primary_days
- 超标统计：exceed_days_by_pollutant.*
- 首要污染物超标天：primary_pollutant_exceed_days.*

**说明文档位置**：`backend/app/tools/query/compare_standard_reports/tool.py:98-111`

### 3.3 ✅ query_xcai_city_history (完整描述)

**返回数据结构**：
```python
{
    "data": [...],              # 标准化记录列表（前24条预览）
    "metadata": {
        "data_id": "air_quality_unified:v1:xxx",
        "total_records": int,
        "returned_records": int,
        "cities": List[str],
        "data_type": "hour" | "day",
        "table": "CityAQIPublishHistory" | "CityDayAQIPublishHistory",
        "time_range": str,
        "schema_version": "v2.0",
        "source": "xcai_sql_server"
    }
}
```

**数据表说明**：
- hour（小时数据）：CityAQIPublishHistory（2017-01-01至今）
- day（日数据）：CityDayAQIPublishHistory（2021-06-25至今）

**说明文档位置**：`backend/app/tools/query/query_xcai_city_history/tool.py:38-54`

### 3.4 ✅ execute_sql_query (完整描述)

**返回数据结构**：
```python
# 方式1：查看表结构
{
    "success": True,
    "data": {
        "table_name": str,
        "columns": [
            {
                "COLUMN_NAME": str,
                "DATA_TYPE": str,
                "CHARACTER_MAXIMUM_LENGTH": int,
                "IS_NULLABLE": "YES" | "NO",
                "COLUMN_DEFAULT": Any
            }
        ]
    },
    "summary": str
}

# 方式2：执行SQL查询
{
    "success": True,
    "data": [...],  # 查询结果列表
    "summary": str
}
```

**说明文档位置**：`backend/app/tools/query/execute_sql_query/tool.py:54-96`

### 3.5 ❓ query_gd_suncere_city_day_new (需检查)

**返回数据结构**（从实现代码推断）：
```python
{
    "status": "success",
    "success": True,
    "data": [...],  # 标准化记录列表（前24条预览）
    "metadata": {
        "tool_name": "query_gd_suncere_city_day_new",
        "data_id": "air_quality_unified:v1:xxx",
        "total_records": int,
        "returned_records": int,
        "cities": List[str],
        "date_range": str,
        "standard": "HJ 633-2026",
        "schema_version": "v2.0",
        "source": "gd_suncere_api",
        "enable_sand_deduction": bool
    }
}
```

**实现位置**：`backend/app/tools/query/query_gd_suncere/tool_city_day_new.py:452-468`

## 4. complex_query_planner 中的 Schema 描述问题

### 4.1 当前状态

`GUANGDONG_QUERY_TOOLS_SCHEMAS` 只包含：
- ✅ `name` - 工具名称
- ✅ `description` - 简短描述（1-2句话）
- ✅ `parameters` - 完整的输入参数定义

### 4.2 缺失内容

- ❌ **返回数据结构说明**
- ❌ **返回字段列表**
- ❌ **各字段的数据类型和含义**
- ❌ **特殊字段说明**（如 result vs data_id）

### 4.3 对比示例

#### 实际工具的完整描述（query_new_standard_report）：
```
【返回数据说明】
- result字段：⭐ 统计汇总结果（综合指数、超标天数、首要污染物比例等）
  - **综合指标**：composite_index（综合指数）, exceed_days（超标天数）, ...
  - **六参数统计**：SO2, SO2_P98, NO2, NO2_P98, ...
  - **加权单项质量指数**：single_indexes.SO2/NO2/PM10/CO/PM2_5/O3_8h
  ...
  - ⚠️ 重要：result 字段包含完整的统计汇总结果，**直接用于报告生成和分析**
- data_id字段：完整日报数据（基于HJ 633-2026新标准计算的每日监测数据）
  - ⚠️ 重要：data_id 只包含每日监测数据，**不包含**统计汇总指标
```

#### complex_query_planner 中的简短描述：
```
"description": "查询HJ 633-2026新标准空气质量统计报表（综合指数、超标天数、达标率、六参数统计浓度）"
```

### 4.4 影响分析

虽然 `complex_query_planner` 只负责生成查询计划（不执行查询），但返回字段描述缺失可能导致：

1. **LLM 理解不完整**：LLM 可能不清楚调用这些工具后会得到什么数据
2. **计划生成不精确**：无法基于返回数据结构优化查询计划
3. **下游工具选择困难**：不清楚哪些数据可用于后续分析

## 5. 建议

### 5.1 短期方案（推荐）

为 `GUANGDONG_QUERY_TOOLS_SCHEMAS` 中的每个工具添加【返回数据说明】部分：

```python
"query_new_standard_report": {
    "name": "query_new_standard_report",
    "description": """
查询HJ 633-2026新标准空气质量统计报表。

【返回数据说明】
- result字段：⭐ 统计汇总结果（综合指数、超标天数、首要污染物比例等）
  - 综合指标：composite_index, exceed_days, exceed_rate, compliance_rate, total_days, valid_days
  - 六参数统计：SO2, SO2_P98, NO2, NO2_P98, PM10, PM10_P95, PM2_5, PM2_5_P95, CO_P95, O3_8h_P90
  - 单项质量指数：single_indexes.*
  - 首要污染物统计：primary_pollutant_days.*, primary_pollutant_ratio.*, total_primary_days
  - 超标统计：exceed_days_by_pollutant.*, primary_pollutant_exceed_days.*
  - 多城市查询时包含 province_wide（全省汇总统计）
- data_id字段：完整日报数据（不含统计指标）
    """.strip(),
    "parameters": {...}
}
```

### 5.2 长期方案

1. **统一 schema 文档**：创建一个单独的文档文件（如 `QUERY_TOOLS_REFERENCE.md`），集中维护所有查询工具的完整说明
2. **动态加载描述**：从实际工具实现中提取 `function_schema`，避免重复维护
3. **版本控制**：为 schema 添加版本号，便于追踪变更

## 6. 总结

| 工具名称 | 实际实现描述 | complex_query_planner 描述 | 状态 |
|---------|------------|--------------------------|------|
| query_new_standard_report | ✅ 完整 | ❌ 简短 | 需补充 |
| compare_standard_reports | ✅ 完整 | ❌ 简短 | 需补充 |
| query_xcai_city_history | ✅ 完整 | ❌ 简短 | 需补充 |
| execute_sql_query | ✅ 完整 | ❌ 简短 | 需补充 |
| query_gd_suncere_city_day_new | ⚠️ 需确认 | ❌ 简短 | 需检查 |
| query_old_standard_report | ⚠️ 未检查 | ❌ 简短 | 需检查 |
| query_standard_comparison | ⚠️ 未检查 | ❌ 简短 | 需检查 |
| query_gd_suncere_city_day | ⚠️ 未检查 | ❌ 简短 | 需检查 |

**建议优先级**：
1. 🔴 高优先级：query_new_standard_report, compare_standard_reports（使用频繁，返回字段复杂）
2. 🟡 中优先级：query_xcai_city_history, execute_sql_query
3. 🟢 低优先级：其他4个工具

**后续行动**：
1. 从实际工具实现中提取返回字段说明
2. 更新 `GUANGDONG_QUERY_TOOLS_SCHEMAS` 中的 description 字段
3. 测试更新后的 schema 是否能提升 LLM 的查询计划质量
