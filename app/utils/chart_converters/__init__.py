"""
图表数据转换器包 v2.0

本包是图表数据转换器的重构版本，已完全模块化拆分。

模块结构：
- chart_data_converter.py: 主入口，集成所有转换器
- pmf_converter.py: PMF结果转换器
- obm_converter.py: OBM/OFP结果转换器
- vocs_converter.py: VOCs数据转换器
- meteorology_converter.py: 气象数据转换器
- d3_converter.py: 3D图表转换器
- map_converter.py: 地图转换器

版本历史：
- v3.1: 初始版本（已废弃）
- v2.0: 重构版本（当前版本）

重构时间: 2025-11-20
重构者: Claude Code

更新日志：
- v2.0.2: 修复空气质量数据转换，使用统一字段映射，支持O3和O3_8h区分
- v2.0.1: 添加air_quality_unified数据类型支持
"""

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

__all__ = [
    'ChartDataConverter',
    'convert_chart_data',
    'PMFChartConverter',
    'OBMChartConverter',
    'VOCsChartConverter',
    'MeteorologyChartConverter',
    'D3ChartConverter',
    'MapChartConverter',
    '_normalize_field_name_for_logging',
    '_validate_and_enhance_chart_v3_1',
    '__version__'
]

__version__ = "2.0.2"
