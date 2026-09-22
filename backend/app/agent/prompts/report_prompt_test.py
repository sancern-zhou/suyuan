from app.agent.prompts.report_prompt import build_report_prompt


def test_report_prompt_routes_city_pollutant_rankings_to_deterministic_tool():
    prompt = build_report_prompt(["analyze_city_pollutant_rankings"])

    assert "analyze_city_pollutant_rankings" in prompt
    assert "PM2.5/PM10/O3" in prompt
    assert "较低/较高排名" in prompt
    assert "不要使用模型自行排序" in prompt


def test_report_prompt_explains_when_to_use_agent_workflow_dag():
    prompt = build_report_prompt(["run_agent_workflow"])

    assert "run_agent_workflow" in prompt
    assert "无依赖节点并行执行" in prompt
    assert "report_analysis_v1" in prompt
