from __future__ import annotations

import asyncio

from app.agent.tool_adapter import call_llm_tool
from app.services.data_registry import data_registry
from app.tools.spatial.spatial_analysis.tool import SpatialAnalysisTool


def test_spatial_analysis_executes_buffer_intersect_and_aggregate():
    sources_entry = data_registry.register_dataset(
        "pollution_source_asset",
        "v1",
        [
            {
                "source_name": "近距离企业",
                "industry_type": "涂装",
                "longitude": 113.215,
                "latitude": 23.392,
            },
            {
                "source_name": "远距离企业",
                "industry_type": "化工",
                "longitude": 113.31,
                "latitude": 23.49,
            },
        ],
        metadata={
            "asset_type": "spatial_point_asset",
            "map_capabilities": {"geometry": "point", "lon_field": "longitude", "lat_field": "latitude"},
        },
    )

    result = asyncio.run(
        SpatialAnalysisTool().execute(
            spec={
                "version": "spatial-spec.v1",
                "intent": "查询花都师范站 3km 范围内污染源并按行业统计",
                "inputs": {
                    "station": {
                        "type": "inline-feature",
                        "geometry": {"type": "Point", "coordinates": [113.2146, 23.3917]},
                        "properties": {"name": "花都师范"},
                    },
                    "pollution_sources": {
                        "type": "data-asset",
                        "data_id": sources_entry.data_id,
                        "geometry": {"lon": "longitude", "lat": "latitude"},
                    },
                },
                "steps": [
                    {
                        "id": "station_buffer",
                        "op": "buffer",
                        "input": "station",
                        "distance": 3000,
                        "unit": "m",
                    },
                    {
                        "id": "sources_in_buffer",
                        "op": "intersect",
                        "left": "pollution_sources",
                        "right": "station_buffer",
                    },
                    {
                        "id": "summary",
                        "op": "aggregate",
                        "input": "sources_in_buffer",
                        "group_by": ["industry_type"],
                        "metrics": [{"func": "count", "as": "count"}],
                    },
                ],
                "outputs": [
                    {"id": "station_buffer", "as": "map-layer", "asset_schema": "spatial_polygon_asset"},
                    {"id": "sources_in_buffer", "as": "map-layer", "asset_schema": "spatial_point_asset"},
                    {"id": "summary", "as": "table", "asset_schema": "analysis_table_asset"},
                ],
            }
        )
    )

    assert result["success"] is True
    outputs = {item["id"]: item for item in result["data"]["outputs"]}
    assert outputs["station_buffer"]["record_count"] == 1
    assert outputs["sources_in_buffer"]["record_count"] == 1
    assert outputs["summary"]["record_count"] == 1

    point_records = data_registry.load_dataset(outputs["sources_in_buffer"]["data_id"])
    assert point_records[0]["source_name"] == "近距离企业"
    summary_records = data_registry.load_dataset(outputs["summary"]["data_id"])
    assert summary_records == [{"industry_type": "涂装", "count": 1}]


def test_spatial_analysis_rejects_unknown_operation():
    result = asyncio.run(
        SpatialAnalysisTool().execute(
            spec={
                "version": "spatial-spec.v1",
                "inputs": {},
                "steps": [{"id": "bad_step", "op": "unknown"}],
                "outputs": [],
            }
        )
    )

    assert result["success"] is False
    assert result["metadata"]["error_code"] == "SPATIAL_SPEC_UNSUPPORTED_OP"
    assert result["metadata"]["step_id"] == "bad_step"


def test_spatial_analysis_accepts_agent_output_object_for_buffer_layer():
    result = asyncio.run(
        SpatialAnalysisTool().execute(
            spec={
                "version": "spatial-spec.v1",
                "inputs": {
                    "station": {
                        "type": "inline-feature",
                        "geometry": {"type": "Point", "coordinates": [113.2146, 23.3917]},
                        "properties": {"name": "花都师范"},
                    }
                },
                "steps": [
                    {
                        "id": "buffer_3km",
                        "op": "buffer",
                        "input": "station",
                        "distance": 3000,
                        "unit": "meter",
                    }
                ],
                "outputs": {
                    "buffer_layer": {
                        "type": "layer",
                        "from_step": "buffer_3km",
                        "name": "花都师范3km缓冲区",
                    }
                },
            }
        )
    )

    assert result["success"] is True
    output = result["data"]["outputs"][0]
    assert output["id"] == "buffer_layer"
    assert output["asset_schema"] == "spatial_polygon_asset"
    records = data_registry.load_dataset(output["data_id"])
    assert records[0]["geometry"]["type"] == "Polygon"
    assert records[0]["name"] == "花都师范"


