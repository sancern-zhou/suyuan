"""修复轮证据摘要：子 Agent 补交提示能看到本轮已完成的工作。"""

from app.tools.agent_tools.call_sub_agent import CallSubAgentTool


def _tool() -> CallSubAgentTool:
    return object.__new__(CallSubAgentTool)


def test_summarize_child_evidence_lists_calls_results_and_files():
    events = [
        {"type": "tool_call", "data": {"tool_name": "get_weather_data"}},
        {
            "type": "tool_result",
            "data": {
                "tool_name": "get_weather_data",
                "result": {
                    "success": True,
                    "file_path": "/tmp/weather.json",
                    "summary": "7208 行逐小时实况",
                },
            },
        },
        {
            "type": "tool_result",
            "data": {
                "tool_name": "execute_python",
                "is_error": True,
                "result": {"success": False, "error": "KeyError: 'temperature'"},
            },
        },
    ]

    digest = _tool()._summarize_child_evidence(events)

    assert "- 发起调用 get_weather_data" in digest
    assert "get_weather_data: 成功" in digest
    assert "/tmp/weather.json" in digest
    assert "execute_python: 失败" in digest
    assert "已保存产物：/tmp/weather.json" in digest


def test_summarize_child_evidence_empty_events_returns_empty_string():
    assert _tool()._summarize_child_evidence([]) == ""


def test_summarize_child_evidence_reads_file_path_from_metadata():
    events = [{
        "type": "tool_result",
        "data": {
            "tool_name": "execute_python",
            "result": {
                "success": True,
                "metadata": {"file_path": "/tmp/out.csv"},
            },
        },
    }]

    digest = _tool()._summarize_child_evidence(events)

    assert "/tmp/out.csv" in digest
