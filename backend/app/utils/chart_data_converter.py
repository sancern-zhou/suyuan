"""
图表数据转换器 v2.0 - 重构版本

本文件是v2.0重构版本的图表数据转换器，已完全模块化拆分。

重构说明：
- 原文件(4422行)已拆分为7个独立模块
- 使用统一的字段映射系统（data_standardizer）
- 移除所有冗余代码和重复逻辑
- 遵循UDF v2.0和Chart v3.1规范

模块结构：
- chart_data_converter.py: 主入口，集成所有转换器
- pmf_converter.py: PMF结果转换器
- obm_converter.py: OBM/OFP结果转换器
- vocs_converter.py: VOCs数据转换器
- meteorology_converter.py: 气象数据转换器
- d3_converter.py: 3D图表转换器
- map_converter.py: 地图转换器

使用方式：
from app.utils.chart_data_converter import convert_chart_data

或者：
from app.utils.chart_converters.chart_data_converter import ChartDataConverter
converter = ChartDataConverter()
result = converter.convert_pmf_result(data, chart_type="pie")

版本历史：
- v3.1: 初始版本（已废弃）
- v2.0: 重构版本（当前版本）
- v2.0.2: 修复空气质量数据转换，使用统一字段映射，支持O3和O3_8h区分
- v2.0.1: 添加air_quality_unified数据类型支持

重构时间: 2025-11-20
重构者: Claude Code
"""

# 向后兼容 - 导入新模块的所有内容
from app.utils.chart_converters.chart_data_converter import (
    ChartDataConverter,
    convert_chart_data,
    PMFChartConverter,
    OBMChartConverter,
    VOCsChartConverter,
    MeteorologyChartConverter,
    D3ChartConverter,
    MapChartConverter,
    _normalize_field_name_for_logging,
    _validate_and_enhance_chart_v3_1,
    __version__
)

# 保持原有类的别名以确保向后兼容
_ChartDataConverter = ChartDataConverter

# 标记文件状态
__deprecated__ = True
__refactored__ = True
__refactor_date__ = "2025-11-20"
__version__ = "2.0.2"

# 日志警告
import structlog
logger = structlog.get_logger(__name__)

logger.warning(
    "chart_data_converter_v2_refactoring",
    message=(
        "原始chart_data_converter.py已重构为模块化结构。"
        "请使用新的导入方式：from app.utils.chart_converters.chart_data_converter import convert_chart_data"
    ),
    new_location="app.utils.chart_converters.chart_data_converter",
    old_location="app.utils.chart_data_converter",
    version="2.0.2"
)
