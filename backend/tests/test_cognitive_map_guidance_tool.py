import pytest

from app.tools.analysis.cognitive_map_guidance.tool import (
    CognitiveMapGuidanceTool,
    build_guidance_from_views,
)
from app.tools import create_global_tool_registry


def _view(relations):
    return {
        "map_id": "cm_test",
        "map_name": "运维故障图谱",
        "source": "property_graph_store",
        "entities": [
            {"entity_id": "e_station", "name": "东城站", "entity_type": "station"},
            {"entity_id": "e_alarm", "name": "零点漂移告警", "entity_type": "alarm"},
            {"entity_id": "e_cause", "name": "分析仪零点漂移", "entity_type": "root_cause"},
            {"entity_id": "e_metric", "name": "NO2小时浓度", "entity_type": "data_metric"},
        ],
        "relations": relations,
        "evidence_summaries": [
            {"evidence_id": "ev_1", "text": "零点漂移会导致小时浓度异常。"},
        ],
    }


def test_build_guidance_classifies_ops_fault_relations():
    views = [
        _view([
            {
                "relation_id": "r1",
                "source_name": "零点漂移告警",
                "target_name": "分析仪零点漂移",
                "relation_type": "alarm_indicates",
            },
            {
                "relation_id": "r2",
                "source_name": "分析仪零点漂移",
                "target_name": "NO2小时浓度",
                "relation_type": "fault_affects_metric",
            },
            {
                "relation_id": "r3",
                "source_name": "分析仪零点漂移",
                "target_name": "站点小时数据",
                "relation_type": "data_source_validates",
            },
        ])
    ]

    guidance = build_guidance_from_views(
        views=views,
        task="分析东城站零点漂移告警原因",
        agent_mode="ops",
    )

    assert guidance["matched"] is True
    assert "分析仪零点漂移" in guidance["analysis_directions"][0]["hypothesis"]
    tool_names = {tool["tool_name"] for tool in guidance["suggested_tools"]}
    assert "query_gd_suncere_station_hour_new" in tool_names
    assert "ops_audit_fetch_dataset" in tool_names
    assert guidance["data_requirements"]


def test_build_guidance_suggests_query_station_geo_tools():
    views = [
        {
            "map_id": "cm_station",
            "map_name": "广东省环境空气监测站点",
            "source": "extraction",
            "entities": [
                {"entity_id": "station_1", "name": "麓湖", "entity_type": "Station"},
                {"entity_id": "pollutant_pm25", "name": "PM2.5", "entity_type": "Pollutant"},
                {"entity_id": "tool_resolve_station_geo", "name": "resolve_station_geo", "entity_type": "Tool"},
            ],
            "relations": [
                {
                    "relation_id": "r1",
                    "source_name": "麓湖",
                    "target_name": "PM2.5",
                    "relation_type": "measures",
                },
                {
                    "relation_id": "r2",
                    "source_name": "resolve_station_geo",
                    "target_name": "麓湖",
                    "relation_type": "produces",
                },
            ],
            "evidence_summaries": [],
        }
    ]

    guidance = build_guidance_from_views(
        views=views,
        task="把 PM2.5 最高的站点显示在地图上",
        agent_mode="query",
    )

    tool_names = {tool["tool_name"] for tool in guidance["suggested_tools"]}
    assert "query_station_standard_report" in tool_names
    assert "read_data_registry" in tool_names
    assert "resolve_station_geo" in tool_names
    assert "create_map_point_asset" in tool_names
    assert "visual_interaction" in tool_names
    assert guidance["data_requirements"]


@pytest.mark.asyncio
async def test_tool_reports_missing_bound_maps(monkeypatch):
    monkeypatch.setattr(
        "app.tools.analysis.cognitive_map_guidance.tool._enabled_binding_map_ids",
        lambda agent_mode: [],
    )

    result = await CognitiveMapGuidanceTool().execute(
        task="分析东城站设备告警",
        agent_mode="ops",
    )

    assert result["success"] is False
    assert "未找到" in result["summary"]


def test_global_registry_exposes_cognitive_map_guidance():
    registry = create_global_tool_registry()
    assert registry.get_tool("cognitive_map_guidance") is not None


def test_guidance_schema_does_not_bias_agent_mode_to_ops():
    schema = CognitiveMapGuidanceTool().get_function_schema()
    description = schema["parameters"]["properties"]["agent_mode"]["description"]

    assert "默认ops" not in description
    assert "graph" in description
