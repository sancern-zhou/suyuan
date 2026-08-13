import asyncio
import json


def _write_station_file(path):
    path.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "站点名称": "测试站点A",
                        "唯一编码": "440100A",
                        "城市名称": "广州",
                        "区县": "越秀区",
                        "经度": 113.2644,
                        "纬度": 23.1291,
                        "详细地址": "测试地址A",
                        "行政区划代码": "440104",
                        "站点类型ID": 1.0,
                    },
                    {
                        "站点名称": "测试站点B",
                        "唯一编码": "440100B",
                        "城市名称": "广州",
                        "区县": "越秀区",
                        "经度": 113.27,
                        "纬度": 23.13,
                        "详细地址": "测试地址B",
                        "行政区划代码": "440104",
                        "站点类型ID": 2.0,
                    },
                    {
                        "站点名称": "深圳站点",
                        "唯一编码": "440300A",
                        "城市名称": "深圳",
                        "区县": "南山区",
                        "经度": 113.93,
                        "纬度": 22.53,
                        "详细地址": "测试地址C",
                        "行政区划代码": "440305",
                        "站点类型ID": 1.0,
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_cognitive_map_entity_query_filters_station_by_city(tmp_path):
    from app.agent.cognition.station_map_builder import STATION_MAP_ID, ensure_station_cognitive_map
    from app.tools.cognition.cognitive_map_entity_query.tool import CognitiveMapEntityQueryTool

    station_file = tmp_path / "stations.json"
    _write_station_file(station_file)
    ensure_station_cognitive_map(root=tmp_path / "cognitive_maps", station_file=station_file)

    result = asyncio.run(
        CognitiveMapEntityQueryTool(cognitive_maps_root=tmp_path / "cognitive_maps").execute(
            map_ids=[STATION_MAP_ID],
            entity_type="Station",
            attribute_filters={"city": "广州"},
            limit=10,
        )
    )

    assert result["success"] is True
    assert result["data"]["count"] == 2
    names = {entity["name"] for entity in result["data"]["entities"]}
    assert names == {"测试站点A", "测试站点B"}
    first = result["data"]["entities"][0]
    assert first["attributes"]["city"] == "广州"
    assert "longitude" in first["attributes"]


def test_cognitive_map_graph_traverse_incoming_located_in_city_to_stations(tmp_path):
    from app.agent.cognition.station_map_builder import STATION_MAP_ID, ensure_station_cognitive_map
    from app.tools.cognition.cognitive_map_graph_traverse.tool import CognitiveMapGraphTraverseTool

    station_file = tmp_path / "stations.json"
    _write_station_file(station_file)
    ensure_station_cognitive_map(root=tmp_path / "cognitive_maps", station_file=station_file)

    result = asyncio.run(
        CognitiveMapGraphTraverseTool(cognitive_maps_root=tmp_path / "cognitive_maps").execute(
            map_ids=[STATION_MAP_ID],
            start_entity="广州",
            relation_type="located_in",
            direction="incoming",
            depth=2,
            target_entity_type="Station",
            limit=10,
        )
    )

    assert result["success"] is True
    assert result["data"]["count"] == 2
    names = {entity["name"] for entity in result["data"]["entities"]}
    assert names == {"测试站点A", "测试站点B"}
    relation_paths = result["data"]["paths"]
    assert any(any(relation["target_name"] == "广州" for relation in path) for path in relation_paths)


def test_query_mode_exposes_cognitive_map_query_tools():
    from app.agent.prompts.tool_registry import get_tools_by_mode
    from app.agent.tool_adapter import get_tool_schemas

    assert "cognitive_map_entity_query" in get_tools_by_mode("query")
    assert "cognitive_map_graph_traverse" in get_tools_by_mode("query")

    schema_names = {schema["name"] for schema in get_tool_schemas(mode="query")}
    assert "cognitive_map_entity_query" in schema_names
    assert "cognitive_map_graph_traverse" in schema_names
