import pandas as pd
import numpy as np

from backend.app.tools.analysis.calculate_soluble.calculate_soluble import calculate_soluble


def _build_sample_df():
    times = pd.date_range("2025-01-01", periods=5, freq="H")
    df = pd.DataFrame(
        {
            "timestamp": times,
            "硝酸根": [1.0, 0.8, 0.5, 0.2, np.nan],
            "硫酸根": [0.5, 0.6, 0.4, 0.1, 0.0],
            "铵离子": [0.8, 0.7, 0.6, 0.5, 0.4],
            "NO2": [10, 8, 5, 2, 1],
            "SO2": [5, 4, 3, 2, 1],
            "PM2.5": [60, 50, 40, 30, 20],
        }
    )
    df = df.set_index("timestamp")
    return df


def test_calculate_soluble_basic():
    df = _build_sample_df()
    res = calculate_soluble(data=df, analysis_type="full")
    assert res["success"] is True
    assert "data" in res
    data = res["data"]
    # 检查 ternary 输出包含 x,y
    tern = data["ternary"]
    assert isinstance(tern, list)
    if len(tern) > 0:
        assert "x" in tern[0] and "y" in tern[0]
    # 检查 OR 输出包含 NOR 和 SOR
    orr = data["or"]
    assert isinstance(orr, list)
    if len(orr) > 0:
        assert "NOR" in orr[0] and "SOR" in orr[0]









