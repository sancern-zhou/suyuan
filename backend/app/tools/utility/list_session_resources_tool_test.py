from types import SimpleNamespace

import pytest

from app.agent.resources.models import ResourceKind, ResourceLocator, ResourceRole, SessionResourceRef
from app.agent.resources.service import SessionResourceManifest
from app.tools.utility.list_session_resources_tool import ListSessionResourcesTool


def make_ref(kind, value, *, logical_key=None):
    locator = ResourceLocator(path=value) if kind is ResourceKind.FILE else ResourceLocator(data_id=value)
    return SessionResourceRef.create(
        kind=kind,
        locator=locator,
        logical_key=logical_key,
        role=ResourceRole.OUTPUT,
        label="Final issue list" if kind is ResourceKind.FILE else "Dataset",
        tool_name="ops_audit_run_rules",
        run_id="run-a",
        turn_sequence=1,
    )


@pytest.mark.asyncio
async def test_tool_reads_only_context_session_and_filters(tmp_path):
    file_ref = make_ref(ResourceKind.FILE, str(tmp_path / "final.json"), logical_key="ops_audit.final_issue_list")
    data_ref = make_ref(ResourceKind.DATA, "data:v1:a")

    class Service:
        async def load(self, session_id):
            assert session_id == "authorized-session"
            return SessionResourceManifest(session_id=session_id, refs=[file_ref, data_ref], version=2)

    tool = ListSessionResourcesTool(service=Service())
    result = await tool.execute(
        context=SimpleNamespace(session_id="authorized-session", runtime_mode="social"),
        kind="file",
        logical_key="ops_audit.final_issue_list",
    )
    assert result["success"] is True
    assert result["data"][0]["locator"]["path"].endswith("final.json")
    assert "session_id" not in tool.get_function_schema()["parameters"]["properties"]


@pytest.mark.asyncio
async def test_tool_rejects_missing_execution_context():
    tool = ListSessionResourcesTool(service=object())
    result = await tool.execute(context=None)
    assert result["success"] is False
