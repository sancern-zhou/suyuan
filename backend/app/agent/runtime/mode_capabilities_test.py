import pytest

from app.agent.runtime.mode_capabilities import supports_native_multimodal


@pytest.mark.parametrize(
    "mode",
    [
        "assistant",
        "ppt",
        "expert",
        "query",
        "report",
        "social",
        "chart",
        "board",
        "ops",
        "graph",
        "custom",
        "memory_consolidator",
        "deliberation_monitoring",
        "future_mode",
        "",
        None,
    ],
)
def test_all_agent_modes_support_native_multimodal(mode):
    assert supports_native_multimodal(mode) is True
