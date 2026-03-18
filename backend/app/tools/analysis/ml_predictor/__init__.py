"""
机器学习预测工具

基于历史数据和机器学习算法预测污染物浓度和空气质量。
支持线性回归、随机森林、LSTM等多种算法。
"""

from .tool import MLPredictorTool

__all__ = ['MLPredictorTool']
