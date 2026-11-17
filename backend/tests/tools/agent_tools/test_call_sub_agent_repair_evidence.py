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


def test_summarize_child_evidence_carries_execute_python_stdout():
    """execute_python 的数值在 stdout：只回 summary 等于没给证据。

    历史事故：子 Agent 已算出 96.29% 等数值，补交提示里只有"执行成功"一句，
    模型据此报 verified_facts=0 交出空结论。
    """
    events = [{
        "type": "tool_result",
        "data": {
            "tool_name": "execute_python",
            "result": {
                "success": True,
                "summary": "✅ 执行成功（exit=0）",
                "stdout": "完成率 96.29%；超期 77 项；重复故障率 38.1%",
            },
        },
    }]

    digest = _tool()._summarize_child_evidence(events)

    assert "96.29%" in digest
    assert "38.1%" in digest


def test_summarize_child_evidence_skips_stdout_for_other_tools():
    """只有 execute_python 的数值在 stdout；其他工具不放大证据体积。"""
    events = [{
        "type": "tool_result",
        "data": {
            "tool_name": "get_weather_data",
            "result": {"success": True, "summary": "7208 行", "stdout": "noise"},
        },
    }]

    digest = _tool()._summarize_child_evidence(events)

    assert "noise" not in digest
