"""大屏行政区边界资产与地图展示契约测试。"""

from __future__ import annotations

import json
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[3] / "frontend"


def test_xuchang_standard_district_boundaries_are_complete():
    data = json.loads((FRONTEND / "public/geo/xuchang_districts.json").read_text())
    districts = {
        feature["properties"]["name"]: feature
        for feature in data["features"]
    }
    assert set(districts) == {"魏都区", "建安区", "鄢陵县", "襄城县", "禹州市", "长葛市"}
    assert all(feature["properties"]["level"] == "district" for feature in districts.values())
    assert all(feature["geometry"]["coordinates"] for feature in districts.values())


def test_alert_capture_uses_all_station_layers():
    screenshot = (FRONTEND.parent / "backend/app/scenarios/xuchang_town_high_value/screenshot.py").read_text()
    assert 'CAPTURE_LAYERS = ["national", "townships", "shengkong", "office"]' in screenshot
    assert '"layers": ",".join(CAPTURE_LAYERS)' in screenshot


def test_map_renders_district_borders_and_light_blue_city_fill():
    panel = (FRONTEND / "src/components/xuchang/bigscreen/StationMapPanel.vue").read_text()
    assert "xuchang_districts.json" in panel
    assert "fillColor: '#75c9f2', fillOpacity: 0.22" in panel
    assert "strokeColor: '#a5dce4', strokeWeight: 1.4" in panel
    assert "if (props.capture) {" in panel and "toggleViewMode()" in panel
