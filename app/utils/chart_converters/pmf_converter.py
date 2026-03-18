"""
PMF结果图表数据转换器 - UDF v2.0 + Chart v3.1

将PMF分析结果转换为标准图表格式，支持饼图、柱状图、时序图等。
遵循最新的UDF v2.0数据规范和Chart v3.1图表规范。

版本：v2.0
"""

from typing import Any, Dict, List, Optional, Union
import structlog

from app.schemas.pmf import PMFResult
from app.schemas.visualization import ChartResponse, ChartMeta

logger = structlog.get_logger()


class PMFChartConverter:
    """PMF结果图表数据转换器

    专门负责将PMF（正矩阵因子分解）分析结果转换为各种图表格式
    """

    @staticmethod
    def convert_to_chart(
        pmf_result: Union[PMFResult, Dict[str, Any], List[Any]],
        chart_type: str = "pie",
        **kwargs
    ) -> Dict[str, Any]:
        """将PMF结果转换为图表数据

        Args:
            pmf_result: PMF分析结果
            chart_type: 图表类型（pie, bar, timeseries）
            **kwargs: 额外参数（meta信息等）

        Returns:
            图表数据（Chart v3.1格式）
        """
        logger.info(
            "pmf_conversion_start",
            input_type=type(pmf_result).__name__,
            chart_type=chart_type
        )

        # 处理列表格式（来自save_data）
        if isinstance(pmf_result, list):
            if not pmf_result:
                return {"error": "PMF结果列表为空"}
            pmf_result = pmf_result[0]

        # 标准化PMF结果对象
        pmf_result_obj = PMFChartConverter._normalize_pmf_result(pmf_result)

        # 根据图表类型生成对应图表
        if chart_type == "pie":
            return PMFChartConverter._generate_pie_chart(pmf_result_obj, **kwargs)
        elif chart_type == "bar":
            return PMFChartConverter._generate_bar_chart(pmf_result_obj, **kwargs)
        elif chart_type == "timeseries":
            return PMFChartConverter._generate_timeseries_chart(pmf_result_obj, **kwargs)

        return {"error": f"不支持的图表类型: {chart_type}"}

    @staticmethod
    def _normalize_pmf_result(pmf_result: Any) -> Any:
        """标准化PMF结果对象

        Args:
            pmf_result: 原始PMF结果

        Returns:
            标准化后的PMF结果对象
        """
        # 检查是否是新的PMFResult格式（包含sources对象列表）
        is_new_format = (
            isinstance(pmf_result, dict) and
            "sources" in pmf_result and
            isinstance(pmf_result.get("sources"), list)
        )

        if is_new_format:
            # 新格式：已经是PMFResult格式
            try:
                if isinstance(pmf_result["sources"][0], dict):
                    # 字典格式的对象列表，需要转换
                    from app.schemas.pmf import PMFSourceContribution, PMFTimeSeriesPoint

                    sources = []
                    for source in pmf_result["sources"]:
                        if isinstance(source, dict):
                            # 确保所有必需字段存在
                            if "concentration" not in source:
                                source = source.copy()
                                source["concentration"] = 0.0
                            if "confidence" not in source:
                                source = source.copy()
                                source["confidence"] = "Unknown"
                            sources.append(PMFSourceContribution(**source))
                        else:
                            sources.append(source)

                    # 转换timeseries
                    timeseries = []
                    if "timeseries" in pmf_result:
                        for ts in pmf_result["timeseries"]:
                            if isinstance(ts, dict):
                                # 解析时间
                                time_str = ts.get("time", "")
                                if isinstance(time_str, str):
                                    from datetime import datetime
                                    try:
                                        time_obj = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                                    except:
                                        time_obj = datetime.now()
                                else:
                                    time_obj = time_str

                                timeseries.append(PMFTimeSeriesPoint(
                                    time=time_obj,
                                    source_values=ts.get("source_values", {})
                                ))
                            else:
                                timeseries.append(ts)

                    # 构建临时PMFResult对象
                    class TempPMFResult:
                        def __init__(self):
                            self.pollutant = "Unknown"
                            self.station_name = "Unknown"
                            self.sources = []
                            self.timeseries = []

                        def get(self, key, default=None):
                            """模拟字典的get方法"""
                            return getattr(self, key, default)

                    temp_result = TempPMFResult()
                    temp_result.pollutant = pmf_result.get("pollutant", "Unknown")
                    temp_result.station_name = pmf_result.get("station_name", "Unknown")
                    temp_result.sources = sources
                    temp_result.timeseries = timeseries

                    return temp_result
                else:
                    # 已经是PMFResult对象列表
                    pmf_result_obj = pmf_result
                    pmf_result_obj.pollutant = pmf_result.get("pollutant", "Unknown")
                    pmf_result_obj.station_name = pmf_result.get("station_name", "Unknown")
                    return pmf_result_obj

            except Exception as e:
                logger.warning("pmf_convert_new_format_failed", error=str(e))
                # 降级到旧格式处理
                return PMFChartConverter._convert_legacy_format(pmf_result)
        else:
            # 旧格式：直接传入PMFResult对象或包含source_contributions的dict
            has_source_contributions = False
            if isinstance(pmf_result, dict):
                has_source_contributions = "source_contributions" in pmf_result

            # 如果是列表但不是新格式，直接返回错误
            if isinstance(pmf_result, list):
                logger.error("pmf_list_format_not_supported_in_legacy")
                return {"error": "列表格式的PMF数据需要先转换为字典格式"}

            # 处理字典格式
            if isinstance(pmf_result, dict):
                # 如果包含source_contributions字段，转换为sources格式
                if "source_contributions" in pmf_result and "sources" not in pmf_result:
                    source_contributions = pmf_result.get("source_contributions", {})
                    sources_list = [
                        {
                            "source_name": name,
                            "contribution_pct": value,
                            "concentration": 0.0,
                            "confidence": "Unknown"
                        }
                        for name, value in source_contributions.items()
                    ]
                    pmf_result = pmf_result.copy()
                    pmf_result["sources"] = sources_list

                # 确保必填字段存在
                if "timeseries" not in pmf_result:
                    pmf_result["timeseries"] = []
                if "performance" not in pmf_result:
                    pmf_result["performance"] = {"R2": 0.0}

                try:
                    return PMFResult(**pmf_result)
                except Exception as e:
                    logger.warning("pmf_convert_dict_failed", error=str(e))
                    return PMFChartConverter._convert_legacy_format(pmf_result)
            else:
                # 非字典非列表的其他对象
                return pmf_result

    @staticmethod
    def _generate_pie_chart(pmf_result: Any, **kwargs) -> Dict[str, Any]:
        """生成PMF饼图

        Args:
            pmf_result: PMF结果对象
            **kwargs: 额外参数

        Returns:
            饼图数据
        """
        # 提取源贡献率
        if hasattr(pmf_result, 'sources') and pmf_result.sources:
            pie_data = [
                {
                    "name": source.source_name if hasattr(source, 'source_name') else getattr(source, 'source_name', 'Unknown'),
                    "value": source.contribution_pct if hasattr(source, 'contribution_pct') else getattr(source, 'contribution_pct', 0)
                }
                for source in pmf_result.sources
            ]
        else:
            # 兼容旧格式
            pie_data = [
                {"name": k, "value": v}
                for k, v in pmf_result.get("source_contributions", {}).items()
            ]

        station_name = getattr(pmf_result, 'station_name', 'Unknown')
        pollutant = getattr(pmf_result, 'pollutant', 'Unknown')

        # 构建meta信息
        meta = {
            "unit": "%",
            "data_source": "pmf_analysis",
            "pollutant": pollutant,
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        return {
            "id": f"pmf_source_contribution_{station_name}",
            "type": "pie",
            "title": f"{station_name}污染源贡献率",
            "data": pie_data,
            "meta": meta
        }

    @staticmethod
    def _generate_bar_chart(pmf_result: Any, **kwargs) -> Dict[str, Any]:
        """生成PMF柱状图

        Args:
            pmf_result: PMF结果对象
            **kwargs: 额外参数

        Returns:
            柱状图数据
        """
        # 提取源贡献率
        if hasattr(pmf_result, 'sources') and pmf_result.sources:
            bar_data = [
                {
                    "category": source.source_name if hasattr(source, 'source_name') else getattr(source, 'source_name', 'Unknown'),
                    "value": source.contribution_pct if hasattr(source, 'contribution_pct') else getattr(source, 'contribution_pct', 0)
                }
                for source in pmf_result.sources
            ]
        else:
            # 兼容旧格式
            bar_data = [
                {"category": k, "value": v}
                for k, v in pmf_result.get("source_contributions", {}).items()
            ]

        station_name = getattr(pmf_result, 'station_name', 'Unknown')
        pollutant = getattr(pmf_result, 'pollutant', 'Unknown')

        option = {
            "x": [item["category"] for item in bar_data],
            "y": [item["value"] for item in bar_data]
        }

        # 构建meta信息
        meta = {
            "unit": "%",
            "data_source": "pmf_analysis",
            "pollutant": pollutant,
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        return {
            "id": f"pmf_source_contribution_bar_{station_name}",
            "type": "bar",
            "title": f"{station_name}污染源贡献率",
            "data": option,
            "meta": meta
        }

    @staticmethod
    def _generate_timeseries_chart(pmf_result: Any, **kwargs) -> Dict[str, Any]:
        """生成PMF时序图

        Args:
            pmf_result: PMF结果对象
            **kwargs: 额外参数

        Returns:
            时序图数据
        """
        series_data = {}
        x_data = []

        if hasattr(pmf_result, 'timeseries') and pmf_result.timeseries:
            # 新格式：timeseries对象列表
            for point in pmf_result.timeseries:
                time_str = point.time.strftime("%Y-%m-%d %H:%M") if hasattr(point.time, 'strftime') else str(point.time)
                x_data.append(time_str)

                for source_name, value in point.source_values.items():
                    if source_name not in series_data:
                        series_data[source_name] = []
                    series_data[source_name].append(value)
        else:
            # 兼容旧格式
            timeseries = getattr(pmf_result, 'timeseries', [])
            if isinstance(timeseries, dict) and "timeseries" in timeseries:
                timeseries = timeseries["timeseries"]

            if isinstance(timeseries, list):
                for point in timeseries:
                    time_str = point.get("time", "") if isinstance(point, dict) else str(point)
                    x_data.append(time_str)

                    # 提取源值（排除time字段）
                    if isinstance(point, dict):
                        for source_name, value in point.items():
                            if source_name != "time":
                                if source_name not in series_data:
                                    series_data[source_name] = []
                                try:
                                    series_data[source_name].append(float(value))
                                except (ValueError, TypeError):
                                    series_data[source_name].append(0.0)

        series = [
            {"name": name, "data": data}
            for name, data in series_data.items()
        ]

        station_name = getattr(pmf_result, 'station_name', 'Unknown')
        pollutant = getattr(pmf_result, 'pollutant', 'Unknown')

        option = {
            "x": x_data,
            "series": series
        }

        # 构建meta信息
        meta = {
            "unit": "%",
            "data_source": "pmf_analysis",
            "pollutant": pollutant,
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        return {
            "id": f"pmf_timeseries_{station_name}",
            "type": "timeseries",
            "title": f"{station_name}源贡献率时序变化",
            "data": option,
            "meta": meta
        }

    @staticmethod
    def _convert_legacy_format(pmf_result: Dict[str, Any]) -> Dict[str, Any]:
        """处理旧格式PMF结果（降级处理）

        Args:
            pmf_result: 旧格式PMF结果

        Returns:
            降级处理结果
        """
        logger.warning("using_legacy_pmf_converter", keys=list(pmf_result.keys()))

        source_contributions = pmf_result.get("source_contributions", {})
        pie_data = [{"name": k, "value": v} for k, v in source_contributions.items()]

        return {
            "id": "pmf_legacy_pie",
            "type": "pie",
            "title": "PMF源解析结果（兼容模式）",
            "data": pie_data,
            "meta": {
                "unit": "%",
                "data_source": "pmf_analysis_legacy",
                "note": "使用兼容模式生成",
                "schema_version": "3.1"
            }
        }
