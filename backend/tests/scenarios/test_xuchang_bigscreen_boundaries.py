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
    # 画布尺寸与前端 CAPTURE_CANVAS 一致，平面取景后市界完整不裁边
    assert '{"width": 1600, "height": 1200}' in screenshot


def test_map_renders_district_borders_and_light_blue_city_fill():
    panel = (FRONTEND / "src/components/xuchang/bigscreen/StationMapPanel.vue").read_text()
    assert "xuchang_districts.json" in panel
    assert "fillColor: '#75c9f2', fillOpacity: 0.22" in panel
    assert "strokeColor: '#a5dce4', strokeWeight: 1.4" in panel


def test_capture_frames_city_boundary_flat_without_tilt():
    """截图平面视角按市界取景：许昌东西扁平，倾斜构图站点分布不均、两侧空白多。"""
    panel = (FRONTEND / "src/components/xuchang/bigscreen/StationMapPanel.vue").read_text()
    assert "fitCaptureBounds()" in panel
    # 取景须按 Web Mercator 自行解算连续 zoom：setBounds 会吸附整级 zoom，
    # 取景框溢出画布会裁掉遮罩层边缘
    assert "setZoomAndCenter" in panel and "Math.log2" in panel
    assert "CAPTURE_CANVAS" in panel and "CAPTURE_PAD" in panel
    # 截图标题带数据时刻
    assert "captureTimeLabel" in panel
    # 取景须等市界加载完成，且 ready 在取景后才发出（截图页以 ready 判定可截图）
    assert "await boundaryLoaded" in panel
    assert "captureFramed" in panel
    # 2.5D 仅保留为交互切换按钮，capture 模式不自动触发
    assert 'v-if="pitchAvailable && !capture"' in panel
    capture_block = panel.split("if (props.capture) {")[1].split("await nextTick()")[0]
    assert "fitCaptureBounds()" in capture_block
    assert "toggleViewMode()" not in capture_block
