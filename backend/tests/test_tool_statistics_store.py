from app.services.tool_statistics_store import ToolStatisticsStore


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
