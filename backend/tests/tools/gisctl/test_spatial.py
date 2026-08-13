from app.tools.gisctl.spatial import bbox_for_features, points_within_polygon


def test_points_within_polygon_filters_points():
    polygon = {
        "type": "Polygon",
        "coordinates": [[[113.0, 23.0], [114.0, 23.0], [114.0, 24.0], [113.0, 24.0], [113.0, 23.0]]],
    }
    points = [
        {"station_name": "inside", "longitude": 113.5, "latitude": 23.5},
        {"station_name": "outside", "longitude": 115.0, "latitude": 23.5},
    ]

    result = points_within_polygon(points, polygon, lon_field="longitude", lat_field="latitude")

    assert [item["station_name"] for item in result] == ["inside"]


def test_bbox_for_features_returns_extent():
    features = [
        {"longitude": 113.0, "latitude": 23.0},
        {"longitude": 114.0, "latitude": 24.0},
    ]

    assert bbox_for_features(features, lon_field="longitude", lat_field="latitude") == [113.0, 23.0, 114.0, 24.0]
