from app.agent.react_agent import ReActAgent


def test_report_auto_followup_uses_ranking_tool_for_ranking_boundaries():
    prompt = ReActAgent.REPORT_FINAL_REVIEW_PROMPT

    assert "analyze_city_pollutant_rankings" in prompt
    assert "排名并列、Top N截取规则" in prompt
    assert "必须使用 `analyze_city_pollutant_rankings`" in prompt
    assert "使用 `execute_python` 进行排名" not in prompt
