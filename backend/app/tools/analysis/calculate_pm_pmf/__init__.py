"""
PMF源解析工具 (Positive Matrix Factorization) - V2.0

Context-Aware版本：使用data_id引用而非直接传递大数组

用于PM2.5/PM10颗粒物与VOCs源解析，识别污染源类型及其贡献率。

V2.0 特性：
- 使用data_id参数（来自get_component_data）
- 完整的schema兼容性验证
- ExecutionContext支持
- 自动数据加载和类型转换

适用范围: 广东省超级站
数据要求: 至少20-30个样本的组分数据
"""
from app.tools.analysis.calculate_pm_pmf.tool import CalculatePMFTool

__all__ = ["CalculatePMFTool"]
