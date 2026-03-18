import pandas as pd
import numpy as np

from backend.app.tools.analysis.calculate_reconstruction.calculate_reconstruction import (
    calculate_reconstruction,
)


def _build_sample_df():
    # 构造一个小样本数据集，包含时间戳与常见组分/元素
    times = pd.date_range("2025-01-01", periods=4, freq="H")
    df = pd.DataFrame(
        {
            "timestamp": times,
            "OC": [2.0, 1.5, 0.0, -0.5],
            "NO3": [1.0, 0.8, 0.5, 0.2],
            "SO4": [0.5, 0.6, 0.4, 0.1],
            "NH4": [0.2, 0.3, 0.1, 0.0],
            "EC": [0.8, 0.7, 0.6, 0.5],
            "Si": [1.0, 0.5, 0.0, 0.0],
            "Ca": [0.2, 0.1, 0.0, 0.0],
            "Zn": [0.01, 0.02, 0.0, 0.0],
        }
    )
    return df


def test_calculate_reconstruction_basic():
    df = _build_sample_df()
    res = calculate_reconstruction(data=df, reconstruction_type="hourly", negative_handling="clip")
    assert res["success"] is True
    assert "data" in res
    data = res["data"]
    # 检查输出记录数与输入一致
    assert len(data) == 4
    # 检查 OM 计算（OC * 1.4）
    first = data[0]
    assert round(first.get("OM", 0), 6) == round(2.0 * 1.4, 6)
    # 检查 crustal 已计算为数值（非负）
    assert first.get("crustal", 0) >= 0
    # 检查 trace 被计算
    assert "trace" in first









