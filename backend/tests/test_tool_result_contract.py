"""Tool result envelope contract tests."""
from app.agent.core.tool_result import result_envelope_indicates_error


def test_failed_status_envelope_is_error():
    assert result_envelope_indicates_error({"status": "failed", "success": False}) is True


def test_success_false_envelope_is_error_even_with_success_status():
    assert result_envelope_indicates_error({"status": "success", "success": False}) is True


def test_success_envelope_is_not_error():
    assert result_envelope_indicates_error({"status": "success", "success": True}) is False
    assert result_envelope_indicates_error({}) is False


def test_non_mapping_payload_is_not_error():
    assert result_envelope_indicates_error(None) is False
    assert result_envelope_indicates_error("ok") is False
