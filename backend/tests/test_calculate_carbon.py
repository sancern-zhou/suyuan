import pandas as pd
import numpy as np

from backend.app.tools.analysis.calculate_carbon.calculate_carbon import calculate_carbon


def _build_sample_df():
    times = pd.date_range("2025-01-01", periods=6, freq="H")
    df = pd.DataFrame(
        {
            "timestamp": times,
            "OC": [2.0, 1.8, 1.5, np.nan, 1.0, 0.5],
            "EC": [0.8, 0.7, 0.6, 0.5, np.nan, 0.2],
            "PM2.5": [50, 45, 40, 35, 30, 25],
        }
    )
    df = df.set_index("timestamp")
    return df


def test_calculate_carbon_basic():
    df = _build_sample_df()
    res = calculate_carbon(data=df, poc_method="ec_normalization")
    assert res["success"] is True
    data = res["data"]
    # 应包含 SOC/POC/EC_OC 字段
    rec0 = data[0]
    assert "POC" in rec0
    assert "SOC" in rec0
    assert "EC_OC" in rec0
    # 当 OC 与 EC 有值时 EC_OC 应为数值
    non_null = [r for r in data if r.get("EC") is not None and r.get("OC") not in (None, 0)]
    if non_null:
        assert any((r.get("EC_OC") is not None) for r in non_null)









