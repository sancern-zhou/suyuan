"""
ReAct Loop Engine (Refactored)

ReAct 循环引擎，实现 Thought → Action → Observation 循环。

重构后的模块化结构：
- MemoryToolsHandler: 内存工具管理
- AgentLogger: 运行日志追踪（学习Mini-Agent）
"""

from typing import Dict, Any, AsyncGenerator, Tuple, List, Optional
from datetime import datetime
import structlog
import json
import os

from ..memory.hybrid_manager import HybridMemoryManager
from .memory_tools_handler import MemoryToolsHandler

# 运行日志（学习Mini-Agent）
from ...utils.agent_logger import AgentLogger
from ..prompts.react_prompts import format_finish_summary_prompt

# 简化的上下文构建器
from ..context.simplified_context_builder import SimplifiedContextBuilder

# 守卫模块（任务完成守卫）
from .guards import TaskCompletionGuard
from .schema_injection import SchemaInjector

logger = structlog.get_logger()


class ReActLoop:
    """
    ReAct 循环引擎（重构版）

    负责执行完整的 ReAct 循环：
    - Thought: LLM 分析当前状态
    - Action: 决定下一步行动（工具调用或完成）
    - Observation: 记录执行结果

    新增特性（学习Mini-Agent）：
    - 运行日志追踪：完整记录执行过程，便于调试
    """

    def __init__(
        self,
        memory_manager: HybridMemoryManager,
        llm_planner,
        tool_executor,
        max_iterations: int = 30,  # 默认30次（适应复杂分析任务）
        stream_enabled: bool = True,
        # 日志配置
        enable_agent_logging: bool = True,
        log_dir: str = "./logs/agent_runs",
        enable_reasoning: bool = False,  # ✅ 思考模式开关（是否显示LLM推理过程）
        is_interruption: bool = False,  # ✅ 是否为用户中断后的对话
        knowledge_base_ids: Optional[list] = None  # ✅ 知识库ID列表
    ):
        """
        初始化 ReAct 循环引擎

        Args:
            memory_manager: 混合记忆管理器
            llm_planner: LLM 规划器
            tool_executor: 工具执行器
            max_iterations: 最大迭代次数（默认30次）
            stream_enabled: 是否启用流式输出
            enable_agent_logging: 是否启用Agent运行日志
            log_dir: 日志目录
            is_interruption: 是否为用户中断后的对话（用户暂停后继续对话时为True）
            knowledge_base_ids: 知识库ID列表（用于知识问答工作流）
        """
        self.memory = memory_manager
        self.planner = llm_planner
        self.executor = tool_executor
        self.max_iterations = max_iterations
        self.stream_enabled = stream_enabled
        self.is_interruption = is_interruption  # ✅ 保存中断标志
        self.knowledge_base_ids = knowledge_base_ids  # ✅ 保存知识库ID列表

        # 初始化处理器模块
        self.memory_tools_handler = MemoryToolsHandler(memory_manager, tool_executor)

        # Agent运行日志
        self.enable_agent_logging = enable_agent_logging
        self.agent_logger = AgentLogger(
            log_dir=log_dir,
            enable_file_logging=enable_agent_logging
        ) if enable_agent_logging else None

        # 简化的上下文构建器
        # llm_planner 是 ReActPlanner 实例，使用 llm_service 属性
        llm_client = llm_planner.llm_service if hasattr(llm_planner, 'llm_service') else None
        self.context_builder = SimplifiedContextBuilder(
            llm_client=llm_client,
            memory_manager=memory_manager,
            tool_registry=tool_executor.tool_registry if hasattr(tool_executor, 'tool_registry') else None
        )

        # ✅ 初始化任务完成守卫
        self.task_completion_guard = TaskCompletionGuard(memory_manager)

        # 注册内存相关工具
        self.memory_tools_handler.register_memory_tools()

        # ✅ 保存思考模式设置
        self.enable_reasoning = enable_reasoning

        # ✅ 初始化当前模式（默认expert）
        self.current_mode = "expert"

        # ✅ 初始化Schema注入器（检测连续工具错误并自动注入schema）
        self.schema_injector = SchemaInjector(consecutive_error_threshold=2)

        logger.info(
            "react_loop_initialized",
            session_id=memory_manager.session_id,
            max_iterations=max_iterations,
            agent_logging=enable_agent_logging,
            enable_reasoning=enable_reasoning,
            knowledge_base_ids=knowledge_base_ids  # ✅ 记录知识库ID
        )

    async def run(
        self,
        user_query: str,
        enhance_with_history: bool = True,
        initial_messages: Optional[List[Dict[str, Any]]] = None,  # ✅ 新增：历史消息注入
        manual_mode: Optional[str] = None,  # ✅ 新增：手动指定模式（"assistant" | "expert"）
        original_query: Optional[str] = None  # ✅ 新增：原始查询（用于保存到历史，不包含记忆增强）
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行单步模式 ReAct 循环（V4版）

        Args:
            user_query: 用户查询（可能包含记忆增强，用于LLM推理）
            enhance_with_history: 是否使用长期记忆增强
            initial_messages: 历史消息列表（用于会话恢复）
            manual_mode: 手动指定Agent模式（"assistant" | "expert"，默认expert）
            original_query: 原始查询（不包含记忆增强，用于保存到对话历史）

        Yields:
            流式事件
        """
        # 设置当前模式（默认expert）
        self.current_mode = manual_mode or "expert"

        logger.info(
            "react_loop_mode_selected",
            mode=self.current_mode,
            manual_override=manual_mode is not None
        )

        # ReAct 循环（默认）
        async for event in self._run_react_loop(
            user_query,
            enhance_with_history,
            initial_messages,  # ✅ 传递历史消息
            original_query  # ✅ 传递原始查询
        ):
            # 附加模式信息到事件
            event["mode"] = self.current_mode
            yield event

    async def _run_react_loop(
        self,
        user_query: str,
        enhance_with_history: bool = True,
        initial_messages: Optional[List[Dict[str, Any]]] = None,  # ✅ 新增：历史消息注入
        original_query: Optional[str] = None  # ✅ 新增：原始查询（用于保存到历史）
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        ReAct 循环（Thought + Action + Observation）

        核心流程：
        1. think_and_action() - 单次LLM调用，同时生成 thought 和 action
        2. 执行工具（TOOL_CALL / TOOL_CALLS）
        3. Observation - 记录结果
        4. 记忆更新
        5. 完成或继续下一轮

        支持 Reflexion 反思机制：
        - 输入验证错误重试
        - 工具执行失败重试

        Args:
            user_query: 用户查询（可能包含记忆增强，用于LLM推理）
            enhance_with_history: 是否使用长期记忆增强
            initial_messages: 历史消息列表（用于会话恢复）
            original_query: 原始查询（不包含记忆增强，用于保存到对话历史）

        Yields:
            流式事件
        """
        try:
            # 新增：开始运行日志记录
            if self.agent_logger:
                run_id = self.agent_logger.start_new_run(
                    session_id=self.memory.session_id,
                    query=user_query,
                    metadata={"enhance_with_history": enhance_with_history}
                )
                logger.info("agent_run_started", run_id=run_id, log_file=self.agent_logger.get_log_file_path())

            # ✅ 设置planner的中断标志
            self.planner.is_interruption = self.is_interruption
            if self.is_interruption:
                logger.info("interruption_flag_set", is_interruption=True, query=user_query[:100])

            # ✅ 检查 session 是否已有历史消息（从 _get_or_create_session 恢复）
            existing_history = self.memory.session.get_messages_for_llm()
            if existing_history:
                logger.info(
                    "session_already_has_history",
                    session_id=self.memory.session_id,
                    history_length=len(existing_history),
                    first_role=existing_history[0].get("role") if existing_history else None,
                    last_role=existing_history[-1].get("role") if existing_history else None,
                    hint="会话已在 _get_or_create_session 中从 SessionManager 恢复"
                )

            # Step 0: 记录用户消息（使用原始查询，不包含记忆增强）
            query_to_save = original_query if original_query is not None else user_query
            self.memory.session.add_user_message(query_to_save)

            # ✅ 调试日志：验证原始查询和增强查询
            if original_query is not None:
                logger.info(
                    "query_separation_verified",
                    original_length=len(original_query),
                    enhanced_length=len(user_query),
                    original_preview=original_query[:100],
                    has_memory_enhancement=user_query != original_query,
                    saved_to_history="original_query",
                    used_for_llm="enhanced_query"
                )

            # Step 1: 使用增强查询（已在 react_agent.py 中加载记忆）
            # user_query 参数已经是增强后的查询（包含记忆上下文）
            enhanced_query = user_query

            # 检测是否有记忆增强（通过比较原始查询和增强查询）
            has_memory = (
                original_query is not None and
                len(user_query) > len(original_query) and
                "长期记忆" in user_query
            )

            logger.info(
                "query_processing",
                query_length=len(user_query),
                original_length=len(original_query) if original_query else 0,
                has_memory_enhancement=has_memory,
                longterm_memory_disabled=not has_memory
            )

            # ✅ 调试日志：显示增强查询的前400字符
            if has_memory:
                logger.debug(
                    "enhanced_query_with_memory",
                    preview=enhanced_query[:400],
                    contains_memory_marker="长期记忆" in enhanced_query,
                    contains_file_path="记忆文件路径" in enhanced_query
                )

            # Step 2: 初始化循环状态
            iteration_count = 0
            task_completed = False
            final_answer = None
            direct_from_workflow = False  # ✅ 跟踪是否来自工作流直接返回
            workflow_sources = []  # ✅ 保存工作流的sources数据
            workflow_visuals = []  # ✅ 保存工作流的visuals数据

            # Yield start event
            yield {
                "type": "start",
                "data": {
                    "query": user_query,
                    "session_id": self.memory.session_id,
                    "timestamp": datetime.now().isoformat()
                }
            }

            # Step 3: ReAct 循环
            while iteration_count < self.max_iterations and not task_completed:
                iteration_count += 1

                logger.info(
                    "react_iteration",
                    iteration=iteration_count,
                    max_iterations=self.max_iterations
                )

                try:
                    # Phase 1: 获取上一次观察结果（用于反思）
                    latest_observation = None
                    if iteration_count > 1:
                        iterations = self.memory.get_iterations()
                        if iterations:
                            latest_observation = iterations[-1].get("observation")

                    # Phase 2: 使用简化的上下文构建器
                    conversation_history = self.memory.session.get_messages_for_llm()

                    # 格式化latest_observation为字符串
                    latest_observation_str = ""
                    if latest_observation:
                        latest_observation_str = self._format_observation(latest_observation)

                    # 使用SimplifiedContextBuilder构建上下文
                    context_result = await self.context_builder.build_for_thought_action(
                        query=enhanced_query,
                        iteration=iteration_count,
                        latest_observation=latest_observation_str,
                        conversation_history=conversation_history,
                        mode=self.current_mode,  # ✅ 传递当前模式
                        is_interruption=self.is_interruption  # ✅ 传递中断标志
                    )

                    # Phase 3: think_and_action（流式LLM调用）
                    # ✅ 使用流式版本，支持纯文本回复的实时流式输出
                    thought = None
                    reasoning = None
                    action = None
                    streaming_buffer = ""  # 流式文本缓冲区
                    think_action_result = None  # 初始化变量，避免后续引用错误

                    async for event in self.planner.think_and_action_v2_streaming(
                        query=enhanced_query,
                        system_prompt=context_result["system_prompt"],
                        user_conversation=context_result["user_conversation"],
                        iteration=iteration_count,
                        latest_observation=latest_observation
                    ):
                        if event["type"] == "streaming_text":
                            # ✅ 流式文本：立即转发给前端
                            chunk = event["data"]["chunk"]
                            is_complete = event["data"]["is_complete"]

                            if chunk:  # 只在有内容时才发送
                                streaming_buffer += chunk
                                yield {
                                    "type": "streaming_text",
                                    "data": {
                                        "chunk": chunk,
                                        "is_complete": is_complete,
                                        "timestamp": datetime.now().isoformat()
                                    },
                                    "session_id": self.memory.session_id  # 【修复】添加session_id确保事件路由到正确模式
                                }

                            if is_complete:
                                # 流式完成，创建 FINAL_ANSWER action
                                action = {
                                    "type": "FINAL_ANSWER",
                                    "answer": streaming_buffer.strip()
                                }
                                # ✅ 关闭流式完成日志
                                # logger.info("streaming_text_complete", length=len(streaming_buffer))

                        elif event["type"] == "action":
                            # 最终 action（thought + action）
                            thought = event["data"]["thought"]
                            reasoning = event["data"].get("reasoning")
                            action = event["data"]["action"]

                            # ✅ 保存 think_action_result 供后续使用
                            think_action_result = event["data"]

                            # Yield thought事件（FINAL_ANSWER 除外）
                            action_type = action.get("type", "TOOL_CALL")
                            if action_type != "FINAL_ANSWER":
                                thought_event = {
                                    "type": "thought",
                                    "data": {
                                        "iteration": iteration_count,
                                        "thought": thought,
                                        "reasoning": reasoning,
                                        "timestamp": datetime.now().isoformat()
                                    }
                                }
                                yield thought_event
                                # ✅ 保存到对话历史
                                self.memory.session.add_thought_message(thought, reasoning)

                    # 如果没有 action（异常情况），降级处理
                    if not action:
                        logger.warning("no_action_from_streaming_planner", iteration=iteration_count)
                        think_action_result = await self.planner.think_and_action_v2(
                            query=enhanced_query,
                            system_prompt=context_result["system_prompt"],
                            user_conversation=context_result["user_conversation"],
                            iteration=iteration_count,
                            latest_observation=latest_observation
                        )
                        thought = think_action_result["thought"]
                        reasoning = think_action_result.get("reasoning")
                        action = think_action_result["action"]

                        thought_event = {
                            "type": "thought",
                            "data": {
                                "iteration": iteration_count,
                                "thought": thought,
                                "reasoning": reasoning,
                                "timestamp": datetime.now().isoformat()
                            }
                        }
                        yield thought_event
                        # ✅ 保存到对话历史
                        self.memory.session.add_thought_message(thought, reasoning)

                    logger.info("action_decided", action_type=action_type, iteration=iteration_count)

                    # FINAL_ANSWER: 直接展示 LLM 的最终回答
                    if action_type == "FINAL_ANSWER":
                        # ✅ 任务状态守卫：在完成任务前检查是否有未完成任务
                        guard_result = await self._guard_task_completion(self.memory.session_id)

                        if guard_result["has_incomplete"]:
                            # ⚠️ 有未完成任务：阻止完成，将警告作为观察结果返回给 LLM
                            observation = {
                                "success": False,
                                "warning": True,
                                "incomplete_tasks": guard_result["incomplete_tasks"],
                                "summary": f"有 {guard_result['incomplete_count']} 个任务尚未完成，不能结束任务。请先完成所有任务。",
                                "guard_warning": guard_result["warning_message"]
                            }

                            yield {
                                "type": "observation",
                                "data": {
                                    "iteration": iteration_count,
                                    "observation": observation,
                                    "timestamp": datetime.now().isoformat()
                                }
                            }

                            # 记录到记忆
                            self.memory.add_iteration(
                                thought=thought,
                                action=action,
                                observation=observation
                            )

                            # 将警告添加到对话历史（让 LLM 看到）
                            warning_message = f"**任务未完成警告**：\n\n{guard_result['warning_message']}"
                            self.memory.session.add_assistant_message(
                                warning_message,
                                thought=thought,
                                reasoning=reasoning if think_action_result is None else think_action_result.get("reasoning")
                            )

                            logger.info(
                                "task_guard_blocked_completion",
                                action_type=action_type,
                                incomplete_count=guard_result["incomplete_count"]
                            )
                            # 不设置 task_completed，让 LLM 继续执行
                            continue

                        # 没有未完成任务，正常完成
                        task_completed = True
                        final_answer = action.get("answer", "")

                        self.memory.add_iteration(
                            thought=thought,
                            action=action,
                            observation={"success": True, "summary": "任务完成"}
                        )

                        self.memory.session.add_assistant_message(
                            final_answer,
                            thought=thought,
                            reasoning=reasoning if think_action_result is None else think_action_result.get("reasoning")
                        )

                        # 注意：final_answer 的流式输出已在 think_and_action_v2_streaming 阶段完成
                        # 这里不需要再次输出

                        logger.info("task_completed_final_answer", iterations=iteration_count)

                        # ✅ 新增：yield agent_finish事件给父Agent（用于call_sub_agent提取结果）
                        yield {
                            "type": "agent_finish",
                            "answer": final_answer,
                            "data": {
                                "iterations": iteration_count,
                                "session_id": self.memory.session_id,
                                "thought": thought,
                                "reasoning": reasoning if think_action_result is None else think_action_result.get("reasoning")
                            }
                        }

                        break

                    # FINISH_SUMMARY: 结束并生成最终答案
                    if action_type == "FINISH_SUMMARY":
                        # ✅ 任务状态守卫：在完成任务前检查是否有未完成任务
                        guard_result = await self._guard_task_completion(self.memory.session_id)

                        if guard_result["has_incomplete"]:
                            # ⚠️ 有未完成任务：阻止完成，将警告作为观察结果返回给 LLM
                            observation = {
                                "success": False,
                                "warning": True,
                                "incomplete_tasks": guard_result["incomplete_tasks"],
                                "summary": f"有 {guard_result['incomplete_count']} 个任务尚未完成，不能生成最终答案。请先完成所有任务。",
                                "guard_warning": guard_result["warning_message"]
                            }

                            yield {
                                "type": "observation",
                                "data": {
                                    "iteration": iteration_count,
                                    "observation": observation,
                                    "timestamp": datetime.now().isoformat()
                                }
                            }

                            # 记录到记忆
                            self.memory.add_iteration(
                                thought=thought,
                                action=action,
                                observation=observation
                            )

                            # 将警告添加到对话历史（让 LLM 看到）
                            warning_message = f"**任务未完成警告**：\n\n{guard_result['warning_message']}"
                            self.memory.session.add_assistant_message(
                                warning_message,
                                thought=thought,
                                reasoning=reasoning if think_action_result is None else think_action_result.get("reasoning")
                            )

                            logger.info(
                                "task_guard_blocked_finish_summary",
                                incomplete_count=guard_result["incomplete_count"]
                            )
                            # 不设置 task_completed，让 LLM 继续执行
                            continue

                        # 没有未完成任务，正常完成
                        task_completed = True

                        # 获取工具结果数据（使用简化版上下文）
                        tool_results = self.memory.session.get_compressed_summary()

                        # 生成最终答案提示词
                        prompt = format_finish_summary_prompt(
                            user_query=user_query,
                            tool_results=tool_results or "无工具调用数据",
                            final_thought=thought
                        )

                        # 调用 LLM 生成最终答案（流式输出）
                        final_answer = ""
                        chunk_count = 0
                        async for chunk in self.planner.stream_user_answer(prompt):
                            final_answer += chunk
                            chunk_count += 1
                            # 流式输出每个 chunk（使用前端已支持的 streaming_text 事件类型）
                            yield {
                                "type": "streaming_text",
                                "data": {
                                    "chunk": chunk,
                                    "is_complete": False
                                }
                            }
                        # 发送流式完成标记
                        yield {
                            "type": "streaming_text",
                            "data": {
                                "chunk": "",
                                "is_complete": True
                            }
                        }
                        logger.info(f"[stream_user_answer] 流式输出完成，共 {chunk_count} 个 chunks，总长度: {len(final_answer)}")

                        self.memory.add_iteration(
                            thought=thought,
                            action={"type": "FINISH_SUMMARY"},
                            observation={"success": True, "summary": "FINISH_SUMMARY: 生成最终答案"}
                        )

                        if final_answer:
                            self.memory.session.add_assistant_message(
                                final_answer,
                                thought=thought,
                                reasoning=reasoning if think_action_result is None else think_action_result.get("reasoning")
                            )

                        yield {
                            "type": "observation",
                            "data": {
                                "iteration": iteration_count,
                                "observation": {"success": True, "summary": "FINISH_SUMMARY: 已生成最终答案"},
                                "timestamp": datetime.now().isoformat()
                            }
                        }

                        logger.info("task_completed_finish_summary", iterations=iteration_count)

                        # ✅ 新增：yield agent_finish事件给父Agent（用于call_sub_agent提取结果）
                        yield {
                            "type": "agent_finish",
                            "answer": final_answer,
                            "data": {
                                "iterations": iteration_count,
                                "session_id": self.memory.session_id,
                                "thought": thought,
                                "reasoning": reasoning if think_action_result is None else think_action_result.get("reasoning")
                            }
                        }

                        break

                    # TOOL_CALLS: 并行执行
                    if action_type == "TOOL_CALLS":
                        tools = action.get("tools", [])

                        # ✅ 为 knowledge_qa_workflow 自动注入 knowledge_base_ids
                        if self.knowledge_base_ids:
                            for tool in tools:
                                if tool.get("tool") == "knowledge_qa_workflow":
                                    args = tool.get("args", {})
                                    if not isinstance(args, dict):
                                        args = {}
                                    # 创建新的args副本，避免修改原数据
                                    tool["args"] = {**args, "knowledge_base_ids": self.knowledge_base_ids}
                                    logger.info(
                                        "knowledge_base_ids_injected_parallel",
                                        knowledge_base_ids_count=len(self.knowledge_base_ids)
                                    )

                        parallel_result = await self.executor.execute_tools_parallel(
                            tools=tools,
                            iteration=iteration_count
                        )

                        observation = {
                            "success": parallel_result.get("success", False),
                            "partial_success": parallel_result.get("partial_success", False),
                            "data": parallel_result.get("data", []),
                            "visuals": parallel_result.get("visuals", []),
                            "data_ids": parallel_result.get("data_ids", []),
                            "tool_results": parallel_result.get("tool_results", []),
                            "summary": parallel_result.get("summary", "并行执行完成"),
                            "parallel": True,
                            "success_count": parallel_result.get("success_count", 0),
                            "total_count": parallel_result.get("total_count", 0)
                        }

                        # 处理visuals（兼容Chart v3.1和ECharts标准格式）
                        if observation.get("visuals"):
                            for idx, vb in enumerate(observation["visuals"]):
                                # ✅ 适配ECharts标准格式：data字段直接包含图表配置
                                if "data" in vb:
                                    # ECharts标准格式
                                    chart_data = vb.get("data", {})
                                    m = vb.get("meta", {})
                                    self.memory.add_chart_observation({
                                        "visual_id": vb.get("id", f"visual_{idx}"),
                                        "chart_id": vb.get("id", f"echarts_{idx}"),
                                        "chart_type": vb.get("type", chart_data.get("series", [{}])[0].get("type", "unknown") if isinstance(chart_data.get("series"), list) and len(chart_data.get("series", [])) > 0 else "unknown"),
                                        "chart_title": vb.get("title", chart_data.get("title", {}).get("text", "")),
                                        "data_id": m.get("source_data_ids", [None])[0] if m else None,
                                        "source_tools": [t.get("tool") for t in tools],
                                        "schema_version": m.get("schema_version", "echarts_standard") if m else "echarts_standard"
                                    })
                                else:
                                    # 旧格式（Chart v3.1）：payload字段
                                    p = vb.get("payload", {})
                                    m = vb.get("meta", {})
                                    self.memory.add_chart_observation({
                                        "visual_id": vb.get("id", f"visual_{idx}"),
                                        "chart_id": p.get("id", f"chart_{idx}"),
                                        "chart_type": p.get("type", "unknown"),
                                        "chart_title": p.get("title", ""),
                                        "data_id": m.get("source_data_ids", [None])[0],
                                        "source_tools": [t.get("tool") for t in tools],
                                        "schema_version": "v2.0"
                                    })

                        action_event = {
                            "type": "action",
                            "data": {
                                "iteration": iteration_count,
                                "action": {**action, "parallel_result": parallel_result},
                                "timestamp": datetime.now().isoformat()
                            }
                        }
                        yield action_event
                        # ✅ 保存到对话历史
                        self.memory.session.add_action_message(action)

                        # 发送observation事件
                        observation_event = {
                            "type": "observation",
                            "data": {
                                "iteration": iteration_count,
                                "observation": observation,
                                "timestamp": datetime.now().isoformat()
                            }
                        }
                        yield observation_event
                        # ✅ 保存到对话历史
                        self.memory.session.add_observation_message(observation)

                        # 检查并行工具结果中是否有PDF预览或Markdown预览，发送office_document事件
                        tool_results = observation.get("tool_results", [])
                        for tool_result in tool_results:
                            result_data = tool_result.get("result", {})
                            # pdf_preview 和 markdown_preview 可能在 result_data 中直接存在，或者在 result_data.data 中
                            pdf_preview = None
                            markdown_preview = None
                            if isinstance(result_data, dict):
                                # 检查直接在 result_data 中的预览
                                if result_data.get("pdf_preview"):
                                    pdf_preview = result_data["pdf_preview"]
                                if result_data.get("markdown_preview"):
                                    markdown_preview = result_data["markdown_preview"]

                                # 获取文件路径和摘要
                                file_path = (
                                    result_data.get("file_path") or
                                    result_data.get("path") or
                                    result_data.get("source_file") or
                                    result_data.get("output_file")
                                )
                                summary = result_data.get("summary", "")

                                # 检查在 result_data.data 中的预览
                                if isinstance(result_data.get("data"), dict):
                                    if not pdf_preview and result_data["data"].get("pdf_preview"):
                                        pdf_preview = result_data["data"]["pdf_preview"]
                                    if not markdown_preview and result_data["data"].get("markdown_preview"):
                                        markdown_preview = result_data["data"]["markdown_preview"]
                                    if not file_path:
                                        file_path = (
                                            result_data["data"].get("file_path") or
                                            result_data["data"].get("path") or
                                            result_data["data"].get("source_file") or
                                            result_data["data"].get("output_file")
                                        )
                                    if not summary:
                                        summary = result_data.get("summary", "")

                            if pdf_preview or markdown_preview:
                                metadata = tool_result.get("metadata", {})
                                event_data = {
                                    "file_path": file_path,
                                    "generator": metadata.get("generator"),
                                    "summary": summary,
                                    "timestamp": datetime.now().isoformat()
                                }

                                if pdf_preview:
                                    event_data["pdf_preview"] = pdf_preview
                                if markdown_preview:
                                    event_data["markdown_preview"] = markdown_preview

                                yield {
                                    "type": "office_document",
                                    "data": event_data
                                }
                                logger.info(
                                    "office_document_event_sent_parallel",
                                    generator=metadata.get("generator"),
                                    has_pdf_preview=bool(pdf_preview),
                                    has_markdown_preview=bool(markdown_preview),
                                    pdf_id=pdf_preview.get("pdf_id") if pdf_preview else None
                                )

                    # TOOL_CALL: 单工具执行
                    elif action_type == "TOOL_CALL":
                        tool_name = action.get("tool")
                        tool_args = action.get("args", {})

                        # ✅ 自动注入 knowledge_base_ids（如果存在）
                        if self.knowledge_base_ids and tool_name == "knowledge_qa_workflow":
                            tool_args = dict(tool_args)  # 创建副本避免修改原参数
                            tool_args["knowledge_base_ids"] = self.knowledge_base_ids
                            logger.info(
                                "knowledge_base_ids_injected_run_loop",
                                tool_name=tool_name,
                                knowledge_base_ids_count=len(self.knowledge_base_ids)
                            )

                        action_event = {
                            "type": "action",
                            "data": {
                                "iteration": iteration_count,
                                "action": action,
                                "timestamp": datetime.now().isoformat()
                            }
                        }
                        yield action_event
                        # ✅ 保存到对话历史
                        self.memory.session.add_action_message(action)

                        observation = await self.executor.execute_tool(
                            tool_name=tool_name,
                            tool_args=tool_args,
                            iteration=iteration_count
                        )

                        # 检查是否是特殊工具（FINISH_SUMMARY）
                        if observation.get("action_type") == "FINISH_SUMMARY":
                            # 特殊工具：转换为对应的 action_type
                            special_action_type = observation["action_type"]
                            logger.info(
                                "special_tool_detected",
                                tool_name=tool_name,
                                action_type=special_action_type
                            )

                            # 使用特殊工具的 action_type
                            action_type = special_action_type

                            # 复用现有的 FINISH_SUMMARY 处理逻辑
                            if action_type == "FINISH_SUMMARY":
                                task_completed = True

                                # 从 observation 中获取 data_id（Agent 传递的数据ID）
                                data_ids = observation.get("data_id")

                                # 构建工具结果数据
                                if data_ids:
                                    # 如果有 data_id，加载完整数据
                                    if isinstance(data_ids, str):
                                        data_ids = [data_ids]

                                    logger.info(
                                        "finish_summary_loading_data",
                                        data_ids=data_ids,
                                        count=len(data_ids)
                                    )

                                    # 通过 DataContextManager 加载数据
                                    tool_results_parts = []

                                    # 预先收集所有迭代的 summary（用于关联 data_id）
                                    iteration_summaries = {}
                                    for iteration in self.memory.get_iterations():
                                        obs = iteration.get('observation', {})
                                        obs_data_id = obs.get('data_id')
                                        if obs_data_id and obs.get('summary'):
                                            iteration_summaries[obs_data_id] = obs['summary']

                                    for data_id in data_ids:
                                        try:
                                            # 从 executor 获取 data_context_manager
                                            data_context_manager = getattr(self.executor, 'data_context_manager', None)
                                            if not data_context_manager:
                                                raise AttributeError("ToolExecutor does not have data_context_manager")

                                            # 使用 data_context_manager 加载数据
                                            data = data_context_manager.get_data(data_id)
                                            if data:
                                                # 将数据转换为可读格式
                                                if isinstance(data, list) and len(data) > 0:
                                                    # 转换为字典格式并处理 datetime 对象
                                                    def serialize_datetime(obj):
                                                        """递归处理 datetime 对象为 ISO 格式字符串"""
                                                        if isinstance(obj, datetime):
                                                            return obj.isoformat()
                                                        elif isinstance(obj, dict):
                                                            return {k: serialize_datetime(v) for k, v in obj.items()}
                                                        elif isinstance(obj, list):
                                                            return [serialize_datetime(item) for item in obj]
                                                        return obj

                                                    data_dict = []
                                                    # 传递完整数据给LLM，不做任何限制
                                                    for item in data:
                                                        if hasattr(item, 'model_dump'):
                                                            item_dict = item.model_dump()
                                                            item_dict = serialize_datetime(item_dict)
                                                            data_dict.append(item_dict)
                                                        else:
                                                            data_dict.append(serialize_datetime(item))

                                                    # 获取关联的 summary（包含图表等可视化内容）
                                                    summary_text = iteration_summaries.get(data_id, "")

                                                    tool_results_parts.append(
                                                        f"## 数据: {data_id}\n"
                                                        f"记录数: {len(data)}\n"
                                                        f"完整数据:\n"
                                                        f"{json.dumps(data_dict, ensure_ascii=False, indent=2)}\n"
                                                        + (f"工具摘要: {summary_text}\n" if summary_text else "")
                                                    )
                                                else:
                                                    tool_results_parts.append(f"## 数据: {data_id}\n数据为空或格式不支持\n")
                                        except Exception as e:
                                            logger.warning(
                                                "finish_summary_data_load_failed",
                                                data_id=data_id,
                                                error=str(e)
                                            )
                                            tool_results_parts.append(f"## 数据: {data_id}\n加载失败: {str(e)}\n")

                                    tool_results = "\n\n".join(tool_results_parts)
                                else:
                                    # 如果没有 data_id，使用历史上下文（包含完整数据）
                                    tool_results = self.memory.session.get_compressed_summary()

                                # 生成最终答案提示词
                                prompt = format_finish_summary_prompt(
                                    user_query=user_query,
                                    tool_results=tool_results or "无工具调用数据",
                                    final_thought=thought
                                )

                                # ========== DEBUG: 打印 FINISH_SUMMARY 提示词 ==========
                                logger.info("=" * 80)
                                logger.info("[DEBUG] ========== FINISH_SUMMARY PROMPT ==========")
                                logger.info("[DEBUG] User Query:")
                                logger.info(user_query)
                                logger.info("[DEBUG] Final Thought:")
                                logger.info(thought)
                                logger.info("[DEBUG] Tool Results (first 5000 chars):")
                                logger.info((tool_results or "无工具调用数据")[:5000])
                                logger.info("[DEBUG] Tool Results length: %d chars", len(tool_results or ""))
                                logger.info("[DEBUG] Full Prompt (first 3000 chars):")
                                logger.info(prompt[:3000])
                                logger.info("[DEBUG] Full Prompt length: %d chars", len(prompt))
                                logger.info("[DEBUG] ========== END FINISH_SUMMARY PROMPT ==========")
                                logger.info("=" * 80)
                                # ========== END DEBUG ==========

                                # 调用 LLM 生成最终答案（流式输出）
                                final_answer = ""
                                async for chunk in self.planner.stream_user_answer(prompt):
                                    final_answer += chunk
                                    # 流式输出每个 chunk（使用前端已支持的 streaming_text 事件类型）
                                    yield {
                                        "type": "streaming_text",
                                        "data": {
                                            "chunk": chunk,
                                            "is_complete": False
                                        }
                                    }
                                # 发送流式完成标记
                                yield {
                                    "type": "streaming_text",
                                    "data": {
                                        "chunk": "",
                                        "is_complete": True
                                    }
                                }

                                self.memory.add_iteration(
                                    thought=thought,
                                    action={"type": "FINISH_SUMMARY"},
                                    observation={"success": True, "summary": "FINISH_SUMMARY: 生成最终答案"}
                                )

                                if final_answer:
                                    self.memory.session.add_assistant_message(
                                        final_answer,
                                        thought=thought,
                                        reasoning=reasoning if think_action_result is None else think_action_result.get("reasoning")
                                    )

                                yield {
                                    "type": "observation",
                                    "data": {
                                        "iteration": iteration_count,
                                        "observation": {"success": True, "summary": "FINISH_SUMMARY: 已生成最终答案"},
                                        "timestamp": datetime.now().isoformat()
                                    }
                                }

                                logger.info("task_completed_finish_summary", iterations=iteration_count)
                                break

                            # 特殊工具已处理，跳过常规流程
                            continue

                    # ERROR: 处理解析错误
                    elif action_type == "ERROR":
                        error_msg = action.get("error", "未知错误")
                        observation = {
                            "success": False,
                            "error": f"输出格式错误: {error_msg}",
                            "summary": f"你的输出格式不正确，请返回严格的JSON格式。错误信息: {error_msg}",
                            "requires_retry": True
                        }
                        logger.warning(
                            "action_error_requires_retry",
                            error=error_msg,
                            iteration=iteration_count
                        )

                    else:
                        observation = {
                            "success": False,
                            "error": f"Unknown action type: {action_type}",
                            "summary": f"任务失败：未知的 action type"
                        }

                    # Phase 3: Observation
                    # ✅ 检查是否可直接作为final answer（优化：避免二次LLM调用）
                    metadata = observation.get("metadata", {})
                    if metadata.get("can_be_final_answer") and observation.get("success"):
                        # 工作流结果可直接作为final answer
                        final_answer_field = metadata.get("final_answer_field", "answer")
                        data = observation.get("data", {})
                        final_answer = data.get(final_answer_field, "")

                        if final_answer:
                            logger.info(
                                "direct_final_answer_from_workflow",
                                tool_name=tool_name,
                                final_answer_field=final_answer_field,
                                answer_length=len(final_answer)
                            )

                            # ✅ 设置标志：来自工作流直接返回
                            direct_from_workflow = True
                            # ✅ 保存 sources 数据
                            workflow_sources = data.get("sources", [])
                            # ✅ 保存 visuals 数据
                            workflow_visuals = observation.get("visuals", [])

                            # 记录到记忆
                            self.memory.add_iteration(
                                thought=thought,
                                action=action,
                                observation={"success": True, "summary": observation.get("summary", "")}
                            )

                            # 添加助手消息
                            self.memory.session.add_assistant_message(
                                final_answer,
                                thought=thought,
                                reasoning=reasoning if think_action_result is None else think_action_result.get("reasoning")
                            )

                            # 流式返回final answer
                            yield {
                                "type": "final_answer",
                                "data": {
                                    "content": final_answer,
                                    "sources": data.get("sources", []),
                                    "metadata": metadata,
                                    "iteration": iteration_count,
                                    "direct_from_workflow": True  # 标记：直接来自工作流
                                }
                            }

                            task_completed = True
                            break

                    # 处理visuals结果事件
                    if observation.get("visuals") and isinstance(observation.get("visuals"), list):
                        # ✅ 收集visuals到workflow_visuals（用于complete事件）
                        workflow_visuals.extend(observation["visuals"])

                        yield {
                            "type": "result",
                            "data": {
                                "status": observation.get("status", "success"),
                                "success": observation.get("success", True),
                                "visuals": observation["visuals"],
                                "metadata": observation.get("metadata", {}),
                                "summary": observation.get("summary", "")
                            }
                        }

                    observation_event = {
                        "type": "observation",
                        "data": {
                            "iteration": iteration_count,
                            "observation": observation,
                            "timestamp": datetime.now().isoformat()
                        }
                    }
                    yield observation_event
                    # ✅ 保存到对话历史
                    self.memory.session.add_observation_message(observation)

                    # 发送office_document事件（用于前端PDF预览面板和Markdown预览面板）
                    data = observation.get("data", {})
                    logger.info(
                        "office_document_event_check",
                        has_data=data is not None,
                        data_is_dict=isinstance(data, dict),
                        data_keys=list(data.keys()) if isinstance(data, dict) else "N/A",
                        has_pdf_preview=isinstance(data, dict) and "pdf_preview" in data,
                        has_markdown_preview=isinstance(data, dict) and "markdown_preview" in data,
                        pdf_preview_type=type(data.get("pdf_preview")).__name__ if isinstance(data, dict) else "N/A",
                        observation_keys=list(observation.keys()),
                    )

                    # 检查是否有PDF预览或Markdown预览
                    has_pdf_preview = isinstance(data, dict) and data.get("pdf_preview")
                    has_markdown_preview = isinstance(data, dict) and data.get("markdown_preview")

                    if has_pdf_preview or has_markdown_preview:
                        metadata = observation.get("metadata", {})
                        # 获取文件路径，支持多种字段名：file_path, path, source_file, output_file
                        file_path = (
                            data.get("file_path") or
                            data.get("path") or
                            data.get("source_file") or
                            data.get("output_file")
                        )

                        event_data = {
                            "file_path": file_path,
                            "generator": metadata.get("generator"),
                            "summary": observation.get("summary", ""),
                            "timestamp": datetime.now().isoformat()
                        }

                        # 添加PDF预览数据
                        if has_pdf_preview:
                            event_data["pdf_preview"] = data["pdf_preview"]

                        # 添加Markdown预览数据
                        if has_markdown_preview:
                            event_data["markdown_preview"] = data["markdown_preview"]

                        yield {
                            "type": "office_document",
                            "data": event_data
                        }

                        logger.info(
                            "office_document_event_sent",
                            generator=metadata.get("generator"),
                            has_pdf_preview=has_pdf_preview,
                            has_markdown_preview=has_markdown_preview,
                            pdf_id=data["pdf_preview"].get("pdf_id") if has_pdf_preview else None,
                            file_path=file_path
                        )

                    # 记忆更新
                    self.memory.add_iteration(thought=thought, action=action, observation=observation)

                    # ❌ 移除：不要将工具调用详情保存到对话历史
                    # 这些详细信息只在实时对话时通过 observation 事件传递给前端
                    # 历史对话恢复时不需要显示这些详细内容
                    # （已经通过 add_observation_message 保存了摘要）

                except Exception as e:
                    logger.error(
                        "iteration_failed",
                        iteration=iteration_count,
                        error=str(e),
                        error_type=type(e).__name__,
                        exc_info=True
                    )

                    yield {
                        "type": "error",
                        "data": {
                            "iteration": iteration_count,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "timestamp": datetime.now().isoformat()
                        }
                    }

                    if "fatal" in str(e).lower():
                        break

            # Step 4: 完成或超时
            if task_completed:
                logger.info(
                    "react_loop_completed",
                    iterations=iteration_count,
                    session_id=self.memory.session_id
                )

                # 新增：记录运行完成日志
                if self.agent_logger:
                    self.agent_logger.end_run(
                        status="completed",
                        final_answer=final_answer,
                        metadata={"iterations": iteration_count}
                    )

                # 记录助手回复
                if final_answer:
                    self.memory.session.add_assistant_response(final_answer)

                # 🔑 保存成功策略到长期记忆
                await self._save_successful_strategy(
                    self.memory.get_iterations(),
                    user_query
                )

                # Note: 长期记忆保存已移除

                # ✅ 日志：输出sources和visuals字段信息
                logger.info(
                    "complete_event_data",
                    sources_count=len(workflow_sources),
                    visuals_count=len(workflow_visuals),
                    direct_from_workflow=direct_from_workflow,
                    sources_preview=workflow_sources[:2] if workflow_sources else [],
                    visuals_preview=[{"id": v.get("id"), "type": v.get("type")} for v in workflow_visuals[:2]] if workflow_visuals else []
                )

                yield {
                    "type": "complete",
                    "data": {
                        "answer": final_answer,
                        "response": final_answer,  # ✅ 同时返回response字段
                        "iterations": iteration_count,
                        "session_id": self.memory.session_id,
                        "timestamp": datetime.now().isoformat(),
                        "sources": workflow_sources,  # ✅ 添加sources字段（已在处理工作流时保存）
                        "visuals": workflow_visuals,  # ✅ 添加visuals字段（图表数据）
                        "direct_from_workflow": direct_from_workflow  # ✅ 标记：是否来自工作流直接返回
                    }
                }

            else:
                # 达到最大迭代次数
                logger.warning(
                    "react_loop_max_iterations",
                    iterations=iteration_count,
                    session_id=self.memory.session_id
                )

                # 记录超时日志
                if self.agent_logger:
                    self.agent_logger.end_run(
                        status="timeout",
                        metadata={"iterations": iteration_count, "reason": "max_iterations_reached"}
                    )

                partial_answer = (
                    "分析任务较复杂，已尝试多种方法但未能在规定步骤内完成。\n\n"
                    "💡 建议：\n"
                    "• 将复杂问题拆分成几个简单问题\n"
                    "• 提供更具体的背景信息\n"
                    "• 直接询问某个特定方面"
                )

                # 记录助手回复
                if partial_answer:
                    self.memory.session.add_assistant_response(partial_answer)

                # ✅ 使用 complete 事件类型（与正常完成一致）
                # agent_bridge 无需特殊处理，直接提取 answer 字段即可
                yield {
                    "type": "complete",
                    "data": {
                        "answer": partial_answer,
                        "response": partial_answer,
                        "iterations": iteration_count,
                        "session_id": self.memory.session_id,
                        "timestamp": datetime.now().isoformat(),
                        "status": "incomplete",  # ✅ 标记状态（可选）
                        "reason": "max_iterations_reached"
                    }
                }

        except Exception as e:
            logger.error(
                "react_loop_fatal_error",
                error=str(e),
                exc_info=True
            )

            # 新增：记录致命错误日志
            if self.agent_logger:
                self.agent_logger.log_error(error=str(e), error_type="fatal")
                self.agent_logger.end_run(status="failed", metadata={"error": str(e)})

            yield {
                "type": "fatal_error",
                "data": {
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
            }

    async def _execute_thought(
        self,
        query: str,
        iteration: int,
        enhanced_context: str = ""
    ) -> Tuple[Dict[str, Any], str]:
        """
        执行思考阶段（Thought）

        Args:
            query: 用户查询
            iteration: 当前迭代次数
            enhanced_context: 增强的上下文（包含实际数据）

        Returns:
            (思考结果, 上下文快照)
        """
        # 获取基础上下文
        base_context = self.memory.session.get_compressed_summary()

        # 构建完整上下文
        full_context = enhanced_context if enhanced_context else base_context

        # 获取对话历史（用于LLM上下文）
        conversation_history = self.memory.session.get_messages_for_llm()

        # 调用 LLM 规划器生成思考
        thought_result = await self.planner.generate_thought(
            query=query,
            context=full_context,
            iteration=iteration,
            enable_reasoning=self.enable_reasoning,
            conversation_history=conversation_history
        )

        logger.debug(
            "thought_generated",
            iteration=iteration,
            thought_preview=thought_result["thought"][:100]
        )

        return thought_result, full_context

    async def _execute_action(
        self,
        thought_result: Dict[str, Any],
        latest_observation: Optional[Dict[str, Any]] = None,
        iteration: int = 1
    ) -> Dict[str, Any]:
        """
        执行行动阶段（Action）

        Args:
            thought_result: 思考结果
            latest_observation: 上一次迭代的观察结果（可能包含Reflexion建议）
            iteration: 当前迭代次数

        Returns:
            行动决策
        """
        # 获取当前上下文（用于decide_action）
        current_context = self.memory.session.get_compressed_summary()

        # 获取对话历史（用于LLM上下文）
        conversation_history = self.memory.session.get_messages_for_llm()

        # 调用 LLM 规划器决定行动（传递上下文和Reflexion建议）
        action = await self.planner.decide_action(
            thought_result,
            context=current_context,
            latest_observation=latest_observation,
            enable_reasoning=self.enable_reasoning,
            conversation_history=conversation_history
        )

        # 安全检查 action 对象
        action_type = action.get("type")
        if not action_type:
            logger.error(
                "action_missing_type",
                action_keys=list(action.keys()) if isinstance(action, dict) else None,
                action=action
            )
            # 返回一个默认的完成行动作为降级策略
            return {
                "type": "FINISH_SUMMARY",
                "answer": "抱歉，Agent 在决策过程中遇到技术问题，未能完成分析。",
                "reasoning": "行动决策缺少必要字段"
            }

        # 新增：处理并行工具调用（TOOL_CALLS）
        if action_type == "TOOL_CALLS":
            tools = action.get("tools", [])

            # ✅ 为 knowledge_qa_workflow 自动注入 knowledge_base_ids
            if self.knowledge_base_ids:
                for tool in tools:
                    if tool.get("tool") == "knowledge_qa_workflow":
                        args = tool.get("args", {})
                        if not isinstance(args, dict):
                            args = {}
                        # 创建新的args副本，避免修改原数据
                        tool["args"] = {**args, "knowledge_base_ids": self.knowledge_base_ids}
                        logger.info(
                            "knowledge_base_ids_injected_parallel_execute_action",
                            knowledge_base_ids_count=len(self.knowledge_base_ids)
                        )

            logger.info(
                "parallel_tool_call_detected",
                tool_count=len(tools),
                tools=[t.get("tool") for t in tools]
            )

            # 并行执行所有工具
            parallel_result = await self.executor.execute_tools_parallel(
                tools=tools,
                iteration=iteration
            )

            # 返回包含并行执行结果的 action
            return {
                "type": "TOOL_CALLS",
                "tools": tools,
                "parallel_result": parallel_result,
                "reasoning": action.get("reasoning", "并行执行多个工具")
            }

        logger.info(
            "action_decided",
            action_type=action_type,
            tool=action.get("tool")
        )

        return action

    async def _execute_observation(
        self,
        action: Dict[str, Any],
        iteration: int
    ) -> Dict[str, Any]:
        """
        执行观察阶段（Observation）

        Args:
            action: 行动决策
            iteration: 当前迭代次数

        Returns:
            观察结果
        """
        # 安全检查action类型
        action_type = action.get("type")
        if action_type != "TOOL_CALL":
            return {
                "success": True,
                "summary": f"任务完成或无效操作，action_type={action_type}"
            }

        # 验证工具名称存在
        tool_name = action.get("tool")
        if not tool_name:
            logger.error(
                "action_missing_tool",
                action=action,
                iteration=iteration
            )
            return {
                "success": False,
                "error": f"Action类型为TOOL_CALL但缺少tool名称: {action}"
            }

        # ✅ 获取工具参数并自动注入 knowledge_base_ids（如果存在）
        tool_args = action.get("args", {})

        # 调试日志：检查注入条件
        logger.info(
            "knowledge_base_ids_injection_check",
            tool_name=tool_name,
            has_kb_ids=self.knowledge_base_ids is not None,
            kb_ids_count=len(self.knowledge_base_ids) if self.knowledge_base_ids else 0,
            is_qa_workflow=tool_name == "knowledge_qa_workflow"
        )

        if self.knowledge_base_ids and tool_name == "knowledge_qa_workflow":
            # 为知识问答工作流自动注入知识库ID
            tool_args = dict(tool_args)  # 创建副本避免修改原参数
            tool_args["knowledge_base_ids"] = self.knowledge_base_ids
            logger.info(
                "knowledge_base_ids_injected",
                tool_name=tool_name,
                knowledge_base_ids_count=len(self.knowledge_base_ids),
                knowledge_base_ids=self.knowledge_base_ids[:2]  # 记录前2个ID
            )

        # 执行工具调用
        observation = await self.executor.execute_tool(
            tool_name=tool_name,
            tool_args=tool_args,
            iteration=iteration
        )

        # ✅ 记录工具执行结果到Schema注入器
        self.schema_injector.record_tool_result(tool_name, observation)

        # ✅ 检查是否需要注入工具schema
        if self.schema_injector.should_inject_schema(tool_name):
            schema_text = self.schema_injector.get_tool_schema(
                tool_name,
                self.executor.tool_registry
            )

            if schema_text:
                # 将schema注入到observation中
                observation["schema_injection"] = schema_text
                observation["schema_injection_notice"] = (
                    f"⚠️ 你连续{self.schema_injector.consecutive_error_threshold}次调用工具{tool_name}失败。"
                    f"已自动注入该工具的完整schema，请仔细阅读参数要求后再试。"
                )

                logger.info(
                    "schema_injected",
                    tool_name=tool_name,
                    error_count=self.schema_injector.tool_error_counts[tool_name]
                )

        logger.info(
            "tool_executed",
            tool=tool_name,
            success=observation.get("success"),
            has_data="data" in observation
        )

        return observation

    async def _guard_task_completion(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        任务状态守卫 - 在任务结束前检查是否有未完成任务

        参考最佳实践：在 LLM 决定完成任务前，强制检查任务状态。
        如果有未完成任务（pending 或 in_progress），生成警告提示。

        Args:
            session_id: 会话 ID

        Returns:
            守卫检查结果：
            {
                "has_incomplete": bool,
                "incomplete_count": int,
                "incomplete_tasks": List[Dict],
                "warning_message": str
            }
        """
        # 使用守卫模块进行检查
        return await self.task_completion_guard.check(session_id)

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        获取记忆统计信息

        Returns:
            统计信息字典
        """
        return {
            "working_iterations": len(self.memory.recent_iterations),
            "compressed_iterations": len(self.memory.session.compressed_iterations),
            "data_files": len(self.memory.session.data_files),
            "session_id": self.memory.session_id
        }

    async def _save_successful_strategy(
        self,
        iterations: List[Dict[str, Any]],
        query: str
    ):
        """
        保存成功的策略模式（已禁用长期记忆保存）

        Args:
            iterations: 迭代记录列表
            query: 用户查询
        """
        # Note: 长期记忆保存已禁用，此方法不再执行任何操作
        # 原因：向量检索无效，经常误导Agent
        try:
            # 仅记录日志，不保存到长期记忆
            tool_sequence = []
            for iteration in iterations:
                action = iteration.get("action", {})
                observation = iteration.get("observation", {})

                if action.get("type") == "TOOL_CALL" and observation.get("success"):
                    tool_sequence.append(action.get("tool", ""))

            if tool_sequence:
                logger.info(
                    "successful_strategy_execution",
                    query=query[:100],
                    tool_count=len(tool_sequence),
                    tools_used=list(set(tool_sequence)),
                    note="Not saved to longterm memory (disabled)"
                )
        except Exception as e:
            logger.error(
                "save_successful_strategy_failed",
                error=str(e)
            )

    def __repr__(self) -> str:
        return f"<ReActLoop session={self.memory.session_id} max_iter={self.max_iterations}>"

    def get_agent_log_summary(self) -> Optional[Dict[str, Any]]:
        """
        获取当前运行的日志摘要

        Returns:
            运行摘要或None
        """
        if self.agent_logger:
            return self.agent_logger.get_run_summary()
        return None

    def get_enhanced_stats(self) -> Dict[str, Any]:
        """
        获取增强的统计信息（包含记忆、日志）

        Returns:
            综合统计信息
        """
        stats = self.get_memory_stats()

        if self.agent_logger:
            stats["current_run"] = self.agent_logger.get_run_summary()

        return stats

    def _format_observation(self, observation: Dict[str, Any]) -> str:
        """
        将观察结果直接序列化为JSON传递给LLM

        简化设计：移除复杂的格式化器层，直接传递完整JSON数据给LLM。
        LLM擅长理解JSON格式，无需额外的文本格式化层。

        Args:
            observation: 观察结果字典

        Returns:
            JSON格式的字符串
        """
        if not observation:
            return ""

        try:
            # ✅ 如果有schema注入，优先显示schema（放在observation前面）
            if "schema_injection" in observation:
                schema_notice = observation.get("schema_injection_notice", "")
                schema_text = observation["schema_injection"]

                # 构建带schema的observation
                formatted = f"{schema_notice}\n\n{schema_text}\n\n---\n\n"

                # 序列化原始observation（移除schema相关字段避免重复）
                obs_copy = {k: v for k, v in observation.items()
                           if k not in ["schema_injection", "schema_injection_notice"]}
                formatted += json.dumps(obs_copy, ensure_ascii=False, indent=2, default=str)

                return formatted

            # 直接序列化为JSON，保持完整信息
            # 使用 ensure_ascii=False 支持中文
            # 使用 indent=2 提高可读性
            # 使用 default=str 处理datetime等特殊类型
            return json.dumps(observation, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error(
                "observation_serialize_failed",
                error=str(e),
                error_type=type(e).__name__
            )
            # 降级：只返回摘要
            return f"状态: {'成功' if observation.get('success') else '失败'}\n摘要: {observation.get('summary', '')}"

    def _format_action_info(self, action: Dict[str, Any]) -> str:
        """
        格式化工具调用信息为字符串

        Args:
            action: 动作字典 {"type": "TOOL_CALL", "tool": "tool_name", "args": {...}}

        Returns:
            格式化的字符串
        """
        if not action or action.get("type") != "TOOL_CALL":
            return ""

        tool_name = action.get("tool", "")
        args = action.get("args", {})

        lines = [f"**调用工具**: {tool_name}"]

        # 格式化参数（隐藏过长的内容）
        if args:
            lines.append("**参数**:")
            for key, value in args.items():
                # 截断过长的字符串参数
                if isinstance(value, str) and len(value) > 100:
                    value = value[:100] + "..."
                # 对路径参数使用正斜杠，避免 JSON 转义问题
                if isinstance(value, str) and key in ["path", "output_dir", "output_file", "save_as"]:
                    value = value.replace("\\", "/")
                lines.append(f"  - {key}: {value}")

        return "\n".join(lines)

