import asyncio

from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.tool_adapter import get_tool_schemas
from app.services.data_registry import DataRegistryService
from app.tools import create_global_tool_registry
from app.tools.gisctl import asset_resolver
from app.tools.gisctl.asset_resolver_tool import ResolveMapDataAssetTool


def _use_temp_registry(monkeypatch, tmp_path) -> DataRegistryService:
    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    monkeypatch.setattr(asset_resolver, "data_registry", registry)
    return registry


def test_resolve_map_data_asset_finds_profiled_registry_dataset(monkeypatch, tmp_path):
    registry = _use_temp_registry(monkeypatch, tmp_path)
    registry.register_dataset(
        "air_quality_station_base",
        "v1",
        [
            {
                "station_name": "广州站",
                "city": "广州",
                "longitude": 113.2644,
                "latitude": 23.1291,
                "aqi": 42,
            },
            {
                "station_name": "深圳站",
                "city": "深圳",
                "longitude": 114.0579,
                "latitude": 22.5431,
                "aqi": 38,
            },
        ],
        data_id="air_quality_station_base:v1:gd",
        metadata={
            "asset_profile": "map_layer_source.station_points",
            "asset_type": "map_layer_source",
            "business_entity": "air_quality_station",
            "domain": "atmospheric_environment",
            "environment": "prod",
            "agent_visibility": "auto_selectable",
            "map_capabilities": {
                "geometry": "point",
                "lon_field": "longitude",
                "lat_field": "latitude",
                "label_field": "station_name",
                "default_color_field": "aqi",
            },
        },
    )

    result = asset_resolver.resolve_map_data_asset(
        intent="广东站点图层",
        asset_profile="map_layer_source.station_points",
        required_fields=["longitude", "latitude"],
        preferred_fields=["station_name", "city", "aqi"],
        limit=5,
    )

    assert result["success"] is True
    assert result["status"] == "success"
    assert result["data"]["selected"]["data_id"] == "air_quality_station_base:v1:gd"
    assert result["data"]["selected"]["asset_profile"] == "map_layer_source.station_points"
    assert result["data"]["selected"]["longitude_field"] == "longitude"
    assert result["data"]["selected"]["latitude_field"] == "latitude"
    assert result["metadata"]["schema_version"] == "map_asset_resolver.v2"


def test_resolve_map_data_asset_excludes_test_assets_from_auto_selection(monkeypatch, tmp_path):
    registry = _use_temp_registry(monkeypatch, tmp_path)
    registry.register_dataset(
        "map_asset_test",
        "v1",
        [
            {
                "station_name": "测试站点",
                "city": "广州",
                "longitude": 113.2644,
                "latitude": 23.1291,
                "aqi": 42,
            }
        ],
        data_id="map_asset_test:v1:stations",
        metadata={
            "asset_profile": "map_layer_source.station_points",
            "asset_type": "map_layer_source",
            "business_entity": "air_quality_station",
            "domain": "atmospheric_environment",
            "environment": "test",
            "agent_visibility": "hidden",
            "description": "广东站点图层测试数据",
        },
    )

    result = asset_resolver.resolve_map_data_asset(
        intent="广东站点图层",
        asset_profile="map_layer_source.station_points",
        required_fields=["longitude", "latitude"],
        preferred_fields=["station_name", "city", "aqi"],
        limit=5,
    )

    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["data"]["selected"] is None
    assert result["metadata"]["excluded_count"] == 1


def test_resolve_map_data_asset_tool_execute_returns_candidates(monkeypatch, tmp_path):
    registry = _use_temp_registry(monkeypatch, tmp_path)
    registry.register_dataset(
        "air_quality_station_base",
        "v1",
        [
            {
                "station_name": "深圳站",
                "city": "深圳",
                "longitude": 114.0579,
                "latitude": 22.5431,
            }
        ],
        data_id="air_quality_station_base:v1:tool",
        metadata={
            "asset_profile": "map_layer_source.station_points",
            "environment": "prod",
            "agent_visibility": "auto_selectable",
            "map_capabilities": {"geometry": "point", "lon_field": "longitude", "lat_field": "latitude"},
            "description": "广东站点图层工具测试数据",
        },
    )
    tool = ResolveMapDataAssetTool()

    result = asyncio.run(
        tool.execute(
            intent="广东站点图层",
            asset_profile="map_layer_source.station_points",
            required_fields=["longitude", "latitude"],
        )
    )

    assert result["success"] is True
    assert result["data"]["selected"]["data_id"]
    assert result["data"]["candidates"]


def test_global_registry_and_query_mode_include_map_asset_resolver():
    registry = create_global_tool_registry()
    schema_names = {schema["name"] for schema in get_tool_schemas(mode="query")}

    assert "resolve_map_data_asset" in registry.list_tools()
    assert "resolve_map_data_asset" in get_tools_by_mode("query")
    assert "resolve_map_data_asset" in schema_names
