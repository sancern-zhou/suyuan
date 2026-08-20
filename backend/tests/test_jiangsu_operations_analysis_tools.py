import pytest

from app.agent.prompts.tool_registry import get_tool_order
from app.tools.jiangsu.operations_analysis import (
    JiangsuAttendanceRecordsTool,
    JiangsuOperationsKnowledgeGraphTool,
    JiangsuStationDirectoryTool,
)


def test_operations_analysis_exposes_live_relationship_graph_first():
    assert get_tool_order("operations_analysis") == [
        "jiangsu_query_operations_graph",
        "jiangsu_fetch_attendance_records",
        "jiangsu_fetch_station_directory",
        "knowledge_graph_query",
    ]


@pytest.mark.asyncio
async def test_attendance_records_maps_filters_and_returns_location_events(monkeypatch):
    tool = JiangsuAttendanceRecordsTool()
    captured = {}

    async def request(path, params):
        captured["path"] = path
        captured["params"] = params
        return {"result": {"items": [{"UserName": "张三", "StationCode": "5006A", "Longitude": 118.7}], "totalCount": 1}}

    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(
        start_time="2026-08-01 00:00:00",
        end_time="2026-08-02 00:00:00",
        user_name="张三",
        unit_id="unit-a",
        station_code="5006A",
    )

    assert result["success"] is True
    assert result["metadata"]["total_count"] == 1
    assert captured["path"] == "operation/AirCityAPPAttendance/GetAttendanceManagement"
    assert ("warrantytime[0]", "2026-08-01 00:00:00") in captured["params"]
    assert ("UserName", "张三") in captured["params"]
    assert ("StationCode", "5006A") in captured["params"]


@pytest.mark.asyncio
async def test_station_directory_filters_result_client_side(monkeypatch):
    tool = JiangsuStationDirectoryTool()

    async def request(path, params):
        assert path == "operation/AirOperaBase/GetOpaEnabledStationAsync"
        assert params == []
        return {"result": [{"stationCode": "5006A"}, {"stationCode": "5005A"}]}

    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(station_codes=["5005A"])

    assert result["success"] is True
    assert result["data"] == [{"stationCode": "5005A"}]


@pytest.mark.asyncio
async def test_attendance_records_rejects_oversized_time_range_before_request():
    tool = JiangsuAttendanceRecordsTool()
    result = await tool.execute(start_time="2026-01-01 00:00:00", end_time="2026-06-01 00:00:00")
    assert result["success"] is False
    assert "不超过 93 天" in result["summary"]


@pytest.mark.asyncio
async def test_operations_graph_resolves_person_unit_station_and_area(monkeypatch):
    tool = JiangsuOperationsKnowledgeGraphTool()
    group_rows = [
        {"id": "OperationUnit", "pId": "Operation", "name": "运维单位", "level": 1},
        {"id": "TH", "pId": "OperationUnit", "name": "武汉天虹", "level": 2},
        {"id": "U1", "pId": "TH", "name": "张三", "level": 3},
    ]
    stations = [
        {
            "stationCode": "5006A", "positionName": "江宁站", "cityCode": "320100",
            "cityName": "南京市", "districtCode": "320115", "districtName": "江宁区",
            "operationUnitId": "TH", "operationUnitName": "武汉天虹", "stationType": 1,
        }
    ]

    async def request(path, params):
        assert params == []
        if path == tool._GROUP_TREE_PATH:
            return {"result": group_rows}
        if path == tool._STATION_PATH:
            return {"result": stations}
        raise AssertionError(path)

    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(queries=["张三"], depth=2)

    assert result["success"] is True
    entity_types = {entity["entity_type"] for entity in result["data"]["entities"]}
    assert {"person", "operation_unit", "station"} <= entity_types
    assert {
        (relation["source_id"], relation["relation_type"], relation["target_id"])
        for relation in result["data"]["relations"]
    } >= {
        ("person:U1", "member_of", "operation_unit:TH"),
        ("operation_unit:TH", "responsible_for", "station:5006A"),
    }


@pytest.mark.asyncio
async def test_operations_graph_exposes_and_filters_station_type(monkeypatch):
    tool = JiangsuOperationsKnowledgeGraphTool()
    group_rows = [{"id": "TH", "pId": "", "name": "江苏运维", "level": 2}]
    stations = [
        {"stationCode": "N", "positionName": "国控站", "cityName": "南京市", "stationType": 1},
        {"stationCode": "P", "positionName": "省控站", "cityName": "南京市", "stationTypeName": "省控"},
    ]

    async def request(path, params):
        if path == tool._GROUP_TREE_PATH:
            return {"result": group_rows}
        if path == tool._STATION_PATH:
            return {"result": stations}
        raise AssertionError(path)

    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(queries=["南京市"], depth=1, station_type="省控")

    assert result["success"] is True
    station_entities = [
        entity for entity in result["data"]["entities"] if entity["entity_type"] == "station"
    ]
    assert [(entity["name"], entity["properties"]["station_type"]) for entity in station_entities] == [("省控站", "省控")]
    assert result["metadata"]["station_type"] == "省控"
    assert result["metadata"]["station_type_filter_applied"] is True


