"""
新标准报表对比分析工具

对比两个时间段基于 HJ 633-2024 新标准的空气质量统计报表

【核心功能】
- 并发查询两个时间段的统计数据
- 自动对比全部统计指标（综合指数、超标天数、六参数等）
- 返回差值、变化率、趋势判断
- 合并存储原始数据，支持后续 aggregate_data 分析

【对比指标】
- 综合指标：composite_index, exceed_days, exceed_rate, compliance_rate, total_days, valid_days
- 六参数统计：SO2, NO2, PM10, PM2_5, CO, O3_8h 及其百分位数
- 单项质量指数：single_indexes.*
- 首要污染物统计：primary_pollutant_days.*, total_primary_days
- 超标统计：exceed_days_by_pollutant.*
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
import structlog

from app.tools.base import LLMTool, ToolCategory
from app.agent.context.execution_context import ExecutionContext
from app.tools.query.query_new_standard_report.tool import execute_query_new_standard_report

logger = structlog.get_logger()


# 对比指标列表（全部指标）
COMPARISON_METRICS = [
    # 综合指标
    "composite_index", "exceed_days", "exceed_rate", "compliance_rate", "total_days", "valid_days",

    # 六参数统计浓度
    "SO2", "SO2_P98",
    "NO2", "NO2_P98",
    "PM10", "PM10_P95",
    "PM2_5", "PM2_5_P95",
    "CO_P95",
    "O3_8h_P90",

    # 单项质量指数
    "single_indexes.SO2", "single_indexes.NO2", "single_indexes.PM10",
    "single_indexes.CO", "single_indexes.PM2_5", "single_indexes.O3_8h",

    # 首要污染物天数
    "primary_pollutant_days.PM2_5", "primary_pollutant_days.PM10",
    "primary_pollutant_days.NO2", "primary_pollutant_days.O3_8h",
    "primary_pollutant_days.CO", "primary_pollutant_days.SO2",
    "total_primary_days",

    # 各污染物超标天数
    "exceed_days_by_pollutant.PM2_5", "exceed_days_by_pollutant.PM10",
    "exceed_days_by_pollutant.SO2", "exceed_days_by_pollutant.NO2",
    "exceed_days_by_pollutant.CO", "exceed_days_by_pollutant.O3_8h",
]

# 百分比字段（只计算差值，不计算变化率）
# 这些字段已经是百分比形式（如 98.5%），计算变化率没有实际意义
PERCENTAGE_METRICS = {
    "exceed_rate",      # 超标率（%）
    "compliance_rate",  # 达标率（%）
}


class CompareStandardReportsTool(LLMTool):
    """新标准报表对比分析工具"""

    def __init__(self):
        function_schema = {
            "name": "compare_standard_reports",
            "description": """对比两个时间段基于 HJ 633-2024 新标准的空气质量统计报表。

【核心功能】
- 并发查询两个时间段的统计数据
- 自动对比全部统计指标（综合指数、超标天数、六参数等）
- 返回差值、变化率
- 合并存储原始数据，支持后续 aggregate_data 分析

【对比指标】
- 综合指标：composite_index, exceed_days, exceed_rate, compliance_rate, total_days, valid_days
- 六参数统计：SO2, NO2, PM10, PM2_5, CO, O3_8h 及其百分位数
- 单项质量指数：single_indexes.*
- 首要污染物统计：primary_pollutant_days.*, total_primary_days
- 超标统计：exceed_days_by_pollutant.*

【返回数据说明】
- result字段：对比结果（包含query_period、comparison_period、differences、change_rates）
  - query_period: 查询时间段的统计数据
  - comparison_period: 对比时间段的统计数据
  - differences: 两个时间段的差值（query_period - comparison_period）
  - change_rates: 变化率百分比（(query_period - comparison_period) / comparison_period * 100）
- data_id字段：合并后的原始数据（包含period标识字段）

