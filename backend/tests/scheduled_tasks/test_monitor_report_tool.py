# -*- coding: utf-8 -*-
"""监控通报提交工具测试（fake 服务 / fake 通知服务）。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.tools.runtime_monitor.report import SubmitMonitorReportTool


def _context(task_id="task_runtime_monitor"):
    return SimpleNamespace(
        scheduled_task_context={"task_id": task_id, "execution_id": "exec-1"},
        user_identifier="",
    )


def _task(task_id="task_runtime_monitor", tags=None):
    return SimpleNamespace(task_id=task_id, name="监控", tags=tags if tags is not None else ["runtime-monitor"])


@pytest.fixture
def fake_service(monkeypatch):
    tasks = {}

    def _install(extra_tasks=None):
        tasks.update(extra_tasks or {})
        service = SimpleNamespace(
            task_storage=SimpleNamespace(get=lambda task_id: tasks.get(task_id)),
        )

        def _get_service():
            return service

        monkeypatch.setattr(
            "app.scheduled_tasks.service.get_scheduled_task_service", _get_service
        )
        return service

    return _install


@pytest.mark.asyncio
async def test_refuses_interactive_context():
    result = await SubmitMonitorReportTool().execute(
        context=SimpleNamespace(scheduled_task_context=None), content="通报"
    )
    assert result["success"] is False
    assert "定时任务执行上下文" in result["summary"]


@pytest.mark.asyncio
async def test_refuses_empty_content():
    result = await SubmitMonitorReportTool().execute(context=_context(), content="  ")
    assert result["success"] is False
    assert "content" in result["summary"]


@pytest.mark.asyncio
async def test_refuses_non_monitor_task(fake_service):
    fake_service({"task_biz": _task("task_biz", tags=[])})
    result = await SubmitMonitorReportTool().execute(
        context=_context("task_biz"), content="通报"
    )
    assert result["success"] is False
    assert "runtime-monitor" in result["summary"]


@pytest.mark.asyncio
async def test_refuses_when_owner_unconfigured(fake_service, monkeypatch):
    from config.settings import settings

    fake_service({"task_runtime_monitor": _task()})
    monkeypatch.setattr(settings, "monitor_report_owner", "")
    result = await SubmitMonitorReportTool().execute(context=_context(), content="通报")
    assert result["success"] is False
    assert "monitor_report_owner" in result["summary"]


@pytest.mark.asyncio
async def test_submits_report_and_passes_report_key(fake_service, monkeypatch):
    from config.settings import settings

    fake_service({"task_runtime_monitor": _task()})
    monkeypatch.setattr(settings, "monitor_report_owner", "alice")
    monkeypatch.setattr(settings, "project_id", "p")
    enqueued = AsyncMock(return_value="monitor:evt-9")
    monkeypatch.setattr(
        "app.social.assistant_notifications.AssistantNotificationService",
        lambda: SimpleNamespace(enqueue_monitor_report=enqueued),
        raising=False,
    )
    result = await SubmitMonitorReportTool().execute(
        context=_context(), content="通报正文", title=" 空格标题 ", report_key="evt-9"
    )
    assert result["success"] is True
    assert result["data"]["message_id"] == "monitor:evt-9"
    enqueued.assert_awaited_once_with(
        project="p", content="通报正文", title="空格标题", report_key="evt-9"
    )


@pytest.mark.asyncio
async def test_reports_invalid_owner_instead_of_silent_drop(fake_service, monkeypatch):
    from config.settings import settings

    fake_service({"task_runtime_monitor": _task()})
    monkeypatch.setattr(settings, "monitor_report_owner", "system")
    enqueued = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.social.assistant_notifications.AssistantNotificationService",
        lambda: SimpleNamespace(enqueue_monitor_report=enqueued),
        raising=False,
    )
    result = await SubmitMonitorReportTool().execute(context=_context(), content="通报")
    assert result["success"] is False
    assert "未送达" in result["summary"]
