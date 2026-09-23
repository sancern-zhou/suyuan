"""
调用子Agent的工具（双向通用）

功能：
- 助手Agent可以调用其他Agent处理任务
- Social Agent可以调用其他Agent进行数据查询和报告生成

Session支持：
- 支持session_id参数实现连续对话
- 不传session_id则创建新session并返回
- 传入session_id则继续已有对话
"""

from contextlib import nullcontext
import json
from typing import Dict, Any, Literal, Optional, List
import structlog
from datetime import datetime
import uuid

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.agent.session.session_manager import get_session_manager
from app.agent.session.models import Session
from app.agent.session.workspace_routing import (
    build_workspace_approval_request,
    build_workspace_promotion,
)
from app.agent.selection_context import load_skill_selection
from app.agent.prompts.tool_registry import get_tools_by_mode
from app.agent.workflow.capabilities import build_child_capability_policy
from app.agent.workflow.resource_handoff import (
    import_workflow_handles,
    result_resource_declarations,
    stored_resource_ref,
)
from app.agent.workflow.target_mode_contract import (
    build_target_mode_contract,
    target_mode_values,
)
from app.agent.workflow.protocol import (
    build_result_envelope,
    extract_structured_result,
    validate_result_schema,
)
from app.agent.workflow.runtime import WorkflowRuntime
from app.agent.workflow.actors import child_actor_registry
from app.utils.path_config import (
    format_agent_path,
    get_data_registry,
    is_path_within,
    resolve_agent_path,
)

logger = structlog.get_logger()

# 获取全局session管理器
session_manager = get_session_manager()

# ⚠️ 支持多种模式：assistant, query, report, social, chart, expert, ops
AgentMode = Literal["assistant", "query", "report", "social", "chart", "expert", "ops", "board", "ppt", "knowledge"]


