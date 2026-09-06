"""Project-owned scheduled task definitions seeded at worker startup."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import ValidationError

from app.scheduled_tasks.models import ScheduledTask, TriggerType, WorkspaceEntry


JIANGSU_STATION_FAULT_TASK_ID = "jiangsu_station_fault_diagnosis"
JIANGSU_FAULT_WORK_ORDER_REVIEW_TASK_ID = "jiangsu_fault_work_order_review"
OBSOLETE_PROJECT_DEFAULT_TASK_IDS = {
    "jiangsu_fault_work_order_qc_review",
    "jiangsu_fault_work_order_env_review",
}


JIANGSU_STATION_FAULT_PROMPT = (
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
)


JIANGSU_FAULT_WORK_ORDER_REVIEW_PROMPT = (
    "仅审核小时数据有效性与剔除时段，granularity 固定 hour；5分钟数据仅作分析参考，不生成分钟级处置。"
    "记忆维护：仅积累故障表现、证据判别、边界经验及案例来源；不复制固定SOP或输出契约，"
    "不维护子分类编号。迁入的示例仅为参考，未经核验或人工确认不得升级为已确认规律。"
    "执行本次江苏省中心故障工单审核任务。先用 read_file 完整读取事件 "
    "payload.evidence_pack_path，再使用已绑定的 fault-work-order-review Skill 按证据包 "
    "sop_id 渐近读取对应 SOP 手册和输出契约，完成审核；SOP-03 必须区分未产生、未上传、"
    "暂时不可见和补传完整性。结束前只调用 "
    "jiangsu_submit_fault_work_order_review 生成右侧人工确认归档卡片。各 SOP 按事实一致性和逻辑一致性判断，"
    "运维提交的详细工单、附件照片、截图、补传回执和影响边界属于核心材料；系统主动抓取的"
    "监测、质控、告警、动环、同城对比和传输辅助数据只做一致性核验，缺失不得机械降级为 "
    "needs_evidence；附件、截图、监测/审核标识和边界已闭环时，非实质性工单措辞瑕疵不得单独"
    "作为退回补材料理由。review_summary 必须用一句话给出结论、数据处置和核心原因，详细核验项"
    "仅做追溯。长期记忆和历史案例只用于形成待核验假设，不能替代本次证据；本次确认的可复用经验由任务历史学习沉淀，不回写固定 SOP。当前阶段禁止自动回写平台工单状态，禁止"
    "自动剔除或修改监测数据。"
)


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
        prompt=JIANGSU_STATION_FAULT_PROMPT,
        timeout_seconds=900,
        created_by="project-default",
        owner_user_id="system",
        owner_username="station-fault-agent",
        owner_display_name="站点故障诊断智能体",
        tags=["江苏", "站点故障", "事件驱动", "待审核工单"],
        workspace_entry=WorkspaceEntry(enabled=True, title="站点故障诊断"),
    )


def build_jiangsu_fault_work_order_review_task() -> ScheduledTask:
    return ScheduledTask(
        task_id=JIANGSU_FAULT_WORK_ORDER_REVIEW_TASK_ID,
        name="江苏故障工单审核",
        description="收到省中心故障工单审核事件后，按证据包 SOP 分支完成审核并形成待人工归档结论。",
        execution_mode="ops",
        skill_id="fault-work-order-review",
        history_learning={"enabled": True, "memory_char_budget": 8000},
        trigger_type=TriggerType.EVENT,
        event_type="jiangsu.fault_work_order.review_requested",
        enabled=True,
        prompt=JIANGSU_FAULT_WORK_ORDER_REVIEW_PROMPT,
        timeout_seconds=1200,
        created_by="project-default",
        owner_user_id="system",
        owner_username="work-order-review-agent",
        owner_display_name="故障工单审核智能体",
        tags=["江苏", "故障工单", "SOP审核", "事件驱动"],
        workspace_entry=WorkspaceEntry(enabled=True, title="故障工单审核"),
    )


DEFAULT_TASK_FACTORIES = {
    JIANGSU_STATION_FAULT_TASK_ID: build_jiangsu_station_fault_task,
    JIANGSU_FAULT_WORK_ORDER_REVIEW_TASK_ID: build_jiangsu_fault_work_order_review_task,
}


def _raw_task_enabled(service, task_id: str) -> bool | None:
    raw_tasks = None
    storage = getattr(service, "task_storage", None)
    reader = getattr(storage, "_read_tasks", None)
    if callable(reader):
        raw_tasks = reader()
    elif hasattr(service, "tasks"):
        tasks = getattr(service, "tasks")
        raw_tasks = list(tasks.values()) if isinstance(tasks, dict) else tasks
    if not isinstance(raw_tasks, list):
        return None
    for raw in raw_tasks:
        if isinstance(raw, dict) and raw.get("task_id") == task_id and "enabled" in raw:
            return bool(raw.get("enabled"))
        if getattr(raw, "task_id", None) == task_id and hasattr(raw, "enabled"):
            return bool(getattr(raw, "enabled"))
    return None


def _delete_obsolete_project_default_tasks(service) -> list[str]:
    deleted: list[str] = []
    for task_id in OBSOLETE_PROJECT_DEFAULT_TASK_IDS:
        delete_task = getattr(service, "delete_task", None)
        if callable(delete_task):
            if delete_task(task_id):
                deleted.append(task_id)
            continue
        tasks = getattr(service, "tasks", None)
        if isinstance(tasks, dict) and task_id in tasks:
            del tasks[task_id]
            deleted.append(task_id)
    return deleted


def ensure_project_default_tasks(service, task_ids: Iterable[str]) -> list[str]:
    """Create missing defaults; never overwrite an operator-edited task.

    Tasks still owned by ``project-default`` are refreshed in place when the
    seeded definition (e.g. the agent prompt) changes, so prompt updates ship
    with the code without touching operator copies.
    """
    requested_ids = list(task_ids)
    created: list[str] = []
    if JIANGSU_FAULT_WORK_ORDER_REVIEW_TASK_ID in requested_ids:
        _delete_obsolete_project_default_tasks(service)
    for task_id in requested_ids:
        factory = DEFAULT_TASK_FACTORIES.get(task_id)
        if factory is None:
            raise ValueError(f"unknown project scheduled task: {task_id}")
        try:
            existing = service.get_task(task_id)
        except ValidationError:
            desired = factory()
            raw_enabled = _raw_task_enabled(service, task_id)
            if raw_enabled is not None:
                desired.enabled = raw_enabled
            service.update_task(desired)
            continue
        if existing is None:
            service.create_task(factory())
            created.append(task_id)
        elif existing.created_by == "project-default":
            desired = factory()
            if (
                existing.prompt != desired.prompt
                or existing.knowledge_base_binding != desired.knowledge_base_binding
                or existing.skill_id != desired.skill_id
                or existing.event_type != desired.event_type
                or existing.execution_mode != desired.execution_mode
                or existing.timeout_seconds != desired.timeout_seconds
            ):
                desired.enabled = existing.enabled
                service.update_task(desired)
    return created
