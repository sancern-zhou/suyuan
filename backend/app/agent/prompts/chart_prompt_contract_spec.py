from app.agent.prompts.chart_prompt import build_chart_prompt


def test_chart_prompt_selects_echarts_tool_without_embedding_its_call_contract():
    prompt = build_chart_prompt(["execute_echarts_python", "read_file"])

    assert "execute_echarts_python" in prompt
    assert "get_raw_data(" not in prompt
    assert "backend_data_registry/datasets" not in prompt
    assert "stdout 每行" not in prompt
    assert "execute_echarts_python 图表生成示例" not in prompt
    assert "series 在顶层" not in prompt
    assert "输出标准 ECharts option" not in prompt
