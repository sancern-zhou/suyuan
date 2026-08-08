import json
from pathlib import Path


def _write_station_file(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "站点名称": "测试站点",
                        "唯一编码": "440100A",
                        "城市名称": "广州",
                        "区县": "越秀区",
                        "经度": 113.2644,
                        "纬度": 23.1291,
                        "详细地址": "测试地址",
                        "行政区划代码": "440104",
                        "站点类型ID": 1.0,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_station_cognitive_map_builder_creates_query_bound_station_entities(tmp_path):
    from app.agent.cognition.station_map_builder import (
        STATION_MAP_ID,
        ensure_station_cognitive_map,
    )

    station_file = tmp_path / "stations.json"
    _write_station_file(station_file)

    result = ensure_station_cognitive_map(root=tmp_path / "cognitive_maps", station_file=station_file)

    assert result["map_id"] == STATION_MAP_ID
    assert result["entity_count"] >= 4
    assert result["relation_count"] >= 3
    assert result["binding"]["agent_mode"] == "query"

    extraction = json.loads((tmp_path / "cognitive_maps" / STATION_MAP_ID / "extraction.json").read_text(encoding="utf-8"))
    station = next(entity for entity in extraction["candidate_entities"] if entity["name"] == "测试站点")
    assert station["entity_type"] == "Station"
    assert station["review_status"] == "published"
    assert station["attributes"]["station_code"] == "440100A"
    assert station["attributes"]["longitude"] == 113.2644
    assert station["attributes"]["latitude"] == 23.1291
    region_by_name = {
        entity["name"]: entity
        for entity in extraction["candidate_entities"]
        if entity["entity_type"] == "Region"
    }
    assert region_by_name["广东省"]["attributes"]["region_kind"] == "province"
    assert region_by_name["广州"]["attributes"]["region_kind"] == "city"
    assert region_by_name["越秀区"]["attributes"]["region_kind"] == "district"

    relation_keys = {
        (relation["source_entity_id"], relation["relation_type"], relation["target_entity_id"])
        for relation in extraction["candidate_relations"]
    }
    assert (station["entity_id"], "located_in", region_by_name["越秀区"]["entity_id"]) in relation_keys
    assert (region_by_name["越秀区"]["entity_id"], "located_in", region_by_name["广州"]["entity_id"]) in relation_keys
    assert (region_by_name["广州"]["entity_id"], "located_in", region_by_name["广东省"]["entity_id"]) in relation_keys

    bindings = json.loads((tmp_path / "cognitive_maps" / "agent_bindings.json").read_text(encoding="utf-8"))
    assert any(binding["map_id"] == STATION_MAP_ID and binding["agent_mode"] == "query" for binding in bindings)


def test_station_cognitive_map_builder_ignores_duplicate_station_code_relations(tmp_path):
    from app.agent.cognition.station_map_builder import (
        STATION_MAP_ID,
        ensure_station_cognitive_map,
    )

    station_file = tmp_path / "stations.json"
    station_file.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "站点名称": "原始站点",
                        "唯一编码": "DUP001",
                        "城市名称": "",
                        "区县": "",
                        "经度": 112.5,
                        "纬度": 23.0,
                        "详细地址": "",
                        "行政区划代码": "",
                        "站点类型ID": 1.0,
                    },
                    {
                        "站点名称": "重复站点",
                        "唯一编码": "DUP001",
                        "城市名称": "广州",
                        "区县": "",
                        "经度": None,
                        "纬度": None,
                        "详细地址": "重复记录",
                        "行政区划代码": "",
                        "站点类型ID": 1.0,
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    ensure_station_cognitive_map(root=tmp_path / "cognitive_maps", station_file=station_file)

    extraction = json.loads((tmp_path / "cognitive_maps" / STATION_MAP_ID / "extraction.json").read_text(encoding="utf-8"))
    station = next(entity for entity in extraction["candidate_entities"] if entity["name"] == "原始站点")
    regions = {
        entity["name"]: entity
        for entity in extraction["candidate_entities"]
        if entity["entity_type"] == "Region"
    }
    relation_keys = {
        (relation["source_entity_id"], relation["relation_type"], relation["target_entity_id"])
        for relation in extraction["candidate_relations"]
    }

    assert "重复站点" not in {entity["name"] for entity in extraction["candidate_entities"]}
    assert "广州" not in regions or (station["entity_id"], "located_in", regions["广州"]["entity_id"]) not in relation_keys
