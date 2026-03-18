"""
OBM/OFP结果图表数据转换器 - UDF v2.0 + Chart v3.1

将OBM（臭氧生成潜势）分析结果转换为标准图表格式，支持饼图、柱状图、雷达图等。
遵循最新的UDF v2.0数据规范和Chart v3.1图表规范。

版本：v2.0
"""

from typing import Any, Dict, List, Optional, Union
import structlog

from app.schemas.obm import OBMOFPResult

logger = structlog.get_logger()


class OBMChartConverter:
    """OBM/OFP结果图表数据转换器

    专门负责将OBM（Observation-Based Model）和OFP（Ozone Formation Potential）分析结果
    转换为各种图表格式
    """

    @staticmethod
    def convert_to_chart(
        obm_result: Union[OBMOFPResult, Dict[str, Any], List[Any]],
        chart_type: str = "bar",
        **kwargs
    ) -> Dict[str, Any]:
        """将OBM/OFP结果转换为图表数据

        Args:
            obm_result: OBM/OFP分析结果
            chart_type: 图表类型（pie, bar, sensitivity/radar）
            **kwargs: 额外参数（meta信息等）

        Returns:
            图表数据（Chart v3.1格式）
        """
        logger.info(
            "obm_conversion_start",
            input_type=type(obm_result).__name__,
            chart_type=chart_type
        )

        # 处理列表格式（来自save_data）
        if isinstance(obm_result, list):
            if not obm_result:
                return {"error": "OBM结果列表为空"}
            obm_result = obm_result[0]

        # 转换为OBMOFPResult对象
        if isinstance(obm_result, dict):
            try:
                obm_result = OBMOFPResult(**obm_result)
            except Exception as e:
                logger.warning("obm_convert_dict_failed", error=str(e))
                return {"error": f"OBM结果格式转换失败: {e}"}

        # 根据图表类型生成对应图表
        if chart_type == "pie":
            return OBMChartConverter._generate_pie_chart(obm_result, **kwargs)
        elif chart_type == "bar":
            return OBMChartConverter._generate_bar_chart(obm_result, **kwargs)
        elif chart_type in ["sensitivity", "radar"]:
            return OBMChartConverter._generate_radar_chart(obm_result, **kwargs)

        return {"error": f"不支持的图表类型: {chart_type}"}

    @staticmethod
    def _generate_pie_chart(obm_result: OBMOFPResult, **kwargs) -> Dict[str, Any]:
        """生成OBM饼图（VOC类别OFP贡献）

        Args:
            obm_result: OBM结果对象
            **kwargs: 额外参数

        Returns:
            饼图数据
        """
        # 饼图：VOC类别OFP贡献
        pie_data = [
            {
                "name": category.category,
                "value": category.total_ofp
            }
            for category in obm_result.category_summary
        ]

        # 构建meta信息
        meta = {
            "unit": "ppb",
            "data_source": "obm_ofp_analysis",
            "total_ofp": obm_result.total_ofp,
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        return {
            "id": f"obm_category_ofp_{obm_result.station_name}",
            "type": "pie",
            "title": f"{obm_result.station_name}VOC类别OFP贡献",
            "data": pie_data,
            "meta": meta
        }

    @staticmethod
    def _generate_bar_chart(obm_result: OBMOFPResult, **kwargs) -> Dict[str, Any]:
        """生成OBM柱状图（VOC物种OFP贡献Top 10）

        Args:
            obm_result: OBM结果对象
            **kwargs: 额外参数

        Returns:
            柱状图数据
        """
        # 柱状图：VOC物种OFP贡献（Top 10）
        species_ofp = obm_result.species_ofp
        # 按OFP值排序，取前10
        species_sorted = sorted(
            species_ofp,
            key=lambda x: x.get("ofp", 0),
            reverse=True
        )[:10]

        bar_data = [
            {
                "category": item.get("species", "Unknown"),
                "value": item.get("ofp", 0)
            }
            for item in species_sorted
        ]

        option = {
            "x": [item["category"] for item in bar_data],
            "y": [item["value"] for item in bar_data]
        }

        # 构建meta信息
        meta = {
            "unit": "ppb",
            "data_source": "obm_ofp_analysis",
            "total_ofp": obm_result.total_ofp,
            "primary_vocs": obm_result.primary_vocs,
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        return {
            "id": f"obm_species_ofp_{obm_result.station_name}",
            "type": "bar",
            "title": f"{obm_result.station_name}VOC物种OFP贡献(Top 10)",
            "data": option,
            "meta": meta
        }

    @staticmethod
    def _generate_radar_chart(obm_result: OBMOFPResult, **kwargs) -> Dict[str, Any]:
        """生成OBM敏感性分析雷达图

        Args:
            obm_result: OBM结果对象
            **kwargs: 额外参数

        Returns:
            雷达图数据
        """
        # 敏感性分析图表 - 雷达图
        sensitivity = obm_result.sensitivity

        option = {
            "x": ["VOCs控制效果", "NOx控制效果"],
            "y": [
                sensitivity.vocs_control_effectiveness,
                sensitivity.nox_control_effectiveness
            ]
        }

        # 构建meta信息
        meta = {
            "unit": "%",
            "data_source": "obm_ofp_analysis",
            "sensitivity_type": sensitivity.sensitivity_type,
            "recommendation": sensitivity.recommendation,
            "schema_version": "3.1"
        }
        if "generator" in kwargs:
            meta["generator"] = kwargs["generator"]
        if "scenario" in kwargs:
            meta["scenario"] = kwargs["scenario"]

        return {
            "id": f"obm_sensitivity_{obm_result.station_name}",
            "type": "radar",
            "title": f"{obm_result.station_name}O3生成敏感性诊断",
            "data": option,
            "meta": meta
        }
