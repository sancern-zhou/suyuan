"""
站点级新标准报表对比分析工具

对比两个时间段基于 HJ 633-2024 新标准的站点级空气质量统计报表

【核心功能】
- 查询两个时间段的站点统计数据
- 自动对比全部统计指标（综合指数、超标天数、六参数等）
- 返回差值、变化率、趋势判断
- 支持单站点和多站点对比

【对比指标】
- 综合指标：composite_index, exceed_days, exceed_rate, compliance_rate, total_days, valid_days
- 六参数统计浓度：SO2, NO2, PM10, PM2_5, CO, O3_8h 及其百分位数
- 单项质量指数：single_indexes.*
- 首要污染物统计：primary_pollutant_days.*, total_primary_days
- 超标统计：exceed_days_by_pollutant.*
- 首要污染物超标天：primary_pollutant_exceed_days.*
"""

from datetime import datetime
from typing import Dict, List, Any, Optional
import structlog

from app.tools.base import LLMTool, ToolCategory
from app.agent.context.execution_context import ExecutionContext
from app.tools.query.query_station_new_standard_report.tool import execute_query_station_new_standard_report

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
    "O3_8h", "O3_8h_P90",

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

    # 首要污染物超标天
    "primary_pollutant_exceed_days.PM2_5", "primary_pollutant_exceed_days.PM10",
    "primary_pollutant_exceed_days.SO2", "primary_pollutant_exceed_days.NO2",
    "primary_pollutant_exceed_days.CO", "primary_pollutant_exceed_days.O3_8h",
]

# 百分比字段（只计算差值，不计算变化率）
PERCENTAGE_METRICS = {
    "exceed_rate",
    "compliance_rate",
}


