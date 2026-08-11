from app.agent.prompts.project_prompt import load_project_mode_prompt
from app.project_config import load_project_context


def test_xuchang_query_and_expert_prompts_include_project_geography_memory():
    context = load_project_context("xuchang")

    for mode in ("query", "expert"):
        prompt = load_project_mode_prompt(mode, context)

        assert prompt is not None
        assert "## 项目长期地理信息" in prompt
        assert "中国河南省许昌市" in prompt
        assert "行政区代码为 `411000`" in prompt
        assert "`Asia/Shanghai`（UTC+8）" in prompt
        assert "`{city_name}` 替换为 `许昌市`" in prompt
        assert "`{city_code}` 替换为 `411000`" in prompt
        assert "北纬 `34.04`、东经 `113.85`" in prompt
        assert "用户明确指定其他城市或区域时，以用户本次指定为准" in prompt


def test_xuchang_query_prompt_combines_query_and_chart_workflows():
    context = load_project_context("xuchang")
    prompt = load_project_mode_prompt("query", context)

    assert prompt is not None
    assert "你是问数生图智能体" in prompt
    assert "## 问数生图工作流" in prompt
    assert "先调用数据查询工具取得可追溯结果" in prompt
    assert "用户已经提供完整数据时，不再调用数据查询工具" in prompt
    assert "网页交互查看的图表" in prompt
