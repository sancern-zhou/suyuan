from datetime import UTC, datetime

import pytest

from app.agent.resources.resource_service import ResourcePublishResult, StoredResource
from app.agent.resources.runtime import stream_with_resources


def primary_file() -> dict:
    return {
        "kind": "file",
        "group_key": "report:air",
        "resource_key": "source",
        "relation": "primary",
        "role": "output",
        "label": "report.pdf",
        "locator": {"path": "/tmp/report.pdf"},
        "format": "pdf",
        "media_type": "application/pdf",
        "renderer": "pdf",
        "capabilities": ["preview", "download"],
    }


def tool_result_event() -> dict:
    return {
        "type": "tool_result",
        "data": {
            "run_id": "run-1",
            "iteration": 2,
            "tool_name": "generate_report",
            "result": {"success": True, "resources": [primary_file()]},
        },
    }


def stored() -> StoredResource:
    now = datetime.now(UTC)
    return StoredResource(
        resource_id="resource-1",
        session_id="session-1",
        group_id="group-1",
        parent_resource_id=None,
        resource_key="source",
        relation="primary",
        kind="file",
        role="output",
        label="report.pdf",
        locator={"path": "/tmp/report.pdf"},
        format="pdf",
        media_type="application/pdf",
        renderer="pdf",
        capabilities=["preview", "download"],
        metadata={},
        tool_name="generate_report",
        run_id="run-1",
        turn_sequence=2,
        version=1,
        status="active",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_tool_resources_are_committed_before_change_event():
    order: list[str] = []

    class RecordingService:
        async def publish_group(self, *_args, **_kwargs):
            order.append("commit")
            return ResourcePublishResult(1, 1, [stored()])

    events = [tool_result_event(), {"type": "complete", "data": {}}]
    emitted = [
        event
        async for event in stream_with_resources(
            events,
            service=RecordingService(),
            session_id="session-1",
            run_id="run-1",
        )
    ]
    order.extend(event["type"] for event in emitted)

    assert order.index("commit") < order.index("resources_changed")
    changed = next(event for event in emitted if event["type"] == "resources_changed")
    assert changed["data"]["resource_version"] == 1
    assert changed["data"]["changed_resource_ids"] == ["resource-1"]


@pytest.mark.asyncio
async def test_failed_persistence_does_not_emit_change_event():
    class FailingService:
        async def publish_group(self, *_args, **_kwargs):
            raise RuntimeError("database unavailable")

    emitted = [
        event
        async for event in stream_with_resources(
            [tool_result_event()],
            service=FailingService(),
            session_id="session-1",
            run_id="run-1",
        )
    ]

    assert not any(event["type"] == "resources_changed" for event in emitted)
    error = next(event for event in emitted if event["type"] == "resource_error")
    assert error["data"]["session_id"] == "session-1"
    assert error["data"]["run_id"] == "run-1"


@pytest.mark.asyncio
async def test_failed_tool_result_is_never_published():
    class UnexpectedService:
        async def publish_group(self, *_args, **_kwargs):
            raise AssertionError("must not publish failed tool result")

    event = tool_result_event()
    event["data"]["is_error"] = True
    emitted = [
        item
        async for item in stream_with_resources(
            [event],
            service=UnexpectedService(),
            session_id="session-1",
            run_id="run-1",
        )
    ]
    assert emitted == [event]
