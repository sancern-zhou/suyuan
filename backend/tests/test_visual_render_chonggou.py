import os
import shutil
from backend.app.tools.visualization.scientific_charts.chonggou import render_chonggou_from_payload


def _sample_payload():
    data = [
        {"timestamp": "2025-01-01T00:00:00Z", "OM": 2.0, "NO3": 1.0, "SO4": 0.5, "NH4": 0.2, "EC": 0.8, "crustal": 1.0, "trace": 0.01, "PM2.5": 50},
        {"timestamp": "2025-01-01T01:00:00Z", "OM": 1.5, "NO3": 0.8, "SO4": 0.6, "NH4": 0.3, "EC": 0.7, "crustal": 0.9, "trace": 0.02, "PM2.5": 45},
    ]
    return {
        "data": data,
        "series": ["OM", "NO3", "SO4", "NH4", "EC", "crustal", "trace"],
        "x": "timestamp",
    }


def test_render_chonggou_generates_files(tmp_path):
    out_dir = tmp_path / "mapout" / "chonggou"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_svg = str(out_dir / "chonggou_test.svg")
    payload = _sample_payload()
    saved = render_chonggou_from_payload(payload, out_svg, fmt="svg", dpi=150)
    assert isinstance(saved, dict)
    assert "svg" in saved and saved["svg"] == out_svg
    # png 也应该存在
    png_path = out_svg.replace(".svg", ".png")
    assert "png" in saved and saved["png"] == png_path
    assert os.path.exists(saved["svg"])
    assert os.path.exists(saved["png"])
    # cleanup
    shutil.rmtree(str(tmp_path))









