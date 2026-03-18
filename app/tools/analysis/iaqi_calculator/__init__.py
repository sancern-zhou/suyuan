"""
IAQI分指数计算工具

基于污染物浓度计算IAQI（中国环境空气质量指数）分指数。
支持PM2.5、PM10、SO2、NO2、CO、O3等主要污染物。
"""

from .tool import IAQICalculatorTool

__all__ = ['IAQICalculatorTool']
