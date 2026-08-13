from app.agent.prompts.ops_prompt import build_ops_prompt
from app.agent.prompts.tool_registry import OPS_TOOL_NAMES, OPS_TOOL_ORDER


def test_ops_prompt_instructs_graph_guided_fault_diagnosis():
    prompt = build_ops_prompt(
        [
            "cognitive_map_guidance",
            "ops_audit_fetch_dataset",
            "query_gd_suncere_station_hour_new",
            "query_gd_suncere_station_day_new",
            "execute_ops_sql_query",
        ]
    )

    assert "认知地图驱动的故障诊断" in prompt
    assert "cognitive_map_guidance" in prompt
    assert "先调用 `cognitive_map_guidance`" in prompt
    assert "普通工单审核" in prompt


def test_ops_tool_registry_includes_cognitive_map_guidance():
    assert "cognitive_map_guidance" in OPS_TOOL_NAMES
    assert "cognitive_map_guidance" in OPS_TOOL_ORDER
