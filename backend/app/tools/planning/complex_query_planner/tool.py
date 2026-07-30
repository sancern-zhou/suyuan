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
from pathlib import Path

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()

PLANNER_DIR = Path(__file__).resolve().parent
QUERY_TOOLS_GUIDE_PATH = PLANNER_DIR / "query_tools_guide.md"
QUERY_TOOL_METADATA_PATH = PLANNER_DIR / "query_tool_metadata.json"


# 广东省查询工具的完整 function_schema 定义
GUANGDONG_QUERY_TOOLS_SCHEMAS = {
    "query_city_standard_report": {
        "name": "query_city_standard_report",
        "description": """
查询广东省城市统计报表接口，直接使用联网接口返回的新/旧国标统计结果，不进行本地日报重算。

【标准参数】
- ns_type=2：新国标
- ns_type=1：旧国标
- ns_type 不传时按查询时段自动选择默认标准：2025-01-01 之前默认旧国标，2025-01-01 及之后默认新国标；跨 2025-01-01 时工具自动拆成旧国标、新国标两次查询并合并返回分段结果
- 2025-01-01 之前接口只有旧标准数据，指定 ns_type=2 查询 2025 年前时段通常无数据返回；用户未明确要求新标准时不要对 2025 年前时段传 ns_type=2

【使用场景】
- 综合指数、达标天数、超标天数、优良率、重污染天数
- SO2、NO2、PM10、PM2.5、CO、O3_8H等统计浓度
- 首要污染物天数/比例、排名等接口报表字段

【返回数据】
- data：默认报告口径数据，已按信息公开口径处理 PM2.5 等展示字段；若 metadata.data_is_complete_for_requested_scope=true，直接用 data 作答，不再读取 read_data_registry
- report_data_id：完整接口报表；read_data_registry(data_id) 默认读取 reporting 报告口径视图
- raw/result：原始接口字段视图，仅用于追溯接口字段
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市列表，如 ['广州', '深圳']；可传广东省、全省、珠三角等区域别名"
                },
                "start_time": {"type": "string", "description": "开始时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                "end_time": {"type": "string", "description": "结束时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                "ns_type": {"type": "integer", "description": "2=新国标，1=旧国标；不传时按查询时段自动选择，2025-01-01 前旧国标，2025-01-01 及之后新国标；跨 2025-01-01 时工具自动拆分两次查询并合并返回。2025-01-01 之前接口只有旧标准数据，指定 ns_type=2 查询 2025 年前时段通常无数据返回。", "enum": [1, 2]},
                "time_type": {"type": "integer", "description": "3周报、4月报、5季报、7年报、8任意时间，默认8"},
                "pollutant_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "接口字段过滤列表，如 ['so2','compositeIndex']；默认不传/为空，接口返回全部字段。仅当需要主动筛选字段时传入"
                },
                "data_source": {"type": "integer", "description": "0原始实况，1审核实况，2原始标况，3审核标况，默认1"},
                "sand_type": {"type": "integer", "description": "0不扣沙，1扣沙，默认1"}
            },
            "required": ["start_time", "end_time"]
        }
    },
    "query_city_standard_yoy_report": {
        "name": "query_city_standard_yoy_report",
        "description": """
查询广东省城市同比/环比统计报表接口，直接使用联网接口返回的新/旧国标对比结果，不进行本地统计重算或本地同比计算。

【标准参数】
- ns_type=2：新国标
- ns_type=1：旧国标

【使用场景】
- 同比、环比、双时段对比、变化率、改善/恶化分析
- 综合指数、优良天数、达标率、重污染天数、SO2/NO2/PM10/PM2.5/CO/O3_8H等指标的当前值、对比值、增幅、排名

【接口说明】
- 当前时段使用 time_point
- 对比时段使用 contrast_time
- 内部调用 GetReportForRangeCompareListFilterAsync，并透传 nsType
        """.strip(),
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "城市列表，如 ['广州', '深圳']；可传广东省、全省、珠三角等区域别名"
                },
                "time_point": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "当前时间范围，如 ['2026-05-08 00:00:00','2026-05-14 00:00:00']"
                },
                "contrast_time": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "对比时间范围，如 ['2025-05-08 00:00:00','2025-05-14 00:00:00']"
                },
                "ns_type": {"type": "integer", "description": "2=新国标，1=旧国标", "enum": [1, 2]},
                "time_type": {"type": "integer", "description": "4月报、8任意时间，默认8"},
                "pollutant_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "接口字段过滤列表，如 ['so2']；默认不传/为空，接口返回全部字段。仅当需要主动筛选字段时传入"
                },
                "data_source": {"type": "integer", "description": "0原始实况，1审核实况，2原始标况，3审核标况，默认1"},
                "sand_type": {"type": "integer", "description": "0不扣沙，1扣沙，默认1"}
            },
            "required": ["time_point", "contrast_time"]
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
  - 可在图表模式中通过 execute_echarts_python 生成交互式图表
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
- working_order_details: 运维工单详情表（18802条，可通过 WORKINGORDERCODE 与 working_orders 关联）
- base_station: 站点基础信息（331条，可与 qc_history/working_orders 按站点字段关联）
- base_station_sup: 上级站点基础信息（100条）
- base_device: 设备基础信息（2606条，可与 working_orders 的 DEVICEID 相关字段关联）
- base_user_station: 用户-站点关联（3632条）
- base_department_station: 部门-站点关联（511条）
- base_contract_station: 合同-站点关联（1175条）

【⚠️ 重要：168城市排名查询规范】
- 168城市排名已拆分为两个表：新标准查询 city_168_statistics_new_standard，旧标准查询 city_168_statistics_old_standard
- 表中已预计算排名，直接使用 comprehensive_index_rank 等字段，无需使用窗口函数
- ❌ 禁止同时调用 query_city_standard_report + execute_sql_query 查询同一批城市统计口径
- ❌ 广东省城市报表（query_city_standard_report）只包含省内21个城市数据，无法用于168城市排名
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
                    "description": "查看表结构（与sql参数二选一）。输入目标表名，如 'city_168_statistics_new_standard'、'city_168_statistics_old_standard'、'qc_history'、'working_orders'、'working_order_details'、'base_station' 或 'base_device'。工具会动态从数据库获取该表的结构信息，包括字段名、数据类型、长度、是否可空等。"
                },
                "sql": {
                    "type": "string",
                    "description": "SQL查询语句（与describe_table参数二选一）。输入完整的SQL SELECT查询语句。中文字符串必须使用N前缀，如 WHERE StationName LIKE N'%增城%'"
                },
                "database": {
                    "type": "string",
                    "description": "数据库名称（可选）。默认为'XcAiDb'，查询质控、工单、base_* 基础表时使用'AirPollutionAnalysis'。",
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
    "query_station_standard_report": {
        "name": "query_station_standard_report",
        "description": "查询广东省站点新/旧国标统计报表，直接调用联网接口，不本地重算。ns_type=2新国标，ns_type=1旧国标；cities会按station_type展开站点，也可直接传stations或站点编码。data和read_data_registry(data_id)默认使用reporting报告口径视图。",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {"type": "array", "items": {"type": "string"}, "description": "城市列表，如['广州']或['广州市']；自动映射为该城市下辖站点编码"},
                "stations": {"type": "array", "items": {"type": "string"}, "description": "站点名称或站点编码列表，如['麓湖']或['1001A']"},
                "station_type": {"type": "string", "description": "站点类型，仅cities时生效，用于筛选下辖站点；默认国控，常用值：国控、省控、市控"},
                "start_time": {"type": "string", "description": "开始时间，YYYY-MM-DD或YYYY-MM-DD HH:MM:SS"},
                "end_time": {"type": "string", "description": "结束时间，YYYY-MM-DD或YYYY-MM-DD HH:MM:SS"},
                "ns_type": {"type": "integer", "description": "2=新国标，1=旧国标", "enum": [1, 2]}
            },
            "required": ["start_time", "end_time"]
        }
    },
    "query_station_standard_yoy_report": {
        "name": "query_station_standard_yoy_report",
        "description": "查询广东省站点新/旧国标同比、环比或双时段对比统计报表，直接调用联网接口，不本地计算变化率。data和read_data_registry(data_id)默认使用reporting报告口径视图。",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {"type": "array", "items": {"type": "string"}, "description": "城市列表，如['广州']或['广州市']；自动映射为该城市下辖站点编码"},
                "stations": {"type": "array", "items": {"type": "string"}, "description": "站点名称或站点编码列表，如['麓湖']或['1001A']"},
                "station_type": {"type": "string", "description": "站点类型，仅cities时生效，用于筛选下辖站点；默认国控，常用值：国控、省控、市控"},
                "time_point": {"type": "array", "items": {"type": "string"}, "description": "当前时间范围"},
                "contrast_time": {"type": "array", "items": {"type": "string"}, "description": "对比时间范围"},
                "ns_type": {"type": "integer", "description": "2=新国标，1=旧国标", "enum": [1, 2]}
            },
            "required": ["time_point", "contrast_time"]
        }
    },
    "query_gd_suncere_district_report": {
        "name": "query_gd_suncere_district_report",
        "description": "查询广东省区县统计报表数据，支持月度(time_type=4)、年度(time_type=7)、任意时段(time_type=8，默认)。支持区县名称/编码，也支持按城市展开下辖区县。",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {"type": "array", "items": {"type": "string"}, "description": "城市列表，如 ['广州', '深圳']；会展开为下辖区县"},
                "districts": {"type": "array", "items": {"type": "string"}, "description": "区县名称列表，如 ['天河区', '福田区']"},
                "district_codes": {"type": "array", "items": {"type": "string"}, "description": "区县编码列表"},
                "start_time": {"type": "string", "description": "开始时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                "end_time": {"type": "string", "description": "结束时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                "time_type": {"type": "integer", "description": "4=月度，7=年度，8=任意时段（默认）", "enum": [4, 7, 8], "default": 8},
                "area_type": {"type": "integer", "description": "区域类型，1=行政区（默认）", "default": 1},
                "cal_area_type": {"type": "integer", "description": "计算区域类型，0=默认", "default": 0},
                "data_source": {"type": "integer", "description": "0=原始实况，1=审核实况（默认）", "enum": [0, 1], "default": 1},
                "ns_type": {"type": "integer", "description": "2=新国标（默认），1=旧国标", "enum": [1, 2], "default": 2},
                "sand_type": {"type": "integer", "description": "0=不扣沙，1=扣沙（默认）", "enum": [0, 1], "default": 1}
            },
            "required": ["start_time", "end_time"]
        }
    },
    "query_gd_suncere_city_hour": {
        "name": "query_gd_suncere_city_hour",
        "description": "查询广东省城市小时数据，用于小时级时间序列分析、污染过程解析。返回标准化的空气质量数据，包含data_id用于完整数据访问。",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {"type": "array", "items": {"type": "string"}, "description": "城市列表，如 ['广州', '深圳']；可传广东省、全省等区域别名"},
                "start_time": {"type": "string", "description": "开始时间，YYYY-MM-DD HH:MM:SS"},
                "end_time": {"type": "string", "description": "结束时间，YYYY-MM-DD HH:MM:SS"},
                "data_source": {"type": "integer", "description": "0=原始实况，1=审核实况（默认）", "enum": [0, 1], "default": 1},
                "ns_type": {"type": "integer", "description": "2=新国标（默认），1=旧国标", "enum": [1, 2], "default": 2}
            },
            "required": ["cities", "start_time", "end_time"]
        }
    },
    "query_gd_suncere_city_day": {
        "name": "query_gd_suncere_city_day",
        "description": "查询广东省城市日数据，通过ns_type参数选择新/旧国标。用于日报分析、月度统计汇总。返回标准化的空气质量数据，包含data_id用于完整数据访问。",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {"type": "array", "items": {"type": "string"}, "description": "城市列表，如 ['广州', '深圳']；可传广东省、全省等区域别名"},
                "start_time": {"type": "string", "description": "开始时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                "end_time": {"type": "string", "description": "结束时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                "data_source": {"type": "integer", "description": "0=原始实况，1=审核实况（默认）", "enum": [0, 1], "default": 1},
                "ns_type": {"type": "integer", "description": "2=新国标（默认），1=旧国标", "enum": [1, 2], "default": 2},
                "sand_type": {"type": "integer", "description": "0=不扣沙，1=扣沙（默认）", "enum": [0, 1], "default": 1}
            },
            "required": ["cities", "start_time", "end_time"]
        }
    },
    "query_gd_suncere_district_day": {
        "name": "query_gd_suncere_district_day",
        "description": "查询广东省区县日数据，支持区县名称/编码查询，也支持按城市展开下辖区县。返回标准化的空气质量数据，包含data_id用于完整数据访问。",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {"type": "array", "items": {"type": "string"}, "description": "城市列表，如 ['广州']；会展开为下辖区县"},
                "districts": {"type": "array", "items": {"type": "string"}, "description": "区县名称列表，如 ['天河区', '福田区']"},
                "district_codes": {"type": "array", "items": {"type": "string"}, "description": "区县编码列表"},
                "start_time": {"type": "string", "description": "开始时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                "end_time": {"type": "string", "description": "结束时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                "data_source": {"type": "integer", "description": "0=原始实况，1=审核实况（默认）", "enum": [0, 1], "default": 1},
                "ns_type": {"type": "integer", "description": "2=新国标（默认），1=旧国标", "enum": [1, 2], "default": 2},
                "sand_type": {"type": "integer", "description": "0=不扣沙，1=扣沙（默认）", "enum": [0, 1], "default": 1}
            },
            "required": ["start_time", "end_time"]
        }
    },
    "get_vocs_data": {
        "name": "get_vocs_data",
        "description": "查询VOCs组分数据，用于VOCs组分分析、臭氧生成潜势(OFP)计算、源解析(PMF)等。返回标准化的VOCs样品数据，包含data_id用于完整数据访问。",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {"type": "array", "items": {"type": "string"}, "description": "城市列表，如 ['广州', '深圳']"},
                "stations": {"type": "array", "items": {"type": "string"}, "description": "站点列表，如 ['麓湖站', '万顷沙站']"},
                "start_time": {"type": "string", "description": "开始时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                "end_time": {"type": "string", "description": "结束时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"}
            },
            "required": ["start_time", "end_time"]
        }
    },
    "get_pm25_ionic": {
        "name": "get_pm25_ionic",
        "description": "查询PM2.5离子组分数据（SO42-、NO3-、NH4+、K+、Na+、Ca2+、Mg2+等），用于二次气溶胶分析、源解析(PMF)等。返回标准化的颗粒物样品数据，包含data_id用于完整数据访问。",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {"type": "array", "items": {"type": "string"}, "description": "城市列表，如 ['广州', '深圳']"},
                "stations": {"type": "array", "items": {"type": "string"}, "description": "站点列表，如 ['麓湖站', '万顷沙站']"},
                "start_time": {"type": "string", "description": "开始时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                "end_time": {"type": "string", "description": "结束时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"}
            },
            "required": ["start_time", "end_time"]
        }
    },
    "get_pm25_carbon": {
        "name": "get_pm25_carbon",
        "description": "查询PM2.5碳组分数据（OC、EC等），用于碳质气溶胶分析、二次有机碳(SOC)估算、源解析(PMF)等。返回标准化的颗粒物样品数据，包含data_id用于完整数据访问。",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {"type": "array", "items": {"type": "string"}, "description": "城市列表，如 ['广州', '深圳']"},
                "stations": {"type": "array", "items": {"type": "string"}, "description": "站点列表，如 ['麓湖站', '万顷沙站']"},
                "start_time": {"type": "string", "description": "开始时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                "end_time": {"type": "string", "description": "结束时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"}
            },
            "required": ["start_time", "end_time"]
        }
    },
    "get_pm25_crustal": {
        "name": "get_pm25_crustal",
        "description": "查询PM2.5地壳元素组分数据（Si、Al、Ca、Fe、Ti等），用于扬尘源解析、地壳元素分析等。返回标准化的颗粒物样品数据，包含data_id用于完整数据访问。",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {"type": "array", "items": {"type": "string"}, "description": "城市列表，如 ['广州', '深圳']"},
                "stations": {"type": "array", "items": {"type": "string"}, "description": "站点列表，如 ['麓湖站', '万顷沙站']"},
                "start_time": {"type": "string", "description": "开始时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                "end_time": {"type": "string", "description": "结束时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"}
            },
            "required": ["start_time", "end_time"]
        }
    },
    "get_weather_forecast": {
        "name": "get_weather_forecast",
        "description": "查询气象预报数据，用于气象条件分析、污染过程预报、轨迹分析等。返回ERA5预报数据或GFS预报数据。",
        "parameters": {
            "type": "object",
            "properties": {
                "cities": {"type": "array", "items": {"type": "string"}, "description": "城市列表，如 ['广州', '深圳']"},
                "start_time": {"type": "string", "description": "开始时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                "end_time": {"type": "string", "description": "结束时间，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"},
                "data_source": {"type": "string", "description": "数据源，era5或gfs", "enum": ["era5", "gfs"], "default": "era5"}
            },
            "required": ["start_time", "end_time"]
        }
    },
    "query_national_province_air_quality": {
        "name": "query_national_province_air_quality",
        "description": "查询全国省份空气质量统计数据，返回六参数均值、综合指数SumIndex和AQI达标率。用于省份排名、区域对比和达标率统计；数据来源为全国发布数据，-99表示缺失。",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "开始日期，格式 'YYYY-MM-DD'"},
                "end_date": {"type": "string", "description": "结束日期，格式 'YYYY-MM-DD'"},
                "ns_type": {"type": "string", "description": "数据类型，默认NS", "enum": ["NS", "NSDay", "OldNS"], "default": "NS"}
            },
            "required": ["start_date", "end_date"]
        }
    },
    "query_national_city_air_quality": {
        "name": "query_national_city_air_quality",
        "description": "查询全国城市空气质量统计数据，返回六参数均值、综合指数SumIndex和AQI达标率。用于城市排名、区域对比和达标率统计；数据来源为全国发布数据，-99表示缺失。",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "开始日期，格式 'YYYY-MM-DD'"},
                "end_date": {"type": "string", "description": "结束日期，格式 'YYYY-MM-DD'"},
                "ns_type": {"type": "string", "description": "数据类型，默认NS", "enum": ["NS", "NSDay", "OldNS"], "default": "NS"}
            },
            "required": ["start_date", "end_date"]
        }
    }
}

# 各模式可用的工具名称
MODE_TOOLS = {
    "query": [
        "query_city_standard_report",
        "query_city_standard_yoy_report",
        "query_xcai_city_history",
        "execute_sql_query",
        "query_station_standard_report",
        "query_station_standard_yoy_report",
        "query_gd_suncere_district_report",
        "query_gd_suncere_city_hour",
        "query_gd_suncere_city_day",
        "query_gd_suncere_district_day",
        "get_vocs_data",
        "get_pm25_ionic",
        "get_pm25_carbon",
        "get_pm25_crustal",
        "get_weather_forecast",
        "query_national_province_air_quality",
        "query_national_city_air_quality",
    ],
    "report": [
        "query_city_standard_report",
        "query_city_standard_yoy_report",
        "query_xcai_city_history",
        "execute_sql_query",
        "query_station_standard_report",
        "query_station_standard_yoy_report",
        "query_gd_suncere_district_report",
        "query_gd_suncere_city_hour",
        "query_gd_suncere_city_day",
        "query_gd_suncere_district_day",
        "get_vocs_data",
        "get_pm25_ionic",
        "get_pm25_carbon",
        "get_pm25_crustal",
        "get_weather_forecast",
        "query_national_province_air_quality",
        "query_national_city_air_quality",
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

## 查询工具策略手册
{query_tools_guide}

## 查询工具结构化元数据
{query_tool_metadata}

## 输出要求
生成JSON格式的查询计划，包含：
1. plan_steps: 步骤列表，每步包含 step(int), tool(str), params(dict), reasoning(str), dependencies(list[int])
2. execution_strategy: 执行策略，包含 parallel_groups(list[list[int]]), estimated_steps(int)
3. result_usage: 说明主Agent执行计划后应读取哪些返回字段路径，以及不要读取哪些字段
4. field_paths: 按工具列出关键结果字段路径
5. warnings: 风险提示或常见误用提醒（如适用）

## 约束条件
- 只能从可用工具列表中选择工具
- 必需参数不能缺失
- 无依赖关系的步骤应放入同一并发组
- 时间范围保持一致
- 如果需求信息不足（如缺少时间范围），在 plan_steps 中说明并返回 error 字段
- 优先使用新标准工具（带 _new 后缀的工具）
- **广东省数据查询优先接口工具**：用户查询广东省、广东省内城市、区县、站点或区域统计数据时，优先调用联网接口查询工具（如 query_city_standard_report、query_city_standard_yoy_report、query_station_standard_report、query_gd_suncere_district_report 等）；不要优先使用 execute_sql_query 查询 SQL 原始表，因为 SQL 数据可能是未经审核数据。只有接口工具无法覆盖全国排名、预计算统计表字段、复杂 JOIN 或白名单表专项查询时，才考虑 execute_sql_query，并在 reasoning/warnings 中说明原因。
- **区域名称默认按区域统计**：用户查询“珠三角”“非珠三角”“粤东”“粤西”“粤北”“粤东西北”等区域时，一般指查询区域统计指标，应将区域名称作为区域/城市参数传给支持区域别名的接口工具，获取区域汇总统计；不要默认展开为下辖地市逐市查询，除非用户明确要求“各地市”“城市明细”“下辖城市分别统计”。
- **月度/年度 time_type 要求**：用户明确需要月度数据、月报、按月统计时，调用支持 time_type 的统计报表工具必须设置 `time_type=4`；用户明确需要年度数据、年报、全年统计或年累计统计时，必须设置 `time_type=7`。不要把默认 `time_type=8` 的任意时段累计结果误当成月度或年度报表结果。
- **简洁性原则**：选择最简洁的工具调用计划，避免不必要的重复查询
  - 如果一个工具能够满足需求，不要调用多个功能相似的工具
  - 优先使用功能完整的工具（如 query_city_standard_report 已包含接口统计报表，无需再调用 query_gd_suncere_city_day_new 获取日报后本地计算）
  - 避免同时查询新旧标准数据，除非用户明确需要对比
  - 合理利用工具的返回数据（如 result 字段已包含统计汇总，无需再从 data_id 读取计算）
  - **避免城市范围重复查询**：如果查询了更大范围的城市集合，就不要再单独查询其子集
    - ❌ 错误：先查询4个城市（清远、茂名、东莞、湛江），再查询全省21个城市
    - ✅ 正确：只查询全省21个城市，从中提取4个城市的数据
  - **避免时间段重复查询**：需要城市同比/环比时，优先用 query_city_standard_yoy_report 一次调用联网对比报表接口；不要再查询日报后重算统计指标
- **SQL查询支持**：execute_sql_query 支持CTE（WITH子句）、窗口函数（ROW_NUMBER、RANK等）、复杂JOIN查询，可用于计算排名、同比环比等。但168城市排名数据已预计算在表中，直接查询排名字段即可，无需使用窗口函数
- **同环比查询要求**：当用户需求涉及"下降"、"上升"、"同比"、"环比"、"变化"、"趋势"、"改善"、"恶化"等城市统计报表查询时，使用 query_city_standard_yoy_report 获取接口对比结果；不得重新计算空气质量统计指标或本地同比
  - ❌ 错误：查询"广州今年空气质量相比去年是否下降"时，调用日报工具后本地计算统计指标
  - ✅ 正确：调用 query_city_standard_yoy_report 传入 time_point、contrast_time 和 ns_type（新国标=2，旧国标=1）
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
                "sql": "SELECT city_name, stat_date, comprehensive_index, comprehensive_index_rank FROM city_168_statistics_new_standard WHERE stat_type = 'annual_ytd' AND stat_date = '2025-01-01' AND city_name IN (N'广州', N'深圳', N'珠海', N'佛山', N'东莞', N'中山', N'江门', N'惠州', N'肇庆') ORDER BY city_name",
                "database": "XcAiDb",
                "limit": 100
            }},
            "reasoning": "直接查询168城市新标准预计算排名数据，限定年度累计统计类型和2025年统计日期，一次查询获取珠三角9个城市的新标准综合指数及排名，无需使用窗口函数或广东省内报表接口代替全国排名",
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
            "tool": "query_city_standard_report",
            "params": {{"cities": ["广州"], "start_time": "2025-01-01", "end_time": "2025-01-31", "ns_type": 2, "time_type": 4, "data_source": 1, "sand_type": 1}},
            "reasoning": "查询广东联网新国标城市月度统计报表接口，time_type=4明确按月报口径返回，data_source=1使用审核实况，sand_type=1使用扣沙口径；未传pollutant_codes表示返回全部统计字段",
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
            description=(
                "复杂查询计划工具。多时间段/多城市分组/不确定工具选择/需要3个以上工具组合时调用。"
                "注意统计报表工具只返回累计结果；月度统计应先查日数据再聚合。"
                "查询计划在返回的data.plan中，按plan_steps执行即可。"
            ),
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
        guide_text = self._load_query_tools_guide()
        metadata = self._load_query_tool_metadata(mode)
        prompt = self._build_planning_prompt(
            query_description,
            mode,
            tools_schemas,
            guide_text,
            metadata
        )

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

    def _load_query_tools_guide(self) -> str:
        """读取复杂查询策略手册，供内部LLM按需使用"""
        try:
            return QUERY_TOOLS_GUIDE_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("complex_query_planner_guide_missing", path=str(QUERY_TOOLS_GUIDE_PATH))
            return "查询工具策略手册未找到，请仅依据工具schema生成保守查询计划。"

    def _load_query_tool_metadata(self, mode: str) -> Dict[str, Any]:
        """读取并按当前模式裁剪查询工具元数据"""
        try:
            metadata = json.loads(QUERY_TOOL_METADATA_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            logger.warning("complex_query_planner_metadata_missing", path=str(QUERY_TOOL_METADATA_PATH))
            return {}
        except json.JSONDecodeError as e:
            logger.warning("complex_query_planner_metadata_invalid", error=str(e))
            return {}

        tool_names = set(MODE_TOOLS.get(mode, []))
        tools = metadata.get("tools", {})
        if isinstance(tools, dict):
            metadata = {
                **metadata,
                "tools": {
                    name: details
                    for name, details in tools.items()
                    if name in tool_names
                }
            }
        return metadata

    def _build_planning_prompt(
        self,
        query_description: str,
        mode: str,
        tools_schemas: Dict[str, Any],
        query_tools_guide: str,
        query_tool_metadata: Dict[str, Any]
    ) -> str:
        """构建查询计划提示词，注入系统当前时间"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return PLANNING_PROMPT_TEMPLATE.format(
            current_time=current_time,
            query_description=query_description,
            mode=mode,
            tools_schemas=self._format_tools_schemas(tools_schemas),
            query_tools_guide=query_tools_guide,
            query_tool_metadata=json.dumps(query_tool_metadata, ensure_ascii=False, indent=2)
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

        for key in [
            "result_usage",
            "field_paths",
            "tool_selection_reason",
            "sql_notes",
            "reasoning_summary",
            "error"
        ]:
            if key in plan:
                result[key] = plan[key]

        if warnings:
            result["warnings"] = [*plan.get("warnings", []), *warnings]
        elif "warnings" in plan:
            result["warnings"] = plan["warnings"]

        return result
