"""
VOCs数据图表转换器 - UDF v2.0 + Chart v3.1

将VOCs（挥发性有机物）数据转换为标准图表格式，支持时序图、饼图、柱状图等。
遵循最新的UDF v2.0数据规范和Chart v3.1图表规范。

版本：v2.0
"""

from typing import Any, Dict, List, Optional, Union
import structlog

from app.schemas.vocs import UnifiedVOCsData

logger = structlog.get_logger()


class VOCsChartConverter:
    """VOCs数据图表转换器

    专门负责将VOCs（挥发性有机物）数据转换为各种图表格式
    """

    @staticmethod
    def convert_to_chart(
        data: Union[List[UnifiedVOCsData], List[Dict[str, Any]], Dict[str, Any]],
        chart_type: str = "timeseries",
        **kwargs
    ) -> Dict[str, Any]:
        """将VOCs数据转换为图表数据

        Args:
            data: VOCs数据（UnifiedVOCsData对象或字典列表）
            chart_type: 图表类型（timeseries, pie, bar）
            **kwargs: 额外参数（meta信息等）

        Returns:
            图表数据（Chart v3.1格式）
        """
        logger.info(
            "vocs_conversion_start",
            input_type=type(data).__name__,
            chart_type=chart_type,
            record_count=len(data) if isinstance(data, (list, dict)) and "data" not in data else 0
        )

        # 如果是UDF格式，提取data字段
        if isinstance(data, dict) and "data" in data:
            data = data["data"]

        # 如果是列表格式但为空
        if not data or (isinstance(data, list) and len(data) == 0):
            return {"error": "VOCs统一数据为空"}

        # 兼容处理：自动纠正常见的图表类型命名错误
        chart_type = VOCsChartConverter._normalize_chart_type(chart_type)

        if chart_type == "timeseries":
            return VOCsChartConverter._generate_timeseries(data, **kwargs)
        elif chart_type == "pie":
            return VOCsChartConverter._generate_pie(data, **kwargs)
        elif chart_type == "bar":
            return VOCsChartConverter._generate_bar(data, **kwargs)

        return {"error": f"不支持的VOCs图表类型: {chart_type}"}

    @staticmethod
    def _normalize_chart_type(chart_type: str) -> str:
        """标准化图表类型名称，自动纠正常见错误"""
        chart_type = chart_type.strip().lower()

        type_mapping = {
            "auto": "bar",
            "automatic": "bar",
            "time_series": "timeseries",
            "time-series": "timeseries",
            "timeseries_chart": "timeseries",
            "line_chart": "line",
            "bar_chart": "bar",
            "pie_chart": "pie"
        }

        normalized = type_mapping.get(chart_type, chart_type)
        if normalized != chart_type:
            logger.info(
                "chart_type_normalized",
                original=chart_type,
                normalized=normalized
            )

        return normalized

    @staticmethod
    def _generate_timeseries(
        data: Union[List[UnifiedVOCsData], List[Dict[str, Any]]],
        **kwargs
    ) -> Dict[str, Any]:
        """生成VOCs时序图（多物种浓度变化）

        Args:
            data: VOCs数据列表
            **kwargs: 额外参数

        Returns:
            时序图数据
        """
        # 收集所有时间点和物种
        time_points = []
        species_values = {}
        station_name = "Unknown"

        for item in data:
            if isinstance(item, dict):
                # 字典格式
                timestamp = item.get("timestamp", "")
                species_data = item.get("species_data", {})
                station_name = item.get("station_name", station_name)

                if not timestamp or not species_data:
                    continue

                time_points.append(timestamp)

                # 收集各物种数据
                for species_name, concentration in species_data.items():
                    if species_name not in species_values:
                        species_values[species_name] = []
                    try:
                        species_values[species_name].append(float(concentration))
                    except (ValueError, TypeError):
                        species_values[species_name].append(0.0)
            else:
                # UnifiedVOCsData对象格式
                timestamp = item.timestamp
                species_data = item.species_data
                station_name = item.station_name

                if not timestamp or not species_data:
                    continue

                time_points.append(timestamp)

                for species_name, concentration in species_data.items():
                    if species_name not in species_values:
                        species_values[species_name] = []
                    species_values[species_name].append(float(concentration))

        if not time_points or not species_values:
            return {"error": "VOCs数据中缺少时间或物种信息"}

        # 选择前10个主要物种（数据最多的）
        species_sorted = sorted(
            species_values.items(),
            key=lambda x: len([v for v in x[1] if v > 0]),
            reverse=True
        )[:10]

        # 构建series数据
        series = []
        for species_name, values in species_sorted:
            series.append({
                "name": species_name,
                "data": values,
                "stack": "total",
                "showSymbol": False,
                "areaStyle": {"opacity": 0.7}
            })

        option = {
            "x": time_points,
            "series": series,
            "stacked": True,
            "chart_style": "stacked_area"
        }

        # 构建meta信息
        meta = {
            "unit": "ppb",
            "data_source": "vocs_unified",
            "station_name": station_name,
            "species_count": len(series),
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        return {
            "id": f"vocs_unified_timeseries_{station_name}",
            "type": "timeseries",
            "title": f"{station_name}VOCs物种浓度时序变化",
            "data": option,
            "meta": meta
        }

    @staticmethod
    def _generate_pie(
        data: Union[List[UnifiedVOCsData], List[Dict[str, Any]]],
        **kwargs
    ) -> Dict[str, Any]:
        """生成VOCs饼图（平均浓度占比）

        Args:
            data: VOCs数据列表
            **kwargs: 额外参数

        Returns:
            饼图数据
        """
        # 计算各物种平均浓度
        species_totals = {}
        station_name = "Unknown"

        for item in data:
            if isinstance(item, dict):
                species_data = item.get("species_data", {})
                station_name = item.get("station_name", station_name)

                for species_name, concentration in species_data.items():
                    if species_name not in species_totals:
                        species_totals[species_name] = 0.0
                    try:
                        species_totals[species_name] += float(concentration)
                    except (ValueError, TypeError):
                        pass
            else:
                species_data = item.species_data
                station_name = item.station_name

                for species_name, concentration in species_data.items():
                    if species_name not in species_totals:
                        species_totals[species_name] = 0.0
                    species_totals[species_name] += float(concentration)

        if not species_totals:
            return {"error": "VOCs数据中缺少物种信息"}

        # 计算平均浓度
        avg_concentrations = {
            name: total / len(data)
            for name, total in species_totals.items()
        }

        # 取前10个
        pie_data = [
            {"name": name, "value": value}
            for name, value in sorted(
                avg_concentrations.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]
        ]

        # 构建meta信息
        meta = {
            "unit": "ppb",
            "data_source": "vocs_unified",
            "station_name": station_name,
            "record_count": len(data),
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        return {
            "id": f"vocs_unified_pie_{station_name}",
            "type": "pie",
            "title": f"{station_name}VOCs平均浓度占比",
            "data": pie_data,
            "meta": meta
        }

    @staticmethod
    def _generate_bar(
        data: Union[List[UnifiedVOCsData], List[Dict[str, Any]]],
        **kwargs
    ) -> Dict[str, Any]:
        """生成VOCs柱状图（平均浓度排名）

        Args:
            data: VOCs数据列表
            **kwargs: 额外参数

        Returns:
            柱状图数据
        """
        # 计算各物种平均浓度
        species_totals = {}
        station_name = "Unknown"

        for item in data:
            if isinstance(item, dict):
                species_data = item.get("species_data", {})
                station_name = item.get("station_name", station_name)

                for species_name, concentration in species_data.items():
                    if species_name not in species_totals:
                        species_totals[species_name] = 0.0
                    try:
                        species_totals[species_name] += float(concentration)
                    except (ValueError, TypeError):
                        pass
            else:
                species_data = item.species_data
                station_name = item.station_name

                for species_name, concentration in species_data.items():
                    if species_name not in species_totals:
                        species_totals[species_name] = 0.0
                    species_totals[species_name] += float(concentration)

        if not species_totals:
            return {"error": "VOCs数据中缺少物种信息"}

        # 计算平均浓度并排序
        avg_concentrations = [
            {"category": name, "value": total / len(data)}
            for name, total in species_totals.items()
        ]
        avg_concentrations.sort(key=lambda x: x["value"], reverse=True)
        avg_concentrations = avg_concentrations[:10]

        option = {
            "x": [item["category"] for item in avg_concentrations],
            "y": [item["value"] for item in avg_concentrations]
        }

        # 构建meta信息
        meta = {
            "unit": "ppb",
            "data_source": "vocs_unified",
            "station_name": station_name,
            "record_count": len(data),
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        return {
            "id": f"vocs_unified_bar_{station_name}",
            "type": "bar",
            "title": f"{station_name}VOCs平均浓度排名",
            "data": option,
            "meta": meta
        }
