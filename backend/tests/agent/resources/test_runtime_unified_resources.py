import pytest

from app.agent.resources.runtime import RunResourceAccumulator, flush_resource_accumulator


def resource_payload(path="/tmp/report.html"):
    return {
        "kind": "file",
        "logical_key": "report:current",
        "role": "report",
        "label": "report",
        "locator": {"path": path},
        "presentation_type": "document",
        "presentation": {"format": "html", "preview": {"type": "html", "url": "/preview"}},
    }


def test_accumulator_accepts_only_explicit_resources():
    accumulator = RunResourceAccumulator(run_id="run-a")
    accumulator.capture({
        "type": "tool_result",
        "data": {"success": True, "resources": [resource_payload()]},
    }, turn_sequence=2)
    accumulator.capture({
        "type": "tool_result",
        "data": {"success": True, "file_path": "/tmp/legacy.html"},
    }, turn_sequence=3)
    assert len(accumulator.resources) == 1
    assert accumulator.resources[0].resource_key() == "report:current"


def test_document_transport_event_is_not_captured_again():
    accumulator = RunResourceAccumulator(run_id="run-a")
    accumulator.capture({
        "type": "tool_result",
        "data": {"success": True, "resources": [resource_payload()]},
    }, turn_sequence=2)
    accumulator.capture({
        "type": "office_document",
        "data": {"file_path": "/tmp/report.html", "html_preview": {"html_url": "/preview"}},
    }, turn_sequence=2)
    assert len(accumulator.resources) == 1


@pytest.mark.asyncio
async def test_flush_uses_unified_upsert_before_terminal_durability():
    accumulator = RunResourceAccumulator(run_id="run-a")
    accumulator.capture({
        "type": "tool_result",
        "data": {"success": True, "resources": [resource_payload()]},
    }, turn_sequence=1)

    class Service:
        async def upsert_run_resources(self, session_id, run_id, resources, *, turn_sequence=0):
            assert session_id == "session-a"
            assert run_id == "run-a"
            assert len(resources) == 1
            return type("Result", (), {"version": 4})()

    terminal_data = {}
    result = await flush_resource_accumulator(Service(), "session-a", accumulator, terminal_data)
    assert result.version == 4
    assert terminal_data == {"resource_version": 4, "resource_durable": True}