class CallSubAgentTool(LLMTool):
    """
    调用子Agent的工具（双向通用）

    用法：
    - Social Agent调用Query Agent：call_sub_agent(target_mode="query", ...)
    - 助手Agent调用其他Agent：call_sub_agent(target_mode="...", ...)
    """

    def __init__(
        self,
        memory_manager=None,  # ⚠️ 已弃用：不再传递 memory_manager 给子Agent
        llm_planner=None,
        tool_executor=None
    ):
        # 定义 function_schema（参考Hermes设计：分离goal和context）
        function_schema = {
            "name": "call_sub_agent",
            "description": (
                "调用另一个 Agent 模式执行任务；继续旧会话需传 session_id。"
                "默认不会自动复用旧的 assistant 子会话。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_mode": {
                        "type": "string",
                        "enum": target_mode_values(),
                        "description": "目标 Agent 模式。能力与工具边界：" + build_target_mode_contract(),
                    },
                    # ✅ 新设计：goal（必需）- 原始任务描述
                    "goal": {
                        "type": "string",
                        "description": "任务目标，保留具体参数。"
                    },
                    # ✅ 新设计：context_str（可选）- 补充上下文
                    "context_str": {
                        "type": "string",
                        "description": "补充上下文。"
                    },
                    "context": {
                        "type": "string",
                        "description": "补充上下文（兼容旧调用，等同于 context_str）。"
                    },
                    # ✅ 新设计：workspace_path（可选）- 工作目录
                    "workspace_path": {
                        "type": "string",
                        "description": "工作目录路径，可选"
                    },
                    # ⚠️ 向后兼容：保留旧参数名
                    "task_description": {
                        "type": "string",
                        "description": "向后兼容，等同于goal"
                    },
                    "context_supplement": {
                        "type": "string",
                        "description": "向后兼容，等同于context_str"
                    },
                    "skill_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 1,
                        "description": "传递给子 Agent 的显式技能 ID，最多一个。"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "子Agent会话ID；只有显式传入 session_id 才会复用旧会话。"
                    },
                    "force_new_session": {
                        "type": "boolean",
                        "description": "是否强制创建新会话；assistant 子会话未传 session_id 时默认已创建新会话。"
                    },
                    "promote_to_workspace": {
                        "type": "boolean",
                        "description": "任务需要持续多轮编辑时，将子Agent会话升级为当前工作空间。适用于 board、ppt、report。"
                    },
                    "_force_isolated_session": {
                        "type": "boolean",
                        "description": "[内部使用] 并发调用时强制session隔离，避免多个子Agent共享同一个session"
                    },
                    "task_id": {
                        "type": "string",
                        "description": "本次工作流任务ID，用于结果追踪和恢复。"
                    },
                    "parent_task_id": {
                        "type": "string",
                        "description": "父任务ID，用于建立任务血缘。"
                    },
                    "task_contract": {
                        "type": "object",
                        "description": "结构化任务协议；子Agent必须按其中的范围、问题和交付要求执行。"
                    },
                    "result_schema": {
                        "type": "object",
                        "description": "子Agent最终结果的JSON Schema子集。提供后会解析并校验结构化结果。"
                    },
                    "repair_attempts": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 2,
                        "description": "结构化结果校验失败时的自动修复轮数，默认1，最多2轮。"
                    },
                    "workflow_run_id": {
                        "type": "string",
                        "description": "可选的运行实例ID；用于恢复同一个工作流运行。"
                    },
                    "allowed_tool_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "子Agent允许使用的工具白名单。"
                    },
                    "denied_tool_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "子Agent禁止使用的工具黑名单。"
                    },
                    "allow_child_delegation": {
                        "type": "boolean",
                        "description": "是否允许子Agent继续调用子Agent，默认允许但仍受嵌套深度限制。"
                    },
                    "deadline_at": {
                        "type": "string",
                        "description": "可选的工作流截止时间，ISO-8601 格式；超时后任务进入 cancelled。"
                    }
                },
                "required": ["target_mode"]  # ✅ 改为：target_mode必需，goal和task_description二选一
            }
        }

        # 初始化基类
        super().__init__(
            name="call_sub_agent",
            description="调用另一个Agent模式作为子Agent执行任务",
            category=ToolCategory.QUERY,  # 归类为查询工具
            function_schema=function_schema,
            version="1.0.0",
            requires_context=True  # ✅ 需要context来获取依赖
        )

        self.memory_manager = memory_manager
        self.llm_planner = llm_planner
        self.tool_executor = tool_executor

    async def execute(
        self,
        context: Optional[Any] = None,  # ✅ ExecutionContext（放在第一位）
        target_mode: AgentMode = None,
        goal: Optional[str] = None,  # ✅ 新参数：任务目标
        task_description: Optional[str] = None,  # ⚠️ 向后兼容
        context_str: Optional[str] = None,  # ✅ 新参数：补充上下文
        context_supplement: Optional[str] = None,  # ⚠️ 向后兼容
        context_text: Optional[str] = None,  # ⚠️ 兼容 schema 中的 context 字段
        skill_ids: Optional[List[str]] = None,
        workspace_path: Optional[str] = None,  # ✅ 新参数：工作目录
        session_id: Optional[str] = None,
        force_new_session: bool = False,
        promote_to_workspace: bool = False,
        _force_isolated_session: bool = False,  # ⚠️ 内部使用：并发时强制隔离
        task_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        task_contract: Optional[Dict[str, Any]] = None,
        result_schema: Optional[Dict[str, Any]] = None,
        repair_attempts: int = 1,
        workflow_run_id: Optional[str] = None,
        allowed_tool_names: Optional[List[str]] = None,
        denied_tool_names: Optional[List[str]] = None,
        allow_child_delegation: bool = True,
        deadline_at: Optional[str] = None,
        _upstream_handles: Optional[List[Dict[str, Any]]] = None,
        **kwargs  # ✅ 捕获额外参数
    ) -> Dict[str, Any]:
        """
        执行子Agent调用（支持session连续对话）

        Args:
            context: ExecutionContext（包含memory_manager等依赖）
            target_mode: 目标Agent模式（"assistant" | "query" | "report" | "social" | "chart" | "expert" | "ops"）
            goal: ⚠️ 任务目标（推荐）：必须完整保留所有参数（文件路径、时间范围等）
            task_description: ⚠️ [向后兼容] 等同于goal
            context_str: 补充上下文（推荐）：技能名称、操作步骤等
            context_supplement: ⚠️ [向后兼容] 等同于context_str
            workspace_path: 工作目录路径（可选）
            session_id: 可选，子Agent会话ID（传入则继续已有对话）
            force_new_session: 是否强制创建新会话
            _force_isolated_session: [内部使用] 并发调用时强制session隔离
            task_id: 工作流任务ID（可选）
            parent_task_id: 父任务ID（可选）
            task_contract: 结构化任务协议（可选）
            result_schema: 子Agent结果Schema（可选）

        Returns:
            {
                "status": "success" | "failed",
                "result": "子Agent的执行结果",
                "data": {...},
                "metadata": {
                    "session_id": "xxx",
                    "is_new_session": true/false
                },
                "summary": "简要总结"
            }
        """
        workflow_runtime = None
        workflow_run = None
        effective_task_id = task_id or f"task-{uuid.uuid4().hex}"

        # ✅ 参数验证
        if not target_mode:
            return {
                "status": "failed",
                "success": False,
                "result": "缺少必需参数：target_mode",
                "data": {},
                "metadata": {"schema_version": "v2.0", "generator": "call_sub_agent"},
                "summary": "参数验证失败"
            }

        # ✅ 参数标准化：优先使用goal，其次task_description（向后兼容）
        effective_goal = goal or task_description
        if not effective_goal:
            return {
                "status": "failed",
                "success": False,
                "result": "缺少必需参数：goal 或 task_description",
                "data": {},
                "metadata": {"schema_version": "v2.0", "generator": "call_sub_agent"},
                "summary": "参数验证失败"
            }

        # ✅ 参数标准化：优先使用context_str，其次context_supplement
        effective_context = context_str or context_supplement or context_text
        if not effective_context and isinstance(kwargs.get("context"), str):
            effective_context = kwargs["context"]
        effective_workspace = None
        if workspace_path and workspace_path.strip():
            try:
                effective_workspace = format_agent_path(resolve_agent_path(workspace_path))
            except (OSError, ValueError) as exc:
                return {
                    "status": "failed",
                    "success": False,
                    "result": f"无效工作目录路径: {exc}",
                    "data": {},
                    "metadata": {"schema_version": "v2.0", "generator": "call_sub_agent"},
                    "summary": "工作目录路径无效",
                }

        try:
            # 获取父Agent模式
            parent_mode = self._get_parent_mode(context)
            runtime_metadata = dict(getattr(context, "runtime_metadata", {}) or {}) if context is not None else {}
            agent_depth = int(runtime_metadata.get("agent_depth", 0) or 0)
            max_agent_depth = int(runtime_metadata.get("max_agent_depth", 2) or 2)
            if agent_depth >= max_agent_depth:
                return {
                    "status": "failed",
                    "success": False,
                    "result": f"子Agent调用深度已达到上限（{max_agent_depth}），拒绝继续嵌套。",
                    "data": {},
                    "metadata": {
                        "schema_version": "workflow.v1",
                        "generator": "call_sub_agent",
                        "agent_depth": agent_depth,
                        "max_agent_depth": max_agent_depth,
                    },
                    "summary": "子Agent嵌套深度超限",
                }
            skill_ids = list(dict.fromkeys(skill_ids or []))
            if len(skill_ids) > 1:
                return {
                    "status": "failed",
                    "success": False,
                    "result": "skill_ids 最多只能传递一个技能",
                    "data": {},
                    "metadata": {"schema_version": "v2.0", "generator": "call_sub_agent"},
                    "summary": "技能参数无效",
                }
            workspace_parent_session_id = (
                getattr(context, "session_id", None)
                if promote_to_workspace
                else None
            )
            if promote_to_workspace and not workspace_parent_session_id:
                return {
                    "status": "failed",
                    "success": False,
                    "result": "持续工作空间必须在已有 Web 会话中创建",
                    "data": {},
                    "metadata": {"schema_version": "v2.0", "generator": "call_sub_agent"},
                    "summary": "缺少父会话上下文",
                }
            if promote_to_workspace and target_mode not in {"board", "ppt", "report"}:
                return {
                    "status": "failed",
                    "success": False,
                    "result": "只有 board、ppt、report 支持持续工作空间升级",
                    "data": {},
                    "metadata": {"schema_version": "v2.0", "generator": "call_sub_agent"},
                    "summary": "不支持的工作空间模式",
                }

            # Persistent workspaces are deferred until the user approves. No
            # child session is created and no specialist model/tool is started
            # on this path.
            if promote_to_workspace:
                promotion = build_workspace_promotion(
                    target_mode=target_mode,
                    session_id=workspace_parent_session_id,
                )
                pending_request = build_workspace_approval_request(
                    promotion=promotion,
                    goal=effective_goal,
                    context_str=effective_context,
                    workspace_path=effective_workspace,
                    skill_ids=skill_ids,
                )
                return {
                    "status": "pending",
                    "success": True,
                    "result": "等待用户审批后启动持续工作空间",
                    "data": {},
                    "metadata": {
                        "schema_version": "v2.0",
                        "generator": "call_sub_agent",
                        "interaction_required": {
                            "kind": "approval",
                            "title": "申请进入持续工作空间",
                            "question": (
                                f"当前任务需要持续使用{target_mode}模式进行多轮编辑，"
                                "是否进入该工作空间？"
                            ),
                            "actions": ["approve", "reject"],
                            "promotion": promotion,
                            "pending_request": pending_request,
                        },
                    },
                    "summary": "已暂停，等待用户审批",
                }
            child_session_id = session_id
            if workspace_parent_session_id:
                # A promoted workspace keeps the web conversation's identity.
                # The specialist owns subsequent turns; no second client session
                # needs to be discovered or synchronized.
                session_id = workspace_parent_session_id
            should_auto_reuse_session = self._should_auto_reuse_session(
                target_mode=target_mode,
                session_id=session_id,
                force_new_session=force_new_session,
                force_isolated_session=_force_isolated_session
            )

            logger.info(
                "calling_sub_agent",
                parent_mode=parent_mode,
                target_mode=target_mode,
                goal=effective_goal[:100] if effective_goal else "",
                context=effective_context[:50] if effective_context else "",
                workspace_path=effective_workspace,
                provided_session_id=session_id,
                force_new_session=force_new_session,
                will_attempt_auto_reuse=should_auto_reuse_session
            )

            # ✅ 从context获取依赖（如果工具初始化时没有传递）
            # ⚠️ 注意：不传递 memory_manager 给子Agent，因为：
            #   1. context.memory_manager 是 HybridMemoryManager（会话记忆）
            #   2. ReActAgent 期望的是 UnifiedMemoryManager（长期记忆）
            #   3. 子Agent应该自己创建 UnifiedMemoryManager
            llm_planner = self.llm_planner
            tool_executor = self.tool_executor

            if context and hasattr(context, 'llm_planner'):
                llm_planner = context.llm_planner
            if context and hasattr(context, 'tool_executor'):
                tool_executor = context.tool_executor

            selected_child_skill = None
            if skill_ids:
                try:
                    available_tools = set(get_tools_by_mode(target_mode).keys())
                    if tool_executor is not None and hasattr(tool_executor, "tool_registry"):
                        available_tools.update(tool_executor.tool_registry.keys())
                    selected_child_skill = load_skill_selection(
                        skill_ids[0],
                        available_tools=available_tools,
                    )
                except (FileNotFoundError, ValueError) as exc:
                    return {
                        "status": "failed",
                        "success": False,
                        "result": f"子 Agent 技能不可用: {exc}",
                        "data": {},
                        "metadata": {"schema_version": "v2.0", "generator": "call_sub_agent"},
                        "summary": "子 Agent 技能不可用",
                    }

            # ✅ 不再验证 memory_manager，让子Agent自己创建

            # ✅ 1. Session处理：确定session_id和对话历史
            conversation_history = []
            is_new_session = False

            if session_id:
                # 明确指定了session_id，继续已有session
                session = session_manager.get_session(session_id)
                if not session and workspace_parent_session_id:
                    session = Session(
                        session_id=session_id,
                        query=effective_goal,
                        parent_mode=parent_mode,
                        child_mode=target_mode,
                        is_sub_agent_session=False,
                    )
                    session_manager.save_session(session)
                if not session:
                    return {
                        "status": "failed",
                        "success": False,
                        "result": f"Session不存在或已过期: {session_id}",
                        "data": {},
                        "metadata": {"schema_version": "v2.0", "generator": "call_sub_agent"},
                        "summary": "Session不存在"
                    }
                # 验证session匹配
                if not workspace_parent_session_id and session.child_mode != target_mode:
                    return {
                        "status": "failed",
                        "success": False,
                        "result": f"Session模式不匹配：期望{session.child_mode}，实际{target_mode}",
                        "data": {},
                        "metadata": {"schema_version": "v2.0", "generator": "call_sub_agent"},
                        "summary": "Session模式不匹配"
                    }
                conversation_history = session.conversation_history
                logger.info(f"继续指定session: {session_id}, 历史消息数: {len(conversation_history)}")
            elif force_new_session or _force_isolated_session:
                # 强制创建新session
                # - force_new_session: 用户显式指定
                # - _force_isolated_session: 并发调用时自动隔离
                session_id = self._generate_session_id(parent_mode, target_mode)
                is_new_session = True
                if _force_isolated_session:
                    logger.info(f"🔄 并发调用隔离：创建独立session: {session_id}")
                else:
                    logger.info(f"强制创建新session: {session_id}")
            elif not should_auto_reuse_session:
                # assistant 子Agent默认不复用旧session，避免跨任务串上下文。
                # 如需连续对话，调用方必须显式传入 session_id。
                session_id = self._generate_session_id(parent_mode, target_mode)
                is_new_session = True
                logger.info(f"assistant子Agent默认创建新session: {session_id}")
            else:
                # 自动查找并复用最近的session（默认行为）
                logger.info(f"尝试自动查找最近的session: parent_mode={parent_mode}, child_mode={target_mode}")
                session = session_manager.find_latest_session(
                    parent_mode=parent_mode,
                    child_mode=target_mode
                )
                if session:
                    # 找到可复用的session
                    session_id = session.session_id
                    conversation_history = session.conversation_history
                    logger.info(
                        f"✅ 自动复用最近session: {session_id}, "
                        f"历史消息数: {len(conversation_history)}, "
                        f"最后更新: {session.updated_at}"
                    )
                else:
                    # 没有找到可复用的session，创建新的
                    session_id = self._generate_session_id(parent_mode, target_mode)
                    is_new_session = True
                    logger.info(f"❌ 未找到可复用session，创建新session: {session_id}")

            # 2. 动态导入（避免循环导入）
            from app.agent.react_agent import ReActAgent

            # 建立通用工作流运行时。运行时快照可由 Session 持久化，模式只负责
            # 提供 task_contract/result_schema，不参与生命周期管理。
            existing_session = session_manager.get_session(session_id) if session_id else None
            runtime_snapshot = {}
            if existing_session:
                runtime_snapshot = (existing_session.metadata or {}).get("workflow_runtime") or {}
            workflow_runtime = WorkflowRuntime(snapshot=runtime_snapshot)
            workflow_run = workflow_runtime.create_run(
                task_id=effective_task_id,
                parent_task_id=parent_task_id,
                run_id=workflow_run_id,
                max_attempts=max(1, min(int(repair_attempts or 0) + 1, 3)),
                deadline_at=deadline_at,
            )
            workflow_runtime.start(workflow_run.run_id)

            def persist_workflow_snapshot(snapshot: Dict[str, Any]) -> None:
                self._persist_workflow_snapshot(
                    session_id=session_id,
                    query=effective_goal,
                    parent_mode=parent_mode,
                    child_mode=target_mode,
                    snapshot=snapshot,
                )

            workflow_runtime.set_persist(persist_workflow_snapshot)
            persist_workflow_snapshot(workflow_runtime.snapshot())
            if workflow_runtime.check_deadline(workflow_run.run_id):
                return {
                    "status": "cancelled",
                    "success": False,
                    "result": "工作流已超过截止时间，未启动子 Agent。",
                    "data": {},
                    "metadata": {
                        "schema_version": "workflow.v1",
                        "generator": "call_sub_agent",
                        "workflow_run_id": workflow_run.run_id,
                    },
                    "summary": "工作流超时取消",
                }
            if parent_task_id:
                workflow_runtime.append(
                    workflow_run.run_id,
                    "task.lineage_attached",
                    payload={"parent_task_id": parent_task_id},
                )
            if task_contract or result_schema:
                workflow_runtime.append(
                    workflow_run.run_id,
                    "task.contract_bound",
                    payload={
                        "task_type": (task_contract or {}).get("task_type"),
                        "contract_fields": sorted((task_contract or {}).keys()),
                        "result_schema_fields": sorted((result_schema or {}).get("properties", {}).keys()),
                    },
                )

            mode_tool_names = set(get_tools_by_mode(target_mode).keys())
            if selected_child_skill:
                mode_tool_names.update(selected_child_skill.required_tools or [])
            capability_policy = build_child_capability_policy(
                allowed_tools=(allowed_tool_names if allowed_tool_names is not None else mode_tool_names),
                denied_tools=denied_tool_names,
                allow_delegation=allow_child_delegation,
            )

            handoff_resource_service = getattr(tool_executor, "resource_service", None)
            imported_resource_refs: List[Dict[str, Any]] = []
            parent_resource_handles = await self._collect_parent_resource_handles(context)
            upstream_group_ids = {
                (str(item.get("source_session_id") or ""), str(item.get("group_id") or ""))
                for item in (_upstream_handles or [])
                if item.get("source_session_id") and item.get("group_id")
            }
            parent_resource_handles = [
                item
                for item in parent_resource_handles
                if (
                    str(item.get("source_session_id") or ""),
                    str(item.get("group_id") or ""),
                ) not in upstream_group_ids
            ]
            imported_parent_resource_refs: List[Dict[str, Any]] = []
            if _upstream_handles or parent_resource_handles:
                if handoff_resource_service is None:
                    from app.agent.resources.resource_service import SessionResourceService

                    handoff_resource_service = SessionResourceService.database()
                if parent_resource_handles:
                    imported_parent_resource_refs = await import_workflow_handles(
                        handoff_resource_service,
                        target_session_id=str(session_id),
                        run_id=workflow_run.run_id,
                        handles=parent_resource_handles,
                    )
                if _upstream_handles:
                    imported_resource_refs = await import_workflow_handles(
                        handoff_resource_service,
                        target_session_id=str(session_id),
                        run_id=workflow_run.run_id,
                        handles=_upstream_handles,
                    )
                workflow_runtime.append(
                    workflow_run.run_id,
                    "task.resources_imported",
                    payload={
                        "requested_count": len(_upstream_handles or []) + len(parent_resource_handles),
                        "imported_count": len(imported_resource_refs) + len(imported_parent_resource_refs),
                        "resource_ids": [
                            item["resource_id"]
                            for item in [*imported_parent_resource_refs, *imported_resource_refs]
                        ],
                    },
                )

            # 3. 构建子 Agent 请求：ReActAgent 会自行构建系统提示，因此把任务、
            # 补充上下文和规范化后的工作目录作为本轮用户请求一起传入。
            scheduled_task_context = (
                getattr(context, "scheduled_task_context", None)
                if context is not None
                else None
            )
            child_request_prompt = self._build_child_request_prompt(
                goal=effective_goal,
                context=effective_context,
                workspace_path=effective_workspace,
                target_mode=target_mode,
                parent_resource_lines=self._format_imported_resource_lines(
                    imported_parent_resource_refs
                ),
                scheduled_task_context=scheduled_task_context,
                skill_id=selected_child_skill.skill_id if selected_child_skill else None,
                task_contract=task_contract,
                result_schema=result_schema,
                upstream_resource_lines=self._format_imported_resource_lines(
                    imported_resource_refs
                ),
            )
            logger.debug(
                "child_request_prompt_built",
                target_mode=target_mode,
                prompt_preview=child_request_prompt[:200] if child_request_prompt else ""
            )

            # 4. 创建临时子Agent实例（复用父Agent的配置）
            # ⚠️ 关键：使用 ReActAgent.analyze() 以获得完整的记忆增强功能
            # ⚠️ 不传递 memory_manager，让子Agent自己创建 UnifiedMemoryManager

            # 所有模式统一使用 ReActAgent；专家模式通过工具注册表中的原子工具/工作流工具完成分析。
            child_registry = capability_policy.filter_registry(
                tool_executor.tool_registry if tool_executor else None
            )
            sub_agent = ReActAgent(
                max_iterations=120,  # 子Agent默认120次迭代
                enable_memory=True,  # ✅ 启用记忆（子Agent会自动创建 UnifiedMemoryManager）
                tool_registry=child_registry  # 子 Agent 只获得策略允许的工具
            )

            # 子Agent必须继承父Agent本次请求已经选定的完整模型优先级链。
            # 先快照再进入新上下文，避免子Agent的 Auto 多模态 profile 重选模型链。
            parent_llm_service = getattr(llm_planner, "llm_service", None)
            child_planner = getattr(sub_agent, "planner", None)
            child_llm_service = getattr(child_planner, "llm_service", None)
            model_chain_context = nullcontext()
            if parent_llm_service is not None and child_llm_service is not None:
                inherited_chain = getattr(tool_executor, "llm_model_chain", None)
                if inherited_chain:
                    parent_provider, parent_model, parent_fallbacks = inherited_chain
                else:
                    parent_provider = parent_llm_service.provider
                    parent_model = parent_llm_service.model
                    parent_fallbacks = parent_llm_service.request_fallbacks
                model_chain_context = child_llm_service.use_provider_chain(
                    parent_provider,
                    parent_model,
                    parent_fallbacks,
                )
                logger.info(
                    "sub_agent_model_chain_inherited",
                    parent_mode=parent_mode,
                    target_mode=target_mode,
                    provider=parent_provider,
                    model=parent_model,
                    fallbacks=parent_fallbacks,
                )

            # 5. 执行子Agent（同一 session + mode 的 turn 串行化，避免上下文交叉）。
            actor_key = f"{session_id or workflow_run.run_id}:{target_mode}"

            async def run_child_turn(
                prompt: str,
                initial_messages: Optional[List[Dict[str, Any]]] = None,
                *,
                include_skill: bool = False,
            ) -> List[Dict[str, Any]]:
                turn_events: List[Dict[str, Any]] = []
                async with child_actor_registry.lease(actor_key):
                    with model_chain_context:
                        async for event in sub_agent.analyze(
                            user_query=prompt,
                            session_id=session_id if session_id else None,
                            manual_mode=target_mode,
                            enhance_with_history=True,
                            initial_messages=initial_messages,
                            user_identifier=None,
                            runtime_metadata={
                                **runtime_metadata,
                                "agent_depth": agent_depth + 1,
                                "max_agent_depth": max_agent_depth,
                                "workflow_run_id": workflow_run.run_id,
                            },
                            selected_skill_context=(
                                selected_child_skill.content
                                if include_skill and selected_child_skill
                                else None
                            ),
                            extra_tool_names=(
                                selected_child_skill.required_tools
                                if include_skill and selected_child_skill
                                else None
                            ),
                        ):
                            turn_events.append(event)
                return turn_events

            result_events = await run_child_turn(
                child_request_prompt,
                conversation_history if conversation_history else None,
                include_skill=True,
            )
            workflow_runtime.append(
                workflow_run.run_id,
                "task.child_turn_completed",
                payload={"event_count": len(result_events)},
            )

            # 7. 提取最终结果；结构化协议失败时在同一 child runtime 上做有限修复。
            final_result = self._extract_final_result(result_events)
            if workflow_runtime.check_deadline(workflow_run.run_id):
                final_result = {
                    **final_result,
                    "status": "cancelled",
                    "answer": "工作流已超过截止时间，子 Agent 结果已取消。",
                }
            structured_result = None
            validation_errors = []
            if result_schema and final_result["status"] != "cancelled":
                structured_result, validation_errors = self._validate_structured_result(
                    final_result.get("answer", ""), result_schema
                )
                attempts = max(0, min(int(repair_attempts or 0), 2))
                for repair_index in range(attempts):
                    if not validation_errors:
                        break
                    workflow_runtime.begin_repair(
                        workflow_run.run_id,
                        errors=validation_errors,
                    )
                    workflow_runtime.append(
                        workflow_run.run_id,
                        "task.result_repair_requested",
                        payload={"repair_index": repair_index + 1, "errors": validation_errors},
                    )
                    repair_prompt = (
                        "上一轮结果未通过结构化结果协议校验。请保留已完成的证据和分析，"
                        "只修复输出格式或缺失字段，并在 ```json 代码块中重新提交完整 JSON。\n"
                        f"校验错误：{json.dumps(validation_errors, ensure_ascii=False)}\n"
                        f"结果协议：{json.dumps(result_schema, ensure_ascii=False)}"
                    )
                    result_events.extend(await run_child_turn(repair_prompt))
                    final_result = self._extract_final_result(result_events)
                    structured_result, validation_errors = self._validate_structured_result(
                        final_result.get("answer", ""), result_schema
                    )
                    if validation_errors:
                        workflow_runtime.start(workflow_run.run_id)

            logger.info(
                "sub_agent_completed",
                target_mode=target_mode,
                status=final_result["status"],
                answer_length=len(final_result.get("answer", "")),
                iterations=len([e for e in result_events if e.get("type") == "tool_call"]),
                session_id=session_id
            )

            # 提取结构化数据
            structured_data = {
                "file_paths": self._extract_file_paths(result_events),
                "chart_urls": self._extract_chart_urls(result_events),  # 图片URL（前端渲染）
                "image_paths": self._extract_image_paths(result_events),  # 本地路径（文件操作）
                "tool_calls": self._extract_tool_calls(result_events)
            }
            if handoff_resource_service is None:
                from app.agent.resources.resource_service import SessionResourceService

                handoff_resource_service = SessionResourceService.database()
            structured_data["resource_refs"] = await self._collect_resource_refs(
                result_events,
                session_id=str(session_id),
                service=handoff_resource_service,
            )
            if result_schema:
                structured_data["structured_result"] = structured_result
                structured_data["validation_errors"] = validation_errors
            structured_data["result_envelope"] = build_result_envelope(
                status=(
                    "completed"
                    if final_result["status"] == "success" and not validation_errors
                    else "cancelled"
                    if final_result["status"] == "cancelled"
                    else "failed"
                ),
                summary=final_result.get("answer", "")[:1000],
                outputs=(
                    structured_result
                    if isinstance(structured_result, dict)
                    else {"answer": final_result.get("answer", "")}
                ),
                artifacts=[
                    {
                        "kind": ref.get("kind") or "artifact",
                        "resource_id": ref["resource_id"],
                        "source_session_id": ref["source_session_id"],
                        "name": ref.get("label"),
                        **({"path": ref["file_path"]} if ref.get("file_path") else {}),
                    }
                    for ref in structured_data["resource_refs"]
                ] + [
                    {"kind": "chart", "url": url}
                    for url in structured_data["chart_urls"]
                ],
                errors=validation_errors,
                metadata={"target_mode": target_mode, "task_id": effective_task_id},
            )
            human_feedback = self._extract_human_feedback(result_events)
            if human_feedback is not None:
                structured_data["human_feedback"] = human_feedback
            # Preserve the latest board payload so a promoted workspace can
            # render immediately after the user approves the handoff.
            for child_event in reversed(result_events):
                if child_event.get("type") != "tool_result":
                    continue
                child_result = (child_event.get("data") or {}).get("result") or {}
                child_data = child_result.get("data") if isinstance(child_result, dict) else None
                child_metadata = child_result.get("metadata") if isinstance(child_result, dict) else None
                if (
                    isinstance(child_data, dict)
                    and isinstance(child_metadata, dict)
                    and child_metadata.get("generator") == "create_drawio_board"
                ):
                    structured_data["artifact_kind"] = "drawio_board"
                    structured_data["board"] = child_data.get("board") or child_data
                    break

            validation_errors = structured_data.get("validation_errors", [])
            succeeded = final_result["status"] == "success" and not validation_errors
            if succeeded:
                workflow_runtime.transition(workflow_run.run_id, "succeeded")
            elif workflow_runtime.get_run(workflow_run.run_id).status != "cancelled":
                workflow_runtime.transition(
                    workflow_run.run_id,
                    "failed",
                    payload={
                        "status": final_result["status"],
                        "validation_errors": validation_errors,
                    },
                )

            # ✅ 8. 保存/更新session
            if not workspace_parent_session_id:
                self._update_session(
                    session_id=session_id,
                    parent_mode=parent_mode,
                    child_mode=target_mode,
                    user_query=effective_goal,  # ✅ 使用effective_goal
                    assistant_answer=final_result["answer"],
                    result_events=result_events,
                    task_id=task_id,
                    parent_task_id=parent_task_id,
                    task_contract=task_contract,
                    result_schema=result_schema,
                    result_status=(
                        "cancelled"
                        if final_result["status"] == "cancelled"
                        else "success"
                        if not structured_data.get("validation_errors")
                        else "invalid_result"
                    ),
                    validation_errors=structured_data.get("validation_errors", []),
                    workflow_snapshot=workflow_runtime.snapshot(),
                )

            # ✅ 构建增强的metadata（包含子Agent的思考过程）
            enhanced_metadata = {
                "schema_version": "v2.0",
                "generator": "call_sub_agent",
                "sub_agent_mode": target_mode,
                "iterations": len([e for e in result_events if e.get("type") == "tool_call"]),
                "file_paths_count": len(structured_data["file_paths"]),
                "chart_urls_count": len(structured_data["chart_urls"]),
                "image_paths_count": len(structured_data["image_paths"]),
                # ✅ 返回session_id给父Agent
                "session_id": session_id,
                "is_new_session": is_new_session
            }
            if task_id:
                enhanced_metadata["task_id"] = task_id
            enhanced_metadata["workflow_run_id"] = workflow_run.run_id
            enhanced_metadata["workflow_status"] = workflow_runtime.get_run(workflow_run.run_id).status
            enhanced_metadata["workflow_event_count"] = len(workflow_runtime.events(run_id=workflow_run.run_id))
            if parent_task_id:
                enhanced_metadata["parent_task_id"] = parent_task_id
            if result_schema:
                enhanced_metadata["result_validation"] = {
                    "valid": not structured_data["validation_errors"],
                    "error_count": len(structured_data["validation_errors"]),
                }

            if promote_to_workspace:
                try:
                    enhanced_metadata["workspace_promotion"] = build_workspace_promotion(
                        target_mode=target_mode,
                        session_id=session_id,
                    )
                    if child_session_id and child_session_id != session_id:
                        enhanced_metadata["workspace_promotion"]["child_session_id"] = child_session_id
                except ValueError as exc:
                    return {
                        "status": "failed",
                        "success": False,
                        "result": str(exc),
                        "data": structured_data,
                        "metadata": enhanced_metadata,
                        "summary": "不支持将该 Agent 升级为持续工作空间",
                    }

            # ✅ 添加思考过程到metadata（父Agent可以使用）
            if "thought" in final_result.get("data", {}):
                enhanced_metadata["thought"] = final_result["data"]["thought"]
            if "reasoning" in final_result.get("data", {}):
                enhanced_metadata["reasoning"] = final_result["data"]["reasoning"]

            resources = result_resource_declarations(
                str(parent_task_id or effective_task_id),
                {effective_task_id: {"data": structured_data}},
            )
            return {
                "status": "success" if succeeded else ("invalid_result" if validation_errors else final_result["status"]),
                "success": succeeded,
                "result": final_result["answer"],  # ✅ LLM的最终答案（最重要）
                "data": structured_data,
                "metadata": enhanced_metadata,
                "summary": (
                    f"{self._get_mode_name(target_mode)}已完成任务"
                    if succeeded
                    else f"{self._get_mode_name(target_mode)}结果未通过结构化协议校验"
                    if validation_errors
                    else f"{self._get_mode_name(target_mode)}执行失败"
                ),
                "resources": resources,
            }

        except Exception as e:
            if workflow_runtime is not None:
                try:
                    run = workflow_run
                    if run and run.status not in {"succeeded", "failed", "cancelled"}:
                        workflow_runtime.transition(
                            run.run_id,
                            "failed",
                            payload={"error": str(e)},
                        )
                except Exception:
                    logger.debug("workflow_runtime_failure_record_failed", exc_info=True)
            logger.error(
                "sub_agent_failed",
                target_mode=target_mode,
                error=str(e),
                goal=effective_goal[:100] if effective_goal else ""
            )
            return {
                "status": "failed",
                "success": False,
                "result": f"子Agent执行失败：{str(e)}",
                "data": {},
                "metadata": {
                    "schema_version": "v2.0",
                    "generator": "call_sub_agent"
                },
                "summary": "任务执行失败"
            }

    async def _collect_parent_resource_handles(self, context) -> List[Dict[str, Any]]:
        """Collect path-backed parent resources for child-session import.

        The child uses an isolated session and therefore cannot read the parent
        catalog directly. Returning typed handles lets the runtime register the
        same resource groups in the child before its sandbox is configured.
        """
        try:
            executor = getattr(context, "tool_executor", None)
            service = getattr(executor, "resource_service", None)
            parent_session_id = getattr(getattr(executor, "memory_manager", None), "session_id", None)
            if service is None or not parent_session_id:
                return []

            from app.agent.resources.resource_map import resource_access_path
            page = await service.list_resources(parent_session_id, limit=500)
            handles = []
            seen_paths = set()
            for stored in page.resources:
                access_path = resource_access_path(stored)
                if not access_path or not is_path_within(
                    resolve_agent_path(access_path), [get_data_registry()]
                ):
                    continue
                if access_path in seen_paths:
                    continue
                seen_paths.add(access_path)
                handles.append(stored_resource_ref(stored))
                if len(handles) >= 50:
                    break
            return handles
        except Exception as exc:
            logger.warning("parent_resource_transfer_failed", error=str(exc))
            return []

    def _build_child_request_prompt(
        self,
        goal: str,
        context: Optional[str] = None,
        workspace_path: Optional[str] = None,
        target_mode: str = "assistant",
        parent_resource_lines: Optional[List[str]] = None,
        scheduled_task_context: Optional[Dict[str, Any]] = None,
        skill_id: Optional[str] = None,
        task_contract: Optional[Dict[str, Any]] = None,
        result_schema: Optional[Dict[str, Any]] = None,
        upstream_resource_lines: Optional[List[str]] = None,
    ) -> str:
        """
        构建子 Agent 本轮请求（分离 goal、补充上下文和工作目录）

        Args:
            goal: 任务目标（完整的原始任务，包含所有参数）
            context: 补充上下文（可选）
            workspace_path: 工作目录路径（可选）
            target_mode: 目标Agent模式

        Returns:
            子 Agent 请求字符串
        """
        parts = [
            "你是作为子Agent被调用，专注完成指定的任务。\n",
            f"**任务目标**:\n{goal}\n"
        ]

        # 添加补充上下文（如果有）
        if context and context.strip():
            parts.append(f"**补充上下文**:\n{context}\n")

        if skill_id:
            parts.append(f"**显式技能**：{skill_id}\n")

        if task_contract:
            parts.append(
                "## 工作流任务协议（必须遵守）\n"
                "以下对象是父 Agent 传入的正式任务边界。不得擅自扩大范围；缺少证据时要在结果中明确标记。\n"
                f"```json\n{json.dumps(task_contract, ensure_ascii=False, indent=2)}\n```\n"
            )
        if result_schema:
            parts.append(
                "## 结构化结果协议（必须遵守）\n"
                "最终回复必须包含一个可解析的 JSON 对象，放在 ```json 代码块中；除 JSON 外可以附简短说明。\n"
                f"```json\n{json.dumps(result_schema, ensure_ascii=False, indent=2)}\n```\n"
            )

        if scheduled_task_context:
            task_name = scheduled_task_context.get("task_name") or scheduled_task_context.get("task_id") or "定时任务"
            execution_id = scheduled_task_context.get("execution_id") or ""
            parts.append(
                "## 后台定时任务执行约束\n"
                f"- 本次子 Agent 由后台定时任务 `{task_name}` 调用"
                + (f"，execution_id={execution_id}" if execution_id else "")
                + "。\n"
                "- 父任务已经由用户提前配置并确认；不要要求父 Agent 或用户再确认后才继续。\n"
                "- 需要审核、复核、工具提交或产物落盘时，在本次子 Agent 执行内直接完成并返回结果。\n"
                "- 如果工具结果要求人工复核，只按工具结果标记 manual_review 并返回，不要等待在线确认。\n"
            )

        # 父会话已登记文件（上传附件等）；子会话无法查询父会话资源目录，
        # 这些真实路径可直接用于 read_file / execute_python（沙箱按白名单挂载）。
        if parent_resource_lines:
            parts.append("**父会话可用文件**（可直接按路径读取，勿编造其他路径）:\n")
            parts.extend(parent_resource_lines)
            parts.append("")

        if upstream_resource_lines:
            parts.append("## 上游依赖资源（已登记到当前子会话，可直接复用）\n")
            parts.extend(upstream_resource_lines)
            parts.append("禁止对这些资源已经覆盖的数据重复查询。\n")

        # 添加工作目录（如果有）
        if workspace_path and workspace_path.strip():
            parts.append(f"**工作目录**:\n{workspace_path}\n")

        # 根据目标模式添加特定提示
        mode_hints = {
            "assistant": (
                "\n⚠️ **关键要求**（办公任务）：\n"
                "- 生成任务清单时，必须在每个任务的content中保留所有原始参数\n"
                "- 禁止摘要化或省略文件路径、时间范围、sheet索引等关键信息\n"
                "- 正确示例：'更新Excel文件 /tmp/会商文件/全国各省份污染物累计平均.xlsx "
                "（第五个sheet，时间段：2026年1-3月和2025年1-3月）'\n"
                "- 错误示例：❌ '更新Excel文件'\n"
            ),
            "social": "\n专注完成上述社交平台任务。\n",
            "query": "\n专注完成上述数据查询任务，请解析用户的自然语言描述，选择合适的工具和参数。\n",
            "report": "\n专注完成上述报告生成任务。\n",
            "ops": "\n专注完成上述运维管理任务，围绕工单查询、审核判断、异常分析和闭环建议给出结构化结果。\n",
            "code": "\n专注完成上述编程任务。\n",
        }

        hint = mode_hints.get(target_mode, "")
        parts.append(hint)

        # ⚠️ 添加file_path返回要求（所有子Agent必须遵守）
        parts.append("\n## ⚠️ 子Agent返回格式要求（CRITICAL）\n")
        parts.append("**必须在最终回复中明确列出所有file_path**，格式如下：\n")
        parts.append("```markdown\n")
        parts.append("**数据溯源**：\n")
        parts.append("- file_path: xxx-xxx (说明)\n")
        parts.append("- file_path: yyy-yyy (说明)\n")
        parts.append("```\n\n")
        parts.append("**提取规则**：\n")
        parts.append("- 从工具返回的 `file_path`、`metadata.file_path`、`data.file_paths` 字段提取\n")
        parts.append("- 父Agent依赖此信息收集数据溯源\n")
        parts.append("- 即使只有一个file_path也必须列出\n")

        return "\n".join(parts)

    def _build_child_system_prompt(
        self,
        goal: str,
        context: Optional[str] = None,
        workspace_path: Optional[str] = None,
        target_mode: str = "assistant",
        parent_resource_lines: Optional[List[str]] = None,
        scheduled_task_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Backward-compatible alias for the child request prompt builder."""
        return self._build_child_request_prompt(
            goal=goal,
            context=context,
            workspace_path=workspace_path,
            target_mode=target_mode,
            parent_resource_lines=parent_resource_lines,
            scheduled_task_context=scheduled_task_context,
        )

    def _extract_final_result(self, events: list) -> Dict:
        """从事件流中提取最终结果"""
        # ✅ 优先查找agent_finish事件（包含完整的answer）
        for event in reversed(events):
            if event.get("type") == "agent_finish":
                result = {
                    "status": "success",
                    "answer": event.get("answer", ""),
                    "data": event.get("data", {})
                }
                logger.info(
                    "agent_finish_event_found",
                    answer_length=len(result["answer"]),
                    has_data=bool(event.get("data"))
                )
                return result

        # 回退：查找最后一个observation事件
        for event in reversed(events):
            if event.get("type") == "observation":
                result = {
                    "status": "success",
                    "answer": event.get("content", ""),
                    "data": event.get("data", {})
                }
                logger.warning(
                    "agent_finish_event_not_found_using_observation",
                    answer_length=len(result["answer"]),
                    observation_keys=list(event.get("data", {}).keys()) if isinstance(event.get("data"), dict) else []
                )
                return result

        logger.error("no_result_event_found_in_sub_agent_events")
        return {
            "status": "failed",
            "answer": "子Agent未返回结果",
            "data": {}
        }

    def _get_mode_name(self, mode: str) -> str:
        """获取模式的友好名称"""
        mode_names = {
            "assistant": "助手Agent",
            "social": "社交Agent",
            "query": "问数Agent",
            "report": "报告Agent",
            "ops": "运维管理Agent",
            "code": "编程Agent",
        }
        return mode_names.get(mode, mode)

    @staticmethod
    def _validate_structured_result(answer: str, schema: Dict[str, Any]):
        structured_result = extract_structured_result(answer)
        if structured_result is None:
            return None, [{
                "path": "$",
                "expected": "JSON result matching result_schema",
                "got": "no structured JSON result",
            }]
        return structured_result, validate_result_schema(structured_result, schema)

    def _extract_file_paths(self, events: list) -> list:
        """Extract file handles from current tool_result and legacy events."""
        file_paths: List[str] = []

        def add(value: Any) -> None:
            values = value if isinstance(value, list) else [value]
            for item in values:
                if isinstance(item, str) and item.strip() and item not in file_paths:
                    file_paths.append(item)

        def collect(mapping: Any) -> None:
            if not isinstance(mapping, dict):
                return
            for key in (
                "file_path",
                "report_file_path",
                "file_paths",
                "report_file_paths",
                "data_file_paths",
            ):
                add(mapping.get(key))
            metadata = mapping.get("metadata")
            if isinstance(metadata, dict):
                for key in ("file_path", "report_file_path", "file_paths", "report_file_paths"):
                    add(metadata.get(key))
            resources = mapping.get("resources")
            if isinstance(resources, list):
                for resource in resources:
                    if isinstance(resource, dict):
                        locator = resource.get("locator")
                        if isinstance(locator, dict):
                            add(locator.get("path"))

        for event in events:
            if event.get("type") == "observation":
                collect(event)
                collect(event.get("data"))
            elif event.get("type") == "tool_result":
                data = event.get("data")
                collect(data)
                result = data.get("result") if isinstance(data, dict) else None
                collect(result)
                collect(result.get("data") if isinstance(result, dict) else None)
        return file_paths

    @staticmethod
    def _format_imported_resource_lines(refs: List[Dict[str, Any]]) -> List[str]:
        lines = []
        for ref in refs:
            details = [
                f"resource_id={ref['resource_id']}",
                f"kind={ref.get('kind') or 'unknown'}",
            ]
            if ref.get("file_path"):
                details.append(f"file_path={ref['file_path']}")
            lines.append(f"- {ref.get('label') or ref['resource_id']} | " + " | ".join(details))
        return lines

    @staticmethod
    def _extract_resource_ids(events: list) -> List[str]:
        resource_ids: List[str] = []

        def add(values: Any) -> None:
            if not isinstance(values, list):
                return
            for value in values:
                text = str(value or "").strip()
                if text and text not in resource_ids:
                    resource_ids.append(text)

        for event in events:
            data = event.get("data") if isinstance(event, dict) else None
            if not isinstance(data, dict):
                continue
            add(data.get("changed_resource_ids"))
            result = data.get("result")
            if not isinstance(result, dict):
                continue
            tracking = result.get("resource_tracking")
            if isinstance(tracking, dict) and tracking.get("durable") is True:
                add(tracking.get("resource_ids"))
        return resource_ids

    async def _collect_resource_refs(
        self,
        events: list,
        *,
        session_id: str,
        service: Any,
    ) -> List[Dict[str, Any]]:
        refs: List[Dict[str, Any]] = []
        for resource_id in self._extract_resource_ids(events):
            stored = await service.get_resource(session_id, resource_id, status="active")
            if stored is not None:
                refs.append(stored_resource_ref(stored))
        return refs

    def _extract_chart_urls(self, events: list) -> list:
        """从事件流中提取所有图表URL（用于前端渲染）"""
        import re
        chart_urls = []
        for event in events:
            if event.get("type") == "observation":
                # 从markdown_image中提取
                content = event.get("content", "")
                if "![" in content:
                    urls = re.findall(r'\(/api/image/[^\)]+\)', content)
                    chart_urls.extend([url[1:-1] for url in urls])

                # 从visuals字段中提取（支持多种嵌套结构）
                # 1. 直接在event的visuals字段
                if "visuals" in event and isinstance(event["visuals"], list):
                    for visual in event["visuals"]:
                        if isinstance(visual, dict):
                            if "payload" in visual and isinstance(visual["payload"], dict):
                                if "image_url" in visual["payload"]:
                                    chart_urls.append(visual["payload"]["image_url"])

                # 2. 在observation.visuals字段
                obs_data = event.get("data", {})
                observation = obs_data.get("observation", {})
                if "visuals" in observation and isinstance(observation["visuals"], list):
                    for visual in observation["visuals"]:
                        if isinstance(visual, dict):
                            if "payload" in visual and isinstance(visual["payload"], dict):
                                if "image_url" in visual["payload"]:
                                    chart_urls.append(visual["payload"]["image_url"])

                # 从data字段中的chart_urls数组提取
                if "data" in event and isinstance(event["data"], dict):
                    if "chart_urls" in event["data"] and isinstance(event["data"]["chart_urls"], list):
                        chart_urls.extend(event["data"]["chart_urls"])
        return list(set(chart_urls))  # 去重

    def _extract_image_paths(self, events: list) -> list:
        """从事件流中提取所有图片本地路径（用于文件操作）"""
        image_paths = []
        for event in events:
            if event.get("type") == "observation":
                obs_data = event.get("data", {})
                observation = obs_data.get("observation", {})

                # 1. 从observation的image_path字段提取
                if isinstance(observation, dict):
                    if "image_path" in observation:
                        image_paths.append(observation["image_path"])
                    # 从visuals字段中提取本地路径
                    if "visuals" in observation and isinstance(observation["visuals"], list):
                        for visual in observation["visuals"]:
                            if isinstance(visual, dict):
                                # 从payload中提取image_path
                                if "payload" in visual and isinstance(visual["payload"], dict):
                                    payload = visual["payload"]
                                    if "image_path" in payload:
                                        image_paths.append(payload["image_path"])
                                    # 同时提取file_path（有些工具用这个字段）
                                    if "file_path" in payload:
                                        image_paths.append(payload["file_path"])

                # 2. 从data字段的根级别提取
                if isinstance(obs_data, dict):
                    if "image_path" in obs_data:
                        image_paths.append(obs_data["image_path"])
                    if "file_path" in obs_data:
                        # 判断是否为图片文件（.png/.jpg/.jpeg等）
                        file_path = obs_data["file_path"]
                        if file_path and any(ext in file_path.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg']):
                            image_paths.append(file_path)

        return list(set(image_paths))  # 去重

    def _extract_tool_calls(self, events: list) -> list:
        """从事件流中提取工具调用记录"""
        tool_calls = []
        for event in events:
            if event.get("type") == "tool_call":
                tool_calls.append({
                    "tool": event.get("generator", event.get("tool", "")),
                    "args": event.get("args", {})
                })
        return tool_calls

    def _extract_human_feedback(self, events: list) -> Optional[Dict[str, Any]]:
        """Preserve a child Agent's pending UI handoff for the parent session."""

        for event in reversed(events):
            if event.get("type") != "tool_result":
                continue
            result = (event.get("data") or {}).get("result")
            data = result.get("data") if isinstance(result, dict) else None
            feedback = data.get("human_feedback") if isinstance(data, dict) else None
            if isinstance(feedback, dict) and feedback.get("required"):
                return feedback
        return None

    def _get_parent_mode(self, context: Optional[Any]) -> str:
        """从context获取父Agent模式"""
        if context and hasattr(context, 'manual_mode'):
            return context.manual_mode
        # 尝试从memory_manager获取
        if context and hasattr(context, 'memory_manager'):
            mm = context.memory_manager
            if hasattr(mm, 'mode'):
                return mm.mode
        return "social"  # 默认社交模式

    def _should_auto_reuse_session(
        self,
        target_mode: Optional[str],
        session_id: Optional[str],
        force_new_session: bool,
        force_isolated_session: bool
    ) -> bool:
        """
        判断是否允许自动复用最近的子Agent session。

        assistant 子Agent默认创建新session，避免复用旧办公任务上下文。
        需要连续对话时，调用方应显式传入 session_id。
        """
        if session_id or force_new_session or force_isolated_session:
            return False
        return target_mode != "assistant"

    def _generate_session_id(self, parent_mode: str, child_mode: str) -> str:
        """生成子Agent session_id"""
        return f"{parent_mode}__to__{child_mode}__{uuid.uuid4().hex}"

    def _update_session(
        self,
        session_id: str,
        parent_mode: str,
        child_mode: str,
        user_query: str,
        assistant_answer: str,
        result_events: List[Dict],
        task_id: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        task_contract: Optional[Dict[str, Any]] = None,
        result_schema: Optional[Dict[str, Any]] = None,
        result_status: Optional[str] = None,
        validation_errors: Optional[List[Dict[str, str]]] = None,
        workflow_snapshot: Optional[Dict[str, Any]] = None,
    ):
        """更新子Agent session"""
        # 加载或创建session
        session = session_manager.get_session(session_id)

        if not session:
            # 创建新session
            session = Session(
                session_id=session_id,
                query=user_query,
                parent_mode=parent_mode,
                child_mode=child_mode,
                is_sub_agent_session=True
            )

        # 添加对话历史
        session.conversation_history.append({
            "role": "user",
            "content": user_query,
            "timestamp": datetime.now().isoformat()
        })

        if task_id or parent_task_id or task_contract or result_schema:
            workflow = dict(session.metadata.get("workflow") or {})
            workflow.update({
                "protocol_version": "workflow.v1",
                "task_id": task_id,
                "parent_task_id": parent_task_id,
                "task_type": (task_contract or {}).get("task_type"),
                "task_contract": task_contract,
                "result_schema": result_schema,
                "status": result_status or "completed",
                "validation_errors": validation_errors or [],
                "workflow_runtime": workflow_snapshot or workflow.get("workflow_runtime") or {},
                "updated_at": datetime.now().isoformat(),
            })
            session.metadata["workflow"] = workflow
        session.conversation_history.append({
            "role": "assistant",
            "content": assistant_answer,
            "timestamp": datetime.now().isoformat()
        })

        # 提取并添加file_paths（visual_ids不再提取，社交模式用chart_urls渲染图片）
        file_paths = self._extract_file_paths(result_events)

        # 去重后添加
        # Data resources are persisted by the unified resource service.

        # 保存session（更新时间戳）
        session_manager.save_session(session, update_timestamp=True)

        logger.info(
            "session_updated",
            session_id=session_id,
            conversation_length=len(session.conversation_history),
            data_count=0
        )

    @staticmethod
    def _persist_workflow_snapshot(
        *,
        session_id: str,
        query: str,
        parent_mode: str,
        child_mode: str,
        snapshot: Dict[str, Any],
    ) -> None:
        """Persist runtime state independently from the final transcript."""
        if not session_id:
            return
        session = session_manager.get_session(session_id)
        if session is None:
            session = Session(
                session_id=session_id,
                query=query,
                parent_mode=parent_mode,
                child_mode=child_mode,
                is_sub_agent_session=True,
            )
        session.metadata["workflow_runtime"] = snapshot
        session_manager.save_session_metadata(session, update_timestamp=True)
