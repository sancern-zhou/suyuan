import json

from app.agent.core.executor import ToolExecutor
from app.agent.memory.session_memory import (
    SessionMemory,
    _downsample_raw_to_budget,
    _minimal_tool_result,
    _prepare_tool_result_for_history,
)
from app.agent.tool_adapter import _convert_to_standard_format
from app.tools.utility.execute_python_tool import _python_success_summary


def test_python_success_summary_embeds_stdout_head():
    summary, alias = _python_success_summary("hello world", 11)
    assert "11 字符" in summary
    assert "hello world" in summary
    assert alias == "hello world"


def test_python_success_summary_empty_stdout():
    summary, alias = _python_success_summary("", 0)
    assert "无 stdout 输出" in summary
    assert alias == ""


def test_python_success_summary_alias_capped_at_2000():
    output = "x" * 5000
    summary, alias = _python_success_summary(output, 5000)
    assert len(alias) == 2000
    # summary 只带 200 字预览（外加 "exit" 里的一个 x）
    assert summary.count("x") <= 201


def test_standard_format_conversion_passes_stdout_through():
    raw = {
        "status": "success",
        "success": True,
        "stdout": "print output",
        "data": {"output": "print output"},
        "summary": "s",
    }
    converted = _convert_to_standard_format(raw, "execute_python", 0.1)
    assert converted["stdout"] == "print output"


def test_minimal_tool_result_preserves_dict_data_output():
    result = {
        "success": True,
        "summary": "✅ 执行成功（exit=0），stdout 5 字符",
        "data": {"output": "hello", "execution": {"exit_code": 0}, "declared_data_file_paths": []},
    }
    minimal = _minimal_tool_result(result)
    assert minimal["data"]["output"] == "hello"
    assert minimal["data_dict_preserved"] is True


def test_minimal_tool_result_skips_dict_data_without_readable_keys():
    result = {
        "success": True,
        "summary": "s",
        "data": {"opaque_blob": {"nested": [1, 2, 3]}},
    }
    minimal = _minimal_tool_result(result)
    assert "data" not in minimal


def test_prepare_tool_result_history_keeps_output_for_oversized_dict_data():
    # 字符串压缩截断上限 8000/字段，需要 3 个大字段才能超过 20000 的 minimal 阈值
    result = {
        "success": True,
        "summary": "s",
        "data": {
            "output": "y" * 19_000,
            "execution": {"exit_code": 0, "details": "z" * 19_000},
            "stderr_tail": "w" * 19_000,
        },
    }
    history_view = _prepare_tool_result_for_history(result)
    assert history_view.get("tool_result_truncated") is True
    assert history_view["data"]["output"].startswith("y")
    assert history_view.get("data_dict_preserved") is True


def test_downsample_raw_to_budget_fits_list_data():
    records = [{"index": i, "payload": "x" * 150} for i in range(200)]
    raw = {"success": True, "summary": "weather", "data": records}
    serialized = json.dumps(raw, ensure_ascii=False)
    assert len(serialized) > 24_000

    out = _downsample_raw_to_budget(serialized, 24_000)
    assert out is not None
    assert len(out) <= 24_000
    parsed = json.loads(out)
    assert 0 < len(parsed["data"]) < 200
    marker = parsed["metadata"]["fresh_projection_downsampled"]
    assert marker["original_count"] == 200
    assert marker["sampled_count"] == len(parsed["data"])
    # 头尾采样保留时间序列首尾
    assert parsed["data"][0]["index"] == 0
    assert parsed["data"][-1]["index"] == 199


def test_downsample_raw_to_budget_returns_none_for_dict_data():
    raw = {"success": True, "data": {"payload": "x" * 30_000}}
    assert _downsample_raw_to_budget(json.dumps(raw), 24_000) is None


def test_downsample_raw_to_budget_returns_none_when_two_records_exceed():
    records = [{"blob": "x" * 20_000} for _ in range(5)]
    raw = {"success": True, "data": records}
    assert _downsample_raw_to_budget(json.dumps(raw), 24_000) is None


def test_session_memory_injects_downsampled_list_result(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.agent.memory.session_memory._fresh_budgets", lambda: (48_000, 24_000)
    )
    session = SessionMemory("downsample-fresh", base_dir=tmp_path)
    session.add_user_message("查历史风向")
    records = [
        {"bjt": f"2026-11-{day:02d} {hour:02d}:00", "dir": 180 + hour, "note": "d" * 250}
        for day in range(11, 16) for hour in range(24)
    ]
    session.add_streaming_tool_results([{
        "tool_name": "get_weather_data",
        "tool_use_id": "t_weather",
        "tool_input": {},
        "result": {"success": True, "summary": "weather rows", "data": records},
    }])

    projected = session.get_messages_for_llm()
    block = projected[-1]["content"][0]
    injected = json.loads(block["content"])
    assert len(injected["data"]) < len(records)
    assert injected["metadata"]["fresh_projection_downsampled"]["original_count"] == len(records)
    assert injected["data"][0]["bjt"] == records[0]["bjt"]


def test_executor_no_longer_resamples_query_tool_data():
    executor = ToolExecutor(tool_registry={})
    result = {
        "success": True,
        "data": [{"timestamp": f"2026-11-11 {hour:02d}:00", "wind": hour} for hour in range(32)],
        "metadata": {"generator": "get_weather_data"},
    }
    normalized = executor._normalize_result("get_weather_data", result)
    assert len(normalized["data"]) == 32
