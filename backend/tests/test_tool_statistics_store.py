from app.services.tool_statistics_store import RECENT_ERRORS_LIMIT, ToolStatisticsStore


def test_tool_statistics_store_persists_across_instances(tmp_path):
    store = ToolStatisticsStore(base_dir=tmp_path)
    store.ensure_tool("demo_tool")
    store.record_execution("demo_tool", success=True, execution_time=2.5)
    store.record_execution("demo_tool", success=False, execution_time=1.0)

    reloaded = ToolStatisticsStore(base_dir=tmp_path)
    stats = reloaded.get_tool_stats("demo_tool")

    assert stats["total"] == 2
    assert stats["success"] == 1
    assert stats["failed"] == 1
    assert stats["avg_execution_time"] == 2.5


def test_tool_statistics_store_records_error_summary_ring_buffer(tmp_path):
    store = ToolStatisticsStore(base_dir=tmp_path)
    store.ensure_tool("demo_tool")
    for index in range(RECENT_ERRORS_LIMIT + 3):
        store.record_execution(
            "demo_tool",
            success=False,
            error_summary=f"TypeError: boom-{index}",
        )

    stats = store.get_tool_stats("demo_tool")

    assert stats["failed"] == RECENT_ERRORS_LIMIT + 3
    assert len(stats["recent_errors"]) == RECENT_ERRORS_LIMIT
    assert stats["recent_errors"][-1]["summary"] == f"TypeError: boom-{RECENT_ERRORS_LIMIT + 2}"

    reloaded = ToolStatisticsStore(base_dir=tmp_path)
    assert (
        reloaded.get_tool_stats("demo_tool")["recent_errors"][-1]["summary"]
        == f"TypeError: boom-{RECENT_ERRORS_LIMIT + 2}"
    )


def test_tool_statistics_store_success_does_not_touch_recent_errors(tmp_path):
    store = ToolStatisticsStore(base_dir=tmp_path)
    store.ensure_tool("demo_tool")
    store.record_execution("demo_tool", success=True, execution_time=1.0)

    stats = store.get_tool_stats("demo_tool")

    assert stats["recent_errors"] == []
