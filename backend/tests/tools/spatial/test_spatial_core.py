import pytest

from app.tools.spatial.core import (
    buffer_geometry_meters,
    distance_meters,
    geojson_to_shape,
    shape_area,
)


def test_area_uses_metric_projection_for_lon_lat_polygon():
    polygon = geojson_to_shape(
        {
            "type": "Polygon",
            "coordinates": [
                [
                    [113.0, 23.0],
                    [113.01, 23.0],
                    [113.01, 23.01],
                    [113.0, 23.01],
                    [113.0, 23.0],
                ]
            ],
        }
    )

    area = shape_area(polygon)

    assert area.square_meters == pytest.approx(1_140_000, rel=0.08)
    assert area.square_kilometers == pytest.approx(1.14, rel=0.08)
    assert area.crs.startswith("EPSG:")


def test_distance_between_lon_lat_points_returns_meters():
    left = geojson_to_shape({"type": "Point", "coordinates": [113.0, 23.0]})
    right = geojson_to_shape({"type": "Point", "coordinates": [113.01, 23.0]})

    distance = distance_meters(left, right)

    assert distance.meters == pytest.approx(1025, rel=0.04)
    assert distance.kilometers == pytest.approx(1.025, rel=0.04)
    assert distance.crs.startswith("EPSG:")


def test_buffer_point_returns_polygon_with_area_metadata():
    point = geojson_to_shape({"type": "Point", "coordinates": [113.0, 23.0]})

    buffered = buffer_geometry_meters(point, 1000)

    assert buffered.geometry.geom_type == "Polygon"
    assert buffered.area.square_meters == pytest.approx(3_136_000, rel=0.04)
    assert buffered.area.square_kilometers == pytest.approx(3.136, rel=0.04)
