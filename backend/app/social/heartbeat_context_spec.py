import pytest

from app.agent.memory.session_memory import SessionMemory
from app.agent.session.models import Session
from app.agent.session.session_manager import SessionManager
from app.social.heartbeat_context import persist_heartbeat_context_event
from app.social.session_mapper import SessionMapper


@pytest.mark.asyncio
async def test_non_silent_heartbeat_records_lightweight_event_in_social_main_session(tmp_path, monkeypatch):
    from app.agent.session import session_manager as file_session_module

    local_manager = SessionManager(storage_base_path=str(tmp_path / "sessions"))
    monkeypatch.setattr(file_session_module, "_global_session_manager", local_manager)

    user_id = "weixin:bot:user"
    session_mapper = SessionMapper(data_dir=str(tmp_path / "social"))
    main_session_id = await session_mapper.get_or_create_session(user_id, mode="social")
    local_manager.save_session(
        Session(
            session_id=main_session_id,
            query="早上问候",
            conversation_history=[
                {"type": "user", "content": "早上好", "timestamp": "2026-07-08T08:00:00"},
                {"type": "final", "content": "早上好。", "timestamp": "2026-07-08T08:00:01"},
            ],
        )
    )

    recorded = await persist_heartbeat_context_event(
        session_mapper=session_mapper,
        user_id=user_id,
        response={
            "should_notify": True,
            "summary": "发现运城市 AQI 小时浓度告警，已生成 report.docx 并推送。",
            "executed_at": "2026-07-08T09:10:30",
        },
        heartbeat_session_id="heartbeat_weixin:bot:user_20260708091000",
        tasks=[{"name": "运城市告警溯源报告推送", "manual_mode": "social"}],
    )

    assert recorded is True
    loaded = local_manager.load_session(main_session_id)
    assert loaded is not None
    event_messages = [
        message
        for message in loaded.conversation_history
        if message.get("type") == "scheduled_task_event"
    ]
    assert len(event_messages) == 1
    event = event_messages[0]
    assert event["role"] == "user"
    assert "运城市告警溯源报告推送" in event["content"]
    assert "heartbeat_weixin:bot:user_20260708091000" in event["content"]
    assert event["data"]["kind"] == "scheduled_task_event"
    assert event["data"]["heartbeat_session_id"] == "heartbeat_weixin:bot:user_20260708091000"

    projected = SessionMemory.project_history_messages_for_llm(
        loaded.conversation_history,
        session_id=main_session_id,
    )
    assert any(
        message["role"] == "user" and "刚刚有一条非静默定时任务执行结果" in str(message["content"])
        for message in projected
    )

    recorded_again = await persist_heartbeat_context_event(
        session_mapper=session_mapper,
        user_id=user_id,
        response={
            "should_notify": True,
            "summary": "发现运城市 AQI 小时浓度告警，已生成 report.docx 并推送。",
            "executed_at": "2026-07-08T09:10:30",
        },
        heartbeat_session_id="heartbeat_weixin:bot:user_20260708091000",
        tasks=[{"name": "运城市告警溯源报告推送", "manual_mode": "social"}],
    )

    assert recorded_again is True
    loaded_again = local_manager.load_session(main_session_id)
    assert len([
        message
        for message in loaded_again.conversation_history
        if message.get("type") == "scheduled_task_event"
    ]) == 1


@pytest.mark.asyncio
async def test_silent_heartbeat_does_not_record_social_main_session_context(tmp_path, monkeypatch):
    from app.agent.session import session_manager as file_session_module

    local_manager = SessionManager(storage_base_path=str(tmp_path / "sessions"))
    monkeypatch.setattr(file_session_module, "_global_session_manager", local_manager)

    user_id = "weixin:bot:user"
    session_mapper = SessionMapper(data_dir=str(tmp_path / "social"))
    main_session_id = await session_mapper.get_or_create_session(user_id, mode="social")
    local_manager.save_session(Session(session_id=main_session_id, query="已有会话"))

    recorded = await persist_heartbeat_context_event(
        session_mapper=session_mapper,
        user_id=user_id,
        response={"should_notify": False, "summary": "HEARTBEAT_OK"},
        heartbeat_session_id="heartbeat_weixin:bot:user_20260708081000",
        tasks=[{"name": "运城市告警溯源报告推送", "manual_mode": "social"}],
    )

    assert recorded is False
    loaded = local_manager.load_session(main_session_id)
    assert loaded is not None
    assert not [
        message
        for message in loaded.conversation_history
        if message.get("type") == "scheduled_task_event"
    ]
