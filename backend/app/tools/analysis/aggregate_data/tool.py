"""
数据聚合分析工具

对查询结果进行聚合计算，支持多种聚合函数和分组方式。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
from datetime import datetime
import math
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.db.database import async_session
from app.agent.context.data_context_manager import DataContextManager
from app.utils.rounding_rules import apply_rounding, ROUNDING_PRECISION
from app.utils.percentile_calculator import calculate_percentile
from app.utils.o3_calculator import calculate_o3_8h_max, calculate_o3_8h_max_for_group

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


# =============================================================================
# 空气质量指数计算常量（基于 HJ 633-2024 新标准）
# =============================================================================

# 新标准IAQI分段表（HJ 633-2024）
# IAQI 分段断点表：[浓度限值, IAQI值]
# 浓度单位：μg/m³（CO为mg/m³）
IAQI_BREAKPOINTS_NEW = {
    'SO2': [        # SO2 日平均
        (0, 0), (50, 50), (150, 100), (475, 150),
        (800, 200), (1600, 300), (2100, 400), (2620, 500)
    ],
    'NO2': [        # NO2 日平均
        (0, 0), (40, 50), (80, 100), (180, 150),
        (280, 200), (565, 300), (750, 400), (940, 500)
    ],
    'PM10': [       # PM10 日平均（新标准，收严）
        (0, 0), (50, 50), (120, 100), (250, 150),
        (350, 200), (420, 300), (500, 400), (600, 500)
    ],
    'CO': [         # CO 日平均（mg/m³）
        (0, 0), (2, 50), (4, 100), (14, 150),
        (24, 200), (36, 300), (48, 400), (60, 500)
    ],
    'O3_8h': [      # O3 日最大8小时平均
        (0, 0), (100, 50), (160, 100), (215, 150),
        (265, 200), (800, 300)  # 浓度 > 800 时，IAQI 固定为 300
    ],
    'PM2_5': [      # PM2.5 日平均（新标准 HJ 633，仅IAQI=100收严）
        (0, 0), (35, 50), (60, 100), (115, 150),
        (150, 200), (250, 300), (350, 400), (500, 500)
    ]
}

# 用于年均综合指数计算的标准限值（新标准）
ANNUAL_STANDARD_LIMITS = {
    'PM2_5': 30,   # 年平均二级标准（新标准收严：35→30）
    'PM10': 60,    # 年平均二级标准（新标准收严：70→60）
    'SO2': 60,     # 年平均二级标准
    'NO2': 40,     # 年平均二级标准
    'CO': 4,       # 24小时平均二级标准（mg/m³）
    'O3_8h': 160   # 日最大8小时平均二级标准
}

# 污染物列名映射（支持多种命名格式）
POLLUTANT_COLUMN_MAP = {
    'PM2_5': ['pm2_5', 'pm25', 'PM2_5', 'PM2.5', 'PM25',
              'measurements.pm2_5', 'measurements.PM2_5', 'measurements.PM2.5', 'measurements.PM25'],  # 添加嵌套字段
    'PM10': ['pm10', 'PM10', 'PM10',
             'measurements.pm10', 'measurements.PM10'],  # 添加嵌套字段
    'SO2': ['so2', 'SO2', 'SO2',
            'measurements.so2', 'measurements.SO2'],  # 添加嵌套字段
    'NO2': ['no2', 'NO2', 'NO2',
            'measurements.no2', 'measurements.NO2'],  # 添加嵌套字段
    'CO': ['co', 'CO', 'CO',
           'measurements.co', 'measurements.CO'],  # 添加嵌套字段
    'O3_8h': ['o3_8h', 'o3', 'O3_8h', 'O3', 'O3',
              'measurements.o3_8h', 'measurements.o3', 'measurements.O3_8h', 'measurements.O3']  # 添加嵌套字段
}


# =============================================================================
# 空气质量指数计算辅助函数
# =============================================================================

def safe_round_for_index(value: float, precision: int) -> float:
    """
    通用修约函数（四舍六入五成双）

    使用Decimal进行精确修约，避免浮点数精度问题

    Args:
        value: 原始值
        precision: 保留的小数位数

    Returns:
        修约后的值
    """
    if value is None:
        return 0.0

    from decimal import Decimal, ROUND_HALF_EVEN

    # 将浮点数转换为字符串再转换为Decimal，避免浮点数精度问题
    value_str = format(value, f'.{precision + 5}f').rstrip('0').rstrip('.')
    decimal_value = Decimal(value_str)

    # 构造修约单位（如0.01表示保留2位小数）
    quantize_unit = Decimal('0.' + '0' * precision) if precision > 0 else Decimal('1')

    # 使用ROUND_HALF_EVEN进行修约
    rounded = decimal_value.quantize(quantize_unit, rounding=ROUND_HALF_EVEN)

    return float(rounded)


def calculate_iaqi_for_aggregate(concentration: float, pollutant: str) -> int:
    """
    计算污染物的空气质量分指数（IAQI）

    使用分段线性插值公式：
    IAQIP = (IAQIHi - IAQILo) / (BPHi - BPLo) × (CP - BPLo) + IAQILo

    特殊情况：
    - O3_8h 浓度 > 800 时，IAQI 固定为 300（最高值）

    Args:
        concentration: 污染物浓度值（μg/m³，CO为mg/m³）
        pollutant: 污染物名称（'SO2', 'NO2', 'PM10', 'CO', 'O3_8h', 'PM2_5'）

    Returns:
        IAQI值（整数）
    """
    # 确保concentration是数值类型（处理API返回的字符串类型）
    if concentration is None or concentration == '' or concentration == '-':
        return 0
    try:
        concentration = float(concentration)
    except (TypeError, ValueError):
        return 0

    if concentration <= 0:
        return 0

    # O3_8h 特殊处理：浓度 > 800 时，IAQI 固定为 300
    if pollutant == 'O3_8h' and concentration > 800:
        return 300

    # 选择对应的分段标准表
    breakpoints = IAQI_BREAKPOINTS_NEW.get(pollutant, [])
    if not breakpoints:
        return 0

    # 找到浓度所在的分段
    for i in range(len(breakpoints) - 1):
        bp_lo, iaqi_lo = breakpoints[i]
        bp_hi, iaqi_hi = breakpoints[i + 1]

        if bp_lo <= concentration <= bp_hi:
            # 使用分段线性插值公式计算IAQI
            if bp_hi == bp_lo:  # 防止除零
                return iaqi_hi
            iaqi = (iaqi_hi - iaqi_lo) / (bp_hi - bp_lo) * (concentration - bp_lo) + iaqi_lo
            return math.ceil(iaqi)  # 向上进位取整数

    # 浓度超过最高分段，返回最高IAQI
    return breakpoints[-1][1]


class AggregateDataTool(LLMTool):
    """数据聚合分析工具"""

    # 支持的聚合函数
    AGGREGATION_FUNCTIONS = {
        'SUM': '求和',
        'AVG': '平均值',
        'MAX': '最大值',
        'MIN': '最小值',
        'COUNT': '计数',
        'STDDEV': '标准差',
        'VAR': '方差',
        'MEDIAN': '中位数',
        'PERCENTILE': '百分位数',
        'O3_8H_MAX': 'O3日最大8小时平均',
        'IAQI': '空气质量分指数',
        'AQI': '空气质量指数',
        'SINGLE_INDEX': '单项指数',
        'COMPREHENSIVE_INDEX': '综合指数',
        'PRIMARY_POLLUTANT': '首要污染物'
    }

    # 时间粒度映射
    TIME_GRANULARITY = {
        'hour': 'hour',
        'day': 'day',
        'month': 'month',
        'year': 'year'
    }

    def __init__(self) -> None:
        function_schema = {
            "name": "aggregate_data",
            "description": (
                "【数据聚合分析工具】对查询结果进行聚合计算和统计分析。\n"
                "\n"
                "**支持15种聚合函数：**\n"
                "- 基础统计：SUM、AVG、MAX、MIN、COUNT、STDDEV、VAR、MEDIAN、PERCENTILE、O3_8H_MAX\n"
                "- 空气质量指数：IAQI（空气质量分指数）、AQI（空气质量指数）、PRIMARY_POLLUTANT（首要污染物）\n"
                "- 质量指数：SINGLE_INDEX（单项指数）、COMPREHENSIVE_INDEX（综合指数）\n"
                "\n"
                "**日期过滤功能（重要）：**\n"
                "- 使用start_date和end_date参数可以只计算指定日期范围的数据\n"
                "- 日期格式：YYYY-MM-DD（如2026-01-17）\n"
                "- 示例：start_date='2026-01-01', end_date='2026-01-31' 只计算1月的数据\n"
                "\n"
                "**⚠️ IAQI函数使用注意事项（重要）：**\n"
                "- 使用IAQI函数时，column参数应指定**浓度字段**（如measurements.PM2_5、measurements.NO2）\n"
                "- 不要使用已存储的IAQI字段（如measurements.PM2_5_IAQI），因为那可能是旧标准计算的值\n"
                "- 工具会根据**新标准（HJ 633-2024）**从浓度重新计算IAQI值\n"
                "- 必须指定pollutant参数（如PM2_5、NO2、SO2等）\n"
                "\n"
                "**使用前必读：**\n"
                "首次使用或需要详细说明时，请先使用read_file工具阅读完整使用指南：\n"
                "read_file(file_path='backend/app/tools/analysis/aggregate_data/aggregate_data_guide.md')\n"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "data_id": {
                        "type": "string",
                        "description": "查询结果的数据ID（来自各查询工具返回的数据ID）"
                    },
                    "aggregations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "column": {
                                    "type": "string",
                                    "description": "要聚合的列名"
                                },
                                "function": {
                                    "type": "string",
                                    "enum": ["SUM", "AVG", "MAX", "MIN", "COUNT", "STDDEV", "VAR", "MEDIAN", "PERCENTILE", "O3_8H_MAX", "IAQI", "AQI", "SINGLE_INDEX", "COMPREHENSIVE_INDEX", "PRIMARY_POLLUTANT"],
                                    "description": "聚合函数"
                                },
                                "alias": {
                                    "type": "string",
                                    "description": "结果字段别名（可选，默认为{function}_{column}）"
                                },
                                "pollutant": {
                                    "type": "string",
                                    "description": "污染物名称（IAQI/SINGLE_INDEX函数必需，用于修约规则和指数计算，如PM2_5、SO2、NO2、O3_8h、CO、PM10等）。\n\n**重要提示**：使用IAQI函数时，column参数应指定浓度字段（如measurements.PM2_5），而不是已存储的IAQI字段（如measurements.PM2_5_IAQI）。工具会根据新标准（HJ 633-2024）从浓度重新计算IAQI值。"
                                },
                                "percentile": {
                                    "type": "number",
                                    "description": "百分位数（PERCENTILE函数必需，取值0-100，如98、95、90）"
                                }
                            },
                            "required": ["column", "function"]
                        },
                        "description": "聚合配置列表"
                    },
                    "group_by": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "分组字段列表（可选）"
                    },
                    "time_granularity": {
                        "type": "string",
                        "enum": ["hour", "day", "month", "year"],
                        "description": "时间粒度（可选）"
                    },
                    "time_column": {
                        "type": "string",
                        "description": "时间列名（可选，默认自动检测）"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "起始日期（可选，格式：YYYY-MM-DD，用于只计算指定日期范围的数据）"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "结束日期（可选，格式：YYYY-MM-DD，用于只计算指定日期范围的数据）"
                    }
                },
                "required": ["data_id", "aggregations"]
            }
        }

        super().__init__(
            name="aggregate_data",
            description="Aggregate and analyze query results with various functions.",
            category=ToolCategory.ANALYSIS,
            function_schema=function_schema,
            requires_context=True,
        )

    async def execute(
        self,
        context: "ExecutionContext",
        data_id: str,
        aggregations: List[Dict[str, Any]],
        group_by: Union[List[str], None] = None,
        time_granularity: Optional[str] = None,
        time_column: Union[str, None] = None,
        start_date: Union[str, None] = None,
        end_date: Union[str, None] = None,
        **_: Any
    ) -> Dict[str, Any]:
        """执行数据聚合分析"""

        # 参数验证
        if not data_id:
            return {
                "status": "failed",
                "success": False,
                "error": "必须提供data_id参数"
            }

        if not aggregations:
            return {
                "status": "failed",
                "success": False,
                "error": "必须提供aggregations参数"
            }

        # 验证聚合函数
        for agg in aggregations:
            func = agg.get("function", "").upper()
            if func not in self.AGGREGATION_FUNCTIONS:
                return {
                    "status": "failed",
                    "success": False,
                    "error": f"不支持的聚合函数: {func}，支持的函数: {list(self.AGGREGATION_FUNCTIONS.keys())}"
                }

            # 验证PERCENTILE函数的percentile参数
            if func == "PERCENTILE":
                percentile = agg.get("percentile")
                if percentile is None:
                    return {
                        "status": "failed",
                        "success": False,
                        "error": "PERCENTILE函数必须提供percentile参数"
                    }
                if not (0 <= percentile <= 100):
                    return {
                        "status": "failed",
                        "success": False,
                        "error": f"percentile参数必须在0-100之间，当前值: {percentile}"
                    }

        logger.info(
            "data_aggregation_start",
            data_id=data_id,
            aggregations=aggregations,
            group_by=group_by,
            time_granularity=time_granularity,
            start_date=start_date,
            end_date=end_date
        )

        try:
            # 步骤1：加载数据
            data = context.get_raw_data(data_id)
            if not data:
                return {
                    "status": "failed",
                    "success": False,
                    "error": f"找不到数据: {data_id}"
                }

            if not isinstance(data, list):
                return {
                    "status": "failed",
                    "success": False,
                    "error": f"数据格式错误，期望list类型，实际: {type(data)}"
                }

            if not data:
                return {
                    "status": "failed",
                    "success": False,
                    "error": "数据为空，无法进行聚合"
                }

            logger.info("data_loaded", row_count=len(data))

            # 步骤1.5：日期过滤（如果指定了日期范围）
            if start_date or end_date:
                original_count = len(data)
                data = self._filter_by_date_range(data, start_date, end_date)
                logger.info(
                    "data_filtered_by_date",
                    original_count=original_count,
                    filtered_count=len(data),
                    start_date=start_date,
                    end_date=end_date
                )

                if not data:
                    return {
                        "status": "failed",
                        "success": False,
                        "error": f"日期过滤后数据为空，请检查日期范围是否正确（start_date={start_date}, end_date={end_date}）"
                    }

            # 【调试日志】检查 2026-01-17 的原始数据和展平后的数据
            for record in data:
                timestamp = record.get("timestamp") or record.get("time_date") or record.get("date") or ""
                if isinstance(timestamp, str) and "2026-01-17" in timestamp:
                    # 展平数据
                    flattened = self._flatten_dict(record)

                    logger.info(
                        "aggregate_data_debug_2026_01_17",
                        date=timestamp[:10],
                        original_data={
                            "PM2_5_top": record.get("PM2_5"),
                            "NO2_top": record.get("NO2"),
                            "PM2_5_measurements": record.get("measurements", {}).get("PM2_5") if isinstance(record.get("measurements"), dict) else None,
                            "NO2_measurements": record.get("measurements", {}).get("NO2") if isinstance(record.get("measurements"), dict) else None,
                        },
                        flattened_data={
                            "PM2_5": flattened.get("PM2_5"),
                            "measurements.PM2_5": flattened.get("measurements.PM2_5"),
                            "NO2": flattened.get("NO2"),
                            "measurements.NO2": flattened.get("measurements.NO2"),
                        },
                        all_flattened_fields=list(flattened.keys())[:40],  # 前40个展平字段
                        note="aggregate_data 读取并展平的数据"
                    )
                    break  # 只记录第一条

            # 步骤2：检测时间列（如果需要）
            if time_granularity and not time_column:
                time_column = self._detect_time_column(data)
                if not time_column:
                    return {
                        "status": "failed",
                        "success": False,
                        "error": "无法检测时间列，请手动指定time_column参数"
                    }
                logger.info("time_column_detected", time_column=time_column)

            # 步骤3：执行聚合计算
            result = self._aggregate(
                data=data,
                aggregations=aggregations,
                group_by=group_by or [],
                time_granularity=time_granularity,
                time_column=time_column
            )

            # 步骤4：保存聚合结果
            aggregated_data_id = None
            try:
                data_ref = context.save_data(
                    data=result["aggregated_data"],
                    schema="aggregated_result",
                    metadata={
                        "source_data_id": data_id,
                        "aggregations": aggregations,
                        "group_by": group_by,
                        "time_granularity": time_granularity,
                        "row_count": len(result["aggregated_data"])
                    }
                )
                aggregated_data_id = data_ref
            except Exception as save_error:
                logger.warning("aggregation_save_failed", error=str(save_error))

            # 步骤5：生成返回结果（UDF v2.0格式）
            agg_desc = self._format_aggregation_description(aggregations)

            return {
                "status": "success",
                "success": True,
                "data": result["aggregated_data"],
                "data_id": aggregated_data_id,
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "aggregate_data",
                    "generator_version": "2.0.0",
                    "field_mapping_applied": True,
                    "field_mapping_info": {"source": "aggregate_data"},
                    "source_data_ids": [data_id],
                    "aggregations": aggregations,
                    "group_by": group_by,
                    "time_granularity": time_granularity,
                    "record_count": len(result["aggregated_data"])
                },
                "summary": f"聚合完成：{agg_desc}，返回{len(result['aggregated_data'])}条结果"
            }

        except Exception as e:
            logger.error("data_aggregation_failed", error=str(e))
            return {
                "status": "failed",
                "success": False,
                "error": f"聚合分析失败: {str(e)}",
                "data_id": data_id
            }

    def _aggregate(
        self,
        data: List[Dict[str, Any]],
        aggregations: List[Dict[str, Any]],
        group_by: List[str],
        time_granularity: Optional[str],
        time_column: Optional[str]
    ) -> Dict[str, Any]:
        """
        执行聚合计算

        Args:
            data: 原始数据
            aggregations: 聚合配置
            group_by: 分组字段
            time_granularity: 时间粒度
            time_column: 时间列名

        Returns:
            聚合结果
        """
        import pandas as pd
        from collections import defaultdict

        # 展平嵌套数据（将measurements.PM2_5提升到顶层）
        # 支持通过点号语法访问嵌套字段
        flattened_data = []
        for record in data:
            flattened = self._flatten_dict(record)
            flattened_data.append(flattened)

        # 转换为DataFrame（展平后支持点号列名）
        df = pd.DataFrame(flattened_data)

        # 时间粒度处理
        if time_granularity and time_column:
            if time_column not in df.columns:
                raise ValueError(f"时间列不存在: {time_column}")

            # 转换时间列
            df[time_column] = pd.to_datetime(df[time_column])

            # 创建时间分组键
            if time_granularity == "hour":
                df["_time_group"] = df[time_column].dt.floor("H")
            elif time_granularity == "day":
                df["_time_group"] = df[time_column].dt.date
            elif time_granularity == "month":
                df["_time_group"] = df[time_column].dt.to_period("M").dt.to_timestamp()
            elif time_granularity == "year":
                df["_time_group"] = df[time_column].dt.year

            # 将时间分组添加到分组字段
            group_by = list(group_by) + ["_time_group"]

        # 分组聚合
        if group_by:
            # 检查分组字段是否存在
            valid_group_by = [col for col in group_by if col in df.columns]
            if len(valid_group_by) < len(group_by):
                missing = set(group_by) - set(valid_group_by)
                logger.warning("group_by_columns_missing", columns=list(missing))

            if valid_group_by:
                grouped = df.groupby(valid_group_by)
            else:
                grouped = None
        else:
            grouped = None

        # 执行聚合计算
        agg_result = {}
        statistics = {}

        for agg_config in aggregations:
            column = agg_config["column"]
            func = agg_config["function"].upper()
            alias = agg_config.get("alias", f"{func}_{column}")
            pollutant = agg_config.get("pollutant")

            if column not in df.columns:
                logger.warning("aggregation_column_missing", column=column)
                continue

            # 执行聚合
            if grouped is not None:
                if func == "COUNT":
                    agg_values = grouped[column].count()
                elif func == "SUM":
                    agg_values = grouped[column].sum()
                elif func == "AVG":
                    agg_values = grouped[column].mean()
                    # 应用修约规则
                    if pollutant:
                        agg_values = agg_values.apply(
                            lambda x: apply_rounding(x, pollutant, 'statistical_data') if pd.notna(x) else x
                        )
                elif func == "MAX":
                    agg_values = grouped[column].max()
                elif func == "MIN":
                    agg_values = grouped[column].min()
                elif func == "STDDEV":
                    agg_values = grouped[column].std()
                    # 应用修约规则
                    if pollutant:
                        agg_values = agg_values.apply(
                            lambda x: apply_rounding(x, pollutant, 'statistical_data') if pd.notna(x) else x
                        )
                elif func == "VAR":
                    agg_values = grouped[column].var()
                    # 应用修约规则
                    if pollutant:
                        agg_values = agg_values.apply(
                            lambda x: apply_rounding(x, pollutant, 'statistical_data') if pd.notna(x) else x
                        )
                elif func == "MEDIAN":
                    agg_values = grouped[column].median()
                    # 应用修约规则
                    if pollutant:
                        agg_values = agg_values.apply(
                            lambda x: apply_rounding(x, pollutant, 'statistical_data') if pd.notna(x) else x
                        )
                elif func == "PERCENTILE":
                    percentile_val = agg_config.get("percentile", 50)
                    agg_values = grouped[column].apply(
                        lambda x: calculate_percentile(x.tolist(), percentile_val)
                    )
                    # 应用修约规则
                    if pollutant:
                        agg_values = agg_values.apply(
                            lambda x: apply_rounding(x, pollutant, 'statistical_data') if pd.notna(x) else x
                        )
                elif func == "O3_8H_MAX":
                    # 特殊处理：需要8小时滑动窗口
                    agg_values = grouped.apply(
                        lambda g: calculate_o3_8h_max_for_group(g, column, time_column or 'time_point')
                    )
                    # 应用修约规则
                    if pollutant:
                        agg_values = agg_values.apply(
                            lambda x: apply_rounding(x, pollutant, 'statistical_data') if pd.notna(x) else x
                        )
                elif func == "IAQI":
                    # 计算IAQI（空气质量分指数）
                    # 先计算平均浓度，再计算IAQI
                    if not pollutant:
                        logger.warning("iaqi_missing_pollutant", column=column)
                        continue
                    # 先计算每组的平均浓度
                    avg_concentrations = grouped[column].mean()
                    # 对平均浓度计算IAQI
                    agg_values = avg_concentrations.apply(
                        lambda x: calculate_iaqi_for_aggregate(x, pollutant) if pd.notna(x) else 0
                    )
                elif func == "SINGLE_INDEX":
                    # 计算单项指数 Ii = Ci / Si
                    if not pollutant:
                        logger.warning("single_index_missing_pollutant", column=column)
                        continue
                    standard_limit = ANNUAL_STANDARD_LIMITS.get(pollutant)
                    if not standard_limit:
                        logger.warning("single_index_unknown_pollutant", pollutant=pollutant)
                        continue
                    agg_values = grouped[column].mean() / standard_limit
                    agg_values = agg_values.apply(
                        lambda x: safe_round_for_index(x, 3) if pd.notna(x) else 0.0
                    )
                elif func == "AQI":
                    # 计算AQI（空气质量指数）= max(IAQI_PM2.5, IAQI_PM10, IAQI_O3, IAQI_NO2, IAQI_SO2, IAQI_CO)
                    # 需要数据中包含所有六参数浓度
                    agg_values = grouped.apply(
                        lambda g: self._calculate_aqi_for_group(g, time_column or 'time_point')
                    )
                elif func == "COMPREHENSIVE_INDEX":
                    # 计算综合指数 = Σ(单项指数)
                    agg_values = grouped.apply(
                        lambda g: self._calculate_comprehensive_index_for_group(g)
                    )
                elif func == "PRIMARY_POLLUTANT":
                    # 计算首要污染物（IAQI最大的污染物）
                    agg_values = grouped.apply(
                        lambda g: self._calculate_primary_pollutant_for_group(g, time_column or 'time_point')
                    )
                else:
                    continue

                agg_result[alias] = agg_values
            else:
                # 全局聚合
                if func == "COUNT":
                    value = df[column].count()
                elif func == "SUM":
                    value = df[column].sum()
                elif func == "AVG":
                    value = df[column].mean()
                    # 应用修约规则
                    if pollutant:
                        value = apply_rounding(value, pollutant, 'statistical_data')
                elif func == "MAX":
                    value = df[column].max()
                elif func == "MIN":
                    value = df[column].min()
                elif func == "STDDEV":
                    value = df[column].std()
                    # 应用修约规则
                    if pollutant:
                        value = apply_rounding(value, pollutant, 'statistical_data')
                elif func == "VAR":
                    value = df[column].var()
                    # 应用修约规则
                    if pollutant:
                        value = apply_rounding(value, pollutant, 'statistical_data')
                elif func == "MEDIAN":
                    value = df[column].median()
                    # 应用修约规则
                    if pollutant:
                        value = apply_rounding(value, pollutant, 'statistical_data')
                elif func == "PERCENTILE":
                    percentile_val = agg_config.get("percentile", 50)
                    value = calculate_percentile(df[column].tolist(), percentile_val)
                    # 应用修约规则
                    if pollutant:
                        value = apply_rounding(value, pollutant, 'statistical_data')
                elif func == "O3_8H_MAX":
                    value = calculate_o3_8h_max(df, column, time_column or 'time_point')
                    if not value.empty:
                        value = value.iloc[0]
                    else:
                        value = None
                    # 应用修约规则
                    if pollutant and value is not None:
                        value = apply_rounding(value, pollutant, 'statistical_data')
                elif func == "IAQI":
                    # 计算IAQI（空气质量分指数）
                    if not pollutant:
                        logger.warning("iaqi_missing_pollutant", column=column)
                        continue
                    # 对于全局聚合，计算平均值的IAQI
                    avg_value = df[column].mean()
                    value = calculate_iaqi_for_aggregate(avg_value, pollutant)
                elif func == "SINGLE_INDEX":
                    # 计算单项指数 Ii = Ci / Si
                    if not pollutant:
                        logger.warning("single_index_missing_pollutant", column=column)
                        continue
                    standard_limit = ANNUAL_STANDARD_LIMITS.get(pollutant)
                    if not standard_limit:
                        logger.warning("single_index_unknown_pollutant", pollutant=pollutant)
                        continue
                    avg_value = df[column].mean()
                    value = safe_round_for_index(avg_value / standard_limit, 3)
                elif func == "AQI":
                    # 计算AQI（空气质量指数）= max(IAQI_PM2.5, IAQI_PM10, IAQI_O3, IAQI_NO2, IAQI_SO2, IAQI_CO)
                    value = self._calculate_aqi_for_dataframe(df, time_column or 'time_point')
                elif func == "COMPREHENSIVE_INDEX":
                    # 计算综合指数 = Σ(单项指数)
                    value = self._calculate_comprehensive_index_for_dataframe(df)
                elif func == "PRIMARY_POLLUTANT":
                    # 计算首要污染物（IAQI最大的污染物）
                    value = self._calculate_primary_pollutant_for_dataframe(df, time_column or 'time_point')
                else:
                    continue

                statistics[alias] = value

        # 转换为结果格式
        if grouped is not None:
            # 重置索引，将分组键转为列
            result_df = pd.DataFrame(agg_result)
            if not result_df.empty:
                result_df = result_df.reset_index()

                # 转换为字典列表
                aggregated_data = result_df.to_dict("records")

                # 转换时间为字符串
                for record in aggregated_data:
                    for key, value in record.items():
                        if pd.notna(value):
                            if isinstance(value, pd.Timestamp):
                                record[key] = value.isoformat()
                            elif hasattr(value, 'item'):  # numpy类型
                                record[key] = value.item()
                        else:
                            record[key] = None
            else:
                aggregated_data = []
        else:
            # 全局聚合结果
            aggregated_data = [statistics]

        return {
            "aggregated_data": aggregated_data,
            "statistics": statistics if not grouped else {}
        }

    def _flatten_dict(self, d: Dict[str, Any], parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
        """
        展平嵌套字典，使用点号分隔嵌套键

        示例:
            {"measurements": {"PM2_5": 47}} → {"measurements.PM2_5": 47}

        Args:
            d: 嵌套字典
            parent_key: 父键前缀
            sep: 分隔符

        Returns:
            展平后的字典
        """
        items: List[tuple[str, Any]] = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                # 递归展平嵌套字典
                items.extend(self._flatten_dict(v, new_key, sep).items())
            else:
                items.append((new_key, v))
        return dict(items)

    def _detect_time_column(self, data: List[Dict[str, Any]]) -> Optional[str]:
        """
        自动检测时间列

        Args:
            data: 数据列表

        Returns:
            时间列名或None
        """
        if not data:
            return None

        first_record = data[0]
        first_record_flattened = self._flatten_dict(first_record)

        # 常见时间列名
        time_keywords = [
            "time", "timestamp", "date", "datetime",
            "time_point", "acq_datetime", "event_date",
            "created_at", "modified_time"
        ]

        for key in first_record_flattened.keys():
            key_lower = key.lower()
            if any(kw in key_lower for kw in time_keywords):
                return key

        return None

    def _find_pollutant_column(self, df: pd.DataFrame, pollutant: str) -> Optional[str]:
        """
        在DataFrame中查找污染物列

        支持多种命名格式，如PM2_5可以是pm2_5、pm25、PM2_5等

        Args:
            df: DataFrame对象
            pollutant: 污染物标准名称（如'PM2_5'）

        Returns:
            找到的列名，未找到返回None
        """
        possible_names = POLLUTANT_COLUMN_MAP.get(pollutant, [pollutant])

        # 【调试日志】记录查找过程
        found_column = None

        for name in possible_names:
            # 首先尝试精确匹配
            if name in df.columns:
                found_column = name
                break

        # 【调试日志】如果找不到或找到特殊字段，记录详细信息
        all_columns = list(df.columns)
        if pollutant in ['PM2_5', 'NO2'] and not found_column:
            logger.info(
                "aggregate_data_find_pollutant_column_failed",
                pollutant=pollutant,
                possible_names=possible_names,
                all_columns=all_columns[:30],  # 前30个列名
                note="未找到污染物列"
            )
        elif pollutant in ['PM2_5', 'NO2'] and found_column:
            # 检查找到的列的实际值
            sample_values = df[found_column].head(3).tolist()
            logger.info(
                "aggregate_data_find_pollutant_column_success",
                pollutant=pollutant,
                found_column=found_column,
                sample_values=sample_values,
                note="找到污染物列"
            )

        return found_column

        # 如果精确匹配失败，尝试模糊匹配（展平后的列名）
        all_columns = df.columns.tolist()
        for col in all_columns:
            for possible_name in possible_names:
                if possible_name.lower() in col.lower():
                    return col

        return None

    def _calculate_aqi_for_group(self, group: pd.DataFrame, time_column: str) -> int:
        """
        计算分组的AQI值

        AQI = max(IAQI_PM2.5, IAQI_PM10, IAQI_O3, IAQI_NO2, IAQI_SO2, IAQI_CO)

        Args:
            group: 分组数据
            time_column: 时间列名

        Returns:
            AQI值
        """
        iaqi_values = []

        # 计算各污染物的IAQI
        for pollutant in ['PM2_5', 'PM10', 'SO2', 'NO2', 'CO', 'O3_8h']:
            column = self._find_pollutant_column(group, pollutant)
            if column and column in group.columns:
                # 计算该污染物的平均浓度
                avg_concentration = group[column].mean()
                if pd.notna(avg_concentration):
                    iaqi = calculate_iaqi_for_aggregate(avg_concentration, pollutant)
                    iaqi_values.append(iaqi)

        # AQI为各IAQI的最大值，向上进位取整数
        return math.ceil(max(iaqi_values)) if iaqi_values else 0

    def _calculate_aqi_for_dataframe(self, df: pd.DataFrame, time_column: str) -> int:
        """
        计算整个DataFrame的AQI值

        AQI = max(IAQI_PM2.5, IAQI_PM10, IAQI_O3, IAQI_NO2, IAQI_SO2, IAQI_CO)

        Args:
            df: DataFrame对象
            time_column: 时间列名

        Returns:
            AQI值
        """
        iaqi_values = []
        iaqi_details = {}

        # 【调试日志】检查是否包含 2026-01-17
        has_2026_01_17 = False
        if time_column in df.columns:
            dates = df[time_column].astype(str)
            if dates.str.contains('2026-01-17').any():
                has_2026_01_17 = True
                # 提取 2026-01-17 的数据
                row_2026_01_17 = df[dates.str.contains('2026-01-17')].iloc[0] if dates.str.contains('2026-01-17').any() else None

        # 计算各污染物的IAQI
        for pollutant in ['PM2_5', 'PM10', 'SO2', 'NO2', 'CO', 'O3_8h']:
            column = self._find_pollutant_column(df, pollutant)
            if column and column in df.columns:
                # 计算该污染物的平均浓度
                avg_concentration = df[column].mean()
                if pd.notna(avg_concentration):
                    iaqi = calculate_iaqi_for_aggregate(avg_concentration, pollutant)
                    iaqi_values.append(iaqi)
                    iaqi_details[pollutant] = {
                        "column": column,
                        "avg_concentration": round(float(avg_concentration), 2),
                        "iaqi": iaqi
                    }

        # 【调试日志】输出 IAQI 计算详情
        if has_2026_01_17:
            logger.info(
                "aggregate_data_aqi_calculation_debug",
                note="DataFrame 包含 2026-01-17 数据",
                iaqi_details=iaqi_details,
                max_iaqi=max(iaqi_values) if iaqi_values else 0,
                data_sample={col: str(df[col].iloc[0]) if col in df.columns else None for col in list(df.columns)[:10]}
            )

        # AQI为各IAQI的最大值，向上进位取整数
        return math.ceil(max(iaqi_values)) if iaqi_values else 0

    def _calculate_comprehensive_index_for_group(self, group: pd.DataFrame) -> float:
        """
        计算分组的综合指数

        综合指数 = Σ(单项指数) = Σ(Ci / Si)
        其中Ci为污染物浓度，Si为标准限值

        Args:
            group: 分组数据

        Returns:
            综合指数值
        """
        single_indexes = []

        # 计算各污染物的单项指数
        for pollutant in ['PM2_5', 'PM10', 'SO2', 'NO2', 'CO', 'O3_8h']:
            column = self._find_pollutant_column(group, pollutant)
            if column and column in group.columns:
                standard_limit = ANNUAL_STANDARD_LIMITS.get(pollutant)
                if standard_limit:
                    # 计算平均浓度
                    avg_concentration = group[column].mean()
                    if pd.notna(avg_concentration):
                        # 单项指数 = 浓度 / 标准限值
                        single_index = avg_concentration / standard_limit
                        single_indexes.append(single_index)

        # 综合指数 = Σ(单项指数)
        comprehensive_index = sum(single_indexes)
        return safe_round_for_index(comprehensive_index, 2)

    def _calculate_comprehensive_index_for_dataframe(self, df: pd.DataFrame) -> float:
        """
        计算整个DataFrame的综合指数

        综合指数 = Σ(单项指数) = Σ(Ci / Si)
        其中Ci为污染物浓度，Si为标准限值

        Args:
            df: DataFrame对象

        Returns:
            综合指数值
        """
        single_indexes = []

        # 计算各污染物的单项指数
        for pollutant in ['PM2_5', 'PM10', 'SO2', 'NO2', 'CO', 'O3_8h']:
            column = self._find_pollutant_column(df, pollutant)
            if column and column in df.columns:
                standard_limit = ANNUAL_STANDARD_LIMITS.get(pollutant)
                if standard_limit:
                    # 计算平均浓度
                    avg_concentration = df[column].mean()
                    if pd.notna(avg_concentration):
                        # 单项指数 = 浓度 / 标准限值
                        single_index = avg_concentration / standard_limit
                        single_indexes.append(single_index)

        # 综合指数 = Σ(单项指数)
        comprehensive_index = sum(single_indexes)
        return safe_round_for_index(comprehensive_index, 2)

    def _calculate_primary_pollutant_for_group(self, group: pd.DataFrame, time_column: str) -> str:
        """
        计算分组的首要污染物

        首要污染物 = IAQI 最大的污染物

        Args:
            group: 分组数据
            time_column: 时间列名

        Returns:
            首要污染物名称（如'PM2.5', 'O3', 'NO2'等）
        """
        iaqi_values = {}

        # 计算各污染物的IAQI
        for pollutant in ['PM2_5', 'PM10', 'SO2', 'NO2', 'CO', 'O3_8h']:
            column = self._find_pollutant_column(group, pollutant)
            if column and column in group.columns:
                # 计算该污染物的平均浓度
                avg_concentration = group[column].mean()
                if pd.notna(avg_concentration):
                    iaqi = calculate_iaqi_for_aggregate(avg_concentration, pollutant)
                    iaqi_values[pollutant] = iaqi

        # 找到IAQI最大的污染物
        if not iaqi_values:
            return "-"

        primary_pollutant = max(iaqi_values.items(), key=lambda x: x[1])[0]

        # 转换为显示名称
        pollutant_display_names = {
            'PM2_5': 'PM2.5',
            'PM10': 'PM10',
            'SO2': 'SO2',
            'NO2': 'NO2',
            'CO': 'CO',
            'O3_8h': 'O3'
        }

        return pollutant_display_names.get(primary_pollutant, primary_pollutant)

    def _calculate_primary_pollutant_for_dataframe(self, df: pd.DataFrame, time_column: str) -> str:
        """
        计算整个DataFrame的首要污染物

        首要污染物 = IAQI 最大的污染物

        Args:
            df: DataFrame对象
            time_column: 时间列名

        Returns:
            首要污染物名称（如'PM2.5', 'O3', 'NO2'等）
        """
        iaqi_values = {}

        # 计算各污染物的IAQI
        for pollutant in ['PM2_5', 'PM10', 'SO2', 'NO2', 'CO', 'O3_8h']:
            column = self._find_pollutant_column(df, pollutant)
            if column and column in df.columns:
                # 计算该污染物的平均浓度
                avg_concentration = df[column].mean()
                if pd.notna(avg_concentration):
                    iaqi = calculate_iaqi_for_aggregate(avg_concentration, pollutant)
                    iaqi_values[pollutant] = iaqi

        # 找到IAQI最大的污染物
        if not iaqi_values:
            return "-"

        primary_pollutant = max(iaqi_values.items(), key=lambda x: x[1])[0]

        # 转换为显示名称
        pollutant_display_names = {
            'PM2_5': 'PM2.5',
            'PM10': 'PM10',
            'SO2': 'SO2',
            'NO2': 'NO2',
            'CO': 'CO',
            'O3_8h': 'O3'
        }

        return pollutant_display_names.get(primary_pollutant, primary_pollutant)

    def _format_aggregation_description(self, aggregations: List[Dict[str, Any]]) -> str:
        """
        格式化聚合描述

        Args:
            aggregations: 聚合配置列表

        Returns:
            格式化的描述字符串
        """
        parts = []
        for agg in aggregations:
            column = agg["column"]
            func = agg["function"]
            alias = agg.get("alias", f"{func}_{column}")
            parts.append(f"{func}({column}) AS {alias}")

        return ", ".join(parts)

    def _filter_by_date_range(
        self,
        data: List[Dict[str, Any]],
        start_date: Union[str, None],
        end_date: Union[str, None]
    ) -> List[Dict[str, Any]]:
        """
        根据日期范围过滤数据

        Args:
            data: 原始数据列表
            start_date: 起始日期（YYYY-MM-DD格式）
            end_date: 结束日期（YYYY-MM-DD格式）

        Returns:
            过滤后的数据列表
        """
        if not start_date and not end_date:
            return data

        from datetime import datetime

        filtered_data = []
        for record in data:
            # 尝试多种可能的时间字段
            timestamp = None
            for key in ['timestamp', 'time', 'date', 'time_point', 'datetime', 'time_date']:
                if key in record:
                    timestamp = record[key]
                    break

            if timestamp is None:
                # 尝试在嵌套的measurements中查找
                if isinstance(record.get('measurements'), dict):
                    timestamp = record['measurements'].get('timestamp')

            if timestamp is None:
                # 如果找不到时间字段，跳过该记录
                continue

            # 转换时间字符串为日期对象进行比较
            try:
                if isinstance(timestamp, str):
                    # 处理多种时间格式
                    record_date = None
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f']:
                        try:
                            record_date = datetime.strptime(timestamp.split('+')[0].split('Z')[0], fmt).date()
                            break
                        except ValueError:
                            continue

                    if record_date is None:
                        # 无法解析时间格式，跳过该记录
                        continue

                    # 将字符串日期转换为日期对象
                    start_dt = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
                    end_dt = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None

                    # 检查日期范围
                    in_range = True
                    if start_dt and record_date < start_dt:
                        in_range = False
                    if end_dt and record_date > end_dt:
                        in_range = False

                    if in_range:
                        filtered_data.append(record)

            except (ValueError, TypeError) as e:
                # 时间解析失败，跳过该记录
                logger.warning("date_parse_failed", record_timestamp=timestamp, error=str(e))
                continue

        return filtered_data


def __init__() -> None:
    return AggregateDataTool()
