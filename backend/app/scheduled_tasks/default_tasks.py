"""Project-owned scheduled task definitions seeded at worker startup."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import ValidationError

from app.scheduled_tasks.models import ScheduledTask, TriggerType, WorkspaceEntry


JIANGSU_STATION_FAULT_TASK_ID = "jiangsu_station_fault_diagnosis"
JIANGSU_FAULT_WORK_ORDER_REVIEW_TASK_ID = "jiangsu_fault_work_order_review"
JIANGSU_SMART_EVENT_TASK_ID = "jiangsu_smart_event_ai_judgment"
JIANGSU_SMART_EVENT_LEGACY_TASK_IDS = {
    "jiangsu_smart_event_power_alarm",
    "jiangsu_smart_event_network_alarm",
    "jiangsu_smart_event_environment_alarm",
    "jiangsu_smart_event_instrument_alarm",
}
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
    "处置步骤和验证标准；调用 submit_task_review 提交人工待办，category 填故障诊断，subject_id 填事件 ID。"
    "以 checks 填写证据核验、actions 填写处置建议、sections 填写故障事实和验证标准，evidence 引用真实证据包。"
    "当前阶段禁止自动执行设备控制、关闭告警或推送工单。"
)


JIANGSU_FAULT_WORK_ORDER_REVIEW_PROMPT = (
    "仅审核小时数据有效性与剔除时段，granularity 固定 hour；5分钟数据仅作分析参考，不生成分钟级处置。"
    "记忆维护：仅积累故障表现、证据判别、边界经验及案例来源；不复制固定SOP或输出契约，"
    "不维护子分类编号。迁入的示例仅为参考，未经核验或人工确认不得升级为已确认规律。"
    "执行本次江苏省中心故障工单审核任务。先用 read_file 完整读取事件 "
    "payload.evidence_pack_path，再使用已绑定的 fault-work-order-review Skill 按证据包 "
    "sop_id 渐近读取对应 SOP 手册和输出契约，完成审核；SOP-03 必须区分未产生、未上传、"
    "暂时不可见和补传完整性。结束前只调用 "
    "submit_task_review 生成右侧人工确认归档卡片。各 SOP 按事实一致性和逻辑一致性判断，"
    "运维提交的详细工单、附件照片、截图、补传回执和影响边界属于核心材料；系统主动抓取的"
    "监测、质控、告警、动环、同城对比和传输辅助数据只做一致性核验，缺失不得机械降级为 "
    "needs_evidence；附件、截图、监测/审核标识和边界已闭环时，非实质性工单措辞瑕疵不得单独"
    "作为退回补材料理由。summary 必须用一句话给出结论、数据处置和核心原因，详细核验项"
    "仅做追溯。长期记忆和历史案例只用于形成待核验假设，不能替代本次证据；本次确认的可复用经验由任务历史学习沉淀，不回写固定 SOP。当前阶段禁止自动回写平台工单状态，禁止"
    "自动剔除或修改监测数据。"
)


def _smart_event_task_prompt(event_type_dictionary: list[str] | None = None) -> str:
    base = (
        "完成本次江苏智能事件研判。告警类型只是线索，先读证据包并核验事实，再判断最终事件类型、数据影响、等级和处置建议。"
        "按 smart-event-judgment Skill 的 output-contract.md 调用 submit_task_review 提交结构化结果。"
        "subject_id 和 event_id 均填 smart_event.event_id，category 填智能事件。"
        "提交成功才生成待办；最终文字回复不参与系统回填。"
        "有数据影响时，在 sections 中完整填写本站时序、区域背景、数据影响判断、事件与数据逻辑方向校验四段分析。"
        "存在 continuity_context 时先核验新增线索和现场反馈，提交覆盖全部已核验事实的完整结论；"
        "连续性判断写入 sections 的 same_cause 字段，不输出文本标记行。"
        "任务记忆和案例只能形成待核验假设，不能替代本次证据。"
        "不得自动关闭告警、派单、修改监测数据或执行设备控制。"
    )
    if event_type_dictionary:
        dictionary_text = "、".join(event_type_dictionary)
        base += f"\n允许的事件类型字典（event_type 必须是以下之一）：{dictionary_text}。"
    return base


def _result_field(field: str, label: str, allowed_values: list[str] | None = None) -> dict:
    return {"field": field, "label": label, "required": True, "allowed_values": allowed_values or []}


def build_jiangsu_smart_event_task(event_type_dictionary: list[str] | None = None) -> ScheduledTask:
    if event_type_dictionary is None:
        try:
            from app.services.jiangsu_smart_event import JiangsuSmartEventService
            cfg = JiangsuSmartEventService().load_config()
            event_type_dictionary = cfg.get("ai_event_type_dictionary") or None
        except Exception:  # noqa: BLE001
            pass
    from app.services.jiangsu_smart_event import AI_EVENT_TYPES
    return ScheduledTask(
        result_requirements=[
            _result_field("title", "事件名称"),
            _result_field("summary", "研判结论"),
            _result_field("sections.event_type", "AI 事件类型", event_type_dictionary or list(AI_EVENT_TYPES)),
            _result_field("sections.suggested_level", "建议等级", ["P0", "P1", "P2", "P3", "待确认"]),
            _result_field("sections.data_impact", "数据影响", ["有数据影响", "无数据影响", "待确认"]),
            _result_field("sections.compliance_explanation_result", "合规解释", ["完全解释", "部分解释", "不能解释", "无合规记录"]),
        ],
        task_id=JIANGSU_SMART_EVENT_TASK_ID,
        name="江苏智能事件AI研判",
        description="按告警线索触发智能事件 AI 研判，由 Agent 完成线索分析并定义最终事件类型。",
        execution_mode="station_fault_diagnosis",
        skill_id="smart-event-judgment",
        knowledge_base_binding="station_fault_diagnosis",
        history_learning={
            "enabled": True,
            "max_recent_cases": 5,
            "memory_char_budget": 8000,
            "active_retrieval_enabled": True,
            "active_retrieval_max_results": 5,
        },
        trigger_type=TriggerType.EVENT,
        event_type="jiangsu.smart_event.alarm",
        enabled=True,
        prompt=_smart_event_task_prompt(event_type_dictionary),
        timeout_seconds=1200,
        created_by="project-default",
        owner_user_id="system",
        owner_username="smart-event-agent",
        owner_display_name="智能事件研判智能体",
        tags=["江苏", "智能事件", "线索分析", "事件类型定义", "事件驱动", "任务专属记忆"],
        workspace_entry=WorkspaceEntry(enabled=True, title="智能事件AI研判"),
    )


def build_jiangsu_station_fault_task() -> ScheduledTask:
    return ScheduledTask(
        result_requirements=[
            _result_field("title", "故障标题"),
            _result_field("summary", "诊断结论"),
            _result_field("sections.fault_facts", "故障事实"),
            _result_field("sections.verification_standard", "验证标准"),
        ],
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
        result_requirements=[
            _result_field("title", "审核标题"),
            _result_field("summary", "审核结论"),
            _result_field("decision", "审核建议", ["approve", "reject", "needs_evidence"]),
            _result_field("sections.work_order_no", "工单号"),
            _result_field("sections.sop_id", "审核 SOP", ["SOP-01", "SOP-02", "SOP-03"]),
        ],
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
DEFAULT_TASK_FACTORIES[JIANGSU_SMART_EVENT_TASK_ID] = build_jiangsu_smart_event_task


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
    for task_id in OBSOLETE_PROJECT_DEFAULT_TASK_IDS | JIANGSU_SMART_EVENT_LEGACY_TASK_IDS:
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
                existing.result_requirements != desired.result_requirements
                or existing.prompt != desired.prompt
                or existing.knowledge_base_binding != desired.knowledge_base_binding
                or existing.skill_id != desired.skill_id
                or existing.event_type != desired.event_type
                or existing.execution_mode != desired.execution_mode
                or existing.timeout_seconds != desired.timeout_seconds
            ):
                desired.enabled = existing.enabled
                desired.model_tier = existing.model_tier
                service.update_task(desired)
    return created
