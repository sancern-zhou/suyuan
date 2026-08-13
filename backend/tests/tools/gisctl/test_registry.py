import asyncio

from app.services.data_registry import data_registry
from app.tools import create_global_tool_registry
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.gisctl.tool import GisctlTool


def test_visual_interaction_tool_is_llm_tool_and_generates_map_program():
    tool = GisctlTool()

    assert isinstance(tool, LLMTool)
    assert tool.name == "visual_interaction"
    assert tool.category == ToolCategory.VISUALIZATION

    schema = tool.get_function_schema()
    assert schema["name"] == "visual_interaction"
    assert "用户视觉交互" in schema["description"]
    assert "回答即所见" in schema["description"]
    assert "command" in schema["parameters"]["properties"]


def test_gisctl_tool_execute_returns_map_program():
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
        data_id="map_layer_test:v1:registry",
    )
    tool = GisctlTool()

    result = asyncio.run(
        tool.execute(
            command={
                "family": "map-spec",
                "action": "create",
                "kind": "point-layer",
                "data_id": "map_layer_test:v1:registry",
                "layer_id": "high_pm25",
                "name": "High PM2.5 stations",
                "lon": "longitude",
                "lat": "latitude",
                "color_by": "pm25",
            }
        )
    )

    assert result["success"] is True
    assert result["status"] == "success"
    assert result["metadata"]["map_program"]["type"] == "map_program"
    assert result["metadata"]["map_program"]["state"]["layers"][0]["id"] == "high_pm25"
    assert result["data"]["map_program"] == result["metadata"]["map_program"]


def test_global_registry_includes_visual_interaction_tool():
    registry = create_global_tool_registry()

    assert "visual_interaction" in registry.list_tools()
