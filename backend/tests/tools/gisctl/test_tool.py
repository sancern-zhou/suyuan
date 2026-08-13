import asyncio

from app.agent.tool_adapter import call_llm_tool
from app.services.data_registry import data_registry
from app.tools.gisctl.tool import execute_gisctl


def test_execute_gisctl_map_spec_point_layer():
    data_registry.register_dataset(
        "map_layer_test",
        "v1",
        [
            {
                "station_name": "测试站点",
                "city": "广州",
                "longitude": 113.2644,
                "latitude": 23.1291,
                "pm25": 38,
            }
        ],
        data_id="map_layer_test:v1:pm25",
    )

    result = execute_gisctl(
        {
            "family": "map-spec",
            "action": "create",
            "kind": "point-layer",
            "data_id": "map_layer_test:v1:pm25",
            "layer_id": "turn_12_pm25_high",
            "name": "PM2.5 high stations",
            "lon": "longitude",
            "lat": "latitude",
            "color_by": "pm25",
            "breaks": [35, 75, 115],
            "colors": ["#facc15", "#fb923c", "#ef4444"],
        }
    )

    assert result["success"] is True
    assert result["status"] == "success"
    assert result["metadata"]["schema_version"] == "gisctl.v1"
    assert result["metadata"]["generator"] == "visual_interaction"
    assert result["data"]["command"] == "map-spec create point-layer"
    assert result["data"]["map_program"] == result["metadata"]["map_program"]
    assert result["metadata"]["map_program"]["state"]["layers"][0]["id"] == "turn_12_pm25_high"


def test_execute_gisctl_rejects_unknown_point_layer_data_id():
    result = execute_gisctl(
        {
            "family": "map-spec",
            "action": "create",
            "kind": "point-layer",
            "data_id": "gd_stations",
            "layer_id": "stations",
            "name": "站点图层",
            "lon": "longitude",
            "lat": "latitude",
        }
    )

    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["data"]["map_program"] is None
    assert result["metadata"]["error_code"] == "MAP_DATA_ASSET_NOT_FOUND"
    assert result["metadata"]["suggested_next_tool"] == "resolve_map_data_asset"


def test_execute_gisctl_map_spec_set_view():
    result = execute_gisctl(
        {
            "family": "map-spec",
            "action": "create",
            "kind": "set-view",
            "center": [113.2644, 23.1291],
            "zoom": 10,
            "name": "广州",
        }
    )

    assert result["success"] is True
    assert result["status"] == "success"
    assert result["data"]["map_program"] == result["metadata"]["map_program"]
    assert result["metadata"]["map_program"]["state"]["view"]["center"] == [113.2644, 23.1291]
    assert result["metadata"]["map_program"]["state"]["view"]["zoom"] == 10
    assert result["metadata"]["map_program"]["state"]["layers"] == []


def test_execute_gisctl_map_spec_dashboard_layer_visibility():
    result = execute_gisctl(
        {
            "family": "map-spec",
            "action": "create",
            "kind": "dashboard-layer",
            "layer_id": "stations",
            "name": "站点",
            "visible": True,
        }
    )

    assert result["success"] is True
    assert result["status"] == "success"
    program = result["metadata"]["map_program"]
    assert program["type"] == "map_program"
    assert program["state"]["layers"] == []
    assert program["state"]["dashboard_layers"] == [{"id": "stations", "visible": True}]
    assert result["data"]["map_program"] == program


def test_execute_gisctl_map_spec_polygon_layer():
    data_registry.register_dataset(
        "spatial_polygon_asset",
        "v1",
        [
            {
                "name": "花都师范 3km 缓冲区",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [113.2, 23.1],
                        [113.3, 23.1],
                        [113.3, 23.2],
                        [113.2, 23.1],
                    ]],
                },
            }
        ],
        data_id="spatial_polygon_asset:v1:test_buffer",
    )

    result = execute_gisctl(
        {
            "family": "map-spec",
            "action": "create",
            "kind": "polygon-layer",
            "data_id": "spatial_polygon_asset:v1:test_buffer",
            "layer_id": "huadu_buffer_3km",
            "name": "花都师范 3km 缓冲区",
            "fill_color": "#2f80ed",
            "fill_opacity": 0.18,
            "stroke_color": "#1f5fbf",
            "stroke_weight": 2,
        }
    )

    assert result["success"] is True
    program = result["metadata"]["map_program"]
    layer = program["state"]["layers"][0]
    assert layer["id"] == "huadu_buffer_3km"
    assert layer["layer_type"] == "polygon"
    assert layer["geometry"]["type"] == "geojson"
    assert layer["style"]["fill_color"] == "#2f80ed"
    assert layer["style"]["fill_opacity"] == 0.18


