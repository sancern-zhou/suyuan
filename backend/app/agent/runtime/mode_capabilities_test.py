from app.agent.runtime.mode_capabilities import supports_native_multimodal


def test_supports_native_multimodal_for_social_and_chart_modes():
    assert supports_native_multimodal("social") is True
    assert supports_native_multimodal("chart") is True


def test_supports_native_multimodal_rejects_text_only_modes():
    assert supports_native_multimodal("assistant") is False
    assert supports_native_multimodal("expert") is False
    assert supports_native_multimodal(None) is False
