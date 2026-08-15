import asyncio
from types import SimpleNamespace

import pytest

from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.tool_adapter import get_react_agent_tool_registry
from app.services.map_program_receipts import map_program_receipt_store
from app.tools.gisctl.map_program_receipt_tool import MapProgramReceiptTool, WaitMapProgramReceiptTool
from app.tools.gisctl.tool import GisctlTool


@pytest.mark.asyncio
async def test_map_program_receipt_tool_reads_frontend_execution_status():
    map_program_receipt_store.clear()
    map_program_receipt_store.record(
        "query_session_demo",
        {
            "program_id": "mapprog_buffer",
            "status": "executed",
            "layers": [
                {
                    "layer_id": "buffer",
                    "status": "layer_rendered",
                    "feature_count": 1,
                }
            ],
            "errors": [],
        },
    )

    result = await MapProgramReceiptTool().execute(
        session_id="query_session_demo",
        program_id="mapprog_buffer",
    )

    assert result["success"] is True
    assert result["data"]["receipt"]["status"] == "executed"
    assert result["data"]["receipt"]["layers"][0]["feature_count"] == 1


def test_map_program_receipt_tool_is_available_to_query_agent():
    assert "get_map_program_receipt" in get_tools_by_mode("query")
    assert "wait_map_program_receipt" in get_tools_by_mode("query")
    assert "visual_interaction" in get_tools_by_mode("query")
    assert "gisctl" not in get_tools_by_mode("query")
    assert "get_map_program_receipt" in get_react_agent_tool_registry()
    assert "wait_map_program_receipt" in get_react_agent_tool_registry()
    assert "visual_interaction" in get_react_agent_tool_registry()


@pytest.mark.asyncio
async def test_wait_map_program_receipt_tool_returns_when_frontend_receipt_arrives():
    map_program_receipt_store.clear()

    async def record_later():
        await asyncio.sleep(0.01)
        map_program_receipt_store.record(
            "query_session_demo",
            {
                "program_id": "mapprog_buffer",
                "status": "executed",
                "layers": [{"layer_id": "buffer", "status": "layer_rendered", "feature_count": 1}],
                "errors": [],
            },
        )

    task = asyncio.create_task(record_later())
    result = await WaitMapProgramReceiptTool().execute(
        session_id="query_session_demo",
        program_id="mapprog_buffer",
        wait_timeout=0.2,
        wait_interval=0.01,
    )
    await task

    assert result["success"] is True
    assert result["data"]["wait_timed_out"] is False
    assert result["data"]["receipt"]["layers"][0]["feature_count"] == 1


@pytest.mark.asyncio
async def test_visual_interaction_registers_pending_map_program_when_session_context_exists():
    map_program_receipt_store.clear()
    context = SimpleNamespace(session_id="query_session_demo")

    result = await GisctlTool().execute(
        context,
        command={
            "family": "map-spec",
            "action": "create",
            "kind": "set-view",
            "target": "广州",
        },
    )

    program_id = result["data"]["map_program"]["program_id"]
    status = map_program_receipt_store.get_program_status("query_session_demo", program_id)
    assert status["status"] == "pending"
    assert status["map_program"]["program_id"] == program_id


def test_map_program_receipt_schema_uses_visual_interaction_language():
    wait_schema = WaitMapProgramReceiptTool().get_function_schema()
    get_schema = MapProgramReceiptTool().get_function_schema()

    assert "视觉交互" in wait_schema["description"]
    assert "用户真实看见" in wait_schema["description"]
    assert "视觉交互" in get_schema["description"]
