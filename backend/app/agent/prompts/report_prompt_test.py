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
    assert "无依赖" in prompt and "并行执行" in prompt
    assert "dependencies" in prompt
    assert "expert_meteorology" in prompt
    assert "expert_analysis" in prompt
    assert "node_results" in prompt
    assert "一个专家节点只回答一个分析问题" in prompt
    assert "同一领域有 N 个相互独立的问题" in prompt


def test_report_prompt_uses_python_as_primary_chart_tool():
    prompt = build_report_prompt(["execute_python", "create_business_chart", "create_report_package"])
    assert "正式报告静态数据图表优先使用 `execute_python`" in prompt
    assert "默认一个独立图表一个图片文件" in prompt
    assert "仅联合阅读确有必要或用户明确要求时合图" in prompt
    assert "按报告正文插入尺寸设计画布、比例和字号" in prompt
    assert "仅在 `create_business_chart` 无法覆盖时" not in prompt


def test_report_prompt_keeps_hourly_data_queries_conservative():
    prompt = build_report_prompt(["run_agent_workflow"])

    assert "小时数据保守取数" in prompt
    assert "最近一周以内的小时数据" in prompt
    assert "不要抓取完整周期的小时数据" in prompt
    assert "重点污染日" in prompt
