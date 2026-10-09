"""
create_scheduled_task工具
创建定时任务：支持显式参数直传完整配置，也支持自然语言解析兜底
"""
import json
import structlog
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.tools.base import LLMTool, ToolCategory
from app.scheduled_tasks import (
    ScheduledTask,
    ScheduleType,
    get_scheduled_task_service
)
from app.scheduled_tasks.models.task import TriggerType
from app.services.llm_service import LLMService

logger = structlog.get_logger()


OPS_WEEKLY_AUDIT_EXECUTION_MODE = "ops"


OPS_WEEKLY_AUDIT_TASK_PROMPT = """这是每周运维工单审核定时任务。

【审核窗口配置】
按执行指令中配置的时间字段、起止时间和工单状态执行；周期周审默认使用技能规定的 weekly_created 窗口。

【执行要求】
1. 作为当前运维 Agent 直接完整执行任务，不调用 call_sub_agent，不要停在计划确认或等待确认节点。
2. 严格按 ops_work_order_audit 技能调用 ops_audit_fetch_dataset 取数，并将其返回的 data.dataset_path 原值传给 ops_audit_run_rules；定时执行的审核产物由工具按 execution_id 自动隔离，不要指定 output_dir。
3. ops_audit_run_rules 会直接生成 final_issue_list_path 和 report_input_path，并返回 report_ready；不得再调用子 Agent 做全量主观审核，也不得调用已移除的 ops_audit_submit_review。
4. 返回 final_issue_list_path、report_input_path、report_ready、pending_review_count、pending_semantic_review_count 和关键统计。
5. 如果 report_ready=true，优先读取 ops_audit_run_rules 返回的 report_context_path（它是已注册的精简报告上下文）；如需追溯再读取本轮 report_input_path。按审核报告规范生成并交付 HTML/Word 报告；问题描述只使用条目的 display_evidence。report_input 已经是报告专用投影，禁止读取或展开 evidence_facts，禁止用 execute_python/read_file/list_directory 重建、筛选或复制 report_input，也不要自行生成 report_input_filtered 文件。
6. 如果 report_ready=false，交付 report_input_path 中的 pending_review_items、pending_semantic_reviews 及原因，不生成正式报告，也不等待在线确认。"""


EXECUTION_MODES = ("assistant", "expert", "ops", "query", "social", "custom", "workflow")
MODEL_TIERS = ("auto", "flash", "pro")
TRIGGER_TYPES = ("schedule", "event")


