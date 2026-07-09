from datetime import datetime

from app.scenarios.yuncheng_trial.fire_hotspot_assets import (
    FIRE_MAP_LABELS,
    bearing_degrees,
    build_fire_hotspot_summary,
    direction_label,
    haversine_km,
    render_fire_hotspot_map,
)


def test_distance_and_direction_helpers() -> None:
    distance = haversine_km(35.0, 111.0, 35.0, 112.0)
    bearing = bearing_degrees(35.0, 111.0, 35.0, 112.0)

    assert 90 < distance < 92
    assert direction_label(bearing) == "E"


def test_build_fire_hotspot_summary_adds_distance_direction_and_limits_top_points() -> None:
    payload = {
        "hotspots": [
            {
                "lat": 35.0,
                "lon": 112.0,
                "frp": 9.0,
                "confidence": 70,
                "brightness": 330.0,
                "acquisition_time": "2026-07-09T13:30:00",
                "satellite": "N20",
                "day_night": "D",
            },
            {
                "lat": 35.5,
                "lon": 111.0,
                "frp": 20.0,
                "confidence": 90,
                "brightness": 340.0,
                "acquisition_time": "2026-07-09T10:00:00",
                "satellite": "N21",
                "day_night": "D",
            },
        ]
        * 12
    }

    summary = build_fire_hotspot_summary(
        payload,
        alert_time=datetime(2026, 7, 9, 15, 0, 0),
        center_lat=35.0,
        center_lon=111.0,
    )

    assert summary["count"] == 24
    assert summary["count_by_window"] == {"within_1h": 0, "within_3h": 12, "within_6h": 24}
    assert summary["nearest_hotspot"]["direction"] == "N"
    assert len(summary["top_hotspots"]) == 20
    assert "不能单独确认具体污染源" in summary["usage_boundary"]


def test_render_fire_hotspot_map_writes_png(tmp_path) -> None:
    summary = build_fire_hotspot_summary(
        {
            "hotspots": [
                {
                    "lat": 35.0,
                    "lon": 112.0,
                    "frp": 9.0,
                    "confidence": 70,
                    "acquisition_time": "2026-07-09T13:30:00",
                    "satellite": "N20",
                }
            ]
        },
        alert_time=datetime(2026, 7, 9, 15, 0, 0),
        center_lat=35.0,
        center_lon=111.0,
    )

    path = render_fire_hotspot_map(
        summary,
        tmp_path / "fire_hotspots_map.png",
        bbox={"min_lat": 33.5, "max_lat": 36.6, "min_lon": 109.3, "max_lon": 112.7},
    )

    assert path.exists()
    assert path.stat().st_size > 10_000


def test_fire_hotspot_map_uses_chinese_labels() -> None:
    assert FIRE_MAP_LABELS["title"] == "NASA FIRMS火点分布图"
    assert FIRE_MAP_LABELS["center_label"] == "运城"
    assert FIRE_MAP_LABELS["hotspot_label"] == "卫星火点"
    assert FIRE_MAP_LABELS["frp_label"] == "火点辐射功率 FRP（MW）"
    assert FIRE_MAP_LABELS["longitude"] == "经度"
    assert FIRE_MAP_LABELS["latitude"] == "纬度"


def test_render_empty_fire_hotspot_map_writes_png(tmp_path) -> None:
    summary = build_fire_hotspot_summary(
        {"hotspots": []},
        alert_time=datetime(2026, 7, 9, 15, 0, 0),
        center_lat=35.0,
        center_lon=111.0,
    )

    path = render_fire_hotspot_map(
        summary,
        tmp_path / "fire_hotspots_map.png",
        bbox={"min_lat": 33.5, "max_lat": 36.6, "min_lon": 109.3, "max_lon": 112.7},
    )

    assert path.exists()
    assert path.stat().st_size > 10_000
