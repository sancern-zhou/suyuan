"""Durable workflow node history lookup and ownership guards."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.agent.session.models import Session
from app.agent.session.session_manager import SessionManager
from app.api import workflow_routes
from app.tools.agent_tools import call_sub_agent


class Catalog:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.reads = []

    async def require_read(self, session_id, user):
        self.reads.append(session_id)
        if not self.allowed:
            raise HTTPException(status_code=403, detail="forbidden")


def test_node_history_resolves_only_parent_linked_child(monkeypatch):
    child = Session(
        session_id="social__to__query__123",
        query="query",
        child_mode="query",
        is_sub_agent_session=True,
        metadata={
            "workflow": {"parent_task_id": "wf", "task_id": "wf:air", "workflow_runtime": {
                "events": [{"sequence": 1, "event_type": "task.running", "timestamp": "2026-09-28T00:00:01Z"}]
            }},
            "execution_history": [
                {"sequence": 1, "type": "tool_call", "tool_name": "air_quality"},
                {"sequence": 2, "type": "tool_result", "tool_name": "air_quality", "success": True},
            ],
        },
        conversation_history=[{"role": "assistant", "content": "空气数据摘要"}],
    )
    snapshot = {
        "workflow_id": "wf",
        "graph": {"wf:air": {"status": "succeeded"}},
        "node_sessions": {"wf:air": child.session_id},
        "runtime": {"events": [{"sequence": 2, "task_id": "wf:air", "event_type": "task.succeeded"}]},
    }
    parent = SimpleNamespace(metadata={"workflow_coordinators": {"wf": snapshot}})

    async def load_parent(_):
        return parent

    monkeypatch.setattr(workflow_routes, "_load_session", load_parent)
    monkeypatch.setattr(workflow_routes, "get_child_session_manager", lambda: SimpleNamespace(load_session=lambda _: child))
    catalog = Catalog()

    async def lookup(task_id="wf:air", after=0, limit=1):
        return await workflow_routes.workflow_node_history(
            "parent", "wf", task_id, after, limit, user=object(), catalog=catalog
        )

    first = asyncio.run(lookup())
    assert first["answer"] == "空气数据摘要"
    assert first["has_more"] is True
    assert [item["sequence"] for item in first["execution_history"]] == [1]
    assert [item["sequence"] for item in asyncio.run(lookup(after=1))["execution_history"]] == [2]
    assert catalog.reads == ["parent", "parent"]

    with pytest.raises(HTTPException) as missing:
        asyncio.run(lookup(task_id="other"))
    assert missing.value.status_code == 404

    snapshot["node_sessions"] = {}
    with pytest.raises(HTTPException) as legacy:
        asyncio.run(lookup())
    assert legacy.value.status_code == 404
    snapshot["graph"]["wf:air"]["status"] = "running"
    assert asyncio.run(lookup())["child_session_id"] is None
    snapshot["graph"]["wf:air"]["status"] = "succeeded"
    snapshot["node_sessions"]["wf:air"] = child.session_id

    child.metadata["workflow"]["parent_task_id"] = "another-workflow"
    with pytest.raises(HTTPException) as unlinked:
        asyncio.run(lookup())
    assert unlinked.value.status_code == 404

    with pytest.raises(HTTPException) as forbidden:
        asyncio.run(workflow_routes.workflow_node_history(
            "parent", "wf", "wf:air", 0, 1, user=object(), catalog=Catalog(allowed=False)
        ))
    assert forbidden.value.status_code == 403


def test_child_execution_trace_persists_without_tool_payloads(tmp_path, monkeypatch):
    manager = SessionManager(storage_base_path=str(tmp_path))
    monkeypatch.setattr(call_sub_agent, "session_manager", manager)
    call_sub_agent.CallSubAgentTool()._update_session(
        session_id="social__to__query__trace",
        parent_mode="social",
        child_mode="query",
        user_query="空气数据",
        assistant_answer="完成",
        result_events=[
            {"type": "tool_call", "generator": "air_quality", "args": {"private": "secret-input"}},
            {"type": "tool_result", "data": {"tool_name": "air_quality", "result": {
                "success": True, "data": "secret-output"
            }}},
            {"type": "agent_finish", "data": {"answer": "完成"}},
        ],
        task_id="wf:air",
        parent_task_id="wf",
        result_status="success",
    )
    saved = manager.load_session("social__to__query__trace")
    assert saved.metadata["execution_history"] == [
        {"sequence": 1, "type": "tool_call", "tool_name": "air_quality"},
        {"sequence": 2, "type": "tool_result", "tool_name": "air_quality", "success": True},
        {"sequence": 3, "type": "agent_finish"},
    ]
    contents = (tmp_path / "social__to__query__trace.json").read_text()
    assert "secret-input" not in contents and "secret-output" not in contents
