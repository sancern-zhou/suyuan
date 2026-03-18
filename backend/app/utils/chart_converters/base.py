"""
基础转换器和通用工具函数
"""

from typing import Any, Dict, List, Optional, Union
import structlog
import unicodedata

from app.utils.data_standardizer import get_data_standardizer

logger = structlog.get_logger()


def normalize_field_name_for_logging(field_name: str) -> str:
    """
    标准化字段名以避免Unicode字符在Windows GBK环境下导致编码错误

    Args:
        field_name: 原始字段名

    Returns:
        标准化后的字段名(Unicode下标字符替换为普通字符)
    """
    normalized = unicodedata.normalize('NFKD', field_name)
    normalized = normalized.replace('₃', '3').replace('₂', '2').replace('₁', '1').replace('₀', '0')
    return normalized


def validate_and_enhance_chart_v3_1(
    chart: Dict[str, Any],
    generator: str = "chart_data_converter",
    original_data_ids: Optional[List[str]] = None,
    scenario: Optional[str] = None
) -> Dict[str, Any]:
    """
    验证并增强图表配置为v3.1标准

    Args:
        chart: 原始图表配置
        generator: 生成器标识
        original_data_ids: 原始数据ID列表
        scenario: 场景标识

    Returns:
        增强后的图表配置(v3.1)
    """
    required_fields = ["id", "type", "title", "data"]
    missing = [f for f in required_fields if f not in chart]

    if missing:
        logger.warning("chart_v3_1_validation_failed", missing_fields=missing, chart_id=chart.get("id", "unknown"))
        return {"error": f"图表格式不完整,缺少字段: {missing}", "required_fields": required_fields}

    if "meta" not in chart:
        chart["meta"] = {}

    chart["meta"]["schema_version"] = "3.1"
    if generator:
        chart["meta"]["generator"] = generator
    if original_data_ids:
        chart["meta"]["original_data_ids"] = original_data_ids
    if scenario:
        chart["meta"]["scenario"] = scenario

    logger.debug("chart_enhanced_to_v3_1", chart_id=chart.get("id"), chart_type=chart.get("type"), generator=generator)
    return chart


def normalize_chart_type(chart_type: str) -> str:
    """
    标准化图表类型名称,自动纠正常见错误

    Args:
        chart_type: 原始图表类型名称

    Returns:
        标准化后的图表类型名称
    """
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
        logger.info("chart_type_normalized", original=chart_type, normalized=normalized)

    return normalized


def extract_measurement_value(measurements: Dict[str, Any], pollutant_name: str) -> Optional[float]:
    """
    从measurements字典中提取指定污染物的值
    使用data_standardizer进行字段映射

    Args:
        measurements: 测量数据字典
        pollutant_name: 标准污染物名称(如"PM2_5", "O3")

    Returns:
        污染物浓度值,未找到返回None
    """
    if not measurements:
        return None

    standardizer = get_data_standardizer()

    # 1. 直接查找标准字段名
    if pollutant_name in measurements:
        try:
            return float(measurements[pollutant_name])
        except (ValueError, TypeError):
            return None

    # 2. 遍历measurements中的所有字段,查找映射到目标污染物的字段
    for key, value in measurements.items():
        mapped_name = standardizer._get_standard_field_name(key)
        if mapped_name == pollutant_name:
            try:
                return float(value)
            except (ValueError, TypeError):
                return None

    return None


class ChartDataConverter:
    """统一的图表数据转换器入口"""

    @staticmethod
    def convert(data: Any, data_type: Optional[str] = None, chart_type: Optional[str] = None,
                context: Any = None, **kwargs) -> Dict[str, Any]:
        """
        统一的图表数据转换接口

        Args:
            data: 输入数据
            data_type: 数据类型
            chart_type: 图表类型
            context: 执行上下文
            **kwargs: 额外参数

        Returns:
            转换后的图表数据
        """
        from .pmf_converter import PMFConverter
        from .obm_converter import OBMConverter
        from .guangdong_converter import GuangdongConverter
        from .meteorology_converter import MeteorologyConverter
        from .spatial_converter import SpatialConverter

        # 自动检测
        if data_type is None and chart_type is None:
            return ChartDataConverter.auto_detect_and_convert(data)

        # 根据data_type转换
        if data_type in ["pmf", "pmf_result"]:
            return PMFConverter.convert(data, chart_type or "pie")
        elif data_type in ["obm", "obm_ofp_result"]:
            return OBMConverter.convert(data, chart_type or "bar")
        elif data_type in ["guangdong_stations", "guangdong_air_quality", "air_quality_unified",
                          "regional_city_comparison", "regional_station_comparison"]:
            return GuangdongConverter.convert(data, chart_type or "timeseries", context=context, **kwargs)
        elif data_type in ["meteorology", "meteorology_unified", "weather", "meteo"]:
            return MeteorologyConverter.convert(data, chart_type or "wind_rose", **kwargs)
        elif data_type in ["3d", "three_dimensional", "spatial"]:
            return SpatialConverter.convert_3d(data, chart_type or "scatter3d", **kwargs)
        elif data_type in ["map", "heatmap", "location", "geo"]:
            return SpatialConverter.convert_map(data, chart_type or "map", **kwargs)

        return {"error": f"不支持的数据类型: {data_type}"}

    @staticmethod
    def auto_detect_and_convert(data: Any, prefer_chart_type: Optional[str] = None) -> Dict[str, Any]:
        """自动检测数据类型并转换"""
        from .pmf_converter import PMFConverter
        from .obm_converter import OBMConverter

        # 检测PMF结果(新格式: sources对象列表)
        if isinstance(data, dict) and "sources" in data and isinstance(data.get("sources"), list):
            logger.info("auto_convert_detected_pmf_new")
            return PMFConverter.convert(data, prefer_chart_type or "pie")

        # 检测PMF结果(旧格式: source_contributions字典 + timeseries)
        if isinstance(data, dict) and "source_contributions" in data and "timeseries" in data:
            logger.info("auto_convert_detected_pmf_legacy")
            return PMFConverter.convert(data, prefer_chart_type or "pie")

        # 检测OBM结果
        if isinstance(data, dict) and "species_ofp" in data:
            logger.info("auto_convert_detected_obm")
            return OBMConverter.convert(data, prefer_chart_type or "bar")

        logger.warning("auto_convert_unknown_type", data_type=type(data).__name__)
        return {"error": "无法识别数据格式", "data_type": type(data).__name__}
