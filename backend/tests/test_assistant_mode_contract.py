"""Canonical mode names, storage source selection and entry-point contracts."""

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.agent.prompts.prompt_builder import build_react_system_prompt
from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.session import session_resolver
from app.agent.workflow.delegation import delegation_error
from app.api.agent import AgentAnalyzeRequest
from app.api.social_app_routes import AppChatRequest
from app.social.session_mapper import SessionMapper
from config.settings import settings


def test_old_mode_is_not_accepted_or_aliased(monkeypatch):
    monkeypatch.setattr(settings, "project_id", "default")
    with pytest.raises(ValueError, match="Unknown mode"):
        get_tools_by_mode("social")
    with pytest.raises(ValueError, match="Unknown mode"):
        build_react_system_prompt("social")
    with pytest.raises(ValidationError):
        AgentAnalyzeRequest(query="hello", skill_ids=[], context_refs=[], mode="social")
    with pytest.raises(ValidationError):
        AppChatRequest(query="hello", mode="social")
    assert AgentAnalyzeRequest(query="hello", skill_ids=[], context_refs=[], mode="assistant").mode == "assistant"
    assert AppChatRequest(query="hello", mode="assistant").mode == "assistant"
    assert delegation_error("assistant", ["office"]) is None
    assert delegation_error("social", ["office"])
    assert delegation_error("office", ["assistant"])


def test_storage_source_is_independent_of_runtime(monkeypatch):
    db, files = object(), object()
    monkeypatch.setattr("app.agent.session.get_session_manager", lambda: db)
    monkeypatch.setattr(session_resolver, "get_file_session_manager", lambda: files)
    assert session_resolver.get_session_manager_for_mode("assistant") is db
    assert session_resolver.get_session_manager_for_mode("channel") is files
    assert session_resolver.get_session_manager_for_mode("office") is db


def test_new_app_session_has_canonical_prefix():
    session_id = SessionMapper.new_session_id(mode="assistant")
    assert re.fullmatch(r"assistant_session_\d{13}_[0-9a-f]{12}", session_id)
    assert not re.fullmatch(r"social_session_\d{13}_[0-9a-f]{12}", session_id)


@pytest.mark.asyncio
async def test_assistant_runtime_requires_personal_memory_instead_of_becoming_office():
    from app.agent.react_agent import ReActAgent

    agent = ReActAgent.__new__(ReActAgent)
    agent.enable_memory = True
    with pytest.raises(ValueError, match="Assistant memory requires"):
        async for _ in ReActAgent.analyze.__wrapped__(agent, user_query="hello", manual_mode="assistant"):
            pass


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["web", "social"])
async def test_scheduled_assistant_binds_the_owners_personal_context(monkeypatch, source):
    from app.scheduled_tasks.executor.task_executor import ScheduledTaskExecutor

    task = SimpleNamespace(
        owner_user_id="alice", owner_username="account-a", owner_display_name="Alice",
        source_session_id="source-session",
    )
    catalog = SimpleNamespace(find=AsyncMock(return_value=SimpleNamespace(owner_user_id="alice", source=source)))
    monkeypatch.setattr("app.conversations.dependencies.get_conversation_catalog", lambda: catalog)
    monkeypatch.setattr("app.social.web_assistant.web_assistant_context", lambda user: {"user_identifier": "web:" + user.id})
    monkeypatch.setattr("app.social.web_assistant.assistant_personal_context", lambda owner: {"user_identifier": owner})
    context, account = await ScheduledTaskExecutor._assistant_task_context(task)
    assert context["user_identifier"] == ("web:alice" if source == "web" else "alice")
    assert account == {"username": "account-a", "display_name": "Alice"}
    catalog.find.return_value.owner_user_id = "bob"
    with pytest.raises(PermissionError):
        await ScheduledTaskExecutor._assistant_task_context(task)
    # 缺归属只降级为不带个人上下文执行（ebe64398），不能让整次执行硬失败。
    task.owner_user_id = "system"
    degraded_context, degraded_account = await ScheduledTaskExecutor._assistant_task_context(task)
    assert degraded_context == {} and degraded_account is None


@pytest.mark.asyncio
async def test_scheduled_assistant_forwards_identity_and_background_metadata():
    from app.scheduled_tasks.executor.task_executor import ScheduledTaskExecutor

    captured = {}

    class Agent:
        async def analyze(self, prompt, **kwargs):
            captured.update(kwargs)
            yield {"type": "complete", "data": {"answer": "done"}}

    executor = ScheduledTaskExecutor.__new__(ScheduledTaskExecutor)
    executor.agent_factory = Agent
    executor.conversation_persistence = SimpleNamespace()
    memory = object()
    executor._assistant_task_context = AsyncMock(return_value=(
        {"user_identifier": "server-user", "assistant_memory_store": memory},
        {"username": "account-a", "display_name": "Alice"},
    ))
    await executor._run_agent(
        "do work", "scheduled-test", manual_mode="assistant",
        runtime_metadata={"scheduled_task": {"task_id": "job-a"}},
    )
    assert captured["manual_mode"] == "assistant"
    assert captured["assistant_memory_store"] is memory
    assert captured["runtime_metadata"]["authenticated_account"]["username"] == "account-a"
    assert captured["runtime_metadata"]["scheduled_task"]["task_id"] == "job-a"
