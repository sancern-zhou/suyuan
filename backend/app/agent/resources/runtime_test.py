import pytest

from .contracts import ResourceDeclaration
from .runtime import RunResourceAccumulator, event_turn_sequence, flush_resource_accumulator


def _resource():
    return {
        "kind": "file",
        "logical_key": "report:current",
        "role": "report",
        "label": "report",
        "locator": {"path": "/tmp/report.html"},
        "presentation_type": "document",
        "presentation": {"format": "html", "preview": {"type": "html", "url": "/preview"}},
    }


def test_accumulator_reads_only_explicit_resource_list():
    accumulator = RunResourceAccumulator(run_id="run-a")
    accumulator.capture({"type": "tool_result", "data": {"resources": [_resource()]}}, turn_sequence=2)
    accumulator.capture({"type": "tool_result", "data": {"file_path": "/tmp/legacy.html"}}, turn_sequence=3)
    assert len(accumulator.resources) == 1
    assert accumulator.resources[0].resource_key() == "report:current"


def test_accumulator_ignores_transport_document_event():
    accumulator = RunResourceAccumulator(run_id="run-a")
    accumulator.capture({"type": "tool_result", "data": {"resources": [_resource()]}}, turn_sequence=2)
    accumulator.capture({"type": "office_document", "data": {"file_path": "/tmp/report.html"}}, turn_sequence=2)
    assert len(accumulator.resources) == 1


@pytest.mark.asyncio
async def test_flush_marks_resource_durable_after_upsert():
    accumulator = RunResourceAccumulator(run_id="run-a")
    accumulator.capture({"type": "tool_result", "data": {"resources": [_resource()]}}, turn_sequence=1)

    class Service:
        async def upsert_run_resources(self, session_id, run_id, resources, *, turn_sequence=0):
            return type("Result", (), {"version": 4})()

    terminal_data = {}
    result = await flush_resource_accumulator(Service(), "session-a", accumulator, terminal_data)
    assert result.version == 4
    assert terminal_data["resource_durable"] is True
    assert terminal_data["resource_version"] == 4


def test_malformed_iteration_falls_back_to_zero():
    assert event_turn_sequence({"iteration": "not-a-number"}) == 0