@pytest.mark.asyncio
async def test_operations_graph_lists_units_when_querying_unit_category(monkeypatch):
    tool = JiangsuOperationsKnowledgeGraphTool()
    group_rows = [
        {"id": "Operation", "pId": "", "name": "运维", "level": 0},
        {"id": "OperationUnit", "pId": "Operation", "name": "运维单位", "level": 1},
        {"id": "TH", "pId": "OperationUnit", "name": "武汉天虹", "level": 2},
        {"id": "SL1", "pId": "OperationUnit", "name": "江苏苏力", "level": 2},
    ]

    async def request(path, params):
        if path == tool._GROUP_TREE_PATH:
            return {"result": group_rows}
        return {"result": []}

    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(queries=["有哪些运维单位"], depth=1, max_entities=10)

    assert result["success"] is True
    assert [entity["name"] for entity in result["data"]["entities"]] == [
        "运维单位", "江苏苏力", "武汉天虹",
    ]
    assert result["data"]["matched_queries"][0]["entity_ids"] == [
        "operation_unit_group:OperationUnit",
    ]
    assert {
        (relation["source_id"], relation["relation_type"], relation["target_id"])
        for relation in result["data"]["relations"]
    } == {
        ("operation_unit_group:OperationUnit", "contains", "operation_unit:SL1"),
        ("operation_unit_group:OperationUnit", "contains", "operation_unit:TH"),
    }


@pytest.mark.asyncio
async def test_operations_graph_lists_units_when_directory_has_no_catalog_node(monkeypatch):
    """Live directories may leave level-2 units parentless; the type-label
    fallback must still list every operation unit for “有哪些运维单位”."""
    tool = JiangsuOperationsKnowledgeGraphTool()
    group_rows = [
        {"id": "TH", "pId": "", "name": "武汉天虹", "level": 2},
        {"id": "SL1", "pId": "", "name": "江苏苏力", "level": 2},
    ]

    async def request(path, params):
        if path == tool._GROUP_TREE_PATH:
            return {"result": group_rows}
        return {"result": []}

    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(queries=["运维单位"], depth=0, max_entities=50)

    assert result["success"] is True
    assert [entity["name"] for entity in result["data"]["entities"]] == [
        "武汉天虹", "江苏苏力",
    ]
    assert result["data"]["matched_queries"][0]["entity_ids"] == [
        "operation_unit:TH", "operation_unit:SL1",
    ]


@pytest.mark.asyncio
async def test_operations_graph_type_fallback_never_overrides_name_match(monkeypatch):
    tool = JiangsuOperationsKnowledgeGraphTool()
    group_rows = [
        {"id": "TH", "pId": "", "name": "武汉天虹", "level": 2},
        {"id": "SL1", "pId": "", "name": "江苏苏力", "level": 2},
    ]
    stations = [
        {
            "stationCode": "5006A", "positionName": "江宁站", "cityName": "南京市",
            "districtName": "江宁区", "operationUnitId": "TH", "operationUnitName": "武汉天虹",
        }
    ]

    async def request(path, params):
        if path == tool._GROUP_TREE_PATH:
            return {"result": group_rows}
        return {"result": stations}

    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(queries=["武汉天虹"], depth=0)

    assert result["data"]["matched_queries"][0]["entity_ids"] == ["operation_unit:TH"]


