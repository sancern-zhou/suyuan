from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api import scheduled_task_routes as routes
from app.auth.models import CurrentUser
from app.scheduled_tasks.models import ScheduledTask
from app.tools.scheduled_tasks import manage_scheduled_tasks as module
from app.tools.scheduled_tasks.create_scheduled_task import CreateScheduledTaskTool
from app.tools.scheduled_tasks.session_identity import resolve_task_user


@pytest.fixture
def tasks(monkeypatch):
    def task(task_id, owner):
        return ScheduledTask(task_id=task_id, name=task_id, description="日报", prompt="汇总用户文件",
                             schedule_type="daily_custom", hour=8, minute=0, owner_user_id=owner)
    items = {"mine": task("mine", "company:2"), "other": task("other", "3")}
    service = SimpleNamespace(
        list_tasks=lambda **kw: list(items.values()), get_task=items.get,
        update_task=lambda task: items.__setitem__(task.task_id, task) or task,
        delete_task=lambda task_id: items.pop(task_id, None) is not None,
        start_task_now=lambda task_id: executed.append(task_id),
        list_task_results=lambda **kw: ([], 0),
        list_executions_page=lambda **kw: ([], 0),
    )
    executed = []
    def set_enabled(task_id, enabled):
        items[task_id].enabled = enabled
        return items[task_id]
    service.enable_task = lambda task_id: set_enabled(task_id, True)
    service.disable_task = lambda task_id: set_enabled(task_id, False)
    monkeypatch.setattr(routes, "get_scheduled_task_service", lambda: service)
    monkeypatch.setattr(module, "resolve_task_user", AsyncMock(return_value=CurrentUser(id="2", username="u", display_name="U")))
    return items, executed


@pytest.mark.asyncio
async def test_list_uses_canonical_owner_and_paginates(tasks):
    result = await module.manage_scheduled_tasks_tool.execute(action="list", page_size=1, data_context_manager=object())
    assert result["success"]
    assert [t["task_id"] for t in result["data"]["tasks"]] == ["mine"]
    assert result["data"]["total"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["get", "update", "enable", "disable", "delete", "execute", "history", "results"])
async def test_foreign_tasks_are_rejected_for_every_action(tasks, action):
    result = await module.manage_scheduled_tasks_tool.execute(action=action, task_id="other", updates={"hour": 9})
    assert not result["success"]
    assert tasks[0]["other"].hour == 8
    assert tasks[1] == []


@pytest.mark.asyncio
async def test_update_reuses_validation_and_preserves_owner(tasks):
    result = await module.manage_scheduled_tasks_tool.execute(action="update", task_id="mine", updates={"hour": 10})
    assert result["success"]
    assert tasks[0]["mine"].hour == 10
    result = await module.manage_scheduled_tasks_tool.execute(action="update", task_id="mine", updates={"owner_user_id": "3"})
    assert not result["success"]
    result = await module.manage_scheduled_tasks_tool.execute(action="update", task_id="mine", updates={"hour": 25})
    assert not result["success"]
    assert tasks[0]["mine"].owner_user_id == "company:2"
    assert tasks[0]["mine"].hour == 10


@pytest.mark.asyncio
async def test_execute_only_submits_and_history_is_available(tasks):
    result = await module.manage_scheduled_tasks_tool.execute(action="execute", task_id="mine")
    assert result["success"] and tasks[1] == ["mine"]
    assert "提交" in result["summary"]
    for action in ("history", "results"):
        result = await module.manage_scheduled_tasks_tool.execute(action=action, task_id="mine")
        assert result["success"] and result["data"]["total"] == 0


@pytest.mark.asyncio
async def test_unresolved_user_fails_closed(tasks, monkeypatch):
    monkeypatch.setattr(module, "resolve_task_user", AsyncMock(side_effect=ValueError("身份未确认")))
    result = await module.manage_scheduled_tasks_tool.execute(action="delete", task_id="mine")
    assert not result["success"] and "mine" in tasks[0]


@pytest.mark.asyncio
async def test_own_task_can_be_disabled_enabled_and_deleted(tasks):
    for action, enabled in (("disable", False), ("enable", True)):
        result = await module.manage_scheduled_tasks_tool.execute(action=action, task_id="mine")
        assert result["success"] and tasks[0]["mine"].enabled is enabled
    result = await module.manage_scheduled_tasks_tool.execute(action="delete", task_id="mine")
    assert result["success"] and "mine" not in tasks[0]


@pytest.mark.asyncio
async def test_identity_is_from_catalog_not_context_user(monkeypatch):
    from app.conversations import dependencies
    find = AsyncMock(return_value=SimpleNamespace(owner_user_id="2", owner_username="u", owner_display_name="U"))
    monkeypatch.setattr(dependencies, "get_conversation_catalog", lambda: SimpleNamespace(find=find))
    user = await resolve_task_user(SimpleNamespace(session_id="s", user_id="1", is_admin=True))
    assert user.id == "2" and not user.is_admin
    find.return_value = None
    with pytest.raises(ValueError):
        await resolve_task_user(SimpleNamespace(session_id="s"))


@pytest.mark.asyncio
async def test_create_without_owner_cannot_create_system_task(monkeypatch):
    from app.tools.scheduled_tasks import create_scheduled_task as create_module
    created = []
    monkeypatch.setattr(create_module, "get_scheduled_task_service", lambda: SimpleNamespace(create_task=created.append))
    tool = CreateScheduledTaskTool()
    monkeypatch.setattr(tool, "_resolve_session_owner", AsyncMock(return_value=None))
    result = await tool.execute(name="日报", description="汇总", prompt="汇总用户文件", schedule_type="daily_8am")
    assert not result["success"] and created == []


@pytest.mark.asyncio
async def test_create_preserves_owner_and_validates_broadcast(monkeypatch):
    from app.tools.scheduled_tasks import create_scheduled_task as create_module
    created = []
    def save(task):
        created.append(task)
        return task
    monkeypatch.setattr(create_module, "get_scheduled_task_service", lambda: SimpleNamespace(create_task=save))
    tool = CreateScheduledTaskTool()
    monkeypatch.setattr(tool, "_resolve_session_owner", AsyncMock(return_value={
        "owner_user_id": "2", "owner_username": "u", "owner_display_name": "U",
    }))
    params = dict(name="日报", description="汇总", prompt="汇总用户文件", schedule_type="daily_8am", execution_mode="assistant")
    result = await tool.execute(**params)
    assert result["success"] and created[0].owner_user_id == "2"
    assert created[0].execution_mode == "assistant"
    result = await tool.execute(**params, broadcast_enabled=True)
    assert not result["success"] and len(created) == 1
