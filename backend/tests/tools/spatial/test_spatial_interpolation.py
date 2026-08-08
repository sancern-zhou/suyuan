from app.services.data_registry import DataRegistryService
from app.tools.spatial.spatial_interpolation import engine
from app.tools.spatial.spatial_interpolation.tool import (
    SPATIAL_INTERPOLATION_GUIDE_PATH,
    SpatialInterpolationTool,
)


def test_spatial_interpolation_schema_points_to_required_guide():
    tool = SpatialInterpolationTool()
    schema_text = str(tool.get_function_schema())

    assert SPATIAL_INTERPOLATION_GUIDE_PATH in tool.description
    assert SPATIAL_INTERPOLATION_GUIDE_PATH in schema_text
    assert "read_file" in schema_text
    assert "visual_interaction" in schema_text
    assert "wait_map_program_receipt" in schema_text


def test_spatial_interpolation_guide_documents_map_layer_closure():
    guide_text = open(SPATIAL_INTERPOLATION_GUIDE_PATH, encoding="utf-8").read()

    assert "spatial_interpolation" in guide_text
    assert "visual_interaction" in guide_text
    assert "line-layer" in guide_text
    assert "wait_map_program_receipt" in guide_text
    assert "不得" in guide_text


def test_spatial_interpolation_guide_documents_registered_data_id_chain():
    guide_text = open(SPATIAL_INTERPOLATION_GUIDE_PATH, encoding="utf-8").read()

    assert "不得手工构造" in guide_text
    assert "execute_python" in guide_text
    assert "backend_data_registry/datasets" in guide_text
    assert "data_registry.register_dataset" in guide_text
    assert "surface.data_id" in guide_text


def _seed_concentration_points(registry: DataRegistryService) -> str:
    data_id = "station_concentration_asset:v1:test_points"
    registry.register_dataset(
        "station_concentration_asset",
        "v1",
        [
            {"station": "A", "longitude": 113.00, "latitude": 23.00, "pm25": 20.0},
            {"station": "B", "longitude": 113.04, "latitude": 23.00, "pm25": 35.0},
            {"station": "C", "longitude": 113.00, "latitude": 23.04, "pm25": 45.0},
            {"station": "D", "longitude": 113.04, "latitude": 23.04, "pm25": 60.0},
            {"station": "E", "longitude": 113.02, "latitude": 23.02, "pm25": 50.0},
        ],
        data_id=data_id,
        metadata={
            "map_capabilities": {
                "geometry": "point",
                "lon_field": "longitude",
                "lat_field": "latitude",
            }
        },
    )
    return data_id


def test_idw_interpolation_registers_grid_and_contour_outputs(tmp_path, monkeypatch):
    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    data_id = _seed_concentration_points(registry)
    monkeypatch.setattr(engine, "data_registry", registry)

    result = engine.execute_interpolation(
        {
            "data_id": data_id,
            "lon": "longitude",
            "lat": "latitude",
            "value": "pm25",
            "pollutant": "PM2.5",
            "unit": "ug/m3",
            "method": "idw",
            "grid_size": 20,
            "contour_levels": 6,
        }
    )

    assert result["success"] is True
    assert result["metadata"]["method_applied"] == "idw"
    outputs = {item["id"]: item for item in result["data"]["outputs"]}
    assert outputs["grid"]["record_count"] == 400
    assert outputs["surface"]["record_count"] == 361
    assert outputs["contours"]["record_count"] > 0
    assert result["visuals"] == []

    grid_records = registry.load_dataset(outputs["grid"]["data_id"])
    assert {"longitude", "latitude", "value"}.issubset(grid_records[0])
    assert min(record["value"] for record in grid_records) >= 20.0
    assert max(record["value"] for record in grid_records) <= 60.0

    surface_records = registry.load_dataset(outputs["surface"]["data_id"])
    assert surface_records[0]["geometry"]["type"] == "Polygon"
    assert {"value", "fill_color", "fill_opacity"}.issubset(surface_records[0])

    contour_records = registry.load_dataset(outputs["contours"]["data_id"])
    assert contour_records[0]["geometry"]["type"] == "LineString"
    assert "level" in contour_records[0]


def test_kriging_without_pykrige_reports_dependency_error_without_fallback(tmp_path, monkeypatch):
    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    data_id = _seed_concentration_points(registry)
    monkeypatch.setattr(engine, "data_registry", registry)
    monkeypatch.setattr(engine, "HAS_PYKRIGE", False)

    result = engine.execute_interpolation(
        {
            "data_id": data_id,
            "lon": "longitude",
            "lat": "latitude",
            "value": "pm25",
            "method": "kriging",
            "allow_fallback": False,
        }
    )

    assert result["success"] is False
    assert result["metadata"]["error_code"] == "SPATIAL_DEPENDENCY_MISSING"
    assert "PyKrige" in result["summary"]


def test_kriging_with_fallback_uses_idw_and_records_warning(tmp_path, monkeypatch):
    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    data_id = _seed_concentration_points(registry)
    monkeypatch.setattr(engine, "data_registry", registry)
    monkeypatch.setattr(engine, "HAS_PYKRIGE", False)

    result = engine.execute_interpolation(
        {
            "data_id": data_id,
            "lon": "longitude",
            "lat": "latitude",
            "value": "pm25",
            "method": "kriging",
            "allow_fallback": True,
            "grid_size": 12,
        }
    )

    assert result["success"] is True
    assert result["metadata"]["method_requested"] == "kriging"
    assert result["metadata"]["method_applied"] == "idw"
    assert any(warning["code"] == "SPATIAL_INTERPOLATION_FALLBACK" for warning in result["metadata"]["warnings"])


def test_interpolation_result_never_returns_static_image_visuals(tmp_path, monkeypatch):
    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    data_id = _seed_concentration_points(registry)
    monkeypatch.setattr(engine, "data_registry", registry)

    result = engine.execute_interpolation(
        {
            "data_id": data_id,
            "lon": "longitude",
            "lat": "latitude",
            "value": "pm25",
            "method": "idw",
            "include_static_image": True,
        }
    )

    assert result["success"] is True
    assert result["visuals"] == []
    assert "image_url" not in str(result)