def test_spatial_analysis_infers_data_asset_geometry_from_metadata():
    station_entry = data_registry.register_dataset(
        "map_point_asset",
        "v1",
        [
            {
                "station_name": "花都师范",
                "longitude": 113.2146,
                "latitude": 23.3917,
            }
        ],
        metadata={
            "asset_type": "map_point_asset",
            "longitude_field": "longitude",
            "latitude_field": "latitude",
            "map_capabilities": {"geometry": "point", "lon_field": "longitude", "lat_field": "latitude"},
        },
    )

    result = asyncio.run(
        SpatialAnalysisTool().execute(
            spec={
                "version": "spatial-spec.v1",
                "inputs": {
                    "point": {
                        "type": "data-asset",
                        "data_id": station_entry.data_id,
                    }
                },
                "steps": [
                    {"id": "buffer_3km", "op": "buffer", "input": "point", "distance": 3000, "unit": "meter"}
                ],
                "outputs": {
                    "buffer_layer": {"type": "layer", "from_step": "buffer_3km", "name": "花都师范3km缓冲区"}
                },
            }
        )
    )

    assert result["success"] is True
    output = result["data"]["outputs"][0]
    assert output["asset_schema"] == "spatial_polygon_asset"
    records = data_registry.load_dataset(output["data_id"])
    assert records[0]["geometry"]["type"] == "Polygon"
    assert records[0]["buffer_center"] == [113.2146, 23.3917]


def test_spatial_analysis_accepts_actual_agent_polygon_layer_spec_variant():
    result = asyncio.run(
        SpatialAnalysisTool().execute(
            spec={
                "inputs": [
                    {
                        "name": "huadu_station",
                        "type": "inline-feature",
                        "geometry": {"type": "Point", "coordinates": [113.2146, 23.3917]},
                        "properties": {"station_name": "花都师范", "station_code": "1007A"},
                    }
                ],
                "steps": [
                    {
                        "name": "buffer_3km",
                        "op": "buffer",
                        "input": "huadu_station",
                        "params": {"distance": 3000, "units": "meters"},
                    }
                ],
                "outputs": [
                    {
                        "name": "buffer_layer",
                        "type": "polygon-layer",
                        "from": "buffer_3km",
                    }
                ],
            }
        )
    )

    assert result["success"] is True
    output = result["data"]["outputs"][0]
    assert output["id"] == "buffer_layer"
    assert output["as"] == "map-layer"
    assert output["asset_schema"] == "spatial_polygon_asset"
    assert output["data_id"].startswith("spatial_polygon_asset:v1:")
    records = data_registry.load_dataset(output["data_id"])
    assert records[0]["geometry"]["type"] == "Polygon"
    assert records[0]["station_name"] == "花都师范"
    assert records[0]["buffer_distance_m"] == 3000


def test_spatial_analysis_is_exposed_to_llm_adapter():
    result = asyncio.run(
        call_llm_tool(
            "spatial_analysis",
            spec={
                "version": "spatial-spec.v1",
                "inputs": {
                    "station": {
                        "type": "inline-feature",
                        "geometry": {"type": "Point", "coordinates": [113.2146, 23.3917]},
                    }
                },
                "steps": [
                    {"id": "station_buffer", "op": "buffer", "input": "station", "distance": 1000, "unit": "m"}
                ],
                "outputs": [{"id": "station_buffer", "as": "map-layer", "asset_schema": "spatial_polygon_asset"}],
            },
        )
    )

    assert result["success"] is True
    assert result["data"]["outputs"][0]["data_id"].startswith("spatial_polygon_asset:v1:")
