"""
复杂查询计划工具

通过单次LLM调用注入广东省相关结构化查询工具的详细 function_schema，
生成工具查询调用计划返回给主Agent执行。

支持模式：仅支持问数模式（query）和报告模式（report）
触发机制：主Agent的LLM根据工具描述自主决定是否调用
"""

import json
import structlog
from typing import Dict, Any, List
from datetime import datetime

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()


# 广东省查询工具的完整 function_schema 定义
GUANGDONG_QUERY_TOOLS_SCHEMAS = {
    "query_gd_suncere_city_day_new": {
        "name": "query_gd_suncere_city_day_new",
        "description": """
查询广东省城市日空气质量数据（新标准 HJ 633-2026）。

【返回数据说明】
- data字段：前24条记录预览（包含每日六参数、AQI、首要污染物、空气质量等级）
  - timestamp：日期时间
  - measurements：{PM2_5, PM10, SO2, NO2, CO, O3_8h, PM2_5_IAQI, PM10_IAQI, AQI}
  - air_quality_level：空气质量等级（优/良/轻度污染/中度污染/重度污染/严重污染）
  - primary_pollutant：首要污染物
- data_id字段：完整数据存储标识符（包含所有日期的日报数据）
  - 支持通过 aggregate_data 工具进行后续分析
  - 支持通过 smart_chart_generator 工具生成图表
- metadata字段：
  - total_records：总记录数
  - standard：HJ 633-2026
  - enable_sand_deduction：是否启用扣沙处理

【新标准变化】
- PM2.5断点：IAQI=100时60μg/m³（旧标准75）
- PM10断点：IAQI=100时120μg/m³（旧标准150）
- 扣沙日处理：剔除沙尘暴天气的PM2.5/PM10数据
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市列表，如 ['广州', '深圳', '珠海']"
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期，格式 YYYY-MM-DD"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，格式 YYYY-MM-DD"
                }
            },
            "required": ["cities", "start_date", "end_date"]
        }
    },
    "query_new_standard_report": {
        "name": "query_new_standard_report",
        "description": """
查询基于HJ 633-2026新标准的空气质量统计报表。

【返回数据说明】
- result字段：⭐ 统计汇总结果（综合指数、超标天数、首要污染物比例等）
  - **综合指标**：composite_index（综合指数）, exceed_days（超标天数）, valid_days（有效天数）, exceed_rate（超标率%）, compliance_rate（达标率%）, total_days（总天数）
  - **六参数统计**：SO2, SO2_P98, NO2, NO2_P98, PM10, PM10_P95, PM2_5, PM2_5_P95, CO_P95, O3_8h_P90
  - **加权单项质量指数**：single_indexes.SO2/NO2/PM10/CO/PM2_5/O3_8h
  - **首要污染物统计**：primary_pollutant_days（各污染物作为首要污染物的天数）, primary_pollutant_ratio（首要污染物比例%）, total_primary_days（总首要污染物天数）
  - **超标统计**：exceed_days_by_pollutant（各污染物超标天数）, exceed_rate_by_pollutant（各污染物超标率%）, primary_pollutant_exceed_days（首要污染物超标天，既是首要污染物又超标的天数）
  - 单城市查询：直接返回城市统计数据
  - 多城市查询：返回各城市统计数据 + province_wide（全省汇总统计）
  - ⚠️ 重要：result 字段包含完整的统计汇总结果，**直接用于报告生成和分析**
- data_id字段：完整日报数据（基于HJ 633-2026新标准计算的每日监测数据）
  - ⚠️ 重要：data_id 只包含每日监测数据（timestamp、AQI、measurements 等），**不包含**统计汇总指标
  - ❌ 不要从 data_id 读取 exceed_days_by_pollutant、primary_pollutant_exceed_days 等统计字段（这些字段只在 result 中）

【全省汇总统计规则】（多城市查询时）
- **均值类指标**（各城市均值）：composite_index, single_indexes.*, SO2, NO2, PM10, PM2_5, CO_P95, O3_8h_P90等
- **累加类指标**（各城市累加）：exceed_days, valid_days, exceed_days_by_pollutant.*, primary_pollutant_days.*, primary_pollutant_exceed_days.*, total_primary_days
- **计算类指标**：exceed_rate, compliance_rate, exceed_rate_by_pollutant.*, primary_pollutant_ratio
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市列表，如 ['广州', '深圳']"
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期，格式 YYYY-MM-DD"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，格式 YYYY-MM-DD"
                },
                "enable_sand_deduction": {
                    "type": "boolean",
                    "description": "是否启用扣沙处理（默认true，剔除沙尘暴天气的PM2.5/PM10数据）"
                }
            },
            "required": ["cities", "start_date", "end_date"]
        }
    },
    "query_old_standard_report": {
        "name": "query_old_standard_report",
        "description": """
查询基于HJ 633-2013旧标准的空气质量统计报表。

【返回数据说明】
- result字段：⭐ 统计汇总结果（结构同新标准报表）
  - **综合指标**：composite_index（综合指数）, exceed_days（超标天数）, valid_days（有效天数）, exceed_rate（超标率%）, compliance_rate（达标率%）, total_days（总天数）
  - **六参数统计**：SO2, SO2_P98, NO2, NO2_P98, PM10, PM10_P95, PM2_5, PM2_5_P95, CO_P95, O3_8h_P90
  - **加权单项质量指数**：single_indexes.*
  - **首要污染物统计**：primary_pollutant_days.*, primary_pollutant_ratio.*, total_primary_days
  - **超标统计**：exceed_days_by_pollutant.*, exceed_rate_by_pollutant.*, primary_pollutant_exceed_days.*
- data_id字段：完整日报数据（基于HJ 633-2013旧标准计算的每日监测数据）

【旧标准特点】
- PM2.5断点：IAQI=100时75μg/m³
- PM10断点：IAQI=100时150μg/m³
- 超标判断：基于单项质量指数 > 1
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市列表，如 ['广州', '深圳']"
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期，格式 YYYY-MM-DD"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，格式 YYYY-MM-DD"
                },
                "enable_sand_deduction": {
                    "type": "boolean",
                    "description": "是否启用扣沙处理（默认true）"
                }
            },
            "required": ["cities", "start_date", "end_date"]
        }
    },
    "query_standard_comparison": {
        "name": "query_standard_comparison",
        "description": """
查询新旧标准对比统计指标（HJ 633-2026 vs HJ 633-2013）。

【返回数据说明】
- result字段：⭐ 新旧标准对比结果
  - **新标准统计**（new_standard）：基于HJ 633-2026计算的统计指标
    - composite_index, exceed_days, exceed_rate, compliance_rate, total_days, valid_days
    - 六参数统计：SO2, SO2_P98, NO2, NO2_P98, PM10, PM10_P95, PM2_5, PM2_5_P95, CO_P95, O3_8h_P90
    - single_indexes.*, primary_pollutant_days.*, exceed_days_by_pollutant.*
  - **旧标准统计**（old_standard）：基于HJ 633-2013计算的统计指标
    - 结构同新标准统计
  - **差值对比**（differences）：new_standard - old_standard
    - composite_index_diff, exceed_days_diff, exceed_rate_diff, compliance_rate_diff
    - 六参数统计差值：SO2_diff, NO2_diff, PM10_diff, PM2_5_diff, CO_P95_diff, O3_8h_P90_diff
  - 单城市查询：直接返回城市对比数据
  - 多城市查询：返回各城市对比数据 + province_wide（全省汇总对比）
- data_id字段：包含新标准和旧标准计算的完整日报数据

【使用场景】
- 评估新标准实施对空气质量评价的影响
- 对比新旧标准的综合指数、超标天数差异
- 分析首要污染物认定变化
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市列表"
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期，格式 YYYY-MM-DD"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，格式 YYYY-MM-DD"
                },
                "enable_sand_deduction": {
                    "type": "boolean",
                    "description": "是否启用扣沙处理（默认true）"
                }
            },
            "required": ["cities", "start_date", "end_date"]
        }
    },
    "compare_standard_reports": {
        "name": "compare_standard_reports",
        "description": """
对比两个时间段基于 HJ 633-2026 新标准的空气质量统计报表。

【返回数据说明】
- result字段：⭐ 完整的对比结果（包含所有城市的详细对比数据）
  - **查询时间段统计**（query_period）：当前时期的统计数据
    - 综合指标：composite_index, exceed_days, exceed_rate, compliance_rate, total_days, valid_days
    - 六参数统计：SO2, SO2_P98, NO2, NO2_P98, PM10, PM10_P95, PM2_5, PM2_5_P95, CO_P95, O3_8h_P90
    - 单项质量指数：single_indexes.*
    - 首要污染物统计：primary_pollutant_days.*, primary_pollutant_ratio.*, total_primary_days
    - 超标统计：exceed_days_by_pollutant.*, exceed_rate_by_pollutant.*, primary_pollutant_exceed_days.*
  - **对比时间段统计**（comparison_period）：基准时期的统计数据（结构同上）
  - **差值分析**（differences）：query_period - comparison_period
    - 所有34个对比指标的差值
  - **变化率分析**（change_rates）：(query_period - comparison_period) / comparison_period * 100
    - 所有34个对比指标的变化率百分比（达标率、超标率等百分比字段只计算差值，不计算变化率）
  - **全省汇总对比**（province_wide）：多城市查询时包含，结构同单城市对比
  - ⚠️ 重要：result 字段包含完整的对比分析结果，**直接用于报告生成和分析，无需再读取 data_id**

【对比指标列表】（34个）
- 综合指标：composite_index, exceed_days, exceed_rate, compliance_rate, total_days, valid_days
- 六参数统计：SO2, SO2_P98, NO2, NO2_P98, PM10, PM10_P95, PM2_5, PM2_5_P95, CO_P95, O3_8h_P90
- 单项质量指数：single_indexes.SO2/NO2/PM10/CO/PM2_5/O3_8h
- 首要污染物天数：primary_pollutant_days.PM2_5/PM10/NO2/O3_8h/CO/SO2, total_primary_days
- 超标天数：exceed_days_by_pollutant.PM2_5/PM10/SO2/NO2/CO/O3_8h
- 首要污染物超标天：primary_pollutant_exceed_days.PM2_5/PM10/SO2/NO2/CO/O3_8h

【使用场景】
- 同比分析：今年 vs 去年同期
- 环比分析：本月 vs 上月
- 评估空气质量改善或恶化趋势
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市列表"
                },
                "query_period": {
                    "type": "object",
                    "properties": {
                        "start_date": {"type": "string", "description": "查询期开始日期，格式 YYYY-MM-DD"},
                        "end_date": {"type": "string", "description": "查询期结束日期，格式 YYYY-MM-DD"}
                    },
                    "required": ["start_date", "end_date"],
                    "description": "查询时间段（当前时期）"
                },
                "comparison_period": {
                    "type": "object",
                    "properties": {
                        "start_date": {"type": "string", "description": "对比期开始日期，格式 YYYY-MM-DD"},
                        "end_date": {"type": "string", "description": "对比期结束日期，格式 YYYY-MM-DD"}
                    },
                    "required": ["start_date", "end_date"],
                    "description": "对比时间段（基准时期，用于同比/环比）"
                },
                "enable_sand_deduction": {
                    "type": "boolean",
                    "description": "是否启用扣沙处理（默认true，剔除沙尘暴天气的PM2.5/PM10数据）"
                }
            },
            "required": ["cities", "query_period", "comparison_period"]
        }
    },
    "query_xcai_city_history": {
        "name": "query_xcai_city_history",
        "description": """
查询全国城市历史空气质量数据（SQL Server XcAiDb数据库）。

【数据表说明】
- hour（小时数据）：CityAQIPublishHistory表，时间范围 2017-01-01 至今
  - 字段：PM2_5, PM10, O3, NO2, SO2, CO, AQI, PrimaryPollutant, Quality
- day（日数据）：CityDayAQIPublishHistory表，时间范围 2021-06-25 至今
  - 字段：PM2_5_24h, PM10_24h, O3_8h_24h, NO2_24h, SO2_24h, CO_24h, AQI, PrimaryPollutant, Quality

【返回数据说明】
- data字段：前24条记录预览（标准化后的空气质量数据）
- data_id字段：完整数据存储标识符
  - 支持通过 aggregate_data 工具进行后续分析
  - 支持通过 smart_chart_generator 工具生成图表
- metadata字段：
  - total_records：总记录数
  - data_type：hour 或 day
  - table：数据表名
  - time_range：时间范围

【使用示例】
- 查询广州2025年3月的小时数据：data_type="hour", cities=["广州市"], start_time="2025-03-01 00:00:00", end_time="2025-03-31 23:00:00"
- 查询深圳近7天的日数据：data_type="day", cities=["深圳市"], start_time="2025-03-22 00:00:00", end_time="2025-03-29 00:00:00"
- 查询北京2024年全年日数据：data_type="day", cities=["北京市"], start_time="2024-01-01 00:00:00", end_time="2024-12-31 00:00:00"

【注意事项】
- 时间格式必须严格：小时数据用 "YYYY-MM-DD HH:MM:SS"，日数据用 "YYYY-MM-DD 00:00:00"
- 城市名称必须带"市"字（如"广州市"、"深圳市"）
- 返回的data_id可用于下游分析工具获取完整数据
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市名称列表，如 ['广州市', '深圳市', '北京市']（必须带'市'字）"
                },
                "data_type": {
                    "type": "string",
                    "enum": ["hour", "day"],
                    "description": "数据类型：hour=查询小时数据表（CityAQIPublishHistory），day=查询日数据表（CityDayAQIPublishHistory）"
                },
                "start_time": {
                    "type": "string",
                    "description": "开始时间（必须），格式：YYYY-MM-DD HH:MM:SS（小时数据）或 YYYY-MM-DD 00:00:00（日数据）"
                },
                "end_time": {
                    "type": "string",
                    "description": "结束时间（必须），格式：YYYY-MM-DD HH:MM:SS（小时数据）或 YYYY-MM-DD 00:00:00（日数据）"
                }
            },
            "required": ["cities", "data_type", "start_time", "end_time"]
        }
    },
    # 问数模式和报告模式
    "execute_sql_query": {
        "name": "execute_sql_query",
        "description": """
通用SQL执行工具，直接执行SQL查询语句访问SQL Server历史数据库。

【核心功能】
- 支持查看表结构（动态从数据库获取字段信息）
- 支持执行SQL查询（SELECT查询、JOIN、聚合等操作）
- 支持新旧标准综合指数查询（city_168_statistics_new_standard、city_168_statistics_old_standard、province_statistics_new_standard、province_statistics_old_standard表）

【两种使用方式（二选一）】
1. 查看表结构：execute_sql_query(describe_table='表名')
   - 动态从数据库获取表结构信息
   - 返回字段名、数据类型、长度、是否可空等信息

2. 执行SQL查询：execute_sql_query(sql='SQL语句')
   - 执行SELECT查询获取数据
   - 支持复杂查询、JOIN、聚合等操作

【返回数据说明】
方式1 - 查看表结构（describe_table）：
- data.table_name：表名
- data.columns：字段列表
  - COLUMN_NAME：字段名
  - DATA_TYPE：数据类型
  - CHARACTER_MAXIMUM_LENGTH：字符长度
  - IS_NULLABLE：是否可空（YES/NO）
  - COLUMN_DEFAULT：默认值
- summary：表结构摘要（包含字段总数和使用提示）

方式2 - 执行SQL查询（sql）：
- data：查询结果列表（每行一个字典，包含所有字段）
- summary：查询结果摘要（包含记录数）

【describe_table 参数说明】
- 输入目标表名（如 'qc_history', 'working_orders'）
- 工具会动态查询数据库获取该表的结构信息
- 不需要提供 sql 参数

【sql 参数说明】
- 输入完整的SQL查询语句
- 不需要提供 describe_table 参数

【⚠️ 重要：中文查询注意事项】
SQL Server 查询中文字符串时，必须使用 N 前缀（表示 Unicode）：
- ❌ 错误：WHERE StationName LIKE '%增城派潭%'
- ✅ 正确：WHERE StationName LIKE N'%增城派潭%'
- ✅ 正确：WHERE StationCode = '1428A'（英文和数字不需要 N 前缀）
- 建议：优先使用 StationCode（站点编码）进行查询，避免中文编码问题

【可用数据表】
- city_168_statistics_new_standard: 168城市空气质量统计（新标准 HJ 633-2026，⚠️ 查询168城市新标准排名专用表。表中直接包含预计算的排名字段，无需使用窗口函数。stat_type: monthly/annual_ytd/current_month，数据周期2024-01至今，城市名不带'市'后缀）
- city_168_statistics_old_standard: 168城市空气质量统计（旧标准 HJ 633-2013，⚠️ 查询168城市旧标准排名专用表。表中直接包含预计算的排名字段，无需使用窗口函数。stat_type: monthly/annual_ytd/current_month，数据周期2024-01至今，城市名不带'市'后缀）
- province_statistics_new_standard: 省级空气质量统计（新标准 HJ 633-2026，⚠️ 查询省级新标准排名专用表。表中直接包含预计算的排名字段，无需使用窗口函数。stat_type: monthly/annual_ytd/current_month，数据周期2024-01至今，省份名不带'省'后缀）
- province_statistics_old_standard: 省级空气质量统计（旧标准 HJ 633-2013，⚠️ 查询省级旧标准排名专用表。表中直接包含预计算的排名字段，无需使用窗口函数。stat_type: monthly/annual_ytd/current_month，数据周期2024-01至今，省份名不带'省'后缀）
- qc_history: 自动质控历史数据表（包含 StationCode、StationName 等字段）
- working_orders: 运维工单记录表

【⚠️ 重要：168城市排名查询规范】
- 168城市排名已拆分为两个表：新标准查询 city_168_statistics_new_standard，旧标准查询 city_168_statistics_old_standard
- 表中已预计算排名，直接使用 comprehensive_index_rank 等字段，无需使用窗口函数
- ❌ 禁止同时调用 query_new_standard_report + query_old_standard_report + execute_sql_query
- ❌ 广东省城市报表（query_new_standard_report等）只包含省内21个城市数据，无法用于168城市排名
- ✅ 正确做法：只调用 execute_sql_query 一次，直接从对应标准表查询综合指数和排名字段

【安全限制】
- 只允许SELECT查询
- 禁止DROP/DELETE/INSERT/UPDATE等操作
- 表名白名单验证
- 最大返回10000条记录

【使用流程】
1. 先查看表结构：execute_sql_query(describe_table='city_168_statistics_new_standard')
2. 根据表结构编写SQL（注意中文字符串使用 N 前缀）
3. 执行查询：execute_sql_query(sql='SELECT ...')

【168城市排名查询示例】（⭐ 直接使用预计算的排名字段）
- 查询城市在新标准下的排名：
  ```sql
  SELECT city_name, stat_date,
         comprehensive_index, comprehensive_index_rank
  FROM city_168_statistics_new_standard
  WHERE stat_type = 'annual_ytd'
    AND city_name IN (N'广州', N'深圳', N'珠海', N'佛山', N'东莞', N'中山', N'江门', N'惠州', N'肇庆')
  ORDER BY city_name
  ```
- 查询城市在旧标准下的排名：
  ```sql
  SELECT city_name, stat_date,
         comprehensive_index_new_algo, comprehensive_index_rank_new_algo
  FROM city_168_statistics_old_standard
  WHERE stat_type = 'annual_ytd'
    AND city_name IN (N'广州', N'深圳', N'珠海', N'佛山', N'东莞', N'中山', N'江门', N'惠州', N'肇庆')
  ORDER BY city_name
  ```
- 新标准表字段说明：
  - comprehensive_index: 新标准综合指数（HJ 633-2026）
  - comprehensive_index_rank: 新标准排名
  - comprehensive_index_new_limit_old_algo: 新限值+旧算法（用于对比）
- 旧标准表字段说明：
  - comprehensive_index_new_algo: 新算法综合指数
  - comprehensive_index_rank_new_algo: 新算法排名
  - comprehensive_index_old_algo: 旧算法综合指数
  - comprehensive_index_rank_old_algo: 旧算法排名
- ⚠️ 注意：表中已预计算排名，直接使用字段即可，无需使用窗口函数
- 其他统计类型：stat_type='monthly'（月报）、stat_type='current_month'（当月）
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "describe_table": {
                    "type": "string",
                    "description": "查看表结构（与sql参数二选一）。输入目标表名，如 'city_168_statistics_new_standard'、'city_168_statistics_old_standard'、'qc_history' 或 'working_orders'。工具会动态从数据库获取该表的结构信息，包括字段名、数据类型、长度、是否可空等。"
                },
                "sql": {
                    "type": "string",
                    "description": "SQL查询语句（与describe_table参数二选一）。输入完整的SQL SELECT查询语句。中文字符串必须使用N前缀，如 WHERE StationName LIKE N'%增城%'"
                },
                "database": {
                    "type": "string",
                    "description": "数据库名称（可选）。默认为'XcAiDb'，查询质控数据时使用'AirPollutionAnalysis'。",
                    "enum": ["XcAiDb", "AirPollutionAnalysis"]
                },
                "limit": {
                    "type": "integer",
                    "description": "返回记录数限制（默认50，最大100，仅用于sql查询）",
                    "default": 50
                }
            }
        }
    },
    "query_gd_suncere_city_day": {
        "name": "query_gd_suncere_city_day",
        "description": """
查询广东省城市日空气质量数据（旧标准 HJ 633-2013）。

【返回数据说明】
- data字段：前24条记录预览（包含每日六参数、AQI、首要污染物、空气质量等级）
  - timestamp：日期时间
  - measurements：{PM2_5, PM10, SO2, NO2, CO, O3_8h, PM2_5_IAQI, PM10_IAQI, AQI}
  - air_quality_level：空气质量等级
  - primary_pollutant：首要污染物
- data_id字段：完整数据存储标识符
  - 支持通过 aggregate_data 工具进行后续分析
  - 支持通过 smart_chart_generator 工具生成图表
- metadata字段：
  - total_records：总记录数
  - standard：HJ 633-2013（旧标准）

【旧标准特点】
- PM2.5断点：IAQI=100时75μg/m³
- PM10断点：IAQI=100时150μg/m³
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市列表，如 ['广州', '深圳']"
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期，格式 YYYY-MM-DD"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，格式 YYYY-MM-DD"
                }
            },
            "required": ["cities", "start_date", "end_date"]
        }
    },
    "query_gd_suncere_city_hour": {
        "name": "query_gd_suncere_city_hour",
        "description": """
查询广东省城市小时空气质量数据。

【核心功能】
- 查询广东省城市的小时级别空气质量数据
- 支持多城市并发查询
- 城市/站点名称自动映射到编码
- 根据查询时间自动判断数据源（原始实况/审核实况）

【使用场景】
- 城市空气质量时序分析
- 区域传输分析
- 多城市对比分析
- 污染过程追溯

【返回数据说明】
- data字段：前24条记录预览
- data_id字段：完整数据存储标识符（UDF v2.0格式）
  - 包含多城市的小时级别污染物数据
  - 可直接传递给可视化工具生成时序图
- metadata字段：
  - total_records：总记录数
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市名称列表，如 ['广州', '深圳', '佛山']"
                },
                "start_time": {
                    "type": "string",
                    "description": "开始时间，格式 'YYYY-MM-DD HH:MM:SS'"
                },
                "end_time": {
                    "type": "string",
                    "description": "结束时间，格式 'YYYY-MM-DD HH:MM:SS'"
                }
            },
            "required": ["cities", "start_time", "end_time"]
        }
    },
    "query_gd_suncere_station_hour_new": {
        "name": "query_gd_suncere_station_hour_new",
        "description": """
查询广东省站点级别小时空气质量数据（基于HJ 633-2026新标准）。

【核心功能】
- 查询广东省站点级别的小时空气质量数据
- 支持按站点类型过滤（国控/省控/市控等）
- 支持按城市名展开（自动查询该城市下所有站点）或直接输入站点名称
- 支持多城市查询（自动合并站点列表）
- ⭐ 按新标准计算IAQI、AQI和首要污染物（PM2.5断点60，PM10断点120）
- 根据查询时间自动判断数据源（三天内原始，三天前审核）
- 浓度值修约（CO保留1位小数，其他取整）
- 返回结果包含 station_name 字段，直观显示站点名称

【与城市小时数据的区别】
- 城市小时数据（query_gd_suncere_city_hour）：城市级别的聚合数据
- 站点小时数据（本工具）：单个监测站点的小时数据，更精细

【使用场景】
- 站点级别的污染物浓度分析
- 城市内不同站点对比分析
- 精细化污染溯源（需要站点级别数据）
- 站点数据质量检查

【输入参数】
- station_type: 站点类型（必填），如 "国控"/"省控"/"市控" 或 "1.0"/"2.0"/"3.0"
- cities: 城市名称列表（如 ["广州", "深圳"]），会自动展开为站点（与 stations 至少提供一个）
- stations: 站点名称列表（如 ["广雅中学", "市监测站"]），直接查询指定站点（与 cities 至少提供一个）
- start_time: 开始时间，格式 "YYYY-MM-DD HH:MM:SS"
- end_time: 结束时间，格式 "YYYY-MM-DD HH:MM:SS"

【站点类型说明】
- 国控(1.0)、省控(2.0)、市控(3.0)、区县控(4.0)、乡镇控(5.0)等
- 支持中文名称和数字ID两种格式

【支持的城市和站点】
- 广州（19站：广雅中学、市监测站、市五中、体育西、广东商学院、麓湖等）
- 深圳（12站：洪湖、华侨城、盐田、龙岗、坪山等）
- 珠海（3站：吉大、前山、唐家）
- 佛山（3站：湾梁、华材职中、南海气象局）
- 韶关（4站：韶关学院、曲江监测站、碧湖山庄、浈江十里亭）

【返回数据说明】
- data_id: 数据引用ID（UDF v2.0格式）
  - 包含站点级别的小时污染物数据
  - ⭐ 包含新标准计算的IAQI、AQI和首要污染物
  - 每条记录包含 station_name 字段（站点中文名称）
  - 可直接传递给可视化工具生成时序图
- metadata字段：
  - total_records：总记录数
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "station_type": {
                    "type": "string",
                    "description": "站点类型（必填），如 '国控'/'省控'/'市控' 或 '1.0'/'2.0'/'3.0'"
                },
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市名称列表，如 ['广州', '深圳']，会自动展开为站点代码（与 stations 至少提供一个）"
                },
                "stations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "站点名称列表，如 ['广雅中学', '市监测站']，直接查询指定站点（与 cities 至少提供一个）"
                },
                "start_time": {
                    "type": "string",
                    "description": "开始时间，格式 'YYYY-MM-DD HH:MM:SS'"
                },
                "end_time": {
                    "type": "string",
                    "description": "结束时间，格式 'YYYY-MM-DD HH:MM:SS'"
                }
            },
            "required": ["station_type", "start_time", "end_time"]
        }
    },
    "query_gd_suncere_station_day_new": {
        "name": "query_gd_suncere_station_day_new",
        "description": """
查询广东省站点级别日空气质量数据（基于HJ 633-2026新标准）。

【核心功能】
- 查询广东省站点级别的日空气质量数据
- 支持按站点类型过滤（国控/省控/市控等）
- 支持按城市名展开（自动查询该城市下所有站点）或直接输入站点名称
- 支持多城市查询（自动合并站点列表）
- ⭐ 按新标准计算IAQI、AQI和首要污染物（PM2.5断点60，PM10断点120）
- 根据查询时间自动判断数据源（三天内原始，三天前审核）
- 浓度值修约（CO保留1位小数，其他取整）
- 返回结果包含 station_name 字段，直观显示站点名称

【与城市日数据的区别】
- 城市日数据（query_gd_suncere_city_day）：城市级别的聚合数据
- 站点日数据（本工具）：单个监测站点的日数据，更精细

【与站点小时数据的区别】
- 站点小时数据（query_gd_suncere_station_hour）：每小时一条记录
- 站点日数据（本工具）：每天一条记录（日均值）

【使用场景】
- 站点级别的日均污染物浓度分析
- 城市内不同站点日数据对比
- 长时间序列趋势分析（站点级别）
- 站点数据质量检查（日数据）

【输入参数】
- station_type: 站点类型（必填），如 "国控"/"省控"/"市控" 或 "1.0"/"2.0"/"3.0"
- cities: 城市名称列表（如 ["广州", "深圳"]），会自动展开为站点（与 stations 至少提供一个）
- stations: 站点名称列表（如 ["广雅中学", "市监测站"]），直接查询指定站点（与 cities 至少提供一个）
- start_date: 开始日期，格式 "YYYY-MM-DD"
- end_date: 结束日期，格式 "YYYY-MM-DD"

【站点类型说明】
- 国控(1.0)、省控(2.0)、市控(3.0)、区县控(4.0)、乡镇控(5.0)等
- 支持中文名称和数字ID两种格式

【支持的城市和站点】
- 广州（19站：广雅中学、市监测站、市五中、体育西、广东商学院、麓湖等）
- 深圳（12站：洪湖、华侨城、盐田、龙岗、坪山等）
- 珠海（3站：吉大、前山、唐家）
- 佛山（3站：湾梁、华材职中、南海气象局）
- 韶关（4站：韶关学院、曲江监测站、碧湖山庄、浈江十里亭）

【返回数据说明】
- data_id: 数据引用ID（UDF v2.0格式）
  - 包含站点级别的日污染物数据
  - ⭐ 包含新标准计算的IAQI、AQI和首要污染物
  - 每条记录包含 station_name 字段（站点中文名称）
  - 可直接传递给可视化工具生成趋势图
- metadata字段：
  - total_records：总记录数
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "station_type": {
                    "type": "string",
                    "description": "站点类型（必填），如 '国控'/'省控'/'市控' 或 '1.0'/'2.0'/'3.0'"
                },
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市名称列表，如 ['广州', '深圳']，会自动展开为站点代码（与 stations 至少提供一个）"
                },
                "stations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "站点名称列表，如 ['广雅中学', '市监测站']，直接查询指定站点（与 cities 至少提供一个）"
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期，格式 'YYYY-MM-DD'"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，格式 'YYYY-MM-DD'"
                }
            },
            "required": ["station_type", "start_date", "end_date"]
        }
    },
    "query_gd_suncere_regional_comparison": {
        "name": "query_gd_suncere_regional_comparison",
        "description": """
查询广东省区域对比空气质量数据。

【核心功能】
- 查询目标城市与周边城市的小时数据
- 用于区域传输分析
- 自动判断数据源类型
- 返回统一格式数据

【使用场景】
- 区域传输分析（本地生成 vs 外部输送）
- 目标城市与周边城市对比
- 污染来源溯源分析

【输入参数】
- target_city: 目标城市名称（如 "广州"）
- nearby_cities: 周边城市名称列表（如 ["佛山", "深圳", "东莞"]）
- start_time: 开始时间，格式 "YYYY-MM-DD HH:MM:SS"
- end_time: 结束时间，格式 "YYYY-MM-DD HH:MM:SS"

【返回数据说明】
- data_id: 数据引用ID（UDF v2.0格式）
  - 包含目标城市和周边城市的小时数据
  - 可直接用于区域传输分析
- metadata字段：
  - total_records：总记录数
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "target_city": {
                    "type": "string",
                    "description": "目标城市名称，如 '广州'"
                },
                "nearby_cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "周边城市名称列表，如 ['佛山', '深圳', '东莞']"
                },
                "start_time": {
                    "type": "string",
                    "description": "开始时间，格式 'YYYY-MM-DD HH:MM:SS'"
                },
                "end_time": {
                    "type": "string",
                    "description": "结束时间，格式 'YYYY-MM-DD HH:MM:SS'"
                }
            },
            "required": ["target_city", "nearby_cities", "start_time", "end_time"]
        }
    },
    "query_station_new_standard_report": {
        "name": "query_station_new_standard_report",
        "description": """
查询站点级基于 HJ 633-2026 新标准的空气质量统计报表。

【核心功能】
- 新标准综合指数计算（PM2.5权重3，O3权重2，NO2权重2，其他权重1）
- 超标天数和达标率统计
- 六参数统计浓度（SO2_P98, NO2_P98, PM10_P95, PM2_5_P95, CO_P95, O3_8h_P90）
- 首要污染物分析
- 支持按站点类型过滤（国控/省控/市控等）

【与城市工具的差异】
- 不支持扣沙处理（站点级别无扣沙数据）
- 使用 station_name 字段替代 city_name
- 支持城市名称自动展开为站点列表
- 支持多站点汇总统计（aggregate参数）

【返回数据说明】
- result字段：⭐ 完整的统计结果（包含所有站点的详细统计数据）
  - 各站点的综合指数、超标天数、达标率、六参数统计等
  - aggregate=true时，额外包含station_aggregate（多站点汇总）
  - ⚠️ 重要：result 字段包含完整的统计分析结果，**直接用于报告生成和分析**
- data_id字段：站点日报工具返回的原始数据存储标识符
  - 仅用于需要访问原始监测数据或进行聚合分析时使用
  - ⚠️ 一般情况下不需要使用此字段，result 字段已包含所有统计结果

【输入参数】
- station_type: 站点类型（必填），如 "国控"/"省控"/"市控" 或 "1.0"/"2.0"/"3.0"
- cities: 城市名称列表（可选，自动展开为该城市下所有站点），如 ['广州']
- stations: 站点名称列表（可选，直接查询指定站点），如 ['广雅中学', '市监测站']
- start_date: 开始日期，格式 YYYY-MM-DD
- end_date: 结束日期，格式 YYYY-MM-DD
- aggregate: 是否计算多站点汇总统计（默认false）

【站点类型说明】
- 国控(1.0)、省控(2.0)、市控(3.0)、区县控(4.0)、乡镇控(5.0)等
- 支持中文名称和数字ID两种格式

【重要】
- cities 和 stations 至少提供一个（为避免数据量过大，不支持全省查询）
- station_type 为必填参数，必须指定站点类型
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "station_type": {
                    "type": "string",
                    "description": "站点类型（必填），如 '国控'/'省控'/'市控' 或 '1.0'/'2.0'/'3.0'"
                },
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市名称列表（可选，自动展开为该城市下所有站点），如 ['广州']"
                },
                "stations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "站点名称列表（可选，直接查询指定站点），如 ['广雅中学', '市监测站']"
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期，格式 YYYY-MM-DD"
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，格式 YYYY-MM-DD"
                },
                "aggregate": {
                    "type": "boolean",
                    "description": "是否计算多站点汇总统计（默认false）"
                }
            },
            "required": ["station_type", "start_date", "end_date"]
        }
    }
}

# 各模式可用的工具名称
MODE_TOOLS = {
    "query": [
        "query_gd_suncere_city_day_new",
        "query_new_standard_report",
        "query_old_standard_report",
        "query_standard_comparison",
        "compare_standard_reports",
        "query_xcai_city_history",
        "execute_sql_query",
        "query_gd_suncere_city_day",
        "query_gd_suncere_city_hour",
        "query_gd_suncere_station_hour_new",
        "query_gd_suncere_station_day_new",
        "query_gd_suncere_regional_comparison",
        "query_station_new_standard_report",
    ],
    "report": [
        "query_gd_suncere_city_day_new",
        "query_new_standard_report",
        "query_old_standard_report",
        "query_standard_comparison",
        "compare_standard_reports",
        "query_xcai_city_history",
        "execute_sql_query",
        "query_gd_suncere_city_hour",
        "query_gd_suncere_station_hour_new",
        "query_gd_suncere_station_day_new",
        "query_gd_suncere_regional_comparison",
        "query_station_new_standard_report",
    ]
}

PLANNING_PROMPT_TEMPLATE = """你是数据查询规划专家。请根据用户需求生成工具调用计划。

## 系统当前时间
{current_time}

⚠️ **重要**: 用户需求中的所有相对时间描述（如"今天"、"本月"、"今年第一季度"等）都必须基于上述系统当前时间推断并转换为具体日期。

## 用户需求
{query_description}

## 当前模式
{mode}模式

## 参数格式说明
- **cities**: 字符串数组，如 ["广州", "深圳"]
- **默认城市范围**: 如果用户未指定城市或说"广东省所有城市"，使用以下21个地级市：
  广州、深圳、珠海、汕头、佛山、韶关、河源、梅州、惠州、汕尾、东莞、中山、江门、阳江、湛江、茂名、肇庆、清远、潮州、揭阳、云浮
- **日期**: YYYY-MM-DD 格式，如 2025-01-31
- **城市名**: 使用简称，不带"市"字（如"广州"而非"广州市"）

## 可用工具及完整参数定义
{tools_schemas}

## 输出要求
生成JSON格式的查询计划，包含：
1. plan_steps: 步骤列表，每步包含 step(int), tool(str), params(dict), reasoning(str), dependencies(list[int])
2. execution_strategy: 执行策略，包含 parallel_groups(list[list[int]]), estimated_steps(int)

## 约束条件
- 只能从可用工具列表中选择工具
- 必需参数不能缺失
- 无依赖关系的步骤应放入同一并发组
- 时间范围保持一致
- 如果需求信息不足（如缺少时间范围），在 plan_steps 中说明并返回 error 字段
- 优先使用新标准工具（带 _new 后缀的工具）
- **简洁性原则**：选择最简洁的工具调用计划，避免不必要的重复查询
  - 如果一个工具能够满足需求，不要调用多个功能相似的工具
  - 优先使用功能完整的工具（如 query_new_standard_report 已包含统计数据，无需再调用 query_gd_suncere_city_day_new 获取原始数据）
  - 避免同时查询新旧标准数据，除非用户明确需要对比
  - 合理利用工具的返回数据（如 result 字段已包含统计汇总，无需再从 data_id 读取计算）
  - **避免城市范围重复查询**：如果查询了更大范围的城市集合，就不要再单独查询其子集
    - ❌ 错误：先查询4个城市（清远、茂名、东莞、湛江），再查询全省21个城市
    - ✅ 正确：只查询全省21个城市，从中提取4个城市的数据
- **SQL查询支持**：execute_sql_query 支持CTE（WITH子句）、窗口函数（ROW_NUMBER、RANK等）、复杂JOIN查询，可用于计算排名、同比环比等。但168城市排名数据已预计算在表中，直接查询排名字段即可，无需使用窗口函数
- **同环比查询强制要求**：当用户需求涉及"下降"、"上升"、"同比"、"环比"、"变化"、"趋势"、"改善"、"恶化"等数据验证查询时，必须调用同环比查询工具（如 compare_standard_reports），不得通过 execute_sql_query 自行计算或多次调用单时段查询工具后人工对比
  - ❌ 错误：查询"广州今年空气质量相比去年是否下降"时，分别调用两次 query_new_standard_report 后人工计算差值
  - ✅ 正确：调用 compare_standard_reports 工具，传入 query_period 和 comparison_period 参数
  - ✅ 正确：查询"168城市排名变化"时，使用 execute_sql_query 从 city_168_statistics_new_standard 表查询不同时间点的排名字段

## 示例输出

### 示例1：168城市排名查询（新标准）
用户需求："查询珠三角9个城市2025年在168城市新标准中的排名"
{{
    "plan_steps": [
        {{
            "step": 1,
            "tool": "execute_sql_query",
            "params": {{
                "sql": "SELECT city_name, stat_date, comprehensive_index, comprehensive_index_rank FROM city_168_statistics_new_standard WHERE stat_type = 'annual_ytd' AND city_name IN (N'广州', N'深圳', N'珠海', N'佛山', N'东莞', N'中山', N'江门', N'惠州', N'肇庆') ORDER BY city_name"
            }},
            "reasoning": "直接查询168城市表中预计算的排名数据（comprehensive_index_rank和comprehensive_index_rank_old字段），一次查询获取珠三角9个城市的新旧标准排名，无需使用窗口函数或分别查询新标准报表和旧标准报表",
            "dependencies": []
        }}
    ],
    "execution_strategy": {{
        "parallel_groups": [[1]],
        "estimated_steps": 1
    }}
}}

### 示例2：广东省城市统计查询
用户需求："查询广州2025年1月空气质量统计"
{{
    "plan_steps": [
        {{
            "step": 1,
            "tool": "query_new_standard_report",
            "params": {{"cities": ["广州"], "start_date": "2025-01-01", "end_date": "2025-01-31"}},
            "reasoning": "查询新标准空气质量统计报表，已包含完整的统计汇总数据",
            "dependencies": []
        }}
    ],
    "execution_strategy": {{
        "parallel_groups": [[1]],
        "estimated_steps": 1
    }}
}}

请直接输出JSON，不要包含其他内容。"""


class ComplexQueryPlannerTool(LLMTool):
    """
    复杂查询计划工具

    通过单次LLM调用注入广东省相关结构化查询工具的详细 function_schema，
    生成工具查询调用计划返回给主Agent执行。

    仅支持问数模式（query）和报告模式（report）。
    """

    def __init__(self):
        super().__init__(
            name="complex_query_planner",
            description="""复杂查询计划工具（多数据源查询规划）。当需要同时查询多组数据、或不确定应使用哪个查询工具时调用。

【适用场景】
- 多时间段对比分析（同比/环比/多时段/季度对比）
- 多城市分组分析（非标准21城列表、城市间对比、分组统计）
- 不确定应该使用哪个工具（新vs旧标准、日报表vs统计报表、小时vs日数据）
- 需要≥3个工具组合执行（查询+聚合+可视化+分析）

【返回数据说明】
- data.plan 字段：⭐ 查询计划（直接包含在返回结果中，无需额外读取文件）
  - plan_steps：查询步骤列表（每个步骤包含工具名称和参数）
  - execution_strategy：执行策略（顺序/并发）
  - ⚠️ 重要：查询计划直接在返回结果的 data.plan 字段中，**按照 plan_steps 逐步执行即可**
- summary 字段：查询计划摘要（包含步骤数量）

【使用示例】
调用后直接从返回结果的 data.plan 字段获取查询计划，按照 plan_steps 逐步执行工具调用。

⚠️ 必需参数: query_description(str, 详细描述查询需求), mode(str, 当前模式: query或report)""",
            category=ToolCategory.PLANNING,
            requires_context=False
        )

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query_description": {
                        "type": "string",
                        "description": "详细描述查询需求，包括城市、时间范围、需要的指标等"
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["query", "report"],
                        "description": "当前Agent模式，query=问数模式，report=报告模式"
                    }
                },
                "required": ["query_description", "mode"]
            }
        }

    async def execute(
        self,
        query_description: str,
        mode: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成查询计划

        Args:
            query_description: 详细的查询需求描述
            mode: 当前模式，仅接受 "query" 或 "report"

        Returns:
            包含 plan_steps 和 execution_strategy 的查询计划
        """
        logger.info(
            "complex_query_planner_start",
            mode=mode,
            query_length=len(query_description)
        )

        if mode not in ["query", "report"]:
            return {
                "success": False,
                "error": f"不支持的模式: {mode}，仅支持 query 和 report",
                "summary": f"模式参数错误: {mode}"
            }

        tools_schemas = self._get_available_tools_schemas(mode)
        prompt = self._build_planning_prompt(query_description, mode, tools_schemas)

        try:
            plan = await self._generate_plan_with_llm(prompt)
        except Exception as e:
            logger.error("complex_query_planner_llm_failed", error=str(e))
            return {
                "success": False,
                "error": f"LLM调用失败: {str(e)}",
                "summary": "查询计划生成失败"
            }

        validated_plan = self._validate_plan(plan, tools_schemas)

        step_count = len(validated_plan.get("plan_steps", []))
        logger.info("complex_query_planner_done", steps=step_count, mode=mode)

        return {
            "success": True,
            "data": {"plan": validated_plan},
            "summary": f"生成了{step_count}步查询计划"
        }

    def _get_available_tools_schemas(self, mode: str) -> Dict[str, Any]:
        """获取该模式下可用工具的完整 schema"""
        tool_names = MODE_TOOLS.get(mode, [])
        return {
            name: GUANGDONG_QUERY_TOOLS_SCHEMAS[name]
            for name in tool_names
            if name in GUANGDONG_QUERY_TOOLS_SCHEMAS
        }

    def _format_tools_schemas(self, tools_schemas: Dict[str, Any]) -> str:
        """将工具 schema 格式化为可读文本"""
        parts = []
        for name, schema in tools_schemas.items():
            parts.append(json.dumps(schema, ensure_ascii=False, indent=2))
        return "\n\n".join(parts)

    def _build_planning_prompt(
        self,
        query_description: str,
        mode: str,
        tools_schemas: Dict[str, Any]
    ) -> str:
        """构建查询计划提示词，注入系统当前时间"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return PLANNING_PROMPT_TEMPLATE.format(
            current_time=current_time,
            query_description=query_description,
            mode=mode,
            tools_schemas=self._format_tools_schemas(tools_schemas)
        )

    async def _generate_plan_with_llm(self, prompt: str) -> Dict[str, Any]:
        """调用LLM生成查询计划"""
        from app.services.llm_service import llm_service
        from app.utils.llm_response_parser import LLMResponseParser

        raw_response = await llm_service.call_llm_with_json_response(prompt)

        # call_llm_with_json_response 已经返回解析后的 dict
        if isinstance(raw_response, dict):
            return raw_response

        # 如果返回字符串，尝试解析
        parser = LLMResponseParser()
        parsed = parser.parse(str(raw_response))
        if parsed:
            return parsed

        raise ValueError(f"无法解析LLM响应: {str(raw_response)[:200]}")

    def _validate_plan(
        self,
        plan: Dict[str, Any],
        tools_schemas: Dict[str, Any]
    ) -> Dict[str, Any]:
        """验证计划的工具存在性和必需参数完整性"""
        if not isinstance(plan, dict):
            return {"plan_steps": [], "execution_strategy": {"parallel_groups": [], "estimated_steps": 0}, "error": "计划格式无效"}

        plan_steps = plan.get("plan_steps", [])
        valid_steps = []
        warnings = []

        for step in plan_steps:
            if not isinstance(step, dict):
                continue

            tool_name = step.get("tool", "")
            params = step.get("params", {})

            # 检查工具是否存在
            if tool_name not in tools_schemas:
                warnings.append(f"步骤{step.get('step', '?')}: 工具 '{tool_name}' 不在可用列表中，已跳过")
                continue

            # 检查必需参数
            schema = tools_schemas[tool_name]
            required_params = schema.get("parameters", {}).get("required", [])
            missing = [p for p in required_params if p not in params]
            if missing:
                warnings.append(f"步骤{step.get('step', '?')}: 工具 '{tool_name}' 缺少必需参数 {missing}")
                # 仍然保留该步骤，让主Agent决定如何处理

            valid_steps.append(step)

        result = {
            "plan_steps": valid_steps,
            "execution_strategy": plan.get("execution_strategy", {
                "parallel_groups": [],
                "estimated_steps": len(valid_steps)
            })
        }

        if warnings:
            result["warnings"] = warnings

        return result
