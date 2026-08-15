from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.prompts.query_prompt import build_query_prompt
from app.agent.tool_adapter import get_tool_schemas


def test_query_prompt_declares_agentic_gis_capability():
    prompt = build_query_prompt(["visual_interaction", "resolve_map_data_asset", "read_data_registry", "query_city_standard_report"])

    assert "用户视觉交互的数据智能体" in prompt
    assert "问数回答不是纯文本答案" in prompt
    assert "自然语言、数据结果和地图视觉状态同步构成一次完整回答" in prompt
    assert "回答即所见" in prompt
    assert "用户在地图上的拖动、缩放、框选、点击和图层切换，应作为下一步分析与视觉交互的直接上下文" in prompt
    assert "查询结果包含城市、区域、站点、经纬度或其他空间对象时，应判断是否需要同步地图视觉状态" in prompt
    assert "如需改变用户所见，应使用本轮可用工具完成视觉交互" in prompt
    assert "具体工具能力、参数和完成信号以工具 schema 与工具返回为准" in prompt
    assert "没有得到视觉交互工具或前端回执的有效结果前，不得声称用户已经看到定位、缩放、图层或要素" in prompt
    assert "不得由模型猜测或手写" in prompt
    assert "`gisctl` 的 `map-spec" not in prompt
    assert "resolve_map_data_asset" not in prompt
    assert "cognitive_map_guidance(agent_mode=\"query\")" not in prompt
    assert "spatial_analysis_guide.md" not in prompt


def test_query_mode_declares_visual_interaction_tool():
    assert "visual_interaction" in get_tools_by_mode("query")
    assert "gisctl" not in get_tools_by_mode("query")
    assert "resolve_map_data_asset" in get_tools_by_mode("query")
    assert "cognitive_map_guidance" in get_tools_by_mode("query")
    assert "resolve_station_geo" in get_tools_by_mode("query")
    assert "create_map_point_asset" in get_tools_by_mode("query")
    assert "spatial_interpolation" in get_tools_by_mode("query")


def test_query_mode_exposes_visual_interaction_schema_to_llm():
    schema_names = {schema["name"] for schema in get_tool_schemas(mode="query")}

    assert "visual_interaction" in schema_names
    assert "gisctl" not in schema_names
    assert "resolve_map_data_asset" in schema_names
    assert "cognitive_map_guidance" in schema_names
    assert "resolve_station_geo" in schema_names
    assert "create_map_point_asset" in schema_names
    assert "spatial_interpolation" in schema_names
