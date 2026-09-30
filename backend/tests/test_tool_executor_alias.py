from app.agent.core.executor import ToolExecutor


def _executor_with_registry(names):
    executor = object.__new__(ToolExecutor)
    executor.tool_registry = {name: object() for name in names}
    return executor


def test_missing_tool_alias_resolves_to_registered_read_file():
    executor = _executor_with_registry(["read_file", "execute_python"])

    assert executor._resolve_tool_alias("read") == "read_file"


def test_alias_resolution_ignores_unregistered_targets_and_unknown_names():
    executor = _executor_with_registry(["read_file", "execute_python"])

    assert executor._resolve_tool_alias("destroy_all") is None
    assert executor._resolve_tool_alias("  READ ") == "read_file"

    limited = _executor_with_registry(["execute_python"])
    assert limited._resolve_tool_alias("read") is None


def test_report_chart_legacy_name_no_longer_resolves():
    executor = _executor_with_registry(["create_business_chart"])
    assert executor._resolve_tool_alias("create_report_chart") is None
