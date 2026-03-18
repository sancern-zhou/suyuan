"""
VOCs PMF源解析工具 (Positive Matrix Factorization) - V3.0

Context-Aware V2版本：使用data_id引用而非直接传递大数组

专门用于VOCs挥发性有机物源解析（臭氧溯源），
使用NIMFA无监督因子分解，自动发现VOCs污染源。

V3.0 特性：
- 使用data_id参数（来自get_vocs_data）
- 完整的schema兼容性验证（vocs/vocs_unified）
- ExecutionContext支持
- 自动数据加载和类型转换
- 规范6.1.2权重选择和6.1.3因子数确定

适用范围: 广东省超级站
数据要求: 至少20个样本，5种以上VOCs物种
"""
from app.tools.analysis.calculate_vocs_pmf.tool import CalculateVOCSPMFTool

__all__ = ["CalculateVOCSPMFTool"]
