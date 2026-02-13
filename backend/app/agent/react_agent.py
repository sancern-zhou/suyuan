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

from typing import Dict, Any, AsyncGenerator, Optional, Tuple
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
        max_iterations: int = 10,
        max_working_memory: int = 20,  # 恒定保留20条详细记录
        working_context_limit: int = 50000,  # 大幅增加字符限制，触发上下文压缩
        large_data_threshold: int = 1000,
        tool_registry: Optional[Dict] = None,
        session_ttl_hours: int = 12,
        enable_multi_expert: bool = True  # 是否启用多专家系统
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
            enable_multi_expert: 是否启用多专家系统
        """
        self.max_iterations = max_iterations
        self.max_working_memory = max_working_memory
        self.working_context_limit = working_context_limit
        self.large_data_threshold = large_data_threshold
        self.enable_multi_expert = enable_multi_expert
        self._session_ttl = timedelta(hours=session_ttl_hours) if session_ttl_hours > 0 else None
        self._session_store: Dict[str, Dict[str, Any]] = {}
        self._session_lock = asyncio.Lock()
        self.expert_router = None  # 专家路由器（延迟初始化）

        # 初始化工具执行器
        self.executor = ToolExecutor(tool_registry=tool_registry)

        # 初始化 LLM 规划器
        self.planner = ReActPlanner(tool_registry=tool_registry)

        logger.info(
            "react_agent_initialized",
            max_iterations=max_iterations,
            max_working_memory=max_working_memory,
            working_context_limit=working_context_limit,
            tool_count=len(self.executor.tool_registry),
            multi_expert_enabled=enable_multi_expert
        )

    def _get_expert_router(self, memory_manager, event_callback=None):
        """
        获取或创建专家路由器（延迟初始化）- 使用V3版本

        Args:
            memory_manager: 记忆管理器
            event_callback: 事件回调函数，用于实时发送专家执行事件

        Returns:
            专家路由器实例
        """
        if self.expert_router is None and self.enable_multi_expert:
            from .experts.expert_router_v3 import ExpertRouterV3

            # 创建专家路由器V3（传入memory_manager和事件回调）
            self.expert_router = ExpertRouterV3(
                memory_manager=memory_manager,
                event_callback=event_callback
            )

            logger.info(
                "expert_router_v3_initialized",
                has_callback=event_callback is not None,
                has_memory_manager=memory_manager is not None
            )

        return self.expert_router

    async def get_expert_system_status(self) -> Dict[str, Any]:
        """
        获取多专家系统状态

        Returns:
            专家系统状态信息
        """
        if not self.enable_multi_expert:
            return {
                "enabled": False,
                "status": "disabled"
            }

        if self.expert_router is None:
            return {
                "enabled": True,
                "status": "not_initialized"
            }

        status = await self.expert_router.get_expert_status()
        health = await self.expert_router.health_check()

        return {
            "enabled": True,
            "status": health.get("overall_status", "unknown"),
            "experts": status,
            "health": health
        }

    async def analyze(
        self,
        user_query: str,
        session_id: Optional[str] = None,
        enhance_with_history: bool = True,
        max_iterations: Optional[int] = None,
        reset_session: bool = False,
        debug_mode: bool = False,
        plan_mode: bool = False,
        precision: str = 'standard',
        enable_multi_expert: Optional[bool] = None,  # ✅ 动态切换单/多专家模式
        knowledge_base_ids: Optional[list] = None,
        enable_reasoning: bool = False,
        is_interruption: bool = False  # ✅ 是否为用户中断后的对话
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        分析用户查询（主入口）

        Args:
            user_query: 用户自然语言查询
            session_id: 会话ID（可选，用于会话恢复）
            enhance_with_history: 是否使用长期记忆增强
            max_iterations: 本次执行的最大迭代数
            reset_session: 是否强制重置会话
            debug_mode: 调试模式开关，开启后会返回 LLM 的上下文信息
            plan_mode: 是否使用 ReWOO 规划模式（一次性生成完整计划）
            precision: EKMA分析精度模式 (fast/standard/full)
            enable_multi_expert: ✅ 动态切换单/多专家模式（None则使用实例默认设置）
            knowledge_base_ids: 知识库ID列表（暂未启用，预留参数）
            enable_reasoning: ✅ 是否启用思考模式（默认False，启用后会显示LLM的推理过程，适用于MiniMax等支持思考模式的模型）
            is_interruption: ✅ 是否为用户中断后的对话（用户暂停后继续对话时为True）

        Yields:
            流式事件：
            - type: "start" | "thought" | "action" | "observation" | "complete" | "error"
            - data: 事件数据
        """
        # 注意：knowledge_base_ids 参数暂未启用，预留用于后续知识库增强功能
        _ = knowledge_base_ids

        # ✅ 动态决定是否启用多专家系统
        # 如果传入enable_multi_expert参数，则优先使用；否则使用实例的默认设置
        should_use_multi_expert = enable_multi_expert if enable_multi_expert is not None else self.enable_multi_expert

        actual_session_id, memory_manager, created_new = await self._get_or_create_session(
            session_id,
            reset_session
        )

        # Update executor's memory_manager to enable DataContextManager
        self.executor.set_memory_manager(memory_manager)

        iteration_limit = max_iterations or self.max_iterations

        logger.info(
            "analysis_started",
            session_id=actual_session_id,
            query=user_query[:100],
            iteration_limit=iteration_limit,
            reused_session=not created_new,
            debug_mode=debug_mode,
            plan_mode=plan_mode,
            enable_multi_expert=should_use_multi_expert,  # ✅ 记录实际使用的模式
            mode="multi_expert" if should_use_multi_expert else "single_expert_react"
        )

        try:
            # ✅ 如果启用多专家系统，直接路由（由专家路由器的NLP决定调用哪些专家）
            if should_use_multi_expert:
                # 创建事件队列用于实时事件转发
                event_queue = asyncio.Queue()

                # 事件回调函数：接收专家路由器的事件并放入队列
                def event_callback(event):
                    # 立即放入队列，不阻塞
                    try:
                        event_queue.put_nowait(event)
                    except asyncio.QueueFull:
                        logger.warning("event_queue_full", event_type=event.get("type"))

                # 获取专家路由器（传入事件回调）
                expert_router = self._get_expert_router(memory_manager, event_callback=event_callback)

                if expert_router:
                    logger.info(
                        "routing_to_multi_expert_system_v3",
                        query=user_query[:100],
                        mode="llm_autonomous_decision"
                    )

                    # 启动一个后台任务来获取pipeline结果
                    pipeline_task = asyncio.create_task(
                        expert_router.execute_pipeline(
                            user_query,
                            precision=precision  # EKMA分析精度模式 (fast/standard/full)
                        )
                    )

                    # 实时转发事件给前端，同时等待pipeline完成
                    try:
                        while not pipeline_task.done() or not event_queue.empty():
                            try:
                                # 等待新事件，最多等1秒
                                event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                                yield event
                            except asyncio.TimeoutError:
                                # 继续等待
                                continue

                        # 等待pipeline最终结果
                        if not pipeline_task.done():
                            pipeline_result = await pipeline_task
                        else:
                            pipeline_result = pipeline_task.result()

                    except Exception as e:
                        logger.error("multi_expert_execution_error", error=str(e))
                        if not pipeline_task.done():
                            pipeline_task.cancel()
                        raise e

                    # 转换为字典格式
                    expert_result = pipeline_result.to_dict()

                    # 返回最终expert_result事件（确保前端收到完整结果）
                    yield {
                        "type": "expert_result",
                        "data": expert_result
                    }

                    # 返回最终完成事件（包含完整结果）
                    if pipeline_result.status in ["success", "partial"]:
                        yield {
                            "type": "complete",
                            "data": {
                                "answer": pipeline_result.final_answer,
                                "source": "multi_expert_system_v3",
                                "confidence": pipeline_result.confidence,
                                "pipeline_status": pipeline_result.status,
                                "expert_results": expert_result.get("expert_results"),
                                "conclusions": pipeline_result.conclusions,
                                "recommendations": pipeline_result.recommendations,
                                "data_ids": pipeline_result.data_ids,
                                "selected_experts": pipeline_result.selected_experts,
                                "visuals": pipeline_result.visuals  # 添加visuals字段
                            }
                        }
                    else:
                        yield {
                            "type": "incomplete",
                            "data": {
                                "answer": "多专家分析未获得有效结果，回退到标准ReAct模式",
                                "source": "multi_expert_system_fallback",
                                "expert_results": expert_result.get("expert_results"),
                                "errors": pipeline_result.errors
                            }
                        }
                    return

            # ✅ 如果不启用多专家系统，使用标准ReAct循环（LLM自主决策调用工具）
            # 每次调用都创建新的 ReAct 循环，但共享会话记忆
            react_loop = ReActLoop(
                memory_manager=memory_manager,
                llm_planner=self.planner,
                tool_executor=self.executor,
                max_iterations=iteration_limit,
                stream_enabled=True,
                is_interruption=is_interruption,  # ✅ 传递中断标志
                plan_mode=plan_mode,  # 传递 plan_mode 参数
                enable_reasoning=enable_reasoning  # ✅ 传递思考模式参数
            )

            async for event in react_loop.run(
                user_query=user_query,
                enhance_with_history=enhance_with_history,
                debug_mode=debug_mode
            ):
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

        返回:
            (session_id, memory_manager, created_new)
        """
        async with self._session_lock:
            self._cleanup_expired_sessions_locked()

            if not reset_session and session_id and session_id in self._session_store:
                entry = self._session_store[session_id]
                entry["last_used"] = datetime.utcnow()
                logger.info("react_session_reused", session_id=session_id)
                return session_id, entry["memory"], False

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
        agent = ReActAgent(**kwargs)

        logger.info("react_agent_created")

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
