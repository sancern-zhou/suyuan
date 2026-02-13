import pandas as pd
import numpy as np

from backend.app.tools.analysis.calculate_crustal.calculate_crustal import calculate_crustal
from backend.app.tools.analysis.calculate_trace.calculate_trace import calculate_trace


def _build_dust_df():
    times = pd.date_range("2025-01-01", periods=4, freq="H")
    df = pd.DataFrame(
        {
            "timestamp": times,
            "Si": [1.0, 0.5, 0.2, 0.1],
            "Ca": [0.2, 0.1, 0.0, 0.0],
            "Fe": [0.5, 0.4, 0.3, 0.2],
        }
    )
    df = df.set_index("timestamp")
    oxide_coeff = {"Si": 2.14, "Ca": 1.40, "Fe": 1.43}
    return df, oxide_coeff


def _build_trace_df():
    times = pd.date_range("2025-01-01", periods=4, freq="H")
    df = pd.DataFrame(
        {
            "timestamp": times,
            "铝": [2.0, 2.1, 1.9, 2.0],
            "Zn": [0.01, 0.02, 0.01, 0.0],
            "Cu": [0.005, 0.006, 0.004, 0.003],
        }
    )
    df = df.set_index("timestamp")
    taylor = {"Zn": 52.6, "Cu": 14.6}
    return df, taylor


def test_calculate_crustal_basic():
    df, oxide = _build_dust_df()
    res = calculate_crustal(data=df, oxide_coeff_dict=oxide, reconstruction_type="hourly")
    assert res["success"] is True
    assert "data" in res
    assert "oxide_converted" in res["data"]


def test_calculate_trace_basic():
    df, taylor = _build_trace_df()
    res = calculate_trace(data=df, al_column="铝", taylor_dict=taylor)
    assert res["success"] is True
    data = res["data"]
    assert "divided_by_taylor" in data









