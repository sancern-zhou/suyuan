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


def test_report_prompt_uses_python_as_primary_chart_tool():
    prompt = build_report_prompt(["execute_python", "create_business_chart", "create_report_package"])
    assert "正式报告静态数据图表优先使用 `execute_python`" in prompt
    assert "可自主设计分面和多子图" in prompt
    assert "仅在 `create_business_chart` 无法覆盖时" not in prompt
