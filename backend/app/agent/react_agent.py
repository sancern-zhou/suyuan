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
        session_ttl_hours: int = 12
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
        """
        self.max_iterations = max_iterations
        self.max_working_memory = max_working_memory
        self.working_context_limit = working_context_limit
        self.large_data_threshold = large_data_threshold
        self._session_ttl = timedelta(hours=session_ttl_hours) if session_ttl_hours > 0 else None
        self._session_store: Dict[str, Dict[str, Any]] = {}
        self._session_lock = asyncio.Lock()

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
            tool_count=len(self.executor.tool_registry)
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
        attachments: Optional[List[Dict[str, Any]]] = None
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

        Yields:
            流式事件：
            - type: "start" | "thought" | "action" | "observation" | "complete" | "error"
            - data: 事件数据
        """
        # ✅ 如果有附件，添加到查询中告知LLM
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
            user_query = user_query + attachment_info
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

            async for event in react_loop.run(
                user_query=user_query,
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
            # 同步 office_documents 到会话对象
            if actual_session_id and actual_session_id in self._session_store:
                office_docs = self._session_store[actual_session_id].get("office_documents", [])
                if office_docs:
                    try:
                        from app.agent.session import get_session_manager
                        session_manager = get_session_manager()
                        session = session_manager.load_session(actual_session_id)
                        if session:
                            session.office_documents = office_docs
                            session_manager.save_session(session)
                            logger.info("office_documents_synced_to_session",
                                       session_id=actual_session_id,
                                       count=len(office_docs))
                    except Exception as e:
                        logger.warning("failed_to_sync_office_documents",
                                      session_id=actual_session_id,
                                      error=str(e))

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
        """刷新会话的最后访问时间"""
        async with self._session_lock:
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

        返回:
            (session_id, memory_manager, created_new)
        """
        async with self._session_lock:
            self._cleanup_expired_sessions_locked()

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
                    saved_session = session_manager.load_session(session_id)

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

    def _cleanup_expired_sessions_locked(self):
        """在已加锁的情况下清理过期会话"""
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
