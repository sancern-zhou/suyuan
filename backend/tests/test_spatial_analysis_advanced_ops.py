import pytest

from app.services.data_registry import DataRegistryService
from app.tools.spatial.spatial_analysis import engine


def _seed_sources(registry: DataRegistryService) -> str:
    data_id = "pollution_source_asset:v1:advanced_fixture"
    registry.register_dataset(
        "pollution_source_asset",
        "v1",
        [
            {
                "name": "近处VOCs企业",
                "longitude": 113.001,
                "latitude": 23.0,
                "source_type": "工业企业",
                "industry_type": "涂料制造",
                "emission_vocs": 10.0,
                "emission_nox": 2.0,
            },
            {
                "name": "远处VOCs企业",
                "longitude": 113.02,
                "latitude": 23.0,
                "source_type": "工业企业",
                "industry_type": "化工",
                "emission_vocs": 30.0,
                "emission_nox": 5.0,
            },
            {
                "name": "加油站",
                "longitude": 112.999,
                "latitude": 23.005,
                "source_type": "加油站",
                "industry_type": "机动车燃油零售",
                "emission_vocs": 5.0,
                "emission_nox": 0.0,
            },
            {
                "name": "南侧企业",
                "longitude": 113.0,
                "latitude": 22.99,
                "source_type": "工业企业",
                "industry_type": "建材",
                "emission_vocs": 2.0,
                "emission_nox": 20.0,
            },
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


def test_spatial_analysis_filter_distance_nearest_aggregate_and_topn(tmp_path, monkeypatch):
    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    data_id = _seed_sources(registry)
    monkeypatch.setattr(engine, "data_registry", registry)

    result = engine.execute_spatial_spec(
        {
            "version": "spatial-spec.v1",
            "intent": "站点周边VOCs企业筛选排序",
            "inputs": {
                "station": {
                    "type": "inline-feature",
                    "geometry": {"type": "Point", "coordinates": [113.0, 23.0]},
                    "properties": {"name": "测试站点"},
                },
                "sources": {"type": "data-asset", "data_id": data_id},
            },
            "steps": [
                {"id": "nearby", "op": "nearest", "left": "sources", "right": "station", "limit": 4},
                {
                    "id": "vocs_sources",
                    "op": "filter",
                    "input": "nearby",
                    "where": {
                        "source_type": {"eq": "工业企业"},
                        "emission_vocs": {"gt": 5},
                    },
                },
                {
                    "id": "summary",
                    "op": "aggregate",
                    "input": "vocs_sources",
                    "group_by": ["source_type"],
                    "metrics": [
                        {"func": "count", "as": "count"},
                        {"func": "sum", "field": "emission_vocs", "as": "vocs_sum"},
                        {"func": "max", "field": "emission_vocs", "as": "vocs_max"},
                        {"func": "avg", "field": "emission_vocs", "as": "vocs_avg"},
                    ],
                },
                {
                    "id": "top_vocs",
                    "op": "top_n",
                    "input": "vocs_sources",
                    "field": "emission_vocs",
                    "limit": 1,
                    "order": "desc",
                },
            ],
            "outputs": {
                "vocs_sources": {"from_step": "vocs_sources", "asset_schema": "spatial_point_asset"},
                "summary": {"from_step": "summary", "asset_schema": "analysis_table_asset"},
                "top_vocs": {"from_step": "top_vocs", "asset_schema": "spatial_point_asset"},
            },
        }
    )

    assert result["success"] is True
    outputs = {item["id"]: item for item in result["data"]["outputs"]}
    assert outputs["vocs_sources"]["record_count"] == 2
    assert outputs["summary"]["record_count"] == 1
    assert outputs["top_vocs"]["record_count"] == 1

    vocs_records = registry.load_dataset(outputs["vocs_sources"]["data_id"])
    assert [record["name"] for record in vocs_records] == ["近处VOCs企业", "远处VOCs企业"]
    assert vocs_records[0]["distance_m"] < vocs_records[1]["distance_m"]

    summary = registry.load_dataset(outputs["summary"]["data_id"])
    assert summary == [
        {
            "source_type": "工业企业",
            "count": 2,
            "vocs_sum": 40.0,
            "vocs_max": 30.0,
            "vocs_avg": 20.0,
        }
    ]

    top_records = registry.load_dataset(outputs["top_vocs"]["data_id"])
    assert top_records[0]["name"] == "远处VOCs企业"


def test_spatial_analysis_upwind_sector_filters_points_by_wind_direction(tmp_path, monkeypatch):
    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    data_id = _seed_sources(registry)
    monkeypatch.setattr(engine, "data_registry", registry)

    result = engine.execute_spatial_spec(
        {
            "version": "spatial-spec.v1",
            "intent": "站点上风向污染源",
            "inputs": {
                "station": {
                    "type": "inline-feature",
                    "geometry": {"type": "Point", "coordinates": [113.0, 23.0]},
                    "properties": {"name": "测试站点"},
                },
                "sources": {"type": "data-asset", "data_id": data_id},
            },
            "steps": [
                {
                    "id": "upwind_sources",
                    "op": "upwind_sector",
                    "sources": "sources",
                    "receptor": "station",
                    "wind_from_degrees": 180,
                    "angle_degrees": 60,
                    "distance": 2000,
                    "unit": "meter",
                }
            ],
            "outputs": {
                "upwind_sources": {"from_step": "upwind_sources", "asset_schema": "spatial_point_asset"}
            },
        }
    )

    assert result["success"] is True
    output = result["data"]["outputs"][0]
    records = registry.load_dataset(output["data_id"])

    assert [record["name"] for record in records] == ["南侧企业"]
    assert records[0]["upwind_direction_degrees"] == 180.0


def test_spatial_analysis_area_clip_and_point_to_polygon_distance(tmp_path, monkeypatch):
    registry = DataRegistryService(base_dir=str(tmp_path / "registry"))
    monkeypatch.setattr(engine, "data_registry", registry)

    result = engine.execute_spatial_spec(
        {
            "version": "spatial-spec.v1",
            "intent": "面面积裁剪和点面距离",
            "inputs": {
                "zone": {
                    "type": "inline-feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [113.0, 23.0],
                                [113.02, 23.0],
                                [113.02, 23.02],
                                [113.0, 23.02],
                                [113.0, 23.0],
                            ]
                        ],
                    },
                    "properties": {"name": "测试区域"},
                },
                "clipper": {
                    "type": "inline-feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [113.01, 23.0],
                                [113.03, 23.0],
                                [113.03, 23.02],
                                [113.01, 23.02],
                                [113.01, 23.0],
                            ]
                        ],
                    },
                    "properties": {"name": "裁剪区域"},
                },
                "site": {
                    "type": "inline-feature",
                    "geometry": {"type": "Point", "coordinates": [113.05, 23.01]},
                    "properties": {"name": "外部站点"},
                },
            },
            "steps": [
                {"id": "zone_area", "op": "area", "input": "zone"},
                {"id": "clipped", "op": "clip", "input": "zone", "mask": "clipper"},
                {"id": "site_distance", "op": "distance", "left": "site", "right": "zone"},
            ],
            "outputs": {
                "zone_area": {"from_step": "zone_area", "asset_schema": "analysis_table_asset"},
                "clipped": {"from_step": "clipped", "asset_schema": "spatial_polygon_asset"},
                "site_distance": {"from_step": "site_distance", "asset_schema": "spatial_point_asset"},
            },
        }
    )

    assert result["success"] is True
    outputs = {item["id"]: item for item in result["data"]["outputs"]}

    area_records = registry.load_dataset(outputs["zone_area"]["data_id"])
    assert area_records[0]["area_m2"] > 4_000_000
    assert area_records[0]["area_km2"] == pytest.approx(area_records[0]["area_m2"] / 1_000_000)

    clipped_records = registry.load_dataset(outputs["clipped"]["data_id"])
    assert clipped_records[0]["geometry"]["type"] == "Polygon"
    assert clipped_records[0]["area_m2"] < area_records[0]["area_m2"]

    distance_records = registry.load_dataset(outputs["site_distance"]["data_id"])
    assert distance_records[0]["distance_m"] == pytest.approx(3000, rel=0.15)
