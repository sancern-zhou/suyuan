"""
百分位数计算模块

使用线性插值法计算百分位数
"""

from typing import List, Union


def calculate_percentile(values: List[Union[float, int, None]], percentile: float) -> float:
    """
    计算百分位数（线性插值法）

    Args:
        values: 数值列表
        percentile: 百分位数（0-100），如50表示中位数，98表示98百分位

    Returns:
        计算得到的百分位数值

    Examples:
        >>> calculate_percentile([1, 2, 3, 4, 5], 50)
        3.0
        >>> calculate_percentile([1, 2, 3, 4, 5, 6], 50)
        3.5
    """
    if not values:
        return 0.0

    # 过滤None值并排序
    sorted_values = sorted([v for v in values if v is not None])
    n = len(sorted_values)

    if n == 0:
        return 0.0
    if n == 1:
        return float(sorted_values[0])

    # 计算索引位置（线性插值法）
    index = (percentile / 100) * (n - 1)
    lower = int(index)
    upper = lower + 1

    # 如果索引超出范围，返回最大值
    if upper >= n:
        return float(sorted_values[-1])

    # 线性插值
    weight = index - lower
    result = sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight

    return float(result)
