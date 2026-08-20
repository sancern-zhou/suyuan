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
        knowledge_base_binding="station_fault_diagnosis",
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
                    "只读查询工具补充取证。知识图谱只作辅助线索：最多调用一次"
                    "knowledge_graph_query（系统注入知识库 ID，depth=1、top_k<=5），不得反复检索或"
                    "因图谱查询阻塞证据诊断；无结果、超时或知识库不可用时立即继续实时告警、监测、"
                    "巡检和质控接口。输出故障摘要、证据时间线、按置信度排序的原因、"
                    "处置步骤和验证标准；随后调用 jiangsu_prepare_fault_work_order 生成待确认"
                    "工单草案（站点、设备、故障现象由系统自动解析，只需提供标题、故障描述、"
                    "处置方案、验证标准和紧急程度）。当前阶段禁止自动执行设备控制或关闭告警；"
                    "工单需人工在右侧面板确认后才推送，不得声称已创建工单或已派单。"
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
    """Create missing defaults; never overwrite an operator-edited task.

    Tasks still owned by ``project-default`` are refreshed in place when the
    seeded definition (e.g. the agent prompt) changes, so prompt updates ship
    with the code without touching operator copies.
    """
    created: list[str] = []
    for task_id in task_ids:
        factory = DEFAULT_TASK_FACTORIES.get(task_id)
        if factory is None:
            raise ValueError(f"unknown project scheduled task: {task_id}")
        existing = service.get_task(task_id)
        if existing is None:
            service.create_task(factory())
            created.append(task_id)
        elif existing.created_by == "project-default":
            desired = factory()
            if (
                existing.steps != desired.steps
                or existing.knowledge_base_binding != desired.knowledge_base_binding
            ):
                desired.enabled = existing.enabled
                service.update_task(desired)
    return created