class CreateScheduledTaskTool(LLMTool):
    """创建定时任务工具"""

    def __init__(self):
        function_schema = {
            "name": "create_scheduled_task",
            "description": (
                "创建定时任务。两种用法：\n"
                "1. 显式传参：已与用户核对好配置时，直接传结构化参数（推荐，不走LLM解析）；\n"
                "2. 自然语言：只传 user_request，由工具解析生成配置。\n"
                "两类参数可混用，显式参数优先。\n\n"
                "调度类型（schedule_type，schedule 触发时必填）共11种：\n"
                "预设：daily_8am（每天8点）/ every_2h / every_30min / monthly_1st_7am / weekly_monday_8am\n"
                "灵活：once（需 run_at）/ interval（需 interval_minutes）/ daily_custom（需 hour、minute）/ "
                "weekly_custom（需 day_of_week、hour、minute）/ monthly_custom（需 day_of_month、hour、minute）/ "
                "quarterly_custom（需 day_of_month、hour、minute）\n\n"
                "执行模式（execution_mode）：assistant/expert/ops/query/social/custom/workflow\n"
                "- custom 必须传 tool_names；workflow 必须传 workflow_name\n"
                "- 事件触发任务需 trigger_type=event 且传 event_type（事件任务无调度周期，由业务事件触发）\n"
                "- broadcast_enabled=true 时必须传 target_user_ids\n"
                "- 可选绑定：skill_id（已发布技能）、knowledge_base_binding（项目知识库键）、report_type\n"
                "- 任务自动归属当前登录用户（服务端解析，无需传参），非管理员用户可在定时任务页面查看并管理自己创建的任务"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_request": {
                        "type": "string",
                        "description": "自然语言任务描述。未传显式参数的字段由它解析补全；已传显式参数时可省略"
                    },
                    "name": {"type": "string", "description": "任务名称（10字以内）"},
                    "description": {"type": "string", "description": "任务描述（说明任务目的）"},
                    "prompt": {"type": "string", "description": "发送给 Agent 的完整任务提示词（详细、具体、可独立执行）"},
                    "execution_mode": {
                        "type": "string",
                        "enum": list(EXECUTION_MODES),
                        "description": "执行模式，默认 expert"
                    },
                    "model_tier": {
                        "type": "string",
                        "enum": list(MODEL_TIERS),
                        "description": "模型档位，默认 auto"
                    },
                    "tool_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "custom 模式固定使用的工具名称列表（仅 custom 模式有效）"
                    },
                    "workflow_name": {
                        "type": "string",
                        "description": "workflow 模式执行的工作流名称（仅 workflow 模式有效）"
                    },
                    "workflow_args": {
                        "type": "object",
                        "description": "workflow 模式的固定输入参数（仅 workflow 模式有效）"
                    },
                    "skill_id": {
                        "type": "string",
                        "description": "执行时注入的已发布技能ID（可先 list_skills 查询）"
                    },
                    "knowledge_base_binding": {
                        "type": "string",
                        "description": "项目知识库绑定键"
                    },
                    "report_type": {"type": "string", "description": "报告成果类型"},
                    "trigger_type": {
                        "type": "string",
                        "enum": list(TRIGGER_TYPES),
                        "description": "触发方式：schedule（定时）/ event（事件），默认 schedule"
                    },
                    "event_type": {"type": "string", "description": "事件类型（trigger_type=event 时必填）"},
                    "event_filters": {
                        "type": "object",
                        "description": "事件属性过滤条件（可选）"
                    },
                    "schedule_type": {"type": "string", "description": "调度类型（11种，见工具描述）"},
                    "run_at": {
                        "type": "string",
                        "description": "一次性任务执行时间，格式 \"2026-02-13 14:30:00\"（schedule_type=once 必填）"
                    },
                    "interval_minutes": {"type": "integer", "description": "间隔分钟数（schedule_type=interval 必填）"},
                    "hour": {"type": "integer", "description": "执行小时 0-23"},
                    "minute": {"type": "integer", "description": "执行分钟 0-59"},
                    "day_of_week": {"type": "integer", "description": "每周星期 0=周一…6=周日（weekly_custom 必填）"},
                    "day_of_month": {"type": "integer", "description": "每月日期 1-31（monthly_custom/quarterly_custom 必填）"},
                    "timeout_seconds": {"type": "integer", "description": "任务总超时时间（秒，默认1800）"},
                    "broadcast_enabled": {
                        "type": "boolean",
                        "description": "是否向社交用户广播执行结果；为 true 时必须传 target_user_ids"
                    },
                    "target_user_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "广播目标社交用户ID列表（broadcast_enabled=true 时必填）"
                    },
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "标签列表"}
                }
            }
        }
        super().__init__(
            name="create_scheduled_task",
            description="创建定时任务（支持显式完整配置或自然语言解析）",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="2.1.0",
            requires_context=True
        )

    async def execute(
        self,
        context: Any = None,
        user_request: Optional[str] = None,
        **params
    ) -> Dict[str, Any]:
        """执行工具：显式参数优先，缺失字段由自然语言解析补全"""
        try:
            explicit = {
                key: value for key, value in params.items()
                if value not in (None, [], {})
            }

            config: Dict[str, Any] = dict(explicit)
            trigger_type = str(config.get("trigger_type") or "schedule")
            core_complete = (
                all(config.get(field) for field in ("name", "description", "prompt"))
                and (config.get("event_type") if trigger_type == "event" else config.get("schedule_type"))
            )
            if user_request and user_request.strip() and not core_complete:
                parsed = await self._parse_user_request(user_request.strip())
                if parsed is None and not explicit:
                    return {
                        "success": False,
                        "data": {"error": "无法解析任务配置"},
                        "summary": "任务配置解析失败，请提供更清晰的描述或显式传入任务参数"
                    }
                if parsed:
                    config = {**parsed, **explicit}

            missing = [field for field in ("name", "description", "prompt") if not config.get(field)]
            if trigger_type == "event":
                if not config.get("event_type"):
                    missing.append("event_type")
            elif not config.get("schedule_type"):
                missing.append("schedule_type")
            if missing:
                return {
                    "success": False,
                    "data": {
                        "error": f"缺少必要字段：{', '.join(missing)}",
                        "missing_fields": missing,
                    },
                    "summary": "任务配置不完整，请补充缺失字段后重试"
                }

            service = get_scheduled_task_service()

            import uuid
            task_id = f"task_{uuid.uuid4().hex[:8]}"

            # 构建任务对象：一个任务就是一次完整的 Agent 执行，由 Agent 自行规划。
            task_kwargs = self._build_task_kwargs(task_id, config)
            self._apply_advanced_fields(task_kwargs, config)
            owner = await self._resolve_session_owner(context)
            if owner:
                task_kwargs.update(owner)
            task = ScheduledTask(**task_kwargs)

            created_task = service.create_task(task)

            return {
                "success": True,
                "data": {
                    "task_id": created_task.task_id,
                    "name": created_task.name,
                    "description": created_task.description,
                    "execution_mode": created_task.execution_mode,
                    "trigger_type": created_task.trigger_type.value,
                    "schedule_type": created_task.schedule_type.value if created_task.schedule_type else None,
                    "event_type": created_task.event_type,
                    "skill_id": created_task.skill_id,
                    "broadcast_enabled": created_task.broadcast_enabled,
                    "timeout_seconds": created_task.timeout_seconds,
                    "next_run_at": str(created_task.next_run_at) if created_task.next_run_at else None
                },
                "summary": (
                    f"已创建定时任务：{created_task.name}\n"
                    f"触发方式：{created_task.trigger_type.value}"
                    + (f"（{created_task.schedule_type.value}）" if created_task.schedule_type else f"（{created_task.event_type}）")
                    + f"\n执行模式：{created_task.execution_mode}\n"
                    f"超时时间：{created_task.timeout_seconds}秒\n"
                    + (f"归属用户：{created_task.owner_display_name}（可在定时任务页面查看）\n" if created_task.owner_user_id != "system" else "")
                    + f"任务ID：{created_task.task_id}"
                )
            }

        except Exception as e:
            logger.error(f"Failed to create scheduled task: {e}", exc_info=True)
            return {
                "success": False,
                "data": {"error": str(e)},
                "summary": f"创建定时任务失败：{str(e)}"
            }

    def _build_task_kwargs(self, task_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """将配置转换为 ScheduledTask 构造参数（类型解析 + 字段校验交给 Pydantic）"""
        task_kwargs: Dict[str, Any] = {
            "task_id": task_id,
            "name": config["name"],
            "description": config["description"],
            "execution_mode": config.get("execution_mode", "expert"),
            "model_tier": config.get("model_tier", "auto"),
            "prompt": config["prompt"],
            "timeout_seconds": config.get("timeout_seconds") or 1800,
            "tags": config.get("tags", []),
        }

        if str(config.get("trigger_type") or "schedule") == "event":
            task_kwargs["trigger_type"] = TriggerType.EVENT
            task_kwargs["event_type"] = str(config["event_type"]).strip()
            if config.get("event_filters"):
                task_kwargs["event_filters"] = config["event_filters"]
            return task_kwargs

        task_kwargs["schedule_type"] = ScheduleType(config["schedule_type"])

        schedule_type = config["schedule_type"]
        if schedule_type == "once":
            task_kwargs["run_at"] = self._parse_run_at(config["run_at"])
        elif schedule_type == "interval":
            task_kwargs["interval_minutes"] = int(config["interval_minutes"])
        elif schedule_type == "daily_custom":
            task_kwargs["hour"] = int(config["hour"])
            task_kwargs["minute"] = int(config["minute"])
        elif schedule_type == "weekly_custom":
            task_kwargs["day_of_week"] = int(config["day_of_week"])
            task_kwargs["hour"] = int(config["hour"])
            task_kwargs["minute"] = int(config["minute"])
        elif schedule_type in ("monthly_custom", "quarterly_custom"):
            task_kwargs["day_of_month"] = int(config["day_of_month"])
            task_kwargs["hour"] = int(config["hour"])
            task_kwargs["minute"] = int(config["minute"])

        return task_kwargs

    @staticmethod
    def _parse_run_at(value: Any) -> datetime:
        """解析一次性任务的执行时间（兼容 "YYYY-MM-DD HH:MM:SS" 与 ISO 格式）"""
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        try:
            return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.fromisoformat(text)

    def _apply_advanced_fields(self, task_kwargs: Dict[str, Any], config: Dict[str, Any]) -> None:
        """透传高级配置字段（绑定、模式专属、广播）"""
        for key in ("skill_id", "knowledge_base_binding", "report_type"):
            value = config.get(key)
            if value:
                task_kwargs[key] = str(value).strip()

        execution_mode = task_kwargs.get("execution_mode")
        if execution_mode == "custom" and config.get("tool_names"):
            task_kwargs["tool_names"] = [str(name).strip() for name in config["tool_names"] if str(name).strip()]
        if execution_mode == "workflow":
            if config.get("workflow_name"):
                task_kwargs["workflow_name"] = str(config["workflow_name"]).strip()
            if config.get("workflow_args"):
                task_kwargs["workflow_args"] = config["workflow_args"]

        if config.get("broadcast_enabled"):
            task_kwargs["broadcast_enabled"] = True
            task_kwargs["target_user_ids"] = [str(uid).strip() for uid in (config.get("target_user_ids") or [])]

    async def _resolve_session_owner(self, context: Any) -> Optional[Dict[str, str]]:
        """把任务归属到当前会话用户，非管理员才能在定时任务页看到自己创建的任务。

        会话未编目（系统执行、历史会话）时返回 None，保持 system 默认归属。
        """
        session_id = getattr(context, "session_id", None)
        if not session_id:
            return None
        try:
            from app.conversations.dependencies import get_conversation_catalog
            record = await get_conversation_catalog().find(str(session_id))
        except Exception as e:
            logger.warning(
                "scheduled_task_owner_lookup_failed",
                session_id=str(session_id),
                error=str(e),
            )
            return None
        if record is None or not record.owner_user_id or record.owner_user_id == "system":
            return None
        return {
            "owner_user_id": record.owner_user_id,
            "owner_username": record.owner_username or record.owner_user_id,
            "owner_display_name": record.owner_display_name or record.owner_username or record.owner_user_id,
        }

    async def _parse_user_request(self, user_request: str) -> Optional[Dict[str, Any]]:
        """使用LLM解析用户请求（自然语言兜底路径）"""
        llm_service = LLMService()

        prompt = f"""你是一个定时任务配置助手。请根据用户的自然语言请求，生成定时任务配置。

用户请求：{user_request}
当前时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

⚠️ 重要提示：
1. 如果用户说"N分钟后"、"N小时后"，请基于当前时间计算具体的执行时间
2. 文档路径中的日期（如"2025年7月8日臭氧垂直.docx"）仅用于识别文档，与任务执行时间无关
3. 只有用户明确指定"明天"、"后天"或具体日期时，才使用那个日期

请分析用户请求，生成JSON格式的任务配置。配置必须包含以下字段：

1. name: 任务名称（简短，10字以内）
2. description: 任务描述（详细说明任务目的）
   模型档位 model_tier: 仅支持 "auto"、"flash"、"pro"；用户未指定时为 "auto"。
3. execution_mode: 执行模式，支持 "assistant"、"expert"、"ops"、"query"、"social"、"custom"、"workflow"
   - 广播、通知、社交文案生成任务优先使用 "assistant"
   - 数据分析、专业推理任务优先使用 "expert"
   - 运维工单审核、运维表单审核、工单复核任务优先使用 "ops"，由当前运维 Agent 直接执行，不调用子 Agent
   - custom 模式必须额外提供 tool_names（工具名称列表）；workflow 模式必须额外提供 workflow_name
4. schedule_type: 调度类型，支持以下类型：
   预设类型：
   - "daily_8am": 每天早上8点
   - "every_2h": 每2小时
   - "every_30min": 每30分钟
   - "monthly_1st_7am": 每月1日早上7点
   - "weekly_monday_8am": 每周一早上8点

   灵活类型：
   - "once": 一次性任务（需额外提供run_at字段，格式："2026-02-13 14:30:00"）
   - "interval": 自定义间隔（需额外提供interval_minutes字段，如5表示每5分钟）
   - "daily_custom": 每天自定义时间（需额外提供hour和minute字段，如hour:9, minute:30表示每天9:30）
   - "weekly_custom": 每周自定义时间（需额外提供day_of_week、hour和minute字段；day_of_week使用0=周一…6=周日）
   - "monthly_custom": 每月自定义日期（需额外提供day_of_month、hour和minute字段，day_of_month为1-31）
   - "quarterly_custom": 每季度首月自定义日期（需额外提供day_of_month、hour和minute字段）

5. 灵活调度参数（根据schedule_type选择）：
   - run_at: 一次性任务的执行时间（schedule_type=once时必填，格式："2026-02-13 14:30:00"）
   - interval_minutes: 间隔分钟数（schedule_type=interval时必填，如5表示每5分钟）
   - hour: 执行小时（daily_custom/weekly_custom/monthly_custom/quarterly_custom 按需提供，0-23）
   - minute: 执行分钟（同上，0-59）
   - day_of_week: 每周执行的星期（schedule_type=weekly_custom时必填，0=周一，6=周日）
   - day_of_month: 每月执行的日期（monthly_custom/quarterly_custom时必填，1-31）

6. prompt: 发送给Agent的完整任务提示词（必须包含，详细、具体）
7. timeout_seconds: 整个任务的总超时时间（秒，默认1800）

8. tags: 标签列表（可选）

9. 可选高级字段（仅在用户明确要求时输出）：
   - skill_id: 绑定的已发布技能ID
   - knowledge_base_binding: 项目知识库绑定键
   - report_type: 报告成果类型
   - broadcast_enabled: 是否广播执行结果（true 时必须同时输出 target_user_ids 社交用户ID列表，否则任务无效）

示例1（预设类型）：
{{
  "name": "每日O3污染分析",
  "description": "每天早上8点分析广州昨天的O3污染情况",
  "execution_mode": "expert",
  "schedule_type": "daily_8am",
  "prompt": "查询广州昨天的O3浓度数据，包括小时值和日均值，并生成污染分析报告",
  "timeout_seconds": 1800,
  "tags": ["O3", "广州", "日报"]
}}

示例2（一次性任务）：
{{
  "name": "臭氧报告分析",
  "description": "分析指定文档的臭氧数据",
  "execution_mode": "expert",
  "schedule_type": "once",
  "run_at": "2026-02-13 14:30:00",
  "prompt": "读取指定文档的表格内容并分析",
  "timeout_seconds": 1800,
  "tags": ["臭氧", "报告"]
}}

示例3（自定义间隔）：
{{
  "name": "PM2.5监测",
  "description": "每5分钟检查PM2.5浓度",
  "schedule_type": "interval",
  "interval_minutes": 5,
  "prompt": "查询最新的PM2.5浓度数据并简要分析变化趋势",
  "timeout_seconds": 600,
  "tags": ["PM2.5", "监测"]
}}

示例4（每月自定义日期）：
{{
  "name": "月度质量报告",
  "description": "每月5日上午9点生成月度报告",
  "execution_mode": "report",
  "schedule_type": "monthly_custom",
  "day_of_month": 5,
  "hour": 9,
  "minute": 0,
  "prompt": "汇总上月监测数据生成月度分析报告",
  "timeout_seconds": 1800,
  "tags": ["月报"]
}}

示例5（广播任务）：
{{
  "name": "每日广播提醒",
  "description": "每天上午9点向社交用户广播当天提醒内容",
  "execution_mode": "assistant",
  "schedule_type": "daily_custom",
  "hour": 9,
  "minute": 0,
  "broadcast_enabled": true,
  "target_user_ids": ["user_001"],
  "prompt": "根据任务描述生成适合广播给社交用户的简短内容，然后调用 broadcast_social_users 工具发送。",
  "timeout_seconds": 600,
  "tags": ["broadcast", "social"]
}}

示例6（每周运维工单审核）：
{{
  "name": "工单周审",
  "description": "每周五上午9点审核运维工单",
  "execution_mode": {json.dumps(OPS_WEEKLY_AUDIT_EXECUTION_MODE)},
  "schedule_type": "weekly_custom",
  "day_of_week": 4,
  "hour": 9,
  "minute": 0,
  "prompt": {json.dumps(OPS_WEEKLY_AUDIT_TASK_PROMPT, ensure_ascii=False)},
  "timeout_seconds": 1800,
  "tags": ["运维", "工单审核", "周审"]
}}

请直接返回JSON，不要包含任何其他文字。"""

        try:
            # ✅ 定时任务配置LLM调用上下文日志
            logger.info(
                "scheduled_task_config_llm_call",
                user_request=user_request[:100] if len(user_request) > 100 else user_request,
                prompt_length=len(prompt),
            )

            response = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000
            )

            content = response

            # 提取JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            # 解析JSON
            config = json.loads(content)

            # 验证必需字段
            required_fields = ["name", "description", "schedule_type"]
            if not all(field in config for field in required_fields):
                logger.error(f"Missing required fields in config: {config}")
                return None
            if not config.get("prompt"):
                logger.error(f"Missing prompt in config: {config}")
                return None

            # 验证schedule_type
            valid_schedules = {item.value for item in ScheduleType}
            if config["schedule_type"] not in valid_schedules:
                logger.error(f"Invalid schedule_type: {config['schedule_type']}")
                return None

            # 验证灵活调度参数
            schedule_type = config["schedule_type"]
            if schedule_type == "once" and "run_at" not in config:
                logger.error("schedule_type=once but run_at is missing")
                return None
            if schedule_type == "interval" and "interval_minutes" not in config:
                logger.error("schedule_type=interval but interval_minutes is missing")
                return None
            if schedule_type == "daily_custom" and ("hour" not in config or "minute" not in config):
                logger.error("schedule_type=daily_custom but hour/minute is missing")
                return None
            if schedule_type == "weekly_custom":
                if "day_of_week" not in config or "hour" not in config or "minute" not in config:
                    logger.error("schedule_type=weekly_custom but day_of_week/hour/minute is missing")
                    return None
                if not 0 <= int(config["day_of_week"]) <= 6:
                    logger.error("schedule_type=weekly_custom but day_of_week is out of range")
                    return None
            if schedule_type in ("monthly_custom", "quarterly_custom"):
                if "day_of_month" not in config or "hour" not in config or "minute" not in config:
                    logger.error(f"schedule_type={schedule_type} but day_of_month/hour/minute is missing")
                    return None
                if not 1 <= int(config["day_of_month"]) <= 31:
                    logger.error(f"schedule_type={schedule_type} but day_of_month is out of range")
                    return None

            return config

        except Exception as e:
            logger.error(f"Failed to parse user request: {e}", exc_info=True)
            return None


# 工具实例
create_scheduled_task_tool = CreateScheduledTaskTool()
