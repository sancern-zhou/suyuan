# -*- coding: utf-8 -*-
"""daily_hours_custom 调度类型：模型校验与触发器构建测试。"""
import pytest
from apscheduler.triggers.cron import CronTrigger

from app.scheduled_tasks.models.task import ScheduledTask, ScheduleType
from app.scheduled_tasks.scheduler.simple_scheduler import SimpleScheduler
from app.scheduled_tasks.storage import TaskStorage


def _task(**overrides):
    payload = {
        "task_id": "task-monitor",
        "name": "运行监控",
        "description": "后台运行监控",
        "execution_mode": "custom",
        "tool_names": ["query_runtime_anomalies"],
        "trigger_type": "schedule",
        "schedule_type": "daily_hours_custom",
        "hours": [23, 1, 7, 0, 12, 1],
        "minute": 5,
        "prompt": "检查后台异常",
        "enabled": True,
    }
    payload.update(overrides)
    return ScheduledTask(**payload)


def test_model_accepts_daily_hours_and_dedupes_in_scheduler():
    task = _task()
    assert task.schedule_type == ScheduleType.DAILY_HOURS_CUSTOM
    assert task.hours == [23, 1, 7, 0, 12, 1]  # 模型不重排，调度器去重排序


@pytest.mark.parametrize("hours", [None, [], [24], [-1], [0, "x"]])
def test_model_rejects_invalid_hours(hours):
    with pytest.raises(ValueError):
        _task(hours=hours)


def test_model_rejects_missing_minute():
    with pytest.raises(ValueError):
        _task(minute=None)


def test_scheduler_builds_single_cron_trigger(monkeypatch):
    task = _task()
    scheduler = SimpleScheduler(TaskStorage())
    captured = {}

    def _fake_add_job(*args, **kwargs):
        captured["trigger"] = kwargs.get("trigger") or (args[2] if len(args) > 2 else None)

    monkeypatch.setattr(scheduler.scheduler, "add_job", _fake_add_job)
    monkeypatch.setattr(scheduler.task_storage, "update", lambda t: t)
    scheduler._schedule_task(task)

    trigger = captured["trigger"]
    assert isinstance(trigger, CronTrigger)
    for field in trigger.fields:
        if str(field.name) == "hour":
            assert "0,1,7,12,23" in str(field)
        if str(field.name) == "minute":
            assert "5" in str(field)


def test_scheduler_skips_invalid_task(monkeypatch):
    # 模型校验已拦截 hours=None；这里绕过校验构造，验证调度器自身的兜底分支。
    task = _task()
    task = ScheduledTask.model_construct(**{**task.model_dump(), "hours": None})
    scheduler = SimpleScheduler(TaskStorage())
    monkeypatch.setattr(
        scheduler.scheduler, "add_job", lambda *args, **kwargs: pytest.fail("should not schedule")
    )
    monkeypatch.setattr(scheduler.task_storage, "update", lambda t: pytest.fail("should not persist"))
    scheduler._schedule_task(task)  # 只记错误日志，不抛异常、不注册 job
