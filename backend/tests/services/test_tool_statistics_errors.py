"""工具统计的最近错误环形缓冲。"""

import pytest

from app.services.tool_statistics_store import ToolStatisticsStore


@pytest.fixture
def store(tmp_path):
    return ToolStatisticsStore(base_dir=tmp_path)


def test_failure_without_summary_keeps_no_error_entry(store):
    store.record_execution("t1", success=False)
    stats = store.get_tool_stats("t1")
    assert stats["failed"] == 1
    assert stats["recent_errors"] == []


def test_failure_error_summary_recorded_and_capped(store):
    for i in range(12):
        store.record_execution(
            "t1",
            success=False,
            execution_time=0.5,
            error_summary=f"ValueError: bad input {i}",
        )
    stats = store.get_tool_stats("t1")
    assert stats["failed"] == 12
    errors = stats["recent_errors"]
    assert len(errors) == store.MAX_RECENT_ERRORS
    # 只保留最近 10 条，最后一条是第 12 次失败
    assert "bad input 11" in errors[-1]["error"]
    assert "bad input 0" not in errors[-1]["error"]
    assert errors[-1]["duration"] == 0.5
    assert errors[-1]["at"]


def test_success_does_not_touch_error_buffer(store):
    store.record_execution("t1", success=False, error_summary="boom")
    store.record_execution("t1", success=True, execution_time=1.2)
    stats = store.get_tool_stats("t1")
    assert stats["success"] == 1
    assert len(stats["recent_errors"]) == 1


def test_legacy_stats_file_without_recent_errors_normalizes(tmp_path):
    import json

    base = tmp_path / "tool_statistics"
    base.mkdir()
    (base / "tool_stats.json").write_text(
        json.dumps({"legacy_tool": {"total": 3, "success": 2, "failed": 1}}),
        encoding="utf-8",
    )
    store = ToolStatisticsStore(base_dir=tmp_path)
    stats = store.get_tool_stats("legacy_tool")
    assert stats["recent_errors"] == []
    store.record_execution("legacy_tool", success=False, error_summary="new failure")
    assert store.get_tool_stats("legacy_tool")["recent_errors"][-1]["error"] == "new failure"


def test_error_summary_truncated_to_200_chars(store):
    store.record_execution("t1", success=False, error_summary="x" * 500)
    assert len(store.get_tool_stats("t1")["recent_errors"][-1]["error"]) == 200