def test_execute_gisctl_map_spec_line_layer_for_interpolation_contours():
    data_registry.register_dataset(
        "contour_line_asset",
        "v1",
        [
            {
                "level": 35.0,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [113.0, 23.0],
                        [113.01, 23.01],
                        [113.02, 23.0],
                    ],
                },
            }
        ],
        data_id="contour_line_asset:v1:test_pm25_contours",
    )

    result = execute_gisctl(
        {
            "family": "map-spec",
            "action": "create",
            "kind": "line-layer",
            "data_id": "contour_line_asset:v1:test_pm25_contours",
            "layer_id": "pm25_interpolation_contours",
            "name": "PM2.5 插值等值线",
            "stroke_color": "#d7191c",
            "stroke_weight": 2,
            "fit_bounds": True,
        }
    )

    assert result["success"] is True
    program = result["metadata"]["map_program"]
    layer = program["state"]["layers"][0]
    assert layer["id"] == "pm25_interpolation_contours"
    assert layer["layer_type"] == "line"
    assert layer["geometry"]["type"] == "geojson"
    assert layer["style"]["stroke_color"] == "#d7191c"
    assert layer["style"]["stroke_weight"] == 2


def test_execute_gisctl_map_spec_interpolation_layer_for_surface_asset():
    data_registry.register_dataset(
        "interpolation_surface_asset",
        "v1",
        [
            {
                "value": 35.0,
                "fill_color": "#fee08b",
                "fill_opacity": 0.58,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [113.0, 23.0],
                        [113.01, 23.0],
                        [113.01, 23.01],
                        [113.0, 23.01],
                        [113.0, 23.0],
                    ]],
                },
            }
        ],
        data_id="interpolation_surface_asset:v1:test_pm25_surface",
    )

    result = execute_gisctl(
        {
            "family": "map-spec",
            "action": "create",
            "kind": "interpolation-layer",
            "data_id": "interpolation_surface_asset:v1:test_pm25_surface",
            "layer_id": "pm25_interpolation_surface",
            "name": "PM2.5 插值渲染",
            "fit_bounds": True,
        }
    )

    assert result["success"] is True
    assert result["data"]["command"] == "map-spec create interpolation-layer"
    layer = result["metadata"]["map_program"]["state"]["layers"][0]
    assert layer["id"] == "pm25_interpolation_surface"
    assert layer["layer_type"] == "polygon"
    assert layer["style"]["type"] == "interpolation_surface"
    assert layer["style"]["feature_fill_color_field"] == "fill_color"
    assert layer["interactions"]["popup_fields"] == ["value", "level", "name"]


def test_execute_gisctl_map_spec_set_view_resolves_target_place():
    result = execute_gisctl(
        {
            "family": "map-spec",
            "action": "create",
            "kind": "set-view",
            "target": "佛山",
            "name": "佛山",
        }
    )

    assert result["success"] is True
    assert result["metadata"]["map_program"]["state"]["view"]["center"] == [113.1214, 23.0219]
    assert result["metadata"]["map_program"]["state"]["view"]["zoom"] == 10


def test_gisctl_adapter_preserves_map_program_metadata():
    result = asyncio.run(
        call_llm_tool(
            "visual_interaction",
            command={
                "family": "map-spec",
                "action": "create",
                "kind": "set-view",
                "target": "东莞",
                "name": "东莞",
            },
        )
    )

    assert result["success"] is True
    assert result["status"] == "success"
    assert result["metadata"]["generator"] == "visual_interaction"
    assert result["metadata"]["map_program"]["type"] == "map_program"
    assert result["metadata"]["map_program"]["state"]["view"]["center"] == [113.7518, 23.0205]
    assert result["data"]["map_program"] == result["metadata"]["map_program"]
