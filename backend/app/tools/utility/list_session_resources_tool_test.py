import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.agent.resources.contracts import ResourceDeclaration, ResourceKind
from app.agent.resources.resource_service import SessionResourceService
from app.tools.resource_declarations import primary_file
from app.tools.utility.list_session_resources_tool import ListSessionResourcesTool


@pytest.mark.asyncio
async def test_tool_reads_only_authorized_context_session_and_filters(tmp_path):
    output = tmp_path / "final.json"
    output.write_text("{}", encoding="utf-8")
    service = SessionResourceService.in_memory()
    await service.publish_group(
        "authorized-session",
        "run-a",
        "ops-audit:final",
        [
            ResourceDeclaration.model_validate(primary_file(
                output,
                group_key="ops-audit:final",
                tool_name="ops_audit_run_rules",
                label="Final issue list",
            ))
        ],
    )

    tool = ListSessionResourcesTool(service=service)
    result = await tool.execute(
        context=SimpleNamespace(session_id="authorized-session", runtime_mode="social"),
        kind=ResourceKind.FILE.value,
        logical_key="primary:json",
        include_locator=False,
    )

    assert result["success"] is True
    assert result["data"][0]["label"] == "Final issue list"
    assert isinstance(result["data"][0]["updated_at"], str)
    datetime.fromisoformat(result["data"][0]["updated_at"])
    json.dumps(result)
    assert "locator" not in result["data"][0]
    assert "session_id" not in tool.get_function_schema()["parameters"]["properties"]


@pytest.mark.asyncio
async def test_tool_rejects_missing_execution_context():
    tool = ListSessionResourcesTool(service=object())
    result = await tool.execute(context=None)
    assert result["success"] is False