class CompareStationStandardReportsTool(LLMTool):
    """站点级新标准报表对比分析工具"""

    def __init__(self):
        function_schema = {
            "name": "compare_station_standard_reports",
            "description": """对比两个时间段基于 HJ 633-2024 新标准的站点级空气质量统计报表。

【核心功能】
- 并发查询两个时间段的站点统计数据
- 自动对比全部统计指标（综合指数、超标天数、六参数等）
- 返回差值、变化率
- 支持单站点和多站点对比

【对比指标】
- 综合指标：composite_index, exceed_days, exceed_rate, compliance_rate, total_days, valid_days
- 六参数统计：SO2, NO2, PM10, PM2_5, CO, O3_8h 及其百分位数
- 单项质量指数：single_indexes.*
- 首要污染物统计：primary_pollutant_days.*, total_primary_days
- 超标统计：exceed_days_by_pollutant.*
- 首要污染物超标天：primary_pollutant_exceed_days.*

【返回数据说明】
- result字段：⭐ 完整的对比结果（包含所有站点的详细对比数据）
  - query_period: 查询时间段的统计数据
  - comparison_period: 对比时间段的统计数据
  - differences: 两个时间段的差值（query_period - comparison_period）
  - change_rates: 变化率百分比（(query_period - comparison_period) / comparison_period * 100）
  - ⚠️ 重要：result 字段包含完整的对比分析结果，**直接用于报告生成和分析**

【多站点汇总对比】（多站点查询时）
- 如果aggregate=true，还包含station_aggregate字段
- station_aggregate结构与单站点对比相同，但数据为多站点汇总统计

【输入参数】
- cities: 城市名称列表（可选，自动展开为站点）
- stations: 站点名称列表（可选，直接查询指定站点）
- query_period: 查询时间段（当前时期）
- comparison_period: 对比时间段（基准时期）
- aggregate: 是否计算多站点汇总对比（默认false）
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "城市名称列表（可选，自动展开为站点），如 ['广州']"
                    },
                    "stations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "站点名称列表（可选，直接查询指定站点），如 ['广雅中学']"
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
                    "aggregate": {
                        "type": "boolean",
                        "description": "是否计算多站点汇总对比（默认false）"
                    }
                },
                "required": ["query_period", "comparison_period"]
            }
        }

        super().__init__(
            name="compare_station_standard_reports",
            description="Compare station standard reports between two time periods",
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

        cities = kwargs.get("cities")
        stations = kwargs.get("stations")
        query_period = kwargs["query_period"]
        comparison_period = kwargs["comparison_period"]
        aggregate = kwargs.get("aggregate", False)

        logger.info(
            "compare_station_standard_reports_start",
            cities=cities,
            stations=stations,
            query_period=query_period,
            comparison_period=comparison_period,
            aggregate=aggregate
        )

        # 2. 查询两个时间段的数据（顺序执行）
        current_result = execute_query_station_new_standard_report(
            cities=cities,
            stations=stations,
            start_date=query_period["start_date"],
            end_date=query_period["end_date"],
            aggregate=aggregate,
            context=context
        )

        comparison_result = execute_query_station_new_standard_report(
            cities=cities,
            stations=stations,
            start_date=comparison_period["start_date"],
            end_date=comparison_period["end_date"],
            aggregate=aggregate,
            context=context
        )

        # 3. 错误处理
        if current_result.get("status") == "failed":
            return self._error_response(f"查询时段失败: {current_result.get('summary', '未知错误')}")

        if comparison_result.get("status") == "failed":
            return self._error_response(f"对比时段失败: {comparison_result.get('summary', '未知错误')}")

        # 4. 提取统计数据
        current_stats = current_result.get("result", {})
        comparison_stats = comparison_result.get("result", {})

        # 5. 计算对比指标
        comparison_result_data = self._calculate_comparison(
            current_stats,
            comparison_stats
        )

        # 6. 构建摘要
        station_count = len([s for s in current_stats.keys() if s != "station_aggregate"])
        if station_count == 1:
            # 单站点查询，找到站点名称
            station_name = next((s for s in current_stats.keys() if s != "station_aggregate"), "未知站点")
            summary_text = f"{station_name} 站点新标准报表对比分析完成（{query_period['start_date']}至{query_period['end_date']} vs {comparison_period['start_date']}至{comparison_period['end_date']}，数据为审核实况）"
        else:
            summary_text = f"多站点新标准报表对比分析完成（{query_period['start_date']}至{query_period['end_date']} vs {comparison_period['start_date']}至{comparison_period['end_date']}，共{station_count}个站点，数据为审核实况）"

        # 7. 返回结果
        result = {
            "status": "success",
            "success": True,
            "data": None,
            "result": comparison_result_data,
            "summary": summary_text,
            "metadata": {
                "schema_version": "v2.0",
                "generator": "compare_station_standard_reports",
                "generator_version": "1.0.0",
                "query_period": query_period,
                "comparison_period": comparison_period,
                "cities": cities or [],
                "stations": stations or [],
                "aggregate": aggregate,
                "station_count": station_count,
            }
        }

        logger.info(
            "compare_station_standard_reports_completed",
            station_count=station_count,
            aggregate_calculated=aggregate
        )

        return result

    def _validate_parameters(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """验证参数"""
        # 检查必需参数
        required = ["query_period", "comparison_period"]
        for key in required:
            if key not in params:
                return False, f"缺少必需参数: {key}"

        # 检查是否有城市或站点
        cities = params.get("cities")
        stations = params.get("stations")
        if not cities and not stations:
            return False, "必须指定 cities 或 stations 参数"

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
                "generator": "compare_station_standard_reports",
                "error": error_msg
            },
            "summary": f"站点对比分析失败: {error_msg}"
        }

    def _calculate_comparison(
        self,
        current_stats: Dict,
        comparison_stats: Dict
    ) -> Dict:
        """计算对比指标"""
        comparison_result = {}

        # 遍历所有站点（除了 station_aggregate）
        station_names = [s for s in current_stats.keys() if s != "station_aggregate"]

        for station_name in station_names:
            current_station = current_stats.get(station_name, {})
            comparison_station = comparison_stats.get(station_name, {})

            # 检查是否都有数据
            if "error" in current_station or "error" in comparison_station:
                # 如果任一时期有错误，跳过该站点
                continue

            station_comparison = {
                "query_period": current_station,
                "comparison_period": comparison_station,
                "differences": {},
                "change_rates": {}
            }

            for metric in COMPARISON_METRICS:
                current_value = self._get_nested_value(current_station, metric)
                comparison_value = self._get_nested_value(comparison_station, metric)

                if current_value is None or comparison_value is None:
                    continue

                # 差值：current - comparison
                diff = current_value - comparison_value
                station_comparison["differences"][metric] = diff

                # 变化率：(current - comparison) / comparison * 100
                # 百分比字段只计算差值，不计算变化率
                if metric in PERCENTAGE_METRICS:
                    station_comparison["change_rates"][metric] = None
                elif comparison_value != 0:
                    change_rate = (diff / comparison_value) * 100
                    station_comparison["change_rates"][metric] = change_rate
                elif current_value == 0:
                    station_comparison["change_rates"][metric] = 0.0
                else:
                    # comparison_value=0 且 current_value!=0，变化率无意义
                    station_comparison["change_rates"][metric] = None

            comparison_result[station_name] = station_comparison

        # 计算多站点汇总对比（如果存在）
        if "station_aggregate" in current_stats and "station_aggregate" in comparison_stats:
            current_aggregate = current_stats["station_aggregate"]
            comparison_aggregate = comparison_stats["station_aggregate"]

            aggregate_comparison = {
                "query_period": current_aggregate,
                "comparison_period": comparison_aggregate,
                "differences": {},
                "change_rates": {}
            }

            for metric in COMPARISON_METRICS:
                current_value = self._get_nested_value(current_aggregate, metric)
                comparison_value = self._get_nested_value(comparison_aggregate, metric)

                if current_value is None or comparison_value is None:
                    continue

                # 差值
                diff = current_value - comparison_value
                aggregate_comparison["differences"][metric] = diff

                # 变化率
                if metric in PERCENTAGE_METRICS:
                    aggregate_comparison["change_rates"][metric] = None
                elif comparison_value != 0:
                    change_rate = (diff / comparison_value) * 100
                    aggregate_comparison["change_rates"][metric] = change_rate
                elif current_value == 0:
                    aggregate_comparison["change_rates"][metric] = 0.0
                else:
                    aggregate_comparison["change_rates"][metric] = None

            comparison_result["station_aggregate"] = aggregate_comparison

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
