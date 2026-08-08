import asyncio

from app.agent.tool_adapter import call_llm_tool
from app.services.data_registry import data_registry
from app.tools.gisctl.create_map_point_asset_tool import CreateMapPointAssetTool
from app.tools.gisctl.tool import execute_gisctl


def test_create_map_point_asset_registers_agent_selected_station():
    result = asyncio.run(
        CreateMapPointAssetTool().execute(
            name="PM2.5最高站点",
            records=[
                {
                    "station_name": "麓湖",
                    "station_code": "1010A",
                    "city": "广州",
                    "longitude": 113.2765,
                    "latitude": 23.1544,
                    "pm25": 88,
                    "rank_reason": "PM2.5最高",
                }
            ],
            layer_id="turn_pm25_top_station",
            color_by="pm25",
            turn_id="turn_pm25_top",
        )
    )

    assert result["success"] is True
    data_id = result["data"]["data_id"]
    assert data_id.startswith("map_point_asset:v1:")
    assert data_registry.get_metadata(data_id) is not None
    assert data_registry.load_sample(data_id)[0]["station_name"] == "麓湖"
    assert result["data"]["longitude_field"] == "longitude"
    assert result["data"]["latitude_field"] == "latitude"
    assert result["data"]["suggested_gisctl_commands"][0]["kind"] == "point-layer"
    assert result["data"]["suggested_gisctl_commands"][0]["data_id"] == data_id
    assert result["data"]["suggested_gisctl_commands"][1]["kind"] == "set-view"
    assert result["data"]["suggested_gisctl_commands"][1]["center"] == [113.2765, 23.1544]


def test_created_map_point_asset_can_drive_gisctl_layer_and_view():
    asset = asyncio.run(
        CreateMapPointAssetTool().execute(
            name="PM2.5最高站点",
            records=[
                {
                    "station_name": "麓湖",
                    "city": "广州",
                    "longitude": 113.2765,
                    "latitude": 23.1544,
                    "pm25": 88,
                }
            ],
            layer_id="turn_pm25_top_station",
            color_by="pm25",
        )
    )

    point_layer = execute_gisctl(asset["data"]["suggested_gisctl_commands"][0])
    set_view = execute_gisctl(asset["data"]["suggested_gisctl_commands"][1])

    assert point_layer["success"] is True
    assert point_layer["metadata"]["map_program"]["state"]["layers"][0]["id"] == "turn_pm25_top_station"
    assert set_view["success"] is True
    assert set_view["metadata"]["map_program"]["state"]["view"]["center"] == [113.2765, 23.1544]


def test_create_map_point_asset_rejects_records_without_coordinates():
    result = asyncio.run(
        CreateMapPointAssetTool().execute(
            name="无坐标站点",
            records=[{"station_name": "麓湖", "pm25": 88}],
        )
    )

    assert result["success"] is False
    assert result["metadata"]["error_code"] == "MAP_POINT_COORDINATES_REQUIRED"
    assert "resolve_station_geo" in result["metadata"]["suggested_next_tools"]


def test_create_map_point_asset_is_exposed_to_llm_adapter():
    result = asyncio.run(
        call_llm_tool(
            "create_map_point_asset",
            name="PM2.5最高站点",
            records=[
                {
                    "station_name": "麓湖",
                    "city": "广州",
                    "longitude": 113.2765,
                    "latitude": 23.1544,
                    "pm25": 88,
                }
            ],
            layer_id="turn_pm25_top_station",
            color_by="pm25",
        )
    )

    assert result["success"] is True
    assert result["data"]["data_id"].startswith("map_point_asset:v1:")
