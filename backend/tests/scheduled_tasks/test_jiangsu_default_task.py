from app.scheduled_tasks.default_tasks import (
    build_jiangsu_fault_work_order_review_task,
    build_jiangsu_station_fault_task,
    ensure_project_default_tasks,
)


class FakeService:
    def __init__(self):
        self.tasks = {}

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def create_task(self, task):
        self.tasks[task.task_id] = task
        return task

    def update_task(self, task):
        self.tasks[task.task_id] = task
        return task

    def delete_task(self, task_id):
        return self.tasks.pop(task_id, None) is not None


class BrokenProjectDefaultService(FakeService):
    def __init__(self):
        super().__init__()
        self.broken = True

    def get_task(self, task_id):
        if self.broken:
            from pydantic import ValidationError

            raise ValidationError.from_exception_data(
                "ScheduledTask",
                [{
                    "type": "missing",
                    "loc": ("prompt",),
                    "input": {"task_id": task_id, "created_by": "project-default"},
                }],
            )
        return super().get_task(task_id)

    def update_task(self, task):
        self.broken = False
        return super().update_task(task)


def test_default_task_targets_fault_agent_and_skill():
    task = build_jiangsu_station_fault_task()

    assert task.event_type == "jiangsu.station_fault.detected"
    assert task.execution_mode == "station_fault_diagnosis"
    assert task.skill_id == "station-alarm-diagnosis"
    assert "jiangsu_prepare_fault_work_order" in task.prompt
    assert task.workspace_entry.enabled is True


def test_work_order_review_default_task_targets_ops_mode_skill_and_submit_tool():
    task = build_jiangsu_fault_work_order_review_task()

    assert task.task_id == "jiangsu_fault_work_order_review"
    assert task.event_type == "jiangsu.fault_work_order.review_requested"
    assert task.execution_mode == "ops"
    assert task.skill_id == "fault-work-order-review"
    assert "payload.evidence_pack_path" in task.prompt
    assert "fault-work-order-review Skill" in task.prompt
    assert "SOP-03" in task.prompt
    assert "jiangsu_submit_fault_work_order_review" in task.prompt
    assert "M1-M8" not in task.prompt
    assert "E1-E9" not in task.prompt
    assert task.workspace_entry.enabled is True


def test_default_task_seeding_is_create_only():
    service = FakeService()

    first = ensure_project_default_tasks(service, ["jiangsu_station_fault_diagnosis"])
    service.tasks["jiangsu_station_fault_diagnosis"].name = "人工修改后的名称"
    second = ensure_project_default_tasks(service, ["jiangsu_station_fault_diagnosis"])

    assert first == ["jiangsu_station_fault_diagnosis"]
    assert second == []
    assert service.tasks["jiangsu_station_fault_diagnosis"].name == "人工修改后的名称"


def test_project_default_prompt_changes_refresh_seeded_task():
    service = FakeService()
    ensure_project_default_tasks(service, ["jiangsu_station_fault_diagnosis"])
    seeded = service.tasks["jiangsu_station_fault_diagnosis"]
    seeded.prompt = "旧提示词"
    seeded.enabled = False

    ensure_project_default_tasks(service, ["jiangsu_station_fault_diagnosis"])

    refreshed = service.tasks["jiangsu_station_fault_diagnosis"]
    assert refreshed.prompt != "旧提示词"
    assert "jiangsu_prepare_fault_work_order" in refreshed.prompt
    # Operator-side toggles survive the refresh.
    assert refreshed.enabled is False


def test_operator_edited_task_is_never_refreshed():
    service = FakeService()
    ensure_project_default_tasks(service, ["jiangsu_station_fault_diagnosis"])
    task = service.tasks["jiangsu_station_fault_diagnosis"]
    task.created_by = "operator"
    task.prompt = "运维人员自定义提示词"

    ensure_project_default_tasks(service, ["jiangsu_station_fault_diagnosis"])

    assert task.prompt == "运维人员自定义提示词"


def test_invalid_seeded_project_task_is_replaced():
    service = BrokenProjectDefaultService()
    service.tasks["jiangsu_station_fault_diagnosis"] = build_jiangsu_station_fault_task()
    service.tasks["jiangsu_station_fault_diagnosis"].enabled = False
    service.tasks["jiangsu_station_fault_diagnosis"].prompt = "旧坏记录"

    created = ensure_project_default_tasks(service, ["jiangsu_station_fault_diagnosis"])

    assert created == []
    assert service.broken is False
    assert "jiangsu_prepare_fault_work_order" in service.tasks["jiangsu_station_fault_diagnosis"].prompt
    assert service.tasks["jiangsu_station_fault_diagnosis"].enabled is False


def test_unified_work_order_review_task_deletes_obsolete_split_tasks():
    service = FakeService()
    service.tasks["jiangsu_fault_work_order_qc_review"] = object()
    service.tasks["jiangsu_fault_work_order_env_review"] = object()

    created = ensure_project_default_tasks(service, ["jiangsu_fault_work_order_review"])

    assert created == ["jiangsu_fault_work_order_review"]
    assert "jiangsu_fault_work_order_review" in service.tasks
    assert "jiangsu_fault_work_order_qc_review" not in service.tasks
    assert "jiangsu_fault_work_order_env_review" not in service.tasks
