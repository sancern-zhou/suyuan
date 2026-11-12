"""city_boundary_map 域渲染器单元测试。

真实资产仅用于 adcode/名称匹配冒烟；其余用例走内联小 GeoJSON，保持快速且不依赖资产内容。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.tools.visualization.create_business_chart.domain.city_boundary_map import (
    COLORS,
    DEFAULT_BOUNDARY_ASSET,
    _continuous_level_colors,
    _level_color_anchors,
    _record_seed_value,
    render_city_boundary_map,
)


def _square_feature(adcode: int, name: str, x: float, y: float) -> dict:
    """以 (x, y) 为中心的 1°×1° 方形城市要素，centroid 取中心。"""
    ring = [[x - 0.5, y - 0.5], [x + 0.5, y - 0.5], [x + 0.5, y + 0.5], [x - 0.5, y + 0.5]]
    return {
        "type": "Feature",
        "properties": {
            "adcode": adcode,
            "name": name,
            "centroid": [x, y],
            "center": [x, y],
            "level": "city",
            "province_adcode": int(x),
            "province_name": "测试省",
        },
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def _inline_geojson() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            _square_feature(320100, "南京市", 118.8, 32.0),
            _square_feature(370800, "济宁市", 116.6, 35.4),
            _square_feature(310000, "上海市", 121.5, 31.2),
        ],
    }


def _render_inline(data: dict, options: dict | None = None):
    data = {"geojson": _inline_geojson(), **data}
    return render_city_boundary_map("测试填色图", data, options or {}, "word")


def test_adcode_matching_renders_and_reports_metadata():
    image_base64, metadata, warnings = _render_inline(
        {"metric": "AQI", "records": [
            {"adcode": 320100, "value": 45},
            {"adcode": 370800, "value": 92},
            {"adcode": 310000, "value": 160},
        ]}
    )

    assert image_base64
    assert metadata["city_count"] == 3
    assert metadata["rendered_polygon_count"] == 3
    assert metadata["unmatched_record_count"] == 0
    assert metadata["boundary_asset"] == "inline_geojson"
    assert metadata["scope"] == "china_city_level"
    assert metadata["classification_basis"] == "AQI"
    assert warnings == []


def test_name_matching_strips_city_suffix():
    _, metadata, _ = _render_inline(
        {"records": [{"city": "南京市", "value": 60}, {"city": "上海", "value": 70}]}
    )

    assert metadata["city_count"] == 2
    assert metadata["unmatched_record_count"] == 0


def test_unmatched_records_are_reported_not_rendered():
    image_base64, metadata, warnings = _render_inline(
        {"records": [
            {"adcode": 320100, "value": 60},
            {"city": "不存在市", "value": 70},
            {"adcode": 999999, "value": 80},
        ]}
    )

    assert image_base64
    assert metadata["city_count"] == 1
    assert metadata["unmatched_record_count"] == 2
    assert metadata["rendered_polygon_count"] == 1
    assert warnings and "不存在市" in warnings[0] and "999999" in warnings[0]


def test_group_order_and_primary_group_metadata():
    _, metadata, _ = _render_inline(
        {"records": [
            {"adcode": 320100, "value": 60, "group": "近场"},
            {"adcode": 370800, "value": 70, "group": "核心"},
            {"adcode": 310000, "value": 80, "group": "近场"},
        ]},
        {"star_adcode": 370800},
    )

    assert metadata["groups"] == ["近场", "核心"]  # 按首次出现排序
    assert metadata["city_count"] == 3


def test_group_order_option_fixes_primary_group():
    _, metadata, _ = _render_inline(
        {"records": [
            {"adcode": 320100, "value": 60, "group": "近场"},
            {"adcode": 370800, "value": 70, "group": "核心"},
        ]},
        {"group_order": ["核心", "近场"]},
    )

    assert metadata["groups"] == ["核心", "近场"]


def test_custom_breaks_must_be_five_ascending_numbers():
    with pytest.raises(ValueError, match="递增"):
        _render_inline(
            {"metric": "SO2", "records": [{"adcode": 320100, "value": 10}]},
            {"breaks": [10, 20]},
        )
    with pytest.raises(ValueError, match="数字数组"):
        _render_inline(
            {"metric": "SO2", "records": [{"adcode": 320100, "value": 10}]},
            {"breaks": [10, "x", 30, 40, 50]},
        )


def test_unknown_metric_requires_breaks():
    with pytest.raises(ValueError, match="breaks"):
        _render_inline(
            {"metric": "VOCs", "records": [{"adcode": 320100, "value": 10}]},
        )


def test_missing_input_records_raises():
    with pytest.raises(ValueError, match="records"):
        render_city_boundary_map("空数据", {"geojson": _inline_geojson()}, {}, "word")


def test_cities_values_array_input_supported():
    _, metadata, _ = _render_inline(
        {"cities": ["南京市", "济宁市"], "values": [55, 65]}
    )

    assert metadata["city_count"] == 2
    assert metadata["render_mode"] == "choropleth"


# —— 可选 IDW 插值示意模式 ——


def _grid_geojson(count: int, start_x: float = 114.0, start_y: float = 33.0) -> dict:
    """count 个 0.9° 间距的方形城市，构成足够插值的点阵。"""
    features = []
    index = 0
    for row in range((count + 2) // 3):
        for col in range(3):
            if index >= count:
                break
            x = start_x + col * 0.9
            y = start_y + row * 0.9
            index += 1
            features.append(_square_feature(90000 + index, f"城{index}市", x, y))
    return {"type": "FeatureCollection", "features": features}


def _idw_records(count: int) -> list[dict]:
    return [
        {"adcode": 90000 + i, "value": 40 + (i * 23) % 180, "min": 30 + i, "max": 60 + i}
        for i in range(1, count + 1)
    ]


def test_idw_mode_renders_with_metadata_and_bounds():
    data = {"geojson": _grid_geojson(10), "metric": "AQI", "records": _idw_records(10)}
    image_base64, metadata, _ = render_city_boundary_map(
        "插值示意", data, {"render_mode": "idw"}, "word"
    )

    assert image_base64
    assert metadata["render_mode"] == "idw"
    assert metadata["rendered_polygon_count"] == 10
    assert metadata["idw"]["power"] == 2.0
    assert metadata["idw"]["skipped_dots"] == 0  # 0.9° 间距网格无密邻，采样点全保留
    assert metadata["scope"] == "china_city_level"


def test_idw_requires_minimum_points():
    data = {"geojson": _grid_geojson(3), "metric": "AQI", "records": _idw_records(3)}
    with pytest.raises(ValueError, match="至少需要"):
        render_city_boundary_map("插值示意", data, {"render_mode": "idw"}, "word")


def test_value_mode_mid_uses_range_midpoint_and_warns_fallback():
    assert _record_seed_value({"min": 80, "max": 110}, "AQI", "mid") == (95.0, True)
    assert _record_seed_value({"minAQI": 80, "maxAQI": 110}, "AQI", "mid")[1] is False
    assert _record_seed_value({"value": 90}, "AQI", "mid") == (90.0, False)
    assert _record_seed_value({"value": 90}, "AQI", "value") == (90.0, False)

    data = {"geojson": _grid_geojson(10), "metric": "AQI", "records": [
        {**r, "min_value": r["min"], "max_value": r["max"]} for r in _idw_records(8)
    ]}
    data["records"].append({"adcode": 90009, "value": 77})  # 无区间 → 回退告警
    _, metadata, warnings = render_city_boundary_map(
        "中值插值", data, {"render_mode": "idw", "value_mode": "mid"}, "word"
    )

    assert metadata["value_mode"] == "mid"
    assert metadata["seed_mid_used"] == 8
    assert warnings and "回退" in warnings[-1]


def test_invalid_render_mode_rejected():
    with pytest.raises(ValueError, match="render_mode"):
        _render_inline(
            {"records": [{"adcode": 320100, "value": 60}]},
            {"render_mode": "kriging"},
        )
    with pytest.raises(ValueError, match="value_mode"):
        _render_inline(
            {"records": [{"adcode": 320100, "value": 60}]},
            {"value_mode": "mean"},
        )


# —— IDW 连续色带与裁剪口径 ——


def test_level_color_anchors_and_continuous_interpolation():
    import numpy as np
    from matplotlib.colors import to_rgb

    anchors = _level_color_anchors([50, 100, 150, 200, 300])
    assert anchors == [25.0, 75.0, 125.0, 175.0, 250.0, 350.0]  # 顶档锚点=300+前档宽一半

    rgb = _continuous_level_colors(np.array([25.0, 100.0, 400.0]), anchors)
    assert np.allclose(rgb[0], to_rgb(COLORS[0]))  # 优锚点 → 纯绿
    assert np.allclose(rgb[2], to_rgb(COLORS[5]))  # 顶锚点外(400>350 截断) → 纯深红
    # 100 介于良(75)与轻度(125)锚点中点 → 黄橙混合色，档间连续过渡
    expected = (np.array(to_rgb(COLORS[1])) + np.array(to_rgb(COLORS[2]))) / 2
    assert np.allclose(rgb[1], expected, atol=1e-6)


def test_idw_clip_cities_is_default_and_land_supported():
    data = {"geojson": _grid_geojson(10), "metric": "AQI", "records": _idw_records(10)}
    _, metadata, _ = render_city_boundary_map(
        "插值示意", data, {"render_mode": "idw"}, "word"
    )
    assert metadata["idw"]["clip"] == "cities"  # 默认：目标城市并集，范围外留白

    data_land = {"geojson": _grid_geojson(10), "metric": "AQI", "records": _idw_records(10)}
    _, metadata_land, _ = render_city_boundary_map(
        "插值示意", data_land, {"render_mode": "idw", "idw_clip": "land"}, "word"
    )
    assert metadata_land["idw"]["clip"] == "land"

    with pytest.raises(ValueError, match="idw_clip"):
        render_city_boundary_map(
            "插值示意",
            {"geojson": _grid_geojson(10), "metric": "AQI", "records": _idw_records(10)},
            {"render_mode": "idw", "idw_clip": "province"},
            "word",
        )


def test_real_asset_matches_adcode_and_municipality_name():
    """全国资产冒烟：跨省 adcode 匹配 + 直辖市按名匹配 + 分级断点生效。"""
    assert DEFAULT_BOUNDARY_ASSET.exists()
    data = {
        "metric": "AQI",
        "records": [
            {"adcode": 320100, "city": "南京市", "value": 92},
            {"adcode": 310000, "city": "上海市", "value": 55},
            {"adcode": 370800, "city": "济宁市", "value": 105},
            {"adcode": 411400, "city": "商丘市", "value": 152, "group": "核心"},
            {"adcode": 410900, "city": "濮阳市", "value": 130, "group": "近场"},
        ],
    }
    image_base64, metadata, warnings = render_city_boundary_map(
        "济宁圈层 AQI 预报", data, {"star_adcode": 370800}, "word"
    )

    assert image_base64
    assert metadata["city_count"] == 5
    assert metadata["rendered_polygon_count"] >= 5
    assert metadata["groups"] == ["核心", "近场"]
    assert metadata["unmatched_record_count"] == 0
    assert metadata["boundary_asset"] == str(DEFAULT_BOUNDARY_ASSET)
    assert json.loads(DEFAULT_BOUNDARY_ASSET.read_text(encoding="utf-8"))["type"] == "FeatureCollection"
