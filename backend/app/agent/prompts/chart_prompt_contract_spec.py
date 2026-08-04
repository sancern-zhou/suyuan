from app.agent.prompts.chart_prompt import build_chart_prompt


def test_chart_prompt_leaves_tool_selection_and_call_contract_to_schema():
    prompt = build_chart_prompt(["execute_echarts_python", "read_file"])

    assert "execute_echarts_python" not in prompt
    assert "read_file" not in prompt
    assert "tool schema 为唯一依据" in prompt
    assert "get_raw_data(" not in prompt
    assert "backend_data_registry/datasets" not in prompt
    assert "stdout 每行" not in prompt
    assert "execute_echarts_python 图表生成示例" not in prompt
    assert "series 在顶层" not in prompt
    assert "输出标准 ECharts option" not in prompt
