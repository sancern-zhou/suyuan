from typing import Optional

def calculate_sor(sulfate: Optional[float], so2: Optional[float]) -> Optional[float]:
    """
    硫酸氧化率 SOR = sulfate / (sulfate + so2 * 1.5)
    若分母 <= 0 返回 None。
    """
    try:
        s = 0.0 if sulfate is None else float(sulfate)
        so2_v = 0.0 if so2 is None else float(so2)
    except Exception:
        return None
    denom = s + so2_v * 1.5
    if denom <= 0:
        return None
    return s / denom

def calculate_nor(nitrate: Optional[float], no2: Optional[float]) -> Optional[float]:
    """
    硝酸氧化率 NOR = nitrate / (nitrate + no2 * 1.34782)
    若分母 <= 0 返回 None。
    """
    try:
        n = 0.0 if nitrate is None else float(nitrate)
        no2_v = 0.0 if no2 is None else float(no2)
    except Exception:
        return None
    denom = n + no2_v * 1.34782
    if denom <= 0:
        return None
    return n / denom









