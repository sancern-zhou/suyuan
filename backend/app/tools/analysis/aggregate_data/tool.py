"""
数据聚合分析工具

对查询结果进行聚合计算，支持多种聚合函数和分组方式。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
from datetime import datetime
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.db.database import async_session
from app.agent.context.data_context_manager import DataContextManager

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


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
        'MEDIAN': '中位数'
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
                "【数据聚合分析工具】对查询结果进行聚合计算和统计分析。"
                ""
                "**核心功能：**"
                "- 支持多种聚合函数：SUM、AVG、MAX、MIN、COUNT、STDDEV、VAR、MEDIAN"
                "- 支持按字段分组聚合（GROUP BY）"
                "- 支持按时间粒度聚合（hour/day/month/year）"
                "- 自动生成聚合结果摘要"
                ""
                "**使用场景：**"
                "- 计算时间序列数据的统计指标（日均、月均、年均）"
                "- 按类别分组统计（如按城市、按站点）"
                "- 计算数据的极值、总和等统计量"
                "- 对原始查询结果进行汇总分析"
                ""
                "**参数说明：**"
                "- data_id: 查询结果的数据ID（必需）"
                "- aggregations: 聚合配置列表（必需）"
                "  - column: 要聚合的列名"
                "  - function: 聚合函数（SUM/AVG/MAX/MIN/COUNT/STDDEV/VAR/MEDIAN）"
                "  - alias: 结果字段别名（可选）"
                "- group_by: 分组字段列表（可选）"
                "- time_granularity: 时间粒度（可选，hour/day/month/year）"
                "- time_column: 时间列名（可选，默认自动检测）"
                ""
                "**示例：**"
                "- 计算PM2.5日均值：aggregations=[{'column':'pm25','function':'AVG'}], time_granularity='day'"
                "- 按城市统计：aggregations=[{'column':'pm25','function':'AVG'}], group_by=['city']"
                "- 多指标统计：aggregations=[{'column':'pm25','function':'AVG'},{'column':'pm25','function':'MAX'}]"
                ""
                "**何时使用：**"
                "- 需要对查询结果进行统计分析"
                "- 需要计算日均、月均、年均值"
                "- 需要按类别分组汇总"
                "- 需要计算极值、总和等统计量"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "data_id": {
                        "type": "string",
                        "description": "查询结果的数据ID（来自generate_sql_query或其他查询工具）"
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
                                    "enum": ["SUM", "AVG", "MAX", "MIN", "COUNT", "STDDEV", "VAR", "MEDIAN"],
                                    "description": "聚合函数"
                                },
                                "alias": {
                                    "type": "string",
                                    "description": "结果字段别名（可选，默认为{function}_{column}）"
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
        **_: Any
    ) -> Dict[str, Any]:
        """执行数据聚合分析"""

        # 参数验证
        if not data_id:
            return {
                "success": False,
                "error": "必须提供data_id参数"
            }

        if not aggregations:
            return {
                "success": False,
                "error": "必须提供aggregations参数"
            }

        # 验证聚合函数
        for agg in aggregations:
            func = agg.get("function", "").upper()
            if func not in self.AGGREGATION_FUNCTIONS:
                return {
                    "success": False,
                    "error": f"不支持的聚合函数: {func}，支持的函数: {list(self.AGGREGATION_FUNCTIONS.keys())}"
                }

        logger.info(
            "data_aggregation_start",
            data_id=data_id,
            aggregations=aggregations,
            group_by=group_by,
            time_granularity=time_granularity
        )

        try:
            # 步骤1：加载数据
            data = context.get_raw_data(data_id)
            if not data:
                return {
                    "success": False,
                    "error": f"找不到数据: {data_id}"
                }

            if not isinstance(data, list):
                return {
                    "success": False,
                    "error": f"数据格式错误，期望list类型，实际: {type(data)}"
                }

            if not data:
                return {
                    "success": False,
                    "error": "数据为空，无法进行聚合"
                }

            logger.info("data_loaded", row_count=len(data))

            # 步骤2：检测时间列（如果需要）
            if time_granularity and not time_column:
                time_column = self._detect_time_column(data)
                if not time_column:
                    return {
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
                aggregated_data_id = data_ref["data_id"]
            except Exception as save_error:
                logger.warning("aggregation_save_failed", error=str(save_error))

            # 步骤5：生成返回结果
            agg_desc = self._format_aggregation_description(aggregations)

            return {
                "success": True,
                "data": result["aggregated_data"],
                "data_id": aggregated_data_id,
                "statistics": result["statistics"],
                "summary": (
                    f"聚合完成：{agg_desc}，"
                    f"返回{len(result['aggregated_data'])}条结果。"
                ),
                "metadata": {
                    "source_data_id": data_id,
                    "aggregations": aggregations,
                    "group_by": group_by,
                    "time_granularity": time_granularity
                }
            }

        except Exception as e:
            logger.error("data_aggregation_failed", error=str(e))
            return {
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

        # 转换为DataFrame
        df = pd.DataFrame(data)

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
                elif func == "MAX":
                    agg_values = grouped[column].max()
                elif func == "MIN":
                    agg_values = grouped[column].min()
                elif func == "STDDEV":
                    agg_values = grouped[column].std()
                elif func == "VAR":
                    agg_values = grouped[column].var()
                elif func == "MEDIAN":
                    agg_values = grouped[column].median()
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
                elif func == "MAX":
                    value = df[column].max()
                elif func == "MIN":
                    value = df[column].min()
                elif func == "STDDEV":
                    value = df[column].std()
                elif func == "VAR":
                    value = df[column].var()
                elif func == "MEDIAN":
                    value = df[column].median()
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

        # 常见时间列名
        time_keywords = [
            "time", "timestamp", "date", "datetime",
            "time_point", "acq_datetime", "event_date",
            "created_at", "updated_at"
        ]

        for key in first_record.keys():
            key_lower = key.lower()
            if any(kw in key_lower for kw in time_keywords):
                return key

        return None

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


def __init__() -> None:
    return AggregateDataTool()
