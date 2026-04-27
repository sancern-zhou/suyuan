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

from typing import Dict, Any, Literal, Optional, List
import structlog
from datetime import datetime

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.agent.session.session_manager import get_session_manager
from app.agent.session.models import Session

logger = structlog.get_logger()

# 获取全局session管理器
session_manager = get_session_manager()

# ⚠️ 支持5种模式：assistant, code, query, report, social
AgentMode = Literal["assistant", "code", "query", "report", "social"]


class CallSubAgentTool(LLMTool):
    """
    调用子Agent的工具（双向通用）

    用法：
    - Social Agent调用Query Agent：call_sub_agent(target_mode="query", ...)
    - Social Agent调用Report Agent：call_sub_agent(target_mode="report", ...)
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
            "description": "调用另一个Agent模式作为子Agent执行任务（支持session连续对话）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_mode": {
                        "type": "string",
                        "enum": ["assistant", "code", "query", "report", "social"],
                        "description": "目标Agent模式（assistant=助手, social=社交, query=问数, report=报告, code=编程）"
                    },
                    # ✅ 新设计：goal（必需）- 原始任务描述
                    "goal": {
                        "type": "string",
                        "description": "⚠️ 任务目标（必须完整保留所有参数）：文件路径、时间范围、sheet索引、城市名称等所有具体参数。禁止摘要化或省略任何细节。\n\n示例：'更新Excel文件 /tmp/会商文件/全国各省份污染物累计平均.xlsx（第五个sheet，时间段：2026年1-3月和2025年1-3月）'"
                    },
                    # ✅ 新设计：context_str（可选）- 补充上下文
                    "context_str": {
                        "type": "string",
                        "description": "补充上下文（可选）：技能名称、操作步骤、背景信息等。如：'按照AQI技能文档的步骤执行'或'用户之前查询过NO2数据，现在查询AQI数据'"
                    },
                    # ✅ 新设计：workspace_path（可选）- 工作目录
                    "workspace_path": {
                        "type": "string",
                        "description": "工作目录路径（可选）：文件所在目录，用于帮助子Agent定位文件。如：'/tmp/会商文件'"
                    },
                    # ⚠️ 向后兼容：保留旧参数名
                    "task_description": {
                        "type": "string",
                        "description": "⚠️ [向后兼容] 等同于goal参数。新代码请使用goal参数。"
                    },
                    "context_supplement": {
                        "type": "string",
                        "description": "⚠️ [向后兼容] 等同于context_str参数。新代码请使用context_str参数。"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "子Agent会话ID（可选，一般不需要传递）：系统会自动复用最近的session。只有需要指定特定session时才传递。"
                    },
                    "force_new_session": {
                        "type": "boolean",
                        "description": "是否强制创建新会话（可选，默认false）：设为true时会创建新的session，而不是复用最近的session。当用户明确开始新话题时使用。"
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
        **kwargs  # ✅ 捕获额外参数
    ) -> Dict[str, Any]:
        """
        执行子Agent调用（支持session连续对话）

        Args:
            context: ExecutionContext（包含memory_manager等依赖）
            target_mode: 目标Agent模式（"assistant" | "query" | "code" | "report" | "social"）
            goal: ⚠️ 任务目标（推荐）：必须完整保留所有参数（文件路径、时间范围等）
            task_description: ⚠️ [向后兼容] 等同于goal
            context_str: 补充上下文（推荐）：技能名称、操作步骤等
            context_supplement: ⚠️ [向后兼容] 等同于context_str
            workspace_path: 工作目录路径（可选）
            session_id: 可选，子Agent会话ID（传入则继续已有对话）
            force_new_session: 是否强制创建新会话

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

        try:
            # 获取父Agent模式
            parent_mode = self._get_parent_mode(context)

            logger.info(
                "calling_sub_agent",
                parent_mode=parent_mode,
                target_mode=target_mode,
                goal=effective_goal[:100] if effective_goal else "",
                context=effective_context[:50] if effective_context else "",
                workspace_path=workspace_path,
                provided_session_id=session_id,
                force_new_session=force_new_session,
                will_attempt_auto_reuse=session_id is None and not force_new_session
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
            elif force_new_session:
                # 强制创建新session
                session_id = self._generate_session_id(parent_mode, target_mode)
                is_new_session = True
                logger.info(f"强制创建新session: {session_id}")
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

            # 3. 构建子Agent系统提示（参考Hermes设计：分离goal和context）
            # 注意：当前 ReActAgent.analyze 不支持 system_prompt_override 参数
            # 关键要求已添加到 assistant_prompt.py 中
            child_system_prompt = self._build_child_system_prompt(
                goal=effective_goal,
                context=effective_context,
                workspace_path=workspace_path,
                target_mode=target_mode
            )
            logger.debug(
                "child_system_prompt_built",
                target_mode=target_mode,
                prompt_preview=child_system_prompt[:200] if child_system_prompt else ""
            )

            # 4. 创建临时子Agent实例（复用父Agent的配置）
            # ⚠️ 关键：使用 ReActAgent.analyze() 以获得完整的记忆增强功能
            # ⚠️ 不传递 memory_manager，让子Agent自己创建 UnifiedMemoryManager
            sub_agent = ReActAgent(
                max_iterations=30,  # 子Agent默认30次迭代
                enable_memory=True,  # ✅ 启用记忆（子Agent会自动创建 UnifiedMemoryManager）
                tool_registry=tool_executor.tool_registry if tool_executor else None  # ✅ 传递工具注册表
            )

            # 5. 执行子Agent（传入所有必要参数）
            # ✅ 双重保障机制（参考Hermes）：
            #   - 系统提示（assistant_prompt.py已包含关键要求）
            #   - 用户消息（effective_goal）仍是纯净的原始任务
            result_events = []
            async for event in sub_agent.analyze(
                user_query=effective_goal,  # ✅ 纯净的原始任务（Hermes方案）
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
                "data_ids": self._extract_data_ids(result_events),
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
                "data_ids_count": len(structured_data["data_ids"]),
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

            return {
                "status": "success",
                "success": True,
                "result": final_result["answer"],  # ✅ LLM的最终答案（最重要）
                "data": structured_data,
                "metadata": enhanced_metadata,
                "summary": f"{self._get_mode_name(target_mode)}已完成任务"
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

    def _build_child_system_prompt(
        self,
        goal: str,
        context: Optional[str] = None,
        workspace_path: Optional[str] = None,
        target_mode: str = "assistant"
    ) -> str:
        """
        构建子Agent系统提示（参考Hermes设计：分离goal和context）

        Args:
            goal: 任务目标（完整的原始任务，包含所有参数）
            context: 补充上下文（可选）
            workspace_path: 工作目录路径（可选）
            target_mode: 目标Agent模式

        Returns:
            子Agent系统提示字符串
        """
        parts = [
            "你是作为子Agent被调用，专注完成指定的任务。\n",
            f"**任务目标**:\n{goal}\n"
        ]

        # 添加补充上下文（如果有）
        if context and context.strip():
            parts.append(f"**补充上下文**:\n{context}\n")

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
            "code": "\n专注完成上述编程任务。\n",
        }

        hint = mode_hints.get(target_mode, "")
        parts.append(hint)

        return "\n".join(parts)

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
            "code": "编程Agent",
        }
        return mode_names.get(mode, mode)

    def _extract_data_ids(self, events: list) -> list:
        """从事件流中提取所有data_id"""
        data_ids = []
        for event in events:
            # 从observation中提取
            if event.get("type") == "observation":
                if "data_id" in event:
                    data_ids.append(event["data_id"])
                # 从data字段中提取
                if "data" in event and isinstance(event["data"], dict):
                    if "data_id" in event["data"]:
                        data_ids.append(event["data"]["data_id"])
                    # 从data字段中的data_ids数组提取
                    if "data_ids" in event["data"] and isinstance(event["data"]["data_ids"], list):
                        data_ids.extend(event["data"]["data_ids"])
                    # ✅ 从metadata.data_id中提取（支持嵌套格式）
                    if "metadata" in event["data"] and isinstance(event["data"]["metadata"], dict):
                        metadata = event["data"]["metadata"]
                        if "data_id" in metadata:
                            # 处理字符串格式
                            if isinstance(metadata["data_id"], str):
                                data_ids.append(metadata["data_id"])
                            # 处理字典格式 {"data_id": "...", "file_path": "..."}
                            elif isinstance(metadata["data_id"], dict):
                                if "data_id" in metadata["data_id"]:
                                    data_ids.append(metadata["data_id"]["data_id"])
        return list(set(data_ids))  # 去重

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

        # 提取并添加data_ids（visual_ids不再提取，社交模式用chart_urls渲染图片）
        data_ids = self._extract_data_ids(result_events)

        # 去重后添加
        existing_data_ids = set(session.data_ids)
        for data_id in data_ids:
            if data_id not in existing_data_ids:
                session.data_ids.append(data_id)

        # 保存session（更新时间戳）
        session_manager.save_session(session, update_timestamp=True)

        logger.info(
            "session_updated",
            session_id=session_id,
            conversation_length=len(session.conversation_history),
            data_count=len(session.data_ids)
        )
