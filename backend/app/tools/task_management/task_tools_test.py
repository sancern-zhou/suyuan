import pytest

from app.agent.context.execution_context import ExecutionContext
from app.agent.task.task_models import TaskList
from app.agent.tool_adapter import call_llm_tool
from app.tools.task_management.task_tools import (
    TaskCreateTool,
    TaskGetTool,
    TaskListTool,
    TaskUpdateTool,
)


def make_context() -> ExecutionContext:
    return ExecutionContext(
        session_id="test-session",
        iteration=1,
        data_manager=None,
        task_list=TaskList(),
    )


def test_task_create_schema_defines_complex_multistep_task_threshold():
    tool = TaskCreateTool()

    assert "8 个以上任务节点" in tool.description
    assert "8 个以上任务节点" in tool.function_schema["description"]
    assert tool.function_schema["parameters"]["required"] == ["tasks"]
    assert "tasks" in tool.function_schema["parameters"]["properties"]
    assert "subject" not in tool.function_schema["parameters"]["properties"]


@pytest.mark.asyncio
async def test_task_tools_create_update_list_and_get_tasks():
    context = make_context()

    created = await TaskCreateTool().execute(
        context=context,
        tasks=[
            {
                "subject": "Inspect logs",
                "description": "Review runtime logs",
                "activeForm": "Inspecting logs",
            }
        ],
    )
    updated = await TaskUpdateTool().execute(
        context=context,
        taskId="1",
        status="in_progress",
    )
    listed = await TaskListTool().execute(context=context)
    fetched = await TaskGetTool().execute(context=context, taskId="1")

    assert created["success"] is True
    assert created["data"]["createdTasks"][0]["id"] == "1"
    assert updated["success"] is True
    assert updated["data"]["statusChange"] == {"from": "pending", "to": "in_progress"}
    assert listed["data"]["tasks"][0]["activeForm"] == "Inspecting logs"
    assert fetched["data"]["task"]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_task_update_reports_no_op_without_marking_failure():
    context = make_context()
    await TaskCreateTool().execute(
        context=context,
        tasks=[
            {
                "subject": "Inspect logs",
                "description": "Review runtime logs",
            }
        ],
    )

    result = await TaskUpdateTool().execute(context=context, taskId="1")

    assert result["success"] is True
    assert result["status"] == "no_op"
    assert result["data"]["updatedFields"] == []


@pytest.mark.asyncio
async def test_task_create_is_idempotent_for_existing_subject_and_description():
    context = make_context()
    first = await TaskCreateTool().execute(
        context=context,
        tasks=[
            {
                "subject": "Generate PPT",
                "description": "Create a 10 page report",
            }
        ],
    )
    await TaskUpdateTool().execute(context=context, taskId="1", status="completed")

    second = await TaskCreateTool().execute(
        context=context,
        tasks=[
            {
                "subject": "Generate PPT",
                "description": "Create a 10 page report",
            }
        ],
    )

    assert first["success"] is True
    assert second["success"] is True
    assert second["status"] == "no_op"
    assert second["data"]["existingTasks"][0]["id"] == "1"
    assert len(context.get_task_list().list()) == 1


@pytest.mark.asyncio
async def test_task_create_creates_multiple_tasks_in_one_call():
    context = make_context()

    result = await TaskCreateTool().execute(
        context=context,
        tasks=[
            {
                "subject": "Read outline",
                "description": "Extract report structure",
                "activeForm": "Reading outline",
            },
            {
                "subject": "Check chart assets",
                "description": "Verify referenced chart files",
                "activeForm": "Checking assets",
            },
        ],
    )

    assert result["success"] is True
    assert result["data"]["createdCount"] == 2
    assert result["data"]["existingCount"] == 0
    assert [task["id"] for task in result["data"]["createdTasks"]] == ["1", "2"]
    assert [task.subject for task in context.get_task_list().list()] == [
        "Read outline",
        "Check chart assets",
    ]


@pytest.mark.asyncio
async def test_task_create_adapter_call_ignores_data_context_manager_injection():
    context = make_context()
    context.data_manager = object()

    result = await call_llm_tool(
        "TaskCreate",
        context,
        tasks=[
            {
                "subject": "Inspect logs",
                "description": "Review runtime logs",
            }
        ],
        data_context_manager=object(),
    )

    assert result["success"] is True
    assert result["data"]["createdTasks"][0]["id"] == "1"
