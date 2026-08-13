"""Project-owned scheduled task definitions seeded at worker startup."""

from __future__ import annotations

from collections.abc import Iterable

from app.scheduled_tasks.models import ScheduledTask, TaskStep, TriggerType, WorkspaceEntry


JIANGSU_STATION_FAULT_TASK_ID = "jiangsu_station_fault_diagnosis"


def build_jiangsu_station_fault_task() -> ScheduledTask:
    return ScheduledTask(
        task_id=JIANGSU_STATION_FAULT_TASK_ID,
        name="江苏站点告警自动诊断",
        description="收到站点告警或监测异常事件后，调用站点故障诊断 Agent 分析并形成待派单方案。",
        execution_mode="station_fault_diagnosis",
        skill_id="station-alarm-diagnosis",
        trigger_type=TriggerType.EVENT,
        event_type="jiangsu.station_fault.detected",
        enabled=True,
        steps=[
            TaskStep(
                step_id="diagnose_station_fault",
                description="读取事件证据包并形成诊断与工单草案",
                agent_prompt=(
                    "处理本次江苏站点故障事件。先用 read_file 读取事件 payload 中的 "
                    "evidence_pack_path，按已加载的站点告警诊断 Skill 分类分析；仅在证据不足时调用"
                    "只读查询工具补充取证。输出故障摘要、证据时间线、按置信度排序的原因、"
                    "处置步骤、验证标准和结构化工单草案。当前阶段禁止自动执行设备控制、"
                    "关闭告警或派单；明确标记需人工审核后派单。"
                ),
                timeout_seconds=900,
                retry_on_failure=False,
            )
        ],
        created_by="project-default",
        owner_user_id="system",
        owner_username="station-fault-agent",
        owner_display_name="站点故障诊断智能体",
        tags=["江苏", "站点故障", "事件驱动", "待审核工单"],
        workspace_entry=WorkspaceEntry(enabled=True, title="站点故障诊断"),
    )


DEFAULT_TASK_FACTORIES = {
    JIANGSU_STATION_FAULT_TASK_ID: build_jiangsu_station_fault_task,
}


def ensure_project_default_tasks(service, task_ids: Iterable[str]) -> list[str]:
    """Create missing defaults only; never overwrite an operator-edited task."""
    created: list[str] = []
    for task_id in task_ids:
        factory = DEFAULT_TASK_FACTORIES.get(task_id)
        if factory is None:
            raise ValueError(f"unknown project scheduled task: {task_id}")
        if service.get_task(task_id) is None:
            service.create_task(factory())
            created.append(task_id)
    return created
