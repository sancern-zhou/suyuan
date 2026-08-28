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
from typing import Dict, Any, Literal, Optional, List
import structlog
from datetime import datetime
import uuid

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.agent.session.session_manager import get_session_manager
from app.agent.session.models import Session
from app.utils.path_config import format_agent_path, resolve_agent_path

logger = structlog.get_logger()

# 获取全局session管理器
session_manager = get_session_manager()

# ⚠️ 支持多种模式：assistant, query, report, social, chart, expert, ops
AgentMode = Literal["assistant", "query", "report", "social", "chart", "expert", "ops"]


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
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_mode": {
                        "type": "string",
                    "enum": ["assistant", "query", "report", "social", "chart", "expert", "ops"],
                    "description": "目标 Agent 模式。"
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
                    "session_id": {
                        "type": "string",
                        "description": "子Agent会话ID；传入则继续指定会话。"
                    },
                    "force_new_session": {
                        "type": "boolean",
                        "description": "是否强制创建新会话。"
                    },
                    "_force_isolated_session": {
                        "type": "boolean",
                        "description": "[内部使用] 并发调用时强制session隔离，避免多个子Agent共享同一个session"
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
        workspace_path: Optional[str] = None,  # ✅ 新参数：工作目录
        session_id: Optional[str] = None,
        force_new_session: bool = False,
        _force_isolated_session: bool = False,  # ⚠️ 内部使用：并发时强制隔离
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
        effective_context = context_str or context_supplement
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

            # ✅ 不再验证 memory_manager，让子Agent自己创建

            # ✅ 1. Session处理：确定session_id和对话历史
            conversation_history = []
            is_new_session = False

            if session_id:
                # 明确指定了session_id，继续已有session
                session = session_manager.get_session(session_id)
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
                if session.child_mode != target_mode:
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

            # 3. 构建子 Agent 请求：ReActAgent 会自行构建系统提示，因此把任务、
            # 补充上下文和规范化后的工作目录作为本轮用户请求一起传入。
            parent_resource_lines = await self._collect_parent_resource_lines(context)
            child_request_prompt = self._build_child_request_prompt(
                goal=effective_goal,
                context=effective_context,
                workspace_path=effective_workspace,
                target_mode=target_mode,
                parent_resource_lines=parent_resource_lines,
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
            sub_agent = ReActAgent(
                max_iterations=120,  # 子Agent默认120次迭代
                enable_memory=True,  # ✅ 启用记忆（子Agent会自动创建 UnifiedMemoryManager）
                tool_registry=tool_executor.tool_registry if tool_executor else None  # ✅ 传递工具注册表
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

            # 5. 执行子Agent（传入所有必要参数）
            # ✅ 双重保障机制（参考Hermes）：
            #   - 系统提示（assistant_prompt.py已包含关键要求）
            #   - 用户消息（effective_goal）仍是纯净的原始任务
            result_events = []
            with model_chain_context:
                async for event in sub_agent.analyze(
                    user_query=child_request_prompt,
                    session_id=session_id if session_id else None,  # ✅ 传递session_id用于会话恢复
                    manual_mode=target_mode,  # ✅ 强制使用指定模式（如 query）
                    enhance_with_history=True,  # ✅ 启用记忆增强
                    initial_messages=conversation_history if conversation_history else None,  # ✅ 传入历史
                    user_identifier=None  # ⚠️ 使用模式专属记忆（不跨模式共享）
                ):
                    result_events.append(event)

            # 7. 提取最终结果
            final_result = self._extract_final_result(result_events)

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

            # ✅ 8. 保存/更新session
            self._update_session(
                session_id=session_id,
                parent_mode=parent_mode,
                child_mode=target_mode,
                user_query=effective_goal,  # ✅ 使用effective_goal
                assistant_answer=final_result["answer"],
                result_events=result_events
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

            # ✅ 添加思考过程到metadata（父Agent可以使用）
            if "thought" in final_result.get("data", {}):
                enhanced_metadata["thought"] = final_result["data"]["thought"]
            if "reasoning" in final_result.get("data", {}):
                enhanced_metadata["reasoning"] = final_result["data"]["reasoning"]

            succeeded = final_result["status"] == "success"
            return {
                "status": final_result["status"],
                "success": succeeded,
                "result": final_result["answer"],  # ✅ LLM的最终答案（最重要）
                "data": structured_data,
                "metadata": enhanced_metadata,
                "summary": (
                    f"{self._get_mode_name(target_mode)}已完成任务"
                    if succeeded
                    else f"{self._get_mode_name(target_mode)}执行失败"
                )
            }

        except Exception as e:
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

    async def _collect_parent_resource_lines(self, context) -> List[str]:
        """列出父会话已登记文件资源，供子 Agent 直接按路径读取。

        子 Agent 使用独立 session_id，查不到父会话的资源目录；把父会话
        catalog 中的真实文件路径随任务一起下发，子 Agent 的沙箱会按
        白名单把这些文件 ro-bind 进执行环境。
        """
        try:
            executor = getattr(context, "tool_executor", None)
            service = getattr(executor, "resource_service", None)
            parent_session_id = getattr(getattr(executor, "memory_manager", None), "session_id", None)
            if service is None or not parent_session_id:
                return []

            from app.agent.resources.resource_map import resource_access_path
            from app.utils.path_config import get_data_registry

            registry_root = str(get_data_registry())
            page = await service.list_resources(parent_session_id, limit=500)
            lines = []
            seen_paths = set()
            for stored in page.resources:
                if stored.kind not in {"file", "artifact"}:
                    continue
                access_path = resource_access_path(stored)
                if not access_path or not access_path.startswith(registry_root):
                    continue
                if access_path in seen_paths:
                    continue
                seen_paths.add(access_path)
                lines.append(f"- {stored.label} -> {access_path}")
                if len(lines) >= 50:
                    break
            return lines
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

        # 父会话已登记文件（上传附件等）；子会话无法查询父会话资源目录，
        # 这些真实路径可直接用于 read_file / execute_python（沙箱按白名单挂载）。
        if parent_resource_lines:
            parts.append("**父会话可用文件**（可直接按路径读取，勿编造其他路径）:\n")
            parts.extend(parent_resource_lines)
            parts.append("")

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
    ) -> str:
        """Backward-compatible alias for the child request prompt builder."""
        return self._build_child_request_prompt(
            goal=goal,
            context=context,
            workspace_path=workspace_path,
            target_mode=target_mode,
            parent_resource_lines=parent_resource_lines,
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

    def _extract_file_paths(self, events: list) -> list:
        """从事件流中提取所有file_path"""
        file_paths = []
        for event in events:
            # 从observation中提取
            if event.get("type") == "observation":
                if "file_path" in event:
                    file_paths.append(event["file_path"])
                # 从data字段中提取
                if "data" in event and isinstance(event["data"], dict):
                    if "file_path" in event["data"]:
                        file_paths.append(event["data"]["file_path"])
                    # 从data字段中的file_paths数组提取
                    if "file_paths" in event["data"] and isinstance(event["data"]["file_paths"], list):
                        file_paths.extend(event["data"]["file_paths"])
                    # 从 metadata.file_path 中提取
                    if "metadata" in event["data"] and isinstance(event["data"]["metadata"], dict):
                        metadata = event["data"]["metadata"]
                        if isinstance(metadata.get("file_path"), str):
                            file_paths.append(metadata["file_path"])
        return list(set(file_paths))  # 去重

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
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"{parent_mode}__to__{child_mode}__{timestamp}"

    def _update_session(
        self,
        session_id: str,
        parent_mode: str,
        child_mode: str,
        user_query: str,
        assistant_answer: str,
        result_events: List[Dict]
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
