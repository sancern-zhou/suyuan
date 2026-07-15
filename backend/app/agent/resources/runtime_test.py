import pytest

from app.agent.resources.runtime import (
    RunReferenceAccumulator,
    event_turn_sequence,
    flush_resource_accumulator,
)
from app.agent.resources.service import ManifestPersistenceError, SessionResourceManifest


def test_accumulator_reads_nested_streaming_tool_result():
    accumulator = RunReferenceAccumulator(run_id="run-a")
    accumulator.capture({
        "type": "tool_result",
        "data": {
            "tool_name": "query",
            "result": {"data_id": "dataset:v1:a"},
            "is_error": False,
        },
    }, turn_sequence=2)
    assert [ref.locator.data_id for ref in accumulator.refs] == ["dataset:v1:a"]


def test_accumulator_ignores_failed_tool_results():
    accumulator = RunReferenceAccumulator(run_id="run-a")
    accumulator.capture({
        "type": "tool_result",
        "data": {"tool_name": "query", "result": {"data_id": "bad:v1:a"}, "is_error": True},
    }, turn_sequence=2)
    assert accumulator.refs == []


def test_accumulator_unions_refs_from_multiple_events():
    accumulator = RunReferenceAccumulator(run_id="run-a")
    for data_id in ("data:v1:a", "data:v1:b"):
        accumulator.capture({
            "type": "tool_result",
            "data": {"tool_name": "query", "result": {"data_id": data_id}},
        }, turn_sequence=1)
    assert {ref.locator.data_id for ref in accumulator.refs} == {"data:v1:a", "data:v1:b"}


@pytest.mark.asyncio
async def test_terminal_flush_marks_refs_durable_before_delivery():
    accumulator = RunReferenceAccumulator(run_id="run-a")
    accumulator.capture({
        "type": "tool_result",
        "data": {"tool_name": "query", "result": {"data_id": "data:v1:a"}},
    }, turn_sequence=1)

    class Service:
        async def merge(self, session_id, refs):
            assert session_id == "session-a"
            return SessionResourceManifest(session_id=session_id, refs=refs, version=4)

    terminal_data = {}
    manifest = await flush_resource_accumulator(Service(), "session-a", accumulator, terminal_data)
    assert manifest.version == 4
    assert terminal_data == {"resource_refs_version": 4, "resource_refs_durable": True}


@pytest.mark.asyncio
async def test_terminal_flush_exposes_non_durable_failure():
    accumulator = RunReferenceAccumulator(run_id="run-a")
    accumulator.capture({
        "type": "tool_result",
        "data": {"tool_name": "query", "result": {"data_id": "data:v1:a"}},
    }, turn_sequence=1)

    class Service:
        async def merge(self, session_id, refs):
            raise ManifestPersistenceError("offline")

    terminal_data = {}
    manifest = await flush_resource_accumulator(Service(), "session-a", accumulator, terminal_data)
    assert manifest is None
    assert terminal_data["resource_refs_durable"] is False
    assert terminal_data["resource_refs_error"] == "manifest_persistence_failed"


def test_malformed_iteration_falls_back_without_breaking_resource_capture():
    assert event_turn_sequence({"iteration": "not-a-number"}) == 0
