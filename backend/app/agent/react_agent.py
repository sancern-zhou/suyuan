"""
ReAct Agent - 主类

真正的 Agent 架构：LLM 自主决策，动态工具调用，无固定工作流。

核心特点：
1. 真正的 ReAct 循环：Thought → Action → Observation
2. LLM 自主决策：每一步由 LLM 决定做什么
3. 动态工具选择：根据需要调用工具，不执行固定流程
4. 三层记忆系统：Working + Session + LongTerm
5. 上下文管理：自动压缩、外部化、RAG增强
"""

from typing import Dict, Any, AsyncGenerator, Optional, Tuple, List
from datetime import datetime, timedelta
import uuid
import structlog
import asyncio

from .memory.hybrid_manager import HybridMemoryManager
from .core.loop import ReActLoop
from .core.planner import ReActPlanner
from .core.executor import ToolExecutor

logger = structlog.get_logger()


class ReActAgent:
    """
    ReAct Agent - 大气环境数据查询与分析智能体

    真正的 Agent 实现（完全LLM自主决策）：
    - ✅ LLM 理解用户意图，自主决策每一步行动
    - ✅ 按需调用工具，不执行不需要的步骤
    - ✅ 动态适应简单和复杂查询
    - ✅ 多专家系统路由由LLM的NLP意图解析决定
    - ✅ 工具参数选择（如forward_simulation）由LLM根据查询自动决定
    - ❌ 无关键词匹配决策
    - ❌ 无固定工作流
    - ❌ 无硬编码规则
    """

    def __init__(
        self,
        max_iterations: int = 30,  # ✅ 默认30次（适应复杂分析任务）
        max_working_memory: int = 20,
        working_context_limit: int = 50000,
        large_data_threshold: int = 1000,
        tool_registry: Optional[Dict] = None,
        session_ttl_hours: int = 12,
        enable_memory: bool = True,  # ✅ 新增：默认启用记忆
        memory_manager: Optional["UnifiedMemoryManager"] = None  # ✅ 新增
    ):
        """
        初始化 ReAct Agent

        Args:
            max_iterations: 最大迭代次数
            max_working_memory: 工作记忆最大迭代数（默认20，详细记录）
            working_context_limit: 工作记忆拼接的上下文字符上限
            large_data_threshold: 大数据阈值（字符数）
            tool_registry: 工具注册表（可选）
            session_ttl_hours: 会话空闲时间，超时将自动清理（小时）
            enable_memory: 是否启用长期记忆（默认True）
            memory_manager: 统一记忆管理器（可选，如果不提供则自动创建）
        """
        self.max_iterations = max_iterations
        self.max_working_memory = max_working_memory
        self.working_context_limit = working_context_limit
        self.large_data_threshold = large_data_threshold
        self._session_ttl = timedelta(hours=session_ttl_hours) if session_ttl_hours > 0 else None
        self._session_store: Dict[str, Dict[str, Any]] = {}
        # ✅ 改用细粒度锁（按 session_id 分组），不同 session 可以并发
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()  # 用于保护 _session_locks 字典本身

        # ✅ 新增：记忆管理器
        self.enable_memory = enable_memory
        self.memory_manager = memory_manager

        if enable_memory and not memory_manager:
            from .memory.unified_memory_manager import UnifiedMemoryManager
            self.memory_manager = UnifiedMemoryManager()
            logger.info("unified_memory_manager_created")

        # 初始化任务列表（用于 TodoWrite 工具）
        from .task.todo_models import TodoList
        self.task_list = TodoList()

        # 初始化工具执行器
        self.executor = ToolExecutor(tool_registry=tool_registry)

        # 初始化 LLM 规划器
        self.planner = ReActPlanner(tool_registry=tool_registry)

        # 将planner注入到executor中（用于call_sub_agent）
        self.executor.llm_planner = self.planner

        # 注册工作流工具（延迟注册需要依赖注入的工具）
        self._register_workflow_tools()

        logger.info(
            "react_agent_initialized",
            max_iterations=max_iterations,
            max_working_memory=max_working_memory,
            working_context_limit=working_context_limit,
            tool_count=len(self.executor.tool_registry),
            enable_memory=enable_memory
        )

    def _register_workflow_tools(self):
        """
        注册工作流工具到工具注册表

        工作流工具已通过 workflow_tool 模块自动注册，
        此方法保留用于未来需要依赖注入的工作流工具。
        """
        # 工作流工具现在通过 app.tools.workflow 模块自动注册
        # 复杂的工作流（standard_analysis_workflow、quick_tracing_workflow）已删除
        # 现在使用任务清单驱动的流程（Agent 读取 md 模板 + TodoWrite）
        pass

    async def analyze(
        self,
        user_query: str,
        session_id: Optional[str] = None,
        enhance_with_history: bool = True,
        max_iterations: Optional[int] = None,
        reset_session: bool = False,
        knowledge_base_ids: Optional[list] = None,
        enable_reasoning: bool = False,
        is_interruption: bool = False,
        initial_messages: Optional[List[Dict[str, Any]]] = None,
        manual_mode: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        user_identifier: Optional[str] = None,  # ✅ 新增：用户标识（可选）
        social_memory_store: Optional[Any] = None,  # ✅ 新增：社交模式外部传入的memory_store（用户隔离）
        social_user_preferences: Optional[dict] = None,  # ✅ 新增：社交模式用户偏好（仅social模式使用）
        social_soul_file_path: Optional[str] = None,  # ✅ 新增：社交模式 soul.md 文件路径
        social_user_file_path: Optional[str] = None,  # ✅ 新增：社交模式 USER.md 文件路径
        social_heartbeat_file_path: Optional[str] = None,  # ✅ 新增：社交模式 HEARTBEAT.md 文件路径
        social_soul_context: Optional[str] = None,  # ✅ 新增：社交模式 soul.md 内容（助理灵魂档案，仅social模式使用）
        social_user_context: Optional[str] = None  # ✅ 新增：社交模式用户上下文（USER.md内容，仅social模式使用）
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        分析用户查询（主入口）

        Args:
            user_query: 用户自然语言查询
            session_id: 会话ID（可选，用于会话恢复）
            enhance_with_history: 是否使用长期记忆增强
            max_iterations: 本次执行的最大迭代数
            reset_session: 是否强制重置会话
            knowledge_base_ids: 知识库ID列表（暂未启用，预留参数）
            enable_reasoning: 是否启用思考模式（默认False，启用后会显示LLM的推理过程，适用于MiniMax等支持思考模式的模型）
            is_interruption: 是否为用户中断后的对话（用户暂停后继续对话时为True）
            initial_messages: 历史消息列表（用于会话恢复，继续之前的对话）
            manual_mode: 双模式架构（assistant | expert，None则使用默认expert模式）
            attachments: 附件列表 [{file_id, name, type, url}]
            user_identifier: 用户标识（用于跨会话记忆，可选）
            social_memory_store: 社交模式外部传入的memory_store（已含用户隔离），避免社交模式走UnifiedMemoryManager的共享路径
            social_user_preferences: 社交模式用户偏好配置（仅social模式使用，用于动态提示词）
            social_soul_file_path: 社交模式 soul.md 文件路径（仅social模式使用）
            social_user_file_path: 社交模式 USER.md 文件路径（仅social模式使用）
            social_soul_context: 社交模式 soul.md 内容（助理灵魂档案，仅social模式使用）
            social_user_context: 社交模式用户上下文内容（USER.md，仅social模式使用，包含用户档案信息）

        Yields:
            流式事件：
            - type: "start" | "thought" | "action" | "observation" | "complete" | "error"
            - data: 事件数据
        """
        # ✅ 新增：构建user_id（根据用户反馈）
        memory_store = None
        memory_context = ""
        unified_user_id = None

        # ✅ 社交模式：使用外部传入的social_memory_store（用户隔离），不走UnifiedMemoryManager
        if self.enable_memory and manual_mode == "social" and social_memory_store is not None:
            memory_store = social_memory_store
            # ✅ 使用 ActiveMemoryRetriever 按关键词召回相关记忆（而非整块注入）
            try:
                from .memory.active_memory_retriever import ActiveMemoryRetriever

                memory_context = ActiveMemoryRetriever().retrieve(
                    memory_store=social_memory_store,
                    query=user_query,
                    recent_messages=initial_messages or []
                )
            except ModuleNotFoundError as e:
                logger.warning("active_memory_retriever_missing_fallback", error=str(e))
                memory_context = social_memory_store.get_memory_context()
            unified_user_id = None  # 社交模式不走通用记忆整合

        elif self.enable_memory and manual_mode:
            if user_identifier and manual_mode != "social":
                # 有user_identifier且非社交模式：跨模式共享记忆（同一用户在所有模式下共享同一个记忆文件）
                unified_user_id = f"{user_identifier}:shared"
                memory_mode = "shared"  # ✅ 使用特殊的 shared 模式，实现跨模式共享
            else:
                # 无user_identifier：模式内共享记忆（每个模式独立记忆，模式之间隔离）
                # ✅ 修复：直接使用 "global" 作为 user_id，让 memory_store 创建模式专属记忆
                unified_user_id = "global"
                memory_mode = manual_mode or "expert"  # ✅ 使用当前模式，实现模式内共享

            # ✅ 加载记忆上下文（用于系统提示词注入，不修改user_query）
            memory_context = None
            if unified_user_id:
                memory_store = await self.memory_manager.get_user_memory(
                    user_id=unified_user_id,
                    mode=memory_mode
                )
                memory_context = memory_store.get_memory_context()  # 从快照获取记忆

        # ✅ 统一：记录记忆注入日志
        if memory_context:
            memory_file_path = str(memory_store.memory_file.resolve()) if memory_store else ""
            logger.info(
                "memory_context_prepared",
                user_id=unified_user_id or "social_external",
                mode=manual_mode,
                context_length=len(memory_context),
                memory_file_path=memory_file_path,
                memory_preview=memory_context[:200] if memory_context else ""
            )

        # ✅ 如果有附件，添加到查询中（保存到对话历史，确保后续能访问文件）
        if attachments and len(attachments) > 0:
            attachment_info = "\n\n**用户上传的附件**：\n"
            for i, att in enumerate(attachments, 1):
                att_type = att.get("type", "file")
                att_name = att.get("name", "unknown")
                att_file_id = att.get("file_id")
                att_url = att.get("url") or ""

                # 对于图片和有file_id的附件，优先使用本地文件路径
                # 因为analyze_image等工具可以直接读取本地文件
                if att_file_id and (att_type == "image" or not att_url.startswith("/")):
                    try:
                        from app.db.database import async_session
                        from app.knowledge_base.models import UploadedFile
                        from sqlalchemy import select

                        async with async_session() as db:
                            result = await db.execute(
                                select(UploadedFile.file_path).where(UploadedFile.id == att_file_id)
                            )
                            path = result.scalar_one_or_none()
                            if path:
                                att_url = path
                                logger.info("using_local_file_path", file_id=att_file_id, path=path)
                    except Exception as e:
                        logger.warning("failed_to_get_file_path", file_id=att_file_id, error=str(e))

                if att_type == "image":
                    attachment_info += f"{i}. 图片: {att_name}\n"
                    attachment_info += f"   路径: {att_url}\n"
                else:
                    attachment_info += f"{i}. 文件: {att_name}\n"
                    attachment_info += f"   路径: {att_url}\n"
            user_query = user_query + attachment_info  # ✅ 添加到查询中（保存到对话历史）

            logger.info(
                "attachments_added_to_query",
                count=len(attachments),
                attachment_types=[a.get("type") for a in attachments],
                attachment_urls=[a.get("url") for a in attachments]
            )

        actual_session_id, memory_manager, created_new = await self._get_or_create_session(
            session_id,
            reset_session
        )

        # Update executor's memory_manager and task_list to enable DataContextManager
        self.executor.set_memory_manager(memory_manager, task_list=self.task_list)

        # ✅ 创建记忆快照
        # 社交模式：使用外部传入的 social_memory_store
        # 其他模式：通过 UnifiedMemoryManager 获取
        if self.enable_memory and memory_store:
            try:
                memory_store.create_snapshot()  # 创建独立副本
            except Exception as e:
                logger.warning("failed_to_create_memory_snapshot", error=str(e))

        iteration_limit = max_iterations or self.max_iterations

        logger.info(
            "analysis_started",
            session_id=actual_session_id,
            query=user_query[:100],
            iteration_limit=iteration_limit,
            reused_session=not created_new,
            mode="react",
            manual_mode=manual_mode or "expert",
            knowledge_base_ids=knowledge_base_ids  # 记录知识库ID
        )

        try:
            # 使用标准 ReAct 循环（LLM 自主决策调用工具）
            # 工具池包括：
            # - 原子工具（基础能力）
            # - 工作流工具（高级能力）
            # - 任务清单驱动流程（Agent 读取 md 模板 + TodoWrite）
            react_loop = ReActLoop(
                memory_manager=memory_manager,
                llm_planner=self.planner,
                tool_executor=self.executor,
                max_iterations=iteration_limit,
                stream_enabled=True,
                is_interruption=is_interruption,
                enable_reasoning=enable_reasoning,
                knowledge_base_ids=knowledge_base_ids  # ✅ 传递知识库ID列表
            )

            # ✅ 设置记忆上下文到上下文构建器（用于系统提示词注入）
            if memory_context:
                react_loop.context_builder.memory_context = memory_context
                logger.debug(
                    "memory_context_set_to_context_builder",
                    context_length=len(memory_context)
                )

            # ✅ 设置记忆文件路径到上下文构建器（所有模式）
            if memory_store:
                react_loop.context_builder.memory_file_path = str(memory_store.memory_file.resolve())
                logger.debug(
                    "memory_file_path_set_to_context_builder",
                    memory_file_path=react_loop.context_builder.memory_file_path,
                    mode=manual_mode
                )

            # ✅ 设置用户偏好到上下文构建器（仅social模式使用）
            # 同时设置记忆工具的用户上下文（确保 remember_fact 等工具写入正确的用户隔离路径）
            if manual_mode == "social" and social_user_preferences:
                react_loop.context_builder.user_preferences = social_user_preferences
                react_loop.context_builder.soul_file_path = social_soul_file_path  # ✅ 传递 soul.md 文件路径
                react_loop.context_builder.user_file_path = social_user_file_path  # ✅ 传递 USER.md 文件路径
                react_loop.context_builder.heartbeat_file_path = social_heartbeat_file_path  # ✅ 传递 HEARTBEAT.md 文件路径
                react_loop.context_builder.soul_context = social_soul_context  # ✅ 传递 soul.md 内容
                react_loop.context_builder.user_context = social_user_context  # ✅ 传递用户上下文（USER.md）

                # ✅ 设置记忆工具的用户上下文（确保写入正确的用户隔离路径）
                from app.tools.social.remember_fact.tool import RememberFactTool
                from app.tools.social.replace_memory.tool import ReplaceMemoryTool
                from app.tools.social.remove_memory.tool import RemoveMemoryTool
                social_user_id = user_identifier  # social_user_id 即 user_identifier
                RememberFactTool.set_memory_context("social", social_user_id)
                ReplaceMemoryTool.set_memory_context("social", social_user_id)
                RemoveMemoryTool.set_memory_context("social", social_user_id)

                logger.debug(
                    "social_memory_context_set",
                    memory_file_path=react_loop.context_builder.memory_file_path,
                    soul_file_path=react_loop.context_builder.soul_file_path,  # ✅ 新增日志
                    user_file_path=react_loop.context_builder.user_file_path,  # ✅ 新增日志
                    has_user_preferences=social_user_preferences is not None,
                    has_soul_context=social_soul_context is not None,  # ✅ 新增日志
                    has_user_context=social_user_context is not None,  # ✅ 新增日志
                    social_user_id=social_user_id
                )

            async for event in react_loop.run(
                user_query=user_query,  # ✅ 原始用户查询（不包含记忆增强）
                enhance_with_history=enhance_with_history,
                initial_messages=initial_messages,
                manual_mode=manual_mode
            ):
                # 捕获office_document事件并保存到会话存储（用于历史对话PDF预览恢复）
                if event.get("type") == "office_document" and event.get("data"):
                    office_doc_data = event["data"]
                    # 确保session_store中有office_documents列表
                    if actual_session_id not in self._session_store:
                        self._session_store[actual_session_id] = {}
                    if "office_documents" not in self._session_store[actual_session_id]:
                        self._session_store[actual_session_id]["office_documents"] = []

                    # 提取关键字段并保存
                    doc_entry = {
                        "pdf_preview": office_doc_data.get("pdf_preview"),
                        # "markdown_preview": office_doc_data.get("markdown_preview"),  # 暂时注释：历史会话恢复功能待实现
                        "file_path": office_doc_data.get("file_path"),
                        "generator": office_doc_data.get("generator"),
                        "summary": office_doc_data.get("summary"),
                        "timestamp": office_doc_data.get("timestamp", datetime.now().isoformat())
                    }

                    # 检查是否已存在（避免重复）
                    file_path = doc_entry["file_path"]
                    existing = self._session_store[actual_session_id]["office_documents"]
                    if not any(d.get("file_path") == file_path for d in existing):
                        existing.append(doc_entry)
                        logger.info(
                            "office_document_saved_to_session",
                            session_id=actual_session_id,
                            file_path=file_path,
                            generator=doc_entry["generator"],
                            total_documents=len(existing)
                        )

                yield event

        except Exception as e:
            logger.error(
                "analysis_fatal_error",
                session_id=actual_session_id,
                error=str(e),
                exc_info=True
            )

            yield {
                "type": "fatal_error",
                "data": {
                    "error": str(e),
                    "session_id": actual_session_id,
                    "timestamp": datetime.now().isoformat()
                }
            }
        finally:
            # ✅ 统一保存会话到数据库（每次分析完成后）
            if actual_session_id:
                try:
                    from app.agent.session import get_session_manager
                    from dataclasses import asdict
                    session_manager = get_session_manager()

                    # ✅ 从数据库加载 session
                    session = await session_manager.load_session(actual_session_id)

                    if session:
                        # 同步 memory.session.conversation_history 到 Session 对象
                        if actual_session_id in self._session_store:
                            entry = self._session_store[actual_session_id]
                            memory_manager = entry.get("memory")
                            if memory_manager and hasattr(memory_manager, "session"):
                                # 将 ConversationTurn dataclass 转换为字典
                                conversation_history_dicts = [
                                    asdict(turn) for turn in memory_manager.session.conversation_history
                                ]
                                session.conversation_history = conversation_history_dicts
                                logger.debug(
                                    "conversation_history_converted",
                                    session_id=actual_session_id,
                                    message_count=len(conversation_history_dicts)
                                )

                            # ✅ 从 _session_store 读取 agent.py 收集的数据
                            collected_data_ids = entry.get("collected_data_ids", [])
                            collected_visuals = entry.get("collected_visuals", [])
                            conversation_history_compressed = entry.get("conversation_history_compressed")

                            # 设置 data_ids 和 visual_ids
                            if collected_data_ids:
                                session.data_ids = collected_data_ids
                                logger.debug("data_ids_set_from_store", count=len(collected_data_ids))

                            if collected_visuals:
                                session.visual_ids = [v.get("id") for v in collected_visuals if v.get("id")]
                                # ✅ 保存完整的可视化数据到 metadata
                                session.metadata["visualizations"] = collected_visuals
                                session.metadata["visuals_count"] = len(collected_visuals)
                                logger.info(
                                    "visualizations_set_in_metadata",
                                    session_id=actual_session_id,
                                    visuals_count=len(collected_visuals)
                                )

                            # 如果有压缩的历史，使用压缩版本
                            if conversation_history_compressed:
                                session.conversation_history = conversation_history_compressed

                            # 同步 office_documents 到会话对象
                            office_docs = entry.get("office_documents", [])
                            if office_docs:
                                session.office_documents = office_docs

                            # 处理错误信息
                            if entry.get("has_error"):
                                session.error = {
                                    "type": entry.get("error_type", "unknown"),
                                    "message": entry.get("error_message", "Unknown error"),
                                    "timestamp": datetime.now().isoformat()
                                }

                        # 保存会话
                        await session_manager.save_session(session)
                        logger.info(
                            "session_saved_after_analysis",
                            session_id=actual_session_id,
                            message_count=len(session.conversation_history),
                            metadata_keys=list(session.metadata.keys()) if session.metadata else []
                        )
                        logger.info(
                            "session_saved_after_analysis",
                            session_id=actual_session_id,
                            message_count=len(session.conversation_history)
                        )
                except Exception as e:
                    logger.warning(
                        "failed_to_save_session_after_analysis",
                        session_id=actual_session_id,
                        error=str(e)
                    )

            # ✅ 后台记忆整合（新增，与上下文压缩完全分离）
            # ⚠️ 社交模式的记忆整合由 agent_bridge.py 负责（使用用户隔离的 social_memory_store），
            #    此处只为非社交模式触发整合
            if unified_user_id and manual_mode and manual_mode != "social":
                try:
                    asyncio.create_task(
                        self._background_memory_consolidation(
                            actual_session_id,
                            unified_user_id,
                            manual_mode
                        )
                    )
                except Exception as e:
                    logger.warning(
                        "failed_to_schedule_memory_consolidation",
                        error=str(e)
                    )

            # ✅ 清理记忆快照
            # 社交模式：使用外部传入的 social_memory_store
            # 其他模式：通过 UnifiedMemoryManager 获取
            if memory_store:
                try:
                    memory_store.cleanup_snapshot()
                except Exception as e:
                    logger.warning("failed_to_cleanup_snapshot", error=str(e))

            # ✅ 清理记忆工具的用户上下文（社交模式）
            if manual_mode == "social":
                try:
                    from app.tools.social.remember_fact.tool import RememberFactTool
                    from app.tools.social.replace_memory.tool import ReplaceMemoryTool
                    from app.tools.social.remove_memory.tool import RemoveMemoryTool
                    RememberFactTool.clear_memory_context()
                    ReplaceMemoryTool.clear_memory_context()
                    RemoveMemoryTool.clear_memory_context()
                except Exception as e:
                    logger.warning("failed_to_clear_social_memory_context", error=str(e))

            await self._mark_session_used(actual_session_id)

    def register_tool(self, name: str, func):
        """
        注册新工具

        Args:
            name: 工具名称
            func: 工具函数（async callable）
        """
        self.executor.register_tool(name, func)

        logger.info(
            "tool_registered_to_agent",
            tool_name=name,
            total_tools=len(self.executor.tool_registry)
        )

    def get_available_tools(self) -> list:
        """
        获取可用工具列表

        Returns:
            工具名称列表
        """
        return self.executor.list_available_tools()

    def refresh_tools(self):
        """
        刷新工具注册表（重新加载所有工具）

        使用场景：
        - 动态添加/删除工具后需要刷新 Agent 实例
        - 工具注册表更新后需要重新加载
        """
        self.executor.refresh_tools()
        logger.info(
            "agent_tools_refreshed",
            agent_id=id(self),
            tool_count=len(self.executor.tool_registry)
        )

    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        获取工具详细信息

        Args:
            tool_name: 工具名称

        Returns:
            工具信息字典，如果不存在返回 None
        """
        return self.executor.get_tool_info(tool_name)

    # ========================================================================
    # 记忆整合方法（统一记忆系统 - Agent模式）
    # ========================================================================

    async def _background_memory_consolidation(
        self,
        session_id: str,
        unified_user_id: str,
        mode: str
    ) -> None:
        """
        后台记忆整合任务（不阻塞主对话）

        核心特性：
        - 异步执行，不阻塞主对话
        - 只基于消息数量触发（与上下文压缩完全分离）
        - 使用Agent模式调用工具更新记忆
        - 快照隔离：后台更新不影响当前对话

        Args:
            session_id: 会话ID
            unified_user_id: 统一用户ID（格式：{mode}:{user_identifier}:{shared|unique}）
            mode: 模式标识
        """
        # 预先导入工具类，确保 finally 块中可以访问
        from app.tools.social.remember_fact.tool import RememberFactTool
        from app.tools.social.replace_memory.tool import ReplaceMemoryTool
        from app.tools.social.remove_memory.tool import RemoveMemoryTool

        try:
            # 1. 获取会话历史
            if session_id not in self._session_store:
                return

            session_data = self._session_store[session_id]
            memory_manager = session_data.get("memory")
            if not memory_manager:
                return

            messages = memory_manager.session.get_messages_for_llm()
            if not messages:
                return

            # 2. 检查是否需要整合（只基于消息数量，不检查token）
            offset = await self.memory_manager.get_consolidation_offset(unified_user_id)
            new_message_count = len(messages) - offset

            # ⚠️ 关键：只检查消息数量，与上下文压缩完全分离
            should_consolidate = new_message_count >= 20

            if not should_consolidate:
                return

            logger.info(
                "memory_consolidation_triggered",
                session_id=session_id,
                messages_to_consolidate=new_message_count
            )

            # 3. 获取现有记忆内容和文件路径
            memory_store = await self.memory_manager.get_user_memory(
                user_id=unified_user_id,
                mode=mode
            )
            existing_memory = memory_store.read_long_term() if memory_store.memory_file.exists() else ""
            memory_file_path = str(memory_store.memory_file.resolve()) if memory_store.memory_file.exists() else ""

            # 计算记忆文件字符数
            current_size = len(existing_memory)
            max_size = 3000  # 与工具中的限制一致
            size_info = f"（{current_size}/{max_size}字符，使用率{current_size/max_size*100:.1f}%）"

            # 4. 构建整合提示词（包含现有记忆、文件路径和字符限制）
            consolidation_prompt = self._build_consolidation_prompt(
                messages[offset:] if offset > 0 else messages,
                mode,
                existing_memory,
                memory_file_path
            )

            # 5. 设置记忆上下文（供记忆工具使用）
            # 解析unified_user_id获取模式信息
            # unified_user_id格式：{mode}:{user_identifier}:{shared|unique}
            user_id = unified_user_id.split(':')[1] if ':' in unified_user_id else None

            # 设置记忆上下文（类变量）
            RememberFactTool.set_memory_context(mode, user_id)
            ReplaceMemoryTool.set_memory_context(mode, user_id)
            RemoveMemoryTool.set_memory_context(mode, user_id)

            # 6. 创建记忆整合Agent
            from .memory_consolidator_factory import create_memory_consolidator_agent
            consolidator_agent = create_memory_consolidator_agent()

            # 7. 异步执行整合
            async for event in consolidator_agent.analyze(
                user_query=consolidation_prompt,
                session_id=f"{session_id}_consolidation",
                manual_mode="memory_consolidator"
            ):
                if event.get("type") == "complete":
                    await self.memory_manager.set_consolidation_offset(
                        unified_user_id,
                        len(messages)
                    )
                    logger.info(
                        "background_memory_consolidation_completed",
                        session_id=session_id,
                        mode=mode,
                        messages_processed=new_message_count
                    )
                    break
                elif event.get("type") == "error":
                    logger.warning(
                        "background_memory_consolidation_failed",
                        session_id=session_id,
                        error=event.get("data", {}).get("error")
                    )
                    break

        except Exception as e:
            logger.exception(
                "background_memory_consolidation_error",
                session_id=session_id,
                mode=mode,
                error=str(e)
            )
        finally:
            # 8. 清除记忆上下文（无论成功或失败）
            try:
                RememberFactTool.clear_memory_context()
                ReplaceMemoryTool.clear_memory_context()
                RemoveMemoryTool.clear_memory_context()
                logger.debug("memory_context_cleared")
            except Exception as e:
                logger.warning("failed_to_clear_memory_context", error=str(e))

    def _build_consolidation_prompt(
        self,
        messages: List[Dict[str, Any]],
        mode: str,
        existing_memory: str = "",
        memory_file_path: str = ""
    ) -> str:
        """
        构建记忆整合提示词

        Args:
            messages: 消息列表
            mode: 模式标识
            existing_memory: 现有记忆内容
            memory_file_path: 记忆文件路径

        Returns:
            整合提示词
        """
        conversation_text = "\n".join([
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in messages[-10:]  # 只使用最近10条
        ])

        # 计算记忆文件字符数
        current_size = len(existing_memory) if existing_memory else 0
        max_size = 3000  # 与工具中的限制一致
        size_info = f"（{current_size}/{max_size}字符，使用率{current_size/max_size*100:.1f}%）"

        # 构建提示词
        prompt_parts = [
            "请分析以下对话内容，提取重要信息并更新长期记忆。",
            "",
            "## 模式",
            mode,
            ""
        ]

        # 添加现有记忆内容（如果有）
        if existing_memory and existing_memory.strip():
            prompt_parts.extend([
                "## 现有记忆",
                f"**当前记忆大小**：{size_info}",
                "",
                "```",
                existing_memory,  # 完整记忆，不限制字符
                "```",
                "",
                "**⚠️ 重要限制**：",
                f"- 记忆文件上限：{max_size}字符",
                f"- 当前使用：{current_size}字符（{current_size/max_size*100:.1f}%）",
                "- 当接近上限（>80%）时，优先使用 remove_memory 删除旧内容",
                "- 当已满（100%）时，必须先删除才能添加新内容",
                ""
            ])
        else:
            # 空记忆文件
            prompt_parts.extend([
                "## 现有记忆",
                "**当前记忆大小**：0/3000字符（0.0%）",
                "",
                "记忆文件为空，可以开始添加记忆。",
                ""
            ])

        # 添加记忆文件路径
        if memory_file_path:
            prompt_parts.extend([
                "## 记忆文件路径",
                memory_file_path,
                ""
            ])

        # 添加对话内容和任务
        prompt_parts.extend([
            "## 对话内容",
            conversation_text,
            "",
            "**任务**：",
            "1. 阅读现有记忆，了解已记住的内容",
            "2. 分析对话内容，识别需要记住的新信息",
            "3. 使用工具更新记忆：",
            "   - remember_fact: 添加新记忆",
            "   - replace_memory: 替换现有记忆",
            "   - remove_memory: 删除过时记忆",
            "4. 给出简洁总结（不超过50字）",
            "",
            "**⚠️ 记忆管理策略**（基于字符限制）：",
            f"- 当记忆使用率 < 80%：可以正常添加新记忆",
            f"- 当记忆使用率 >= 80%：优先删除临时、过时或低优先级的记忆",
            f"- 当记忆使用率 = 100%：必须先删除才能添加（工具会返回错误）",
            "",
            "**注意事项**：",
            "- 避免重复记忆（先检查现有记忆）",
            "- 更新偏好设置时使用replace_memory",
            "- 删除临时或错误记忆时使用remove_memory",
            "- 优先保留高价值信息（用户偏好 > 领域知识 > 历史结论 > 环境信息）",
            "- 记忆文件路径已在上方提供，工具会自动使用"
        ])

        return "\n".join(prompt_parts)

    # ========================================================================
    # 简单查询方法
    # ========================================================================

    async def simple_query(
        self,
        user_query: str,
        max_iterations: Optional[int] = None,
        session_id: Optional[str] = None,
        enhance_with_history: bool = True
    ) -> str:
        """
        简单查询（非流式）

        Args:
            user_query: 用户查询
            max_iterations: 最大迭代次数（可选）
            session_id: 会话ID（可选）
            enhance_with_history: 是否使用长期记忆增强

        Returns:
            最终答案字符串
        """
        final_answer = ""

        async for event in self.analyze(
            user_query,
            session_id=session_id,
            enhance_with_history=enhance_with_history,
            max_iterations=max_iterations
        ):
            if event["type"] == "complete":
                final_answer = event["data"].get("answer", "")
                break
            elif event["type"] == "incomplete":
                final_answer = event["data"].get("answer", "")
                break
            elif event["type"] == "fatal_error":
                final_answer = f"分析失败：{event['data'].get('error')}"
                break

        return final_answer

    async def _mark_session_used(self, session_id: str):
        """刷新会话的最后访问时间（使用细粒度锁）"""
        # 获取该 session 的锁（如果不存在则说明 session 未创建，无需处理）
        session_lock = self._session_locks.get(session_id)
        if not session_lock:
            return

        async with session_lock:
            if session_id in self._session_store:
                self._session_store[session_id]["last_used"] = datetime.utcnow()

    async def _get_or_create_session(
        self,
        session_id: Optional[str],
        reset_session: bool = False
    ) -> Tuple[str, HybridMemoryManager, bool]:
        """
        获取或创建会话记忆管理器

        ✅ 修复：从 SessionManager 恢复历史会话状态，确保历史对话上下文不丢失
        ✅ 性能优化：使用细粒度锁（按 session_id），不同 session 可以并发

        返回:
            (session_id, memory_manager, created_new)
        """
        # 确定实际的 session_id
        actual_session_id = session_id or self._generate_session_id()

        # 获取或创建该 session_id 对应的锁
        async with self._global_lock:
            if actual_session_id not in self._session_locks:
                self._session_locks[actual_session_id] = asyncio.Lock()
            session_lock = self._session_locks[actual_session_id]

        # 使用该 session 的锁（允许不同 session 并发）
        async with session_lock:
            # 清理过期会话
            self._cleanup_expired_sessions()

            # ✅ 优先重用内存中的会话
            if not reset_session and session_id and session_id in self._session_store:
                entry = self._session_store[session_id]
                entry["last_used"] = datetime.utcnow()
                logger.info("react_session_reused", session_id=session_id)
                return session_id, entry["memory"], False

            # ✅ 新增：尝试从 SessionManager 恢复会话
            if session_id and not reset_session:
                try:
                    from app.agent.session import get_session_manager
                    session_manager = get_session_manager()
                    saved_session = await session_manager.load_session(session_id)

                    if saved_session and saved_session.conversation_history:
                        logger.info(
                            "react_session_restored_from_manager",
                            session_id=session_id,
                            history_length=len(saved_session.conversation_history),
                            has_data_ids=bool(saved_session.data_ids),
                            data_ids_count=len(saved_session.data_ids) if saved_session.data_ids else 0
                        )

                        # 创建新的 memory_manager（但会从 saved_session 恢复历史）
                        memory_manager = HybridMemoryManager(
                            session_id=session_id,
                            max_working_iterations=self.max_working_memory,
                            large_data_threshold=self.large_data_threshold,
                            working_context_limit=self.working_context_limit,
                            batch_compress_threshold=11,  # 第11次触发首次压缩
                            compress_batch_size=10  # 每次压缩10条
                        )

                        # ✅ 立即加载历史消息到 memory_manager.session
                        if saved_session.conversation_history:
                            memory_manager.session.load_history_messages(saved_session.conversation_history)
                            logger.info(
                                "react_session_history_loaded",
                                session_id=session_id,
                                message_count=len(saved_session.conversation_history)
                            )

                        # 保存到内存缓存
                        self._session_store[session_id] = {
                            "memory": memory_manager,
                            "created": datetime.utcnow(),
                            "last_used": datetime.utcnow()
                        }

                        return session_id, memory_manager, False  # False 表示不是新建，是恢复的

                except Exception as e:
                    logger.warning(
                        "react_session_restore_failed",
                        session_id=session_id,
                        error=str(e),
                        hint="将创建新会话"
                    )

            # 创建全新会话
            actual_session_id = session_id or self._generate_session_id()

            if actual_session_id in self._session_store:
                old_entry = self._session_store.pop(actual_session_id)
                try:
                    old_entry["memory"].cleanup()
                except Exception as cleanup_error:
                    logger.warning(
                        "react_session_cleanup_failed",
                        session_id=actual_session_id,
                        error=str(cleanup_error)
                    )

            memory_manager = HybridMemoryManager(
                session_id=actual_session_id,
                max_working_iterations=self.max_working_memory,
                large_data_threshold=self.large_data_threshold,
                working_context_limit=self.working_context_limit,
                batch_compress_threshold=11,  # 第11次触发首次压缩
                compress_batch_size=10  # 每次压缩10条
            )

            self._session_store[actual_session_id] = {
                "memory": memory_manager,
                "last_used": datetime.utcnow()
            }

            logger.info("react_session_created", session_id=actual_session_id)
            return actual_session_id, memory_manager, True

    def _cleanup_expired_sessions(self):
        """清理过期会话（需要在细粒度锁内调用）"""
        if not self._session_store or not self._session_ttl:
            return

        expire_before = datetime.utcnow() - self._session_ttl
        expired_ids = [
            sid for sid, meta in self._session_store.items()
            if meta["last_used"] < expire_before
        ]

        for sid in expired_ids:
            entry = self._session_store.pop(sid, None)
            if not entry:
                continue
            try:
                entry["memory"].cleanup()
            except Exception as cleanup_error:
                logger.warning(
                    "react_session_cleanup_failed",
                    session_id=sid,
                    error=str(cleanup_error)
                )
            logger.info("react_session_expired", session_id=sid)

            # 清理对应的锁（直接删除，无需额外锁保护）
            self._session_locks.pop(sid, None)

    def _generate_session_id(self) -> str:
        """生成唯一的会话ID"""
        return f"react_{uuid.uuid4().hex[:12]}"

    def __repr__(self) -> str:
        return (
            f"<ReActAgent "
            f"max_iter={self.max_iterations} "
            f"tools={len(self.executor.tool_registry)}>"
        )


# =========================
# 便捷工厂函数
# =========================

def create_react_agent(
    with_test_tools: bool = False,
    **kwargs
) -> ReActAgent:
    """
    创建 ReAct Agent 实例

    Args:
        with_test_tools: 是否包含测试工具
        **kwargs: 传递给 ReActAgent 的其他参数

    Returns:
        配置好的 ReActAgent 实例
    """
    if with_test_tools:
        from .core.executor import create_test_executor

        # 创建包含测试工具的执行器
        executor = create_test_executor()
        tool_registry = executor.tool_registry

        agent = ReActAgent(tool_registry=tool_registry, **kwargs)

        logger.info(
            "react_agent_created_with_test_tools",
            tool_count=len(agent.get_available_tools())
        )
    else:
        # ✅ 加载全局工具注册表
        from app.agent.tool_adapter import get_react_agent_tool_registry
        tool_registry = get_react_agent_tool_registry()

        agent = ReActAgent(tool_registry=tool_registry, **kwargs)

        logger.info(
            "react_agent_created",
            tool_count=len(tool_registry)
        )

    return agent


# =========================
# 使用示例
# =========================

"""
# 基础使用

from app.agent.react_agent import create_react_agent

# 创建 Agent（包含测试工具）
agent = create_react_agent(with_test_tools=True)

# 流式分析
async for event in agent.analyze("分析广州天河站2025-08-09的O3污染"):
    print(f"[{event['type']}]", event['data'])

# 简单查询（非流式）
answer = await agent.simple_query("查询广州今天的天气")
print(answer)


# 注册自定义工具

async def custom_tool(param1: str, param2: int):
    # 工具实现
    return {"success": True, "data": "结果"}

agent.register_tool("custom_tool", custom_tool)


# 查看可用工具
print("可用工具:", agent.get_available_tools())
print("工具详情:", agent.get_tool_info("get_weather_data"))
"""
