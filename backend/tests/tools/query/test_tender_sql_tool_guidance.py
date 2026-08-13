from app.tools.query.execute_sql_query.tool import ExecuteTenderSQLQueryTool


def test_tender_sql_tool_guides_agent_to_final_state_not_run_logs():
    tool = ExecuteTenderSQLQueryTool()
    description = tool.function_schema["description"]

    assert "tender_notices" in description
    assert "最终事实表" in description
    assert "accepted_missing_notice" in description
    assert "不要累加saved_notices" in description
    assert "不要仅因旧run存在detail_fetch_failures就判断补录未完成" in description