@pytest.mark.asyncio
async def test_operations_graph_connects_all_entity_types_from_any_seed(monkeypatch):
    tool = JiangsuOperationsKnowledgeGraphTool()
    group_rows = [
        {"id": "OperationUnit", "pId": "Operation", "name": "运维单位", "level": 1},
        {"id": "TH", "pId": "OperationUnit", "name": "武汉天虹", "level": 2},
        {"id": "U1", "pId": "TH", "name": "张三", "level": 3},
    ]
    station_rows = [{
        "stationCode": "5006A",
        "positionName": "江宁站",
        "cityCode": "320100",
        "cityName": "南京市",
        "districtCode": "320115",
        "districtName": "江宁区",
        "operationUnitId": "TH",
        "operationUnitName": "武汉天虹",
    }]

    async def request(path, params):
        if path == tool._GROUP_TREE_PATH:
            return {"result": group_rows}
        return {"result": station_rows}

    monkeypatch.setattr(tool, "_request", request)
    expected_types = {"person", "operation_unit", "station", "city", "district"}
    for query in ("张三", "武汉天虹", "江宁站", "江宁区", "南京市"):
        result = await tool.execute(queries=[query], depth=2, max_entities=20)
        assert result["success"] is True
        entity_types = {
            entity["entity_type"]
            for entity in result["data"]["entities"]
            if entity["entity_type"] != "operation_unit_group"
        }
        assert entity_types == expected_types

    graph = await tool._load_graph()
    relation_keys = {
        (relation["source_id"], relation["relation_type"], relation["target_id"])
        for relation in graph["relations"]
    }
    assert ("operation_unit:TH", "operates_in", "city:320100") in relation_keys
    assert ("operation_unit:TH", "operates_in", "district:320115") in relation_keys


@pytest.mark.asyncio
async def test_operations_graph_preserves_second_hop_types_when_station_fanout_is_large(monkeypatch):
    tool = JiangsuOperationsKnowledgeGraphTool()
    group_rows = [
        {"id": "OperationUnit", "pId": "Operation", "name": "运维单位", "level": 1},
        {"id": "TH", "pId": "OperationUnit", "name": "武汉天虹", "level": 2},
        {"id": "U1", "pId": "TH", "name": "张三", "level": 3},
    ]
    station_rows = [
        {
            "stationCode": f"S{i}",
            "positionName": f"站点{i}",
            "cityCode": "320100",
            "cityName": "南京市",
            "districtCode": "320115",
            "districtName": "江宁区",
            "operationUnitId": "TH",
            "operationUnitName": "武汉天虹",
        }
        for i in range(50)
    ]

    async def request(path, params):
        if path == tool._GROUP_TREE_PATH:
            return {"result": group_rows}
        return {"result": station_rows}

    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(queries=["南京市"], depth=2, max_entities=20)

    assert result["success"] is True
    assert {entity["entity_type"] for entity in result["data"]["entities"]} >= {
        "city", "district", "station", "operation_unit", "person",
    }


@pytest.mark.asyncio
async def test_operations_graph_matches_qualified_district_without_returning_full_directory(monkeypatch):
    tool = JiangsuOperationsKnowledgeGraphTool()

    async def request(path, params):
        if path == tool._GROUP_TREE_PATH:
            return {"result": []}
        return {"result": [
            {
                "stationCode": "A", "positionName": "A站", "cityCode": "320100",
                "cityName": "南京市", "districtCode": "320115", "districtName": "江宁区",
            },
            {
                "stationCode": "B", "positionName": "B站", "cityCode": "320300",
                "cityName": "徐州市", "districtCode": "320302", "districtName": "鼓楼区",
            },
        ]}

    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(queries=["南京市江宁区"], depth=0, max_entities=10)

    assert result["success"] is True
    assert [entity["entity_id"] for entity in result["data"]["entities"]] == ["district:320115"]


@pytest.mark.asyncio
async def test_operations_graph_externalizes_large_selection(monkeypatch):
    tool = JiangsuOperationsKnowledgeGraphTool()
    group_rows = [
        {"id": "OperationUnit", "pId": "Operation", "name": "运维单位", "level": 1},
        {"id": "LLD1", "pId": "OperationUnit", "name": "隆力德", "level": 2},
    ]
    station_rows = [
        {
            "stationCode": f"S{i}", "positionName": f"隆力德站点{i}",
            "cityCode": "320100", "cityName": "南京市",
            "districtCode": "320115", "districtName": "江宁区",
            "operationUnitId": "LLD1", "operationUnitName": "隆力德",
        }
        for i in range(80)
    ]

    async def request(path, params):
        return {"result": group_rows if path == tool._GROUP_TREE_PATH else station_rows}

    saved = {}

    class Context:
        def save_data(self, *, data, schema, metadata):
            saved.update(data=data, schema=schema, metadata=metadata)
            return "/tmp/jiangsu_operations_graph.json"

    monkeypatch.setattr(tool, "_request", request)
    result = await tool.execute(context=Context(), queries=["隆力德"], depth=1, max_entities=120)

    assert result["success"] is True
    assert result["data_complete"] is False
    assert result["file_path"] == "/tmp/jiangsu_operations_graph.json"
    assert result["metadata"]["record_count"] > result["metadata"]["returned_entity_count"]
    assert saved["schema"] == "jiangsu_operations_graph"
    assert len(saved["data"]["entities"]) == result["metadata"]["record_count"]
    assert len(saved["data"]["relations"]) == result["metadata"]["relation_count"]
