# -*- coding: utf-8 -*-
from typing import Dict

OXIDE_COEFFICIENTS: Dict[str, float] = {
    # 元素（中文） -> 氧化物换算系数
    "硅": 2.14,   # Si → SiO2
    "钙": 1.40,   # Ca → CaO
    "钛": 1.67,   # Ti → TiO2
    "铁": 1.43,   # Fe → Fe2O3
    "铝": 1.89,   # Al → Al2O3
    "锰": 1.29,   # Mn → MnO
}

TAYLOR_ABUNDANCES: Dict[str, float] = {
    "硅": 28.8,
    "钙": 4.15,
    "钛": 0.44,
    "铁": 4.65,
    "铝": 8.23,
    "锰": 0.10,
}

# 英文元素名到中文名的映射（常用列名兼容）
ELEMENT_NAME_MAP: Dict[str, str] = {
    "Si": "硅",
    "Ca": "钙",
    "Ti": "钛",
    "Fe": "铁",
    "Al": "铝",
    "Mn": "锰",
}

def element_to_oxide_mass(element_mass: float, element_symbol: str) -> float:
    """
    将元素质量（ug/m3）换算为对应氧化物质量（ug/m3）。
    element_symbol 支持英文或中文元素名（如 'Si' 或 '硅'）。
    当未找到系数时返回 0 并且调用方应记录警告。
    """
    if element_mass is None:
        return 0.0
    key = element_symbol
    if key in ELEMENT_NAME_MAP:
        key = ELEMENT_NAME_MAP[key]
    coeff = OXIDE_COEFFICIENTS.get(key)
    if coeff is None:
        return 0.0
    return float(element_mass) * coeff









