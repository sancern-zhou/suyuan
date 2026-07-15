import asyncio

import pytest

from app.agent.resources.manifest import merge_resource_refs, project_session_resources
from app.agent.resources.runtime import RunReferenceAccumulator
from app.agent.resources.service import SessionResourceManifest, SessionResourceManifestService
from app.tools.analysis.ops_work_order_audit.tool import _standard_success


class LockedMemoryRepository:
    def __init__(self):
        self.rows = {}
        self.lock = asyncio.Lock()

    async def load(self, session_id):
        return self.rows.get(session_id, SessionResourceManifest(session_id=session_id))

    async def merge(self, session_id, incoming):
        if not incoming:
            return await self.load(session_id)
        async with self.lock:
            current = await self.load(session_id)
            stored = SessionResourceManifest(
                session_id=session_id,
                refs=merge_resource_refs(current.refs, incoming),
                version=current.version + 1,
            )
            self.rows[session_id] = stored
            return stored

    async def delete(self, session_id):
        return self.rows.pop(session_id, None) is not None


def _ops_event(tmp_path, data_id):
    result = _standard_success(
        "ops_audit_run_rules",
        "done",
        {
            "final_issue_list_path": str(tmp_path / f"{data_id[-1]}-final.json"),
            "data_id": data_id,
        },
    )
    return {
        "type": "tool_result",
        "data": {"tool_name": "ops_audit_run_rules", "result": result, "is_error": False},
    }


@pytest.mark.asyncio
async def test_refs_survive_request_boundary_and_mode_switch(tmp_path):
    repository = LockedMemoryRepository()
    service = SessionResourceManifestService(repository)
    accumulator = RunReferenceAccumulator(run_id="run-web")
    accumulator.capture(_ops_event(tmp_path, "ops:v1:a"), turn_sequence=1)
    await service.merge("shared-session", accumulator.refs)

    await service.merge("shared-session", [])
    restored = await service.load("shared-session")
    final_ref = next(ref for ref in restored.refs if ref.logical_key == "ops_audit.final_issue_list")
    assert final_ref.locator.path.endswith("a-final.json")

    web_context = project_session_resources(
        restored.refs, query="刚才的审核结果", available_tools={"read_file"}
    )
    social_context = project_session_resources(
        restored.refs, query="刚才的审核结果", available_tools={"read_file"}
    )
    assert web_context == social_context
    assert "a-final.json" in social_context


@pytest.mark.asyncio
async def test_concurrent_cross_mode_merges_keep_union(tmp_path):
    service = SessionResourceManifestService(LockedMemoryRepository())
    first = RunReferenceAccumulator(run_id="run-web")
    second = RunReferenceAccumulator(run_id="run-social")
    first.capture(_ops_event(tmp_path, "ops:v1:a"), turn_sequence=1)
    second.capture(_ops_event(tmp_path, "ops:v1:b"), turn_sequence=1)

    await asyncio.gather(
        service.merge("shared-session", first.refs),
        service.merge("shared-session", second.refs),
    )
    restored = await service.load("shared-session")
    assert {ref.locator.data_id for ref in restored.refs if ref.locator.data_id} == {
        "ops:v1:a",
        "ops:v1:b",
    }
