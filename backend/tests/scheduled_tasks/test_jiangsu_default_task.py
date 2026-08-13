from app.scheduled_tasks.default_tasks import (
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


def test_default_task_targets_fault_agent_and_skill():
    task = build_jiangsu_station_fault_task()

    assert task.event_type == "jiangsu.station_fault.detected"
    assert task.execution_mode == "station_fault_diagnosis"
    assert task.skill_id == "station-alarm-diagnosis"
    assert task.workspace_entry.enabled is True


def test_default_task_seeding_is_create_only():
    service = FakeService()

    first = ensure_project_default_tasks(service, ["jiangsu_station_fault_diagnosis"])
    service.tasks["jiangsu_station_fault_diagnosis"].name = "人工修改后的名称"
    second = ensure_project_default_tasks(service, ["jiangsu_station_fault_diagnosis"])

    assert first == ["jiangsu_station_fault_diagnosis"]
    assert second == []
    assert service.tasks["jiangsu_station_fault_diagnosis"].name == "人工修改后的名称"
