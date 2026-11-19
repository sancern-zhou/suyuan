import pytest
from pydantic import ValidationError
from unittest.mock import Mock

from app.scheduled_tasks.event_catalog import get_event_definitions
from app.scheduled_tasks.models import ScheduledTask, TaskEvent
from app.scheduled_tasks.scheduler import SimpleScheduler
from app.scheduled_tasks.storage import TaskStorage


def _task_kwargs() -> dict:
    return {"prompt": "处理事件"}


def test_legacy_task_defaults_to_schedule_trigger():
    task = ScheduledTask(
        task_id="legacy",
        name="legacy",
        description="legacy task",
        schedule_type="daily_8am",
        **_task_kwargs(),
    )

    assert task.trigger_type == "schedule"
    assert task.event_type is None


def test_event_task_requires_event_type():
    with pytest.raises(ValidationError, match="event_type is required"):
        ScheduledTask(
            task_id="event",
            name="event",
            description="event task",
            trigger_type="event",
            schedule_type=None,
            **_task_kwargs(),
        )


def test_broadcast_task_requires_recipients():
    with pytest.raises(ValidationError, match="target_user_ids is required"):
        ScheduledTask(
            task_id="event",
            name="event",
            description="event task",
            trigger_type="event",
            schedule_type=None,
            event_type="xuchang.station_deviation.alert_created",
            broadcast_enabled=True,
            **_task_kwargs(),
        )


def test_event_matches_scalar_and_list_filters():
    event = TaskEvent(
        event_id="alert-1",
        event_type="xuchang.station_deviation.alert_created",
        attributes={"city": "许昌市", "alert_level": "medium"},
        payload={"evidence_dir": "/tmp/evidence"},
    )

    assert event.matches({"city": "许昌市", "alert_level": ["medium", "high"]})
    assert not event.matches({"city": "太原市"})


def test_xuchang_daily_attainment_exceedance_event_is_registered():
    definitions = {item.event_type: item for item in get_event_definitions()}

    event = definitions["xuchang.daily_attainment.predicted_exceedance"]
    assert "target_pollutant" in event.filter_fields


def _event_task() -> ScheduledTask:
    return ScheduledTask(
        task_id="event",
        name="event",
        description="event task",
        trigger_type="event",
        event_type="xuchang.station_deviation.alert_created",
        **_task_kwargs(),
    )


def test_add_event_task_does_not_schedule_it(tmp_path):
    scheduler = SimpleScheduler(TaskStorage(storage_dir=tmp_path))
    scheduler._schedule_task = Mock()

    scheduler.add_task(_event_task())

    scheduler._schedule_task.assert_not_called()


def test_update_event_task_removes_old_job_without_rescheduling(tmp_path):
    scheduler = SimpleScheduler(TaskStorage(storage_dir=tmp_path))
    scheduler.remove_task = Mock()
    scheduler._schedule_task = Mock()

    scheduler.update_task(_event_task())

    scheduler.remove_task.assert_called_once_with("event")
    scheduler._schedule_task.assert_not_called()


def test_scheduler_can_calculate_next_run_for_cron_task(tmp_path):
    storage = TaskStorage(storage_dir=tmp_path)
    task = ScheduledTask(
        task_id="daily-task",
        name="daily task",
        description="daily task",
        schedule_type="daily_8am",
        **_task_kwargs(),
    )
    storage.create(task)
    scheduler = SimpleScheduler(storage)

    scheduler._schedule_task(task)

    stored = storage.get(task.task_id)
    assert stored.next_run_at is not None
    assert scheduler.scheduler.get_job(task.task_id) is not None


def test_scheduler_supports_monthly_first_day_task(tmp_path):
    storage = TaskStorage(storage_dir=tmp_path)
    task = ScheduledTask(
        task_id="monthly-task",
        name="monthly task",
        description="monthly task",
        schedule_type="monthly_1st_7am",
        **_task_kwargs(),
    )
    storage.create(task)
    scheduler = SimpleScheduler(storage)

    scheduler._schedule_task(task)

    assert scheduler.scheduler.get_job(task.task_id) is not None


def test_scheduler_supports_weekly_monday_eight_am_task(tmp_path):
    storage = TaskStorage(storage_dir=tmp_path)
    task = ScheduledTask(
        task_id="weekly-monday-task",
        name="weekly monday task",
        description="weekly monday task",
        schedule_type="weekly_monday_8am",
        **_task_kwargs(),
    )
    storage.create(task)
    scheduler = SimpleScheduler(storage)

    scheduler._schedule_task(task)

    job = scheduler.scheduler.get_job(task.task_id)
    assert job is not None
    assert "day_of_week='mon'" in str(job.trigger)


def test_scheduler_supports_weekly_custom_friday_task(tmp_path):
    storage = TaskStorage(storage_dir=tmp_path)
    task = ScheduledTask(
        task_id="weekly-friday-task",
        name="weekly friday task",
        description="weekly friday task",
        schedule_type="weekly_custom",
        day_of_week=4,
        hour=9,
        minute=30,
        **_task_kwargs(),
    )
    storage.create(task)
    scheduler = SimpleScheduler(storage)

    scheduler._schedule_task(task)

    job = scheduler.scheduler.get_job(task.task_id)
    assert job is not None
    assert "day_of_week='4'" in str(job.trigger)
    assert "hour='9'" in str(job.trigger)
    assert "minute='30'" in str(job.trigger)


def test_weekly_custom_requires_weekday_and_time():
    with pytest.raises(ValidationError, match="day_of_week, hour and minute are required"):
        ScheduledTask(
            task_id="weekly-invalid",
            name="weekly invalid",
            description="weekly invalid",
            schedule_type="weekly_custom",
            **_task_kwargs(),
        )


def test_event_definitions_filtered_by_project_namespace():
    """事件目录消费口按部署项目过滤命名空间：其他项目不暴露 xuchang.* 事件。"""
    from types import SimpleNamespace

    from app.scheduled_tasks.event_catalog import (
        _event_belongs_to_project,
        get_event_definition,
        get_event_definitions,
    )

    assert get_event_definitions(SimpleNamespace(project="default")) == []
    assert (
        get_event_definition("xuchang.station_deviation.alert_created", SimpleNamespace(project="default"))
        is None
    )

    xuchang = SimpleNamespace(project="xuchang")
    assert get_event_definitions(xuchang), "xuchang 部署应看到自己的事件"
    assert (
        get_event_definition("xuchang.station_deviation.alert_created", xuchang)
        is not None
    )

    # jiangsu-ops 部署通过命名空间首段匹配分支自持目录中的 jiangsu.* 事件
    assert _event_belongs_to_project("jiangsu.smart_event.judged", "jiangsu-ops") is True
    assert _event_belongs_to_project("xuchang.station_deviation.alert_created", "jiangsu-ops") is False

    # 不传 manifest 保持旧行为（全量，向后兼容）
    assert len(get_event_definitions()) >= 10