【输入参数】
- cities: 城市列表
- query_period: 查询时间段 {start_date, end_date}
- comparison_period: 对比时间段 {start_date, end_date}
- enable_sand_deduction: 是否启用扣沙处理（默认true）
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市列表，如 ['广州', '深圳']"
                    },
                    "query_period": {
                        "type": "object",
                        "description": "查询时间段（当前时期）",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "开始日期，格式 YYYY-MM-DD"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "结束日期，格式 YYYY-MM-DD"
                            }
                        },
                        "required": ["start_date", "end_date"]
                    },
                    "comparison_period": {
                        "type": "object",
                        "description": "对比时间段（基准时期，用于同比/环比）",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "开始日期，格式 YYYY-MM-DD"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "结束日期，格式 YYYY-MM-DD"
                            }
                        },
                        "required": ["start_date", "end_date"]
                    },
                    "enable_sand_deduction": {
                        "type": "boolean",
                        "description": "是否启用扣沙处理（剔除沙尘暴天气的PM2.5/PM10数据），默认true"
                    }
                },
                "required": ["cities", "query_period", "comparison_period"]
            }
        }

        super().__init__(
            name="compare_standard_reports",
            description="Compare standard reports between two time periods",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True
        )

    async def execute(self, context: ExecutionContext, **kwargs) -> Dict[str, Any]:
        """执行对比分析"""
        # 1. 参数验证
        is_valid, error_msg = self._validate_parameters(kwargs)
        if not is_valid:
            return self._error_response(error_msg)

        cities = kwargs["cities"]
        query_period = kwargs["query_period"]
        comparison_period = kwargs["comparison_period"]
        enable_sand_deduction = kwargs.get("enable_sand_deduction", True)

        logger.info(
            "compare_standard_reports_start",
            cities=cities,
            query_period=query_period,
            comparison_period=comparison_period,
            enable_sand_deduction=enable_sand_deduction
        )

        # 2. 并发查询两个时间段的数据（排除超标详情）
        current_task = execute_query_new_standard_report(
            cities=cities,
            start_date=query_period["start_date"],
            end_date=query_period["end_date"],
            enable_sand_deduction=enable_sand_deduction,
            exclude_exceed_details=True,  # 不返回超标详情
            context=context
        )

        comparison_task = execute_query_new_standard_report(
            cities=cities,
            start_date=comparison_period["start_date"],
            end_date=comparison_period["end_date"],
            enable_sand_deduction=enable_sand_deduction,
            exclude_exceed_details=True,  # 不返回超标详情
            context=context
        )

        current_result, comparison_result = await asyncio.gather(
            current_task, comparison_task,
            return_exceptions=True
        )

        # 3. 错误处理
        if isinstance(current_result, Exception):
            logger.error("query_period_failed", error=str(current_result))
            return self._error_response(f"查询时段数据获取失败: {str(current_result)}")

        if isinstance(comparison_result, Exception):
            logger.error("comparison_period_failed", error=str(comparison_result))
            return self._error_response(f"对比时段数据获取失败: {str(comparison_result)}")

        # 检查查询状态
        if current_result.get("status") == "failed":
            return self._error_response(f"查询时段失败: {current_result.get('summary', '未知错误')}")

        if comparison_result.get("status") == "failed":
            return self._error_response(f"对比时段失败: {comparison_result.get('summary', '未知错误')}")

        # 4. 提取并合并原始数据
        current_data_id = current_result.get("metadata", {}).get("data_id")
        comparison_data_id = comparison_result.get("metadata", {}).get("data_id")

        merged_data_id = None
        if current_data_id and comparison_data_id:
            try:
                current_raw_data = context.get_raw_data(current_data_id)
                comparison_raw_data = context.get_raw_data(comparison_data_id)

                merged_data = self._merge_period_data(
                    current_raw_data if current_raw_data else [],
                    comparison_raw_data if comparison_raw_data else [],
                    query_period,
                    comparison_period
                )

                # 保存合并数据
                save_result = context.save_data(
                    data=merged_data,
                    schema="air_quality_unified",
                    metadata={
                        "source_data_ids": [current_data_id, comparison_data_id],
                        "comparison_type": "period_comparison",
                        "query_period": query_period,
                        "comparison_period": comparison_period
                    }
                )
                merged_data_id = save_result["data_id"] if isinstance(save_result, dict) else save_result

                logger.info(
                    "period_data_merged",
                    merged_data_id=merged_data_id,
                    merged_records=len(merged_data)
                )
            except Exception as e:
                logger.warning("failed_to_merge_data", error=str(e))

        # 5. 计算对比指标
        current_stats = current_result.get("result", {})
        comparison_stats = comparison_result.get("result", {})

        # 处理单城市和多城市的情况
        if isinstance(current_stats, dict) and len(cities) == 1:
            # 单城市查询，current_stats 直接是城市统计
            current_stats = {cities[0]: current_stats}
        if isinstance(comparison_stats, dict) and len(cities) == 1:
            comparison_stats = {cities[0]: comparison_stats}

        comparison_result_data = self._calculate_comparison(
            current_stats,
            comparison_stats
        )

        # 6. 返回结果
        result = {
            "status": "success",
            "success": True,
            "data": None,
            "data_id": merged_data_id,
            "result": comparison_result_data,
            "metadata": {
                "schema_version": "v2.0",
                "generator": "compare_standard_reports",
                "generator_version": "1.0.0",
                "query_period": query_period,
                "comparison_period": comparison_period,
                "source_data_ids": [current_data_id, comparison_data_id] if current_data_id and comparison_data_id else [],
                "cities": cities,
                "enable_sand_deduction": enable_sand_deduction
            },
            "summary": self._generate_summary(comparison_result_data, query_period, comparison_period)
        }

        logger.info(
            "compare_standard_reports_completed",
            cities_count=len(comparison_result_data),
            merged_data_id=merged_data_id
        )

        return result

    def _validate_parameters(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """验证参数"""
        # 检查必需参数
        required = ["cities", "query_period", "comparison_period"]
        for key in required:
            if key not in params:
                return False, f"缺少必需参数: {key}"

        # 检查城市列表
        cities = params.get("cities")
        if not isinstance(cities, list) or not cities:
            return False, "cities 必须是非空列表"

        # 检查时间段格式
        for period_key in ["query_period", "comparison_period"]:
            period = params.get(period_key)
            if not isinstance(period, dict):
                return False, f"{period_key} 必须是对象"

            for date_key in ["start_date", "end_date"]:
                date_str = period.get(date_key)
                if not date_str:
                    return False, f"{period_key}.{date_key} 不能为空"

                # 验证日期格式
                try:
                    datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    return False, f"{period_key}.{date_key} 格式错误，应为 YYYY-MM-DD"

        return True, None

    def _error_response(self, error_msg: str) -> Dict[str, Any]:
        """返回错误响应"""
        return {
            "status": "failed",
            "success": False,
            "data": None,
            "metadata": {
                "schema_version": "v2.0",
                "generator": "compare_standard_reports",
                "error": error_msg
            },
            "summary": f"对比分析失败: {error_msg}"
        }

    def _merge_period_data(
        self,
        current_data: List[Dict],
        comparison_data: List[Dict],
        query_period: Dict,
        comparison_period: Dict
    ) -> List[Dict]:
        """合并两个时间段的原始数据，添加标识字段"""
        merged = []

        # 为查询时段数据添加标识
        for record in current_data:
            record_copy = record.copy()
            record_copy["period"] = "current"
            record_copy["period_label"] = self._format_period_label(
                query_period["start_date"],
                query_period["end_date"]
            )
            merged.append(record_copy)

        # 为对比时段数据添加标识
        for record in comparison_data:
            record_copy = record.copy()
            record_copy["period"] = "comparison"
            record_copy["period_label"] = self._format_period_label(
                comparison_period["start_date"],
                comparison_period["end_date"]
            )
            merged.append(record_copy)

        return merged

    def _format_period_label(self, start_date: str, end_date: str) -> str:
        """生成时间段标签"""
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        # 单月: 2025-03
        if start.month == end.month and start.year == end.year:
            return f"{start.year}-{start.month:02d}"

        # 单季度: 2025-Q1
        if start.month == 1 and end.month == 3 and start.year == end.year:
            return f"{start.year}-Q1"
        if start.month == 4 and end.month == 6 and start.year == end.year:
            return f"{start.year}-Q2"
        if start.month == 7 and end.month == 9 and start.year == end.year:
            return f"{start.year}-Q3"
        if start.month == 10 and end.month == 12 and start.year == end.year:
            return f"{start.year}-Q4"

        # 全年: 2025-FY
        if start.month == 1 and end.month == 12 and start.year == end.year:
            return f"{start.year}-FY"

        # 默认: 返回日期范围
        return f"{start_date}_to_{end_date}"

    def _calculate_comparison(
        self,
        current_stats: Dict,
        comparison_stats: Dict
    ) -> Dict:
        """计算对比指标"""
        comparison_result = {}

        for city in current_stats.keys():
            current_city = current_stats[city]
            comparison_city = comparison_stats.get(city, {})

            city_comparison = {
                "query_period": current_city,
                "comparison_period": comparison_city,
                "differences": {},
                "change_rates": {}
            }

            for metric in COMPARISON_METRICS:
                current_value = self._get_nested_value(current_city, metric)
                comparison_value = self._get_nested_value(comparison_city, metric)

                if current_value is None or comparison_value is None:
                    continue

                # 差值：current - comparison
                diff = current_value - comparison_value
                city_comparison["differences"][metric] = diff

                # 变化率：(current - comparison) / comparison * 100
                # 百分比字段（如达标率、超标率）只计算差值，不计算变化率
                if metric in PERCENTAGE_METRICS:
                    # 百分比字段不计算变化率
                    city_comparison["change_rates"][metric] = None
                elif comparison_value != 0:
                    change_rate = (diff / comparison_value) * 100
                    city_comparison["change_rates"][metric] = change_rate
                elif current_value == 0:
                    city_comparison["change_rates"][metric] = 0.0
                else:
                    city_comparison["change_rates"][metric] = float('inf')

            comparison_result[city] = city_comparison

        return comparison_result

    def _get_nested_value(self, data: Dict, path: str):
        """获取嵌套字典中的值（支持 "single_indexes.SO2" 格式）"""
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value

    def _generate_summary(
        self,
        comparison_result: Dict,
        query_period: Dict,
        comparison_period: Dict
    ) -> str:
        """生成对比摘要"""
        if not comparison_result:
            return "对比分析完成，无结果数据"

        query_label = self._format_period_label(
            query_period["start_date"],
            query_period["end_date"]
        )
        comparison_label = self._format_period_label(
            comparison_period["start_date"],
            comparison_period["end_date"]
        )

        # 找出综合指数变化最大的城市
        max_change_city = None
        max_change_value = None

        for city, data in comparison_result.items():
            composite_diff = data.get("differences", {}).get("composite_index")
            if composite_diff is not None:
                if max_change_value is None or abs(composite_diff) > abs(max_change_value):
                    max_change_value = composite_diff
                    max_change_city = city

        # 生成摘要
        summary_parts = [
            f"对比分析完成 ({query_label} vs {comparison_label})",
            f"共 {len(comparison_result)} 个城市"
        ]

        if max_change_city and max_change_value is not None:
            city_data = comparison_result[max_change_city]
            change_rate = city_data.get("change_rates", {}).get("composite_index", 0)

            # 直接根据差值判断趋势
            trend_text = "上升" if max_change_value > 0 else "下降"
            if abs(max_change_value) < 0.001:
                trend_text = "持平"

            summary_parts.append(
                f"{max_change_city}综合指数{trend_text}{abs(max_change_value):.2f}（{abs(change_rate):.1f}%）"
            )

        return "，".join(summary_parts) + "。"
