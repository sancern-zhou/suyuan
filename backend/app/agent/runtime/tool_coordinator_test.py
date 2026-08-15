from app.agent.runtime.tool_coordinator import ToolCoordinator


def test_chart_mode_read_file_does_not_default_to_native_multimodal_attachment():
    coordinator = ToolCoordinator(tool_executor=None)

    normalized = coordinator.normalize_tool_input(
        "read_file",
        {"path": "/tmp/chart.png"},
        mode="chart",
    )

    assert "as_multimodal_attachment" not in normalized


def test_native_multimodal_read_file_preserves_explicit_false_attachment_choice():
    coordinator = ToolCoordinator(tool_executor=None)

    normalized = coordinator.normalize_tool_input(
        "read_file",
        {"path": "/tmp/chart.png", "as_multimodal_attachment": False},
        mode="chart",
    )

    assert normalized["as_multimodal_attachment"] is False


def test_native_multimodal_read_file_preserves_explicit_true_attachment_choice():
    coordinator = ToolCoordinator(tool_executor=None)

    normalized = coordinator.normalize_tool_input(
        "read_file",
        {"path": "/tmp/chart.png", "as_multimodal_attachment": True},
        mode="social",
    )

    assert normalized["as_multimodal_attachment"] is True


def test_social_mode_read_file_does_not_default_to_native_multimodal_attachment():
    coordinator = ToolCoordinator(tool_executor=None)

    normalized = coordinator.normalize_tool_input(
        "read_file",
        {"path": "/tmp/social.png"},
        mode="social",
    )

    assert "as_multimodal_attachment" not in normalized


def test_assistant_mode_read_file_does_not_default_to_native_multimodal_attachment():
    coordinator = ToolCoordinator(tool_executor=None)

    normalized = coordinator.normalize_tool_input(
        "read_file",
        {"path": "/tmp/doc.txt"},
        mode="assistant",
    )

    assert "as_multimodal_attachment" not in normalized
