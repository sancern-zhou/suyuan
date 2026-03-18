import numpy as np
from typing import Tuple

def to_ternary_coordinates(a: float, b: float, c: float) -> Tuple[float, float]:
    """
    三元坐标转换：把 (a,b,c) 转为笛卡尔坐标 (x,y) 便于绘图。
    当 total <= 0 时返回 (np.nan, np.nan)。
    """
    try:
        total = float(a) + float(b) + float(c)
    except Exception:
        return (np.nan, np.nan)
    if total <= 0 or np.isclose(total, 0.0):
        return (np.nan, np.nan)
    a_norm = float(a) / total
    b_norm = float(b) / total
    c_norm = float(c) / total
    x = 0.5 * (2 * b_norm + c_norm)
    y = (np.sqrt(3) / 2.0) * c_norm
    return x, y









