"""
ReAct Loop Engine (Refactored)

ReAct 循环引擎，实现 Thought → Action → Observation 循环。

重构后的模块化结构：
- ReWOOExecutor: ReWOO 规划执行
- MemoryToolsHandler: 内存工具管理
- AutoTokenManager: 自动Token管理（学习Mini-Agent）
- AgentLogger: 运行日志追踪（学习Mini-Agent）
"""

from typing import Dict, Any, AsyncGenerator, Tuple, List, Optional
from datetime import datetime
import structlog
import json

from ..memory.hybrid_manager import HybridMemoryManager
from .rewoo_executor import ReWOOExecutor
from .memory_tools_handler import MemoryToolsHandler

# 新增：自动Token管理和运行日志（学习Mini-Agent）
from ...utils.auto_token_manager import AutoTokenManager
from ...utils.agent_logger import AgentLogger
from ..prompts.react_prompts import format_finish_summary_prompt

# 新增：简化的上下文构建器
from ..context.simplified_context_builder import SimplifiedContextBuilder

logger = structlog.get_logger()


class ReActLoop:
    """
    ReAct 循环引擎（重构版）

    负责执行完整的 ReAct 循环：
    - Thought: LLM 分析当前状态
    - Action: 决定下一步行动（工具调用或完成）
    - Observation: 记录执行结果

    支持两种执行模式：
    1. ReAct 模式（默认）: 动态循环，灵活应对
    2. ReWOO 模式: 一次性规划，减少 LLM 调用

    新增特性（学习Mini-Agent）：
    - 自动Token管理：防止长对话context溢出
    - 运行日志追踪：完整记录执行过程，便于调试
    """

    def __init__(
        self,
        memory_manager: HybridMemoryManager,
        llm_planner,
        tool_executor,
        max_iterations: int = 10,
        stream_enabled: bool = True,
        plan_mode: bool = False,
        # 新增：Token管理和日志配置
        token_limit: int = 80000,
        enable_agent_logging: bool = True,
        log_dir: str = "./logs/agent_runs",
        enable_reasoning: bool = False,  # ✅ 思考模式开关（是否显示LLM推理过程）
        single_step_mode: bool = False,  # ✅ V4优化：单步模式（合并Thought+Action）
        is_interruption: bool = False  # ✅ 是否为用户中断后的对话
    ):
        """
        初始化 ReAct 循环引擎

        Args:
            memory_manager: 混合记忆管理器
            llm_planner: LLM 规划器
            tool_executor: 工具执行器
            max_iterations: 最大迭代次数
            stream_enabled: 是否启用流式输出
            plan_mode: 是否使用 ReWOO 规划模式
            token_limit: Token上限（用于自动压缩）
            enable_agent_logging: 是否启用Agent运行日志
            log_dir: 日志目录
            single_step_mode: V4优化：单步模式（一次LLM调用同时生成Thought和Action）
            is_interruption: 是否为用户中断后的对话（用户暂停后继续对话时为True）
        """
        self.memory = memory_manager
        self.planner = llm_planner
        self.executor = tool_executor
        self.max_iterations = max_iterations
        self.stream_enabled = stream_enabled
        self.plan_mode = plan_mode
        self.single_step_mode = single_step_mode  # V4优化
        self.is_interruption = is_interruption  # ✅ 保存中断标志

        # 初始化处理器模块
        self.rewoo_executor = ReWOOExecutor(memory_manager, llm_planner, tool_executor)
        self.memory_tools_handler = MemoryToolsHandler(memory_manager, tool_executor)

        # 新增：自动Token管理器（学习Mini-Agent）
        self.token_manager = AutoTokenManager(token_limit=token_limit)

        # 新增：Agent运行日志（学习Mini-Agent）
        self.enable_agent_logging = enable_agent_logging
        self.agent_logger = AgentLogger(
            log_dir=log_dir,
            enable_file_logging=enable_agent_logging
        ) if enable_agent_logging else None

        # 新增：简化的上下文构建器
        # llm_planner 是 ReActPlanner 实例，使用 llm_service 属性
        llm_client = llm_planner.llm_service if hasattr(llm_planner, 'llm_service') else None
        self.context_builder = SimplifiedContextBuilder(
            llm_client=llm_client,
            memory_manager=memory_manager,
            tool_registry=tool_executor.tool_registry if hasattr(tool_executor, 'tool_registry') else None
        )

        # 注册内存相关工具
        self.memory_tools_handler.register_memory_tools()

        # ✅ 保存思考模式设置
        self.enable_reasoning = enable_reasoning

        # ✅ 初始化当前模式（默认expert）
        self.current_mode = "expert"

        logger.info(
            "react_loop_initialized",
            session_id=memory_manager.session_id,
            max_iterations=max_iterations,
            plan_mode=plan_mode,
            token_limit=token_limit,
            agent_logging=enable_agent_logging,
            enable_reasoning=enable_reasoning,
            single_step_mode=single_step_mode  # V4优化
        )

    async def run(
        self,
        user_query: str,
        enhance_with_history: bool = True,
        debug_mode: bool = False,
        initial_messages: Optional[List[Dict[str, Any]]] = None,  # ✅ 新增：历史消息注入
        manual_mode: Optional[str] = None  # ✅ 新增：手动指定模式（"assistant" | "expert"）
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行单步模式 ReAct 循环（V4版）

        Args:
            user_query: 用户查询
            enhance_with_history: 是否使用长期记忆增强
            debug_mode: 调试模式
            initial_messages: 历史消息列表（用于会话恢复）
            manual_mode: 手动指定Agent模式（"assistant" | "expert"，默认expert）

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

        # 模式路由：plan_mode 是回退选项
        if self.plan_mode:
            logger.info("using_rewoo_mode_fallback", query=user_query[:100])
            async for event in self.rewoo_executor.execute_plan(
                user_query,
                max_iterations=self.max_iterations
            ):
                yield event
        else:
            # 单步模式（默认）
            async for event in self._run_react_loop(
                user_query,
                enhance_with_history,
                debug_mode,
                initial_messages  # ✅ 传递历史消息
            ):
                # 附加模式信息到事件
                event["mode"] = self.current_mode
                yield event

    async def _run_react_loop(
        self,
        user_query: str,
        enhance_with_history: bool = True,
        debug_mode: bool = False,
        initial_messages: Optional[List[Dict[str, Any]]] = None  # ✅ 新增：历史消息注入
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        V4单步模式：ReAct 循环（合并 Thought + Action）

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
            user_query: 用户查询
            enhance_with_history: 是否使用长期记忆增强
            debug_mode: 调试模式

        Yields:
            流式事件
        """
        try:
            # 新增：开始运行日志记录
            if self.agent_logger:
                run_id = self.agent_logger.start_new_run(
                    session_id=self.memory.session_id,
                    query=user_query,
                    metadata={"enhance_with_history": enhance_with_history, "debug_mode": debug_mode}
                )
                logger.info("agent_run_started", run_id=run_id, log_file=self.agent_logger.get_log_file_path())

            # ✅ 设置planner的中断标志
            self.planner.is_interruption = self.is_interruption
            if self.is_interruption:
                logger.info("interruption_flag_set", is_interruption=True, query=user_query[:100])

            # ✅ Step 0a: 如果有历史消息，先加载到 session（用于会话恢复）
            if initial_messages:
                self.memory.session.load_history_messages(initial_messages)
                logger.info(
                    "initial_messages_loaded",
                    session_id=self.memory.session_id,
                    message_count=len(initial_messages)
                )

            # Step 0: 记录用户消息
            self.memory.session.add_user_message(user_query)

            # Step 1: 使用原始查询（长期记忆增强已移除）
            enhanced_query = user_query
            logger.info(
                "query_processing",
                query_length=len(user_query),
                longterm_memory_disabled=True
            )

            # Step 2: 初始化循环状态
            iteration_count = 0
            task_completed = False
            final_answer = None

            # Yield start event
            yield {
                "type": "start",
                "data": {
                    "query": user_query,
                    "session_id": self.memory.session_id,
                    "timestamp": datetime.now().isoformat()
                }
            }

            # Step 3: 单步模式循环（V4）
            while iteration_count < self.max_iterations and not task_completed:
                iteration_count += 1

                # Token检查
                await self._check_and_compress_tokens()

                logger.info(
                    "single_step_iteration",
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
                        mode=self.current_mode  # ✅ 传递当前模式
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
                                    }
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
                                yield {
                                    "type": "thought",
                                    "data": {
                                        "iteration": iteration_count,
                                        "thought": thought,
                                        "reasoning": reasoning,
                                        "timestamp": datetime.now().isoformat()
                                    }
                                }

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

                        yield {
                            "type": "thought",
                            "data": {
                                "iteration": iteration_count,
                                "thought": thought,
                                "reasoning": reasoning,
                                "timestamp": datetime.now().isoformat()
                            }
                        }

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

                        logger.info("task_completed_final_answer", iterations=iteration_count)
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

                        # 调用 LLM 生成最终答案
                        final_answer = ""
                        async for chunk in self.planner.stream_user_answer(prompt):
                            final_answer += chunk

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

                    # TOOL_CALLS: 并行执行
                    if action_type == "TOOL_CALLS":
                        tools = action.get("tools", [])
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

                        # 处理visuals
                        if observation.get("visuals"):
                            for idx, vb in enumerate(observation["visuals"]):
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

                        yield {
                            "type": "action",
                            "data": {
                                "iteration": iteration_count,
                                "action": {**action, "parallel_result": parallel_result},
                                "timestamp": datetime.now().isoformat()
                            }
                        }

                    # TOOL_CALL: 单工具执行
                    elif action_type == "TOOL_CALL":
                        tool_name = action.get("tool")
                        tool_args = action.get("args", {})

                        yield {
                            "type": "action",
                            "data": {
                                "iteration": iteration_count,
                                "action": action,
                                "timestamp": datetime.now().isoformat()
                            }
                        }

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

                                # 调用 LLM 生成最终答案
                                final_answer = ""
                                async for chunk in self.planner.stream_user_answer(prompt):
                                    final_answer += chunk

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

                    else:
                        observation = {
                            "success": False,
                            "error": f"Unknown action type: {action_type}",
                            "summary": f"任务失败：未知的 action type"
                        }

                    # Phase 3: Observation
                    # 处理visuals结果事件
                    if observation.get("visuals") and isinstance(observation.get("visuals"), list):
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

                    yield {
                        "type": "observation",
                        "data": {
                            "iteration": iteration_count,
                            "observation": observation,
                            "timestamp": datetime.now().isoformat()
                        }
                    }

                    # 记忆更新
                    self.memory.add_iteration(thought=thought, action=action, observation=observation)

                    if observation.get("summary"):
                        # 使用完整格式化内容（包含完整数据）而非仅摘要
                        full_message = self._format_observation(observation)
                        # 添加工具调用信息（帮助LLM了解历史操作）
                        action_info = self._format_action_info(action)
                        full_message = f"{action_info}\n\n{full_message}"

                        # 🔍 详细日志：验证完整数据传递
                        metadata = observation.get("metadata", {})
                        generator = metadata.get("generator", "")
                        data = observation.get("data")
                        logger.info(
                            "format_observation_debug",
                            generator=generator,
                            full_message_length=len(full_message),
                            full_message_preview=full_message[:500] if len(full_message) > 500 else full_message,
                            has_analysis=isinstance(data, dict) and "analysis" in data,
                            observation_keys=list(observation.keys()),
                            data_keys=list(data.keys()) if isinstance(data, dict) else []
                        )

                        self.memory.session.add_assistant_message(
                            full_message,
                            thought=thought,
                            reasoning=reasoning if think_action_result is None else think_action_result.get("reasoning")
                        )


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

                yield {
                    "type": "complete",
                    "data": {
                        "answer": final_answer,
                        "response": final_answer,  # ✅ 同时返回response字段
                        "iterations": iteration_count,
                        "session_id": self.memory.session_id,
                        "timestamp": datetime.now().isoformat()
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

                partial_answer = "抱歉，达到最大迭代次数限制，未能完成分析。请尝试简化查询或分步提问。"

                # 记录助手回复
                if partial_answer:
                    self.memory.session.add_assistant_response(partial_answer)

                yield {
                    "type": "incomplete",
                    "data": {
                        "answer": partial_answer,
                        "iterations": iteration_count,
                        "reason": "max_iterations_reached",
                        "timestamp": datetime.now().isoformat()
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

        # 执行工具调用
        observation = await self.executor.execute_tool(
            tool_name=tool_name,
            tool_args=action.get("args", {}),
            iteration=iteration
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
        try:
            # 获取任务列表（FINAL_ANSWER 模式下，使用最小化的 ExecutionContext）
            from app.agent.context.execution_context import ExecutionContext
            from app.agent.context.data_context_manager import DataContextManager

            # 创建临时的 DataContextManager（用于访问 TaskList）
            # ✅ 修复：使用 self.memory 而非 session_id
            data_manager = DataContextManager(memory_manager=self.memory)

            # 创建 ExecutionContext（iteration 参数在此场景下不使用，传入 0）
            context = ExecutionContext(
                session_id=session_id,
                iteration=0,
                data_manager=data_manager
            )
            task_list = context.get_task_list()

            if not task_list:
                return {
                    "has_incomplete": False,
                    "incomplete_count": 0,
                    "incomplete_tasks": [],
                    "warning_message": ""
                }

            # 检查未完成任务
            incomplete_tasks = []
            for task in task_list.get_tasks().values():
                if task.status.value in ["pending", "in_progress"]:
                    incomplete_tasks.append({
                        "id": task.id,
                        "subject": task.subject,
                        "status": task.status.value,
                        "progress": task.progress
                    })

            # 按状态排序（in_progress 优先）
            incomplete_tasks.sort(key=lambda t: 0 if t["status"] == "in_progress" else 1)

            has_incomplete = len(incomplete_tasks) > 0

            if has_incomplete:
                # 生成警告消息
                task_list_str = "\n".join(
                    f"- [{t['status']}] {t['subject']} (ID: {t['id']})"
                    for t in incomplete_tasks
                )

                warning_message = f"""
## ⚠️ 任务未完成警告

检测到你有 {len(incomplete_tasks)} 个任务尚未完成：

{task_list_str}

## 必须执行的操作

根据任务清单管理规范，你必须：

1. **标记任务完成**：对每个 in_progress 任务调用
   ```json
   {{"tool": "update_task", "args": {{"task_id": "任务ID", "status": "completed"}}}}
   ```

2. **确认所有任务**：调用 list_tasks 查看任务状态
   ```json
   {{"tool": "list_tasks", "args": {{}}}}
   ```

3. **然后才能结束**：所有任务完成后才能调用 FINISH

禁止创建任务后就不再管理状态！
"""
                logger.warning(
                    "task_guard_incomplete_found",
                    session_id=session_id,
                    incomplete_count=len(incomplete_tasks),
                    task_ids=[t["id"] for t in incomplete_tasks]
                )
            else:
                warning_message = ""
                logger.info(
                    "task_guard_all_completed",
                    session_id=session_id
                )

            return {
                "has_incomplete": has_incomplete,
                "incomplete_count": len(incomplete_tasks),
                "incomplete_tasks": incomplete_tasks,
                "warning_message": warning_message
            }

        except Exception as e:
            logger.error(
                "task_guard_check_failed",
                session_id=session_id,
                error=str(e),
                exc_info=True
            )
            # 守卫检查失败不影响主流程
            return {
                "has_incomplete": False,
                "incomplete_count": 0,
                "incomplete_tasks": [],
                "warning_message": ""
            }

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
        mode = "ReWOO" if self.plan_mode else "ReAct"
        return f"<ReActLoop session={self.memory.session_id} mode={mode} max_iter={self.max_iterations}>"

    # ==================== 新增：Token管理和日志辅助方法 ====================

    async def _check_and_compress_tokens(self):
        """
        检查Token使用并按需压缩（学习Mini-Agent）

        与现有三层记忆系统协同工作：
        - 检查会话记忆的消息历史
        - 超限时触发自动摘要
        - 保持三层记忆的独立性
        """
        try:
            # 获取会话消息用于Token检查
            session_messages = self.memory.session.get_messages_for_llm()

            # 检查是否需要摘要
            if self.token_manager.should_summarize(session_messages):
                logger.info(
                    "token_limit_approaching",
                    estimated_tokens=self.token_manager.estimate_tokens(session_messages),
                    limit=self.token_manager.token_limit
                )

                # 使用LLM生成摘要的回调
                async def llm_summarizer(prompt: str) -> str:
                    try:
                        result = await self.planner.generate_summary(prompt)
                        return result
                    except Exception:
                        return ""

                # 执行摘要
                compressed_messages = await self.token_manager.maybe_summarize(
                    session_messages,
                    llm_summarizer=llm_summarizer
                )

                # 更新会话记忆（如果有压缩）
                if len(compressed_messages) < len(session_messages):
                    self.memory.session.update_messages(compressed_messages)
                    logger.info(
                        "session_messages_compressed",
                        before=len(session_messages),
                        after=len(compressed_messages),
                        tokens_saved=self.token_manager.stats.get("tokens_saved", 0)
                    )

        except Exception as e:
            logger.warning(
                "token_compression_failed",
                error=str(e)
            )
            # Token压缩失败不应阻断主流程

    def get_token_stats(self) -> Dict[str, Any]:
        """
        获取Token使用统计

        Returns:
            Token统计信息
        """
        return self.token_manager.get_stats()

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
        获取增强的统计信息（包含记忆、Token、日志）

        Returns:
            综合统计信息
        """
        stats = self.get_memory_stats()
        stats["token_management"] = self.get_token_stats()

        if self.agent_logger:
            stats["current_run"] = self.agent_logger.get_run_summary()

        return stats

    async def _run_react_loop_single_step(
        self,
        user_query: str,
        enhance_with_history: bool = True,
        debug_mode: bool = False
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        V4优化：单步模式 ReAct 循环

        合并 Thought + Action 为单次 LLM 调用，显著减少 LLM 调用次数。

        流程：
        1. 调用 think_and_action() 同时生成 thought 和 action
        2. 如果是 TOOL_CALLS，执行并行工具调用
        3. 如果是 TOOL_CALL，执行单工具调用
        4. 如果是 FINISH，生成最终答案

        Args:
            user_query: 用户查询
            enhance_with_history: 是否使用长期记忆增强
            debug_mode: 调试模式

        Yields:
            流式事件
        """
        try:
            # 开始运行日志记录
            if self.agent_logger:
                run_id = self.agent_logger.start_new_run(
                    session_id=self.memory.session_id,
                    query=user_query,
                    metadata={
                        "enhance_with_history": enhance_with_history,
                        "debug_mode": debug_mode,
                        "mode": "single_step"
                    }
                )
                logger.info("agent_run_started", run_id=run_id)

            # Step 0: 记录用户消息
            self.memory.session.add_user_message(user_query)

            # Step 1: 使用原始查询（长期记忆增强已移除）
            enhanced_query = user_query

            # Step 2: 初始化循环状态
            iteration_count = 0
            task_completed = False
            final_answer = None

            # Yield start event
            yield {
                "type": "start",
                "data": {
                    "query": user_query,
                    "session_id": self.memory.session_id,
                    "timestamp": datetime.now().isoformat()
                }
            }

            # Step 3: 单步模式循环
            while iteration_count < self.max_iterations and not task_completed:
                iteration_count += 1

                # Token 检查
                await self._check_and_compress_tokens()

                logger.info(
                    "single_step_iteration_start",
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
                        mode=self.current_mode  # ✅ 传递当前模式
                    )

                    # Phase 3: 调用合并的 think_and_action_v2 方法
                    think_action_result = await self.planner.think_and_action_v2(
                        query=enhanced_query,
                        system_prompt=context_result["system_prompt"],
                        user_conversation=context_result["user_conversation"],
                        iteration=iteration_count,
                        latest_observation=latest_observation
                    )

                    thought = think_action_result["thought"]
                    action = think_action_result["action"]
                    reasoning = think_action_result.get("reasoning")

                    # Phase 2: 执行 Action
                    action_type = action.get("type", "FINAL_ANSWER")

                    # Yield thought 事件（FINAL_ANSWER 除外）
                    if action_type != "FINAL_ANSWER":
                        yield {
                            "type": "thought",
                            "data": {
                                "iteration": iteration_count,
                                "thought": thought,
                                "reasoning": reasoning,
                                "timestamp": datetime.now().isoformat()
                            }
                        }

                    logger.info(
                        "single_step_action_decided",
                        action_type=action_type,
                        iteration=iteration_count
                    )

                    # FINAL_ANSWER: 直接展示 LLM 的最终回答
                    if action_type == "FINAL_ANSWER":
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

                        logger.info("task_completed_final_answer", iterations=iteration_count)
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

                        # 调用 LLM 生成最终答案
                        final_answer = ""
                        async for chunk in self.planner.stream_user_answer(prompt):
                            final_answer += chunk

                        # 记录到记忆
                        self.memory.add_iteration(
                            thought=thought,
                            action=action,
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

                        break

                    # 执行工具调用
                    if action_type == "TOOL_CALLS":
                        # 并行执行多个工具
                        tools = action.get("tools", [])
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
                            "parallel": True
                        }

                        # 处理 visuals（复用原有逻辑）
                        if observation.get("visuals"):
                            for idx, visual_block in enumerate(observation["visuals"]):
                                payload = visual_block.get("payload", {})
                                meta = visual_block.get("meta", {})
                                self.memory.add_chart_observation({
                                    "visual_id": visual_block.get("id", f"visual_{idx}"),
                                    "chart_id": payload.get("id", f"chart_{idx}"),
                                    "chart_type": payload.get("type", "unknown"),
                                    "chart_title": payload.get("title", "无标题"),
                                    "summary": f"已生成图表: {payload.get('title', '')}",
                                    "data_id": meta.get("source_data_ids", [None])[0],
                                    "source_tools": [t.get("tool") for t in tools],
                                    "schema_version": "v2.0"
                                })

                        yield {
                            "type": "action",
                            "data": {
                                "iteration": iteration_count,
                                "action": {**action, "parallel_result": parallel_result},
                                "timestamp": datetime.now().isoformat()
                            }
                        }

                    elif action_type == "TOOL_CALL":
                        # 单工具执行
                        tool_name = action.get("tool")
                        tool_args = action.get("args", {})

                        yield {
                            "type": "action",
                            "data": {
                                "iteration": iteration_count,
                                "action": action,
                                "timestamp": datetime.now().isoformat()
                            }
                        }

                        observation = await self.executor.execute_tool(
                            tool_name=tool_name,
                            tool_args=tool_args,
                            iteration=iteration_count
                        )
                    else:
                        observation = {
                            "success": False,
                            "error": f"未知的 action type: {action_type}",
                            "summary": f"任务失败：未知的 action type"
                        }

                    # Phase 3: Observation
                    yield {
                        "type": "observation",
                        "data": {
                            "iteration": iteration_count,
                            "observation": observation,
                            "timestamp": datetime.now().isoformat()
                        }
                    }

                    # 添加到记忆
                    self.memory.add_iteration(
                        thought=thought,
                        action=action,
                        observation=observation
                    )

                    if observation.get("summary"):
                        # 使用完整格式化内容（包含完整数据）而非仅摘要
                        full_message = self._format_observation(observation)
                        # 添加工具调用信息（帮助LLM了解历史操作）
                        action_info = self._format_action_info(action)
                        full_message = f"{action_info}\n\n{full_message}"

                        # 🔍 详细日志：验证完整数据传递
                        metadata = observation.get("metadata", {})
                        generator = metadata.get("generator", "")
                        data = observation.get("data")
                        logger.info(
                            "format_observation_debug",
                            generator=generator,
                            full_message_length=len(full_message),
                            full_message_preview=full_message[:500] if len(full_message) > 500 else full_message,
                            has_analysis=isinstance(data, dict) and "analysis" in data,
                            observation_keys=list(observation.keys()),
                            data_keys=list(data.keys()) if isinstance(data, dict) else []
                        )

                        self.memory.session.add_assistant_message(
                            full_message,
                            thought=thought,
                            reasoning=reasoning if think_action_result is None else think_action_result.get("reasoning")
                        )

                    # 早停检查：连续3次工具失败则停止
                    recent_iterations = self.memory.get_iterations()
                    _recent = recent_iterations[-3:]
                    _failures = sum(1 for it in _recent if not it.get("observation", {}).get("success", True))
                    if len(_recent) >= 3 and _failures >= 3:
                        logger.warning("early_stop_consecutive_failures", iteration=iteration_count)
                        break

                except Exception as e:
                    logger.error(
                        "single_step_iteration_failed",
                        iteration=iteration_count,
                        error=str(e),
                        exc_info=True
                    )

                    yield {
                        "type": "error",
                        "data": {
                            "iteration": iteration_count,
                            "error": str(e),
                            "timestamp": datetime.now().isoformat()
                        }
                    }

                    if "fatal" in str(e).lower():
                        break

            # Step 4: 完成或超时
            if task_completed:
                logger.info(
                    "single_step_loop_completed",
                    iterations=iteration_count,
                    session_id=self.memory.session_id
                )

                if self.agent_logger:
                    self.agent_logger.end_run(
                        status="completed",
                        final_answer=final_answer,
                        metadata={"iterations": iteration_count}
                    )

                if final_answer:
                    self.memory.session.add_assistant_response(final_answer)

                await self._save_successful_strategy(
                    self.memory.get_iterations(),
                    user_query
                )

                # Note: 长期记忆保存已移除

                yield {
                    "type": "complete",
                    "data": {
                        "answer": final_answer,
                        "response": final_answer,  # ✅ 同时返回response字段
                        "iterations": iteration_count,
                        "session_id": self.memory.session_id,
                        "timestamp": datetime.now().isoformat()
                    }
                }
            else:
                logger.warning(
                    "single_step_loop_max_iterations",
                    iterations=iteration_count,
                    session_id=self.memory.session_id
                )

                if self.agent_logger:
                    self.agent_logger.end_run(
                        status="timeout",
                        metadata={"iterations": iteration_count}
                    )

                partial_answer = await self._generate_partial_answer()

                if partial_answer:
                    self.memory.session.add_assistant_response(partial_answer)

                # Note: 长期记忆保存已移除

                yield {
                    "type": "incomplete",
                    "data": {
                        "answer": partial_answer,
                        "iterations": iteration_count,
                        "reason": "max_iterations_reached",
                        "timestamp": datetime.now().isoformat()
                    }
                }

        except Exception as e:
            logger.error(
                "single_step_loop_fatal_error",
                error=str(e),
                exc_info=True
            )

            if self.agent_logger:
                self.agent_logger.log_error(error=str(e), error_type="fatal")
                self.agent_logger.end_run(status="failed")

            yield {
                "type": "fatal_error",
                "data": {
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
            }

    def _format_observation(self, observation: Dict[str, Any]) -> str:
        """
        格式化观察结果为字符串

        Args:
            observation: 观察结果字典

        Returns:
            格式化的字符串
        """
        if not observation:
            return ""

        lines = []

        # 状态
        success = observation.get("success", False)
        lines.append(f"**状态**: {'成功' if success else '失败'}")

        # 数据引用
        if "data_ref" in observation:
            lines.append(f"**数据引用**: {observation['data_ref']}")

        # 错误信息
        if not success and "error" in observation:
            lines.append(f"**错误**: {observation['error']}")

        # Reflexion建议
        if "reflexion_suggestion" in observation:
            lines.append(f"**反思建议**: {observation['reflexion_suggestion']}")

        # ✅ 特殊处理：并行工具执行结果
        if observation.get("parallel") and observation.get("tool_results"):
            # 并行执行：分别格式化每个工具的结果
            tool_results = observation["tool_results"]
            lines.append(f"**并行执行结果** ({len(tool_results)} 个工具)")

            for idx, tool_res in enumerate(tool_results, 1):
                tool_name = tool_res.get("tool", f"tool_{idx}")
                result_data = tool_res.get("result", {})

                if result_data.get("success"):
                    # 递归调用 _format_observation 格式化单个工具结果
                    sub_observation = result_data
                    sub_lines = self._format_observation_sub(sub_observation, tool_name)
                    lines.append(f"\n### 工具 {idx}: {tool_name}")
                    lines.extend(sub_lines)
                else:
                    # 工具执行失败
                    error_msg = result_data.get("error", "未知错误")
                    lines.append(f"\n### 工具 {idx}: {tool_name}")
                    lines.append(f"**状态**: 失败")
                    lines.append(f"**错误**: {error_msg}")

            return "\n".join(lines)

        # ✅ 优先展示完整数据（适用于 bash 工具和 Office 工具）
        # 完全不截断，依赖上下文压缩策略
        if success and "data" in observation and isinstance(observation["data"], dict):
            data = observation["data"]
            metadata = observation.get("metadata", {})
            generator = metadata.get("generator", "")

            # ✅ 特殊处理：办公助理工具始终显示完整内容
            # 包括：Office 工具、analyze_image、read_file、grep、glob、list_directory
            is_office_tool = generator in ["word_processor", "excel_processor", "ppt_processor"]
            is_image_tool = generator == "analyze_image"
            is_file_tool = generator == "read_file"
            is_grep_tool = generator == "grep"
            is_glob_tool = generator in ["glob", "search_files"]
            is_list_dir_tool = generator == "list_directory"

            # 🔍 详细日志：验证工具识别
            if is_image_tool or is_file_tool or is_office_tool or is_grep_tool or is_glob_tool or is_list_dir_tool:
                logger.info(
                    "office_tool_detected",
                    generator=generator,
                    is_image_tool=is_image_tool,
                    is_file_tool=is_file_tool,
                    is_office_tool=is_office_tool,
                    is_grep_tool=is_grep_tool,
                    is_glob_tool=is_glob_tool,
                    is_list_dir_tool=is_list_dir_tool,
                    has_analysis="analysis" in data,
                    has_content="content" in data,
                    has_results="results" in data,
                    has_files="files" in data,
                    has_entries="entries" in data,
                    data_type=data.get("type", "unknown")
                )

            if is_image_tool and "analysis" in data:
                # analyze_image 工具：显示完整的图片分析结果
                lines.append(f"**完整分析结果**:\n{data['analysis']}")
                # 🔍 详细日志：记录完整分析结果
                logger.info(
                    "analyze_image_full_result_added",
                    analysis_length=len(data['analysis']),
                    analysis_preview=data['analysis'][:200] if len(data['analysis']) > 200 else data['analysis']
                )
            elif is_file_tool:
                # read_file 工具：根据文件类型显示不同内容
                file_type = data.get("type", "")
                if file_type == "image":
                    # 图片文件：显示分析结果（不显示 base64）
                    if "analysis" in data:
                        lines.append(f"**图片分析结果**:\n{data['analysis']}")
                        # 🔍 详细日志：记录完整分析结果
                        logger.info(
                            "read_file_image_analysis_added",
                            analysis_length=len(data['analysis']),
                            analysis_preview=data['analysis'][:200] if len(data['analysis']) > 200 else data['analysis']
                        )
                    elif "analysis_error" in data:
                        lines.append(f"**分析失败**: {data['analysis_error']}")
                    # 显示图片信息
                    lines.append(f"\n**图片信息**:")
                    lines.append(f"  路径: `{data.get('path', 'N/A')}`")
                    lines.append(f"  格式: {data.get('format', 'N/A')}")
                    lines.append(f"  大小: {data.get('size', 0)} bytes")
                elif "content" in data:
                    # 文本文件：显示完整的文件内容
                    lines.append(f"**文件内容**:\n{data['content']}")
            elif is_office_tool:
                # Word/Excel/PPT 工具：显示完整文档内容
                if "content" in data:
                    lines.append(f"**文档内容**:\n```\n{data['content']}\n```")
                elif "images" in data:
                    # extract_images 操作：显示完整图片列表
                    images = data["images"]
                    if isinstance(images, list):
                        # extract_images 返回的图片列表
                        lines.append(f"**提取的图片数量**: {len(images)}")
                        for img in images:
                            lines.append(f"\n**图片 {img['index']}**:")
                            lines.append(f"  路径: `{img['path']}`")
                            lines.append(f"  尺寸: {img['width']} x {img['height']}")
                    elif isinstance(images, int):
                        # stats 操作返回的图片数量
                        lines.append(f"**图片数量**: {images}")
                elif "tables" in data:
                    # 表格数据（完整显示）
                    tables = data["tables"]
                    lines.append(f"**表格数量**: {data.get('table_count', len(tables))}")
                    for idx, table in enumerate(tables):
                        lines.append(f"\n**表格 {idx + 1}**: {table['rows']}行 × {table['cols']}列")
                        lines.append(f"```json\n{json.dumps(table['data'], ensure_ascii=False, indent=2)}\n```")
                elif "data" in data and isinstance(data.get("data"), list):
                    # Excel 数据（二维数组）
                    lines.append(f"**数据内容**:\n```json\n{json.dumps(data['data'], ensure_ascii=False, indent=2)}\n```")

                # 显示统计信息
                if "stats" in data:
                    lines.append(f"**统计信息**: {data['stats']}")

                # 显示范围信息（如果有）
                if "range" in data:
                    lines.append(f"**读取范围**: 第{data['range']['start']+1}-{data['range']['end']}段（共{data['range']['total']}段）")
                    if data.get("has_more"):
                        lines.append(f"⚠️ 还有{data['range']['total']-data['range']['end']}段未读取，可继续分页读取")

            elif is_grep_tool:
                # grep 工具：显示完整搜索结果
                if "results" in data:
                    results = data["results"]
                    total_matches = data.get("total_matches", 0)
                    lines.append(f"**搜索结果** (共 {total_matches} 处匹配):")
                    if isinstance(results, list):
                        for result in results[:50]:  # 最多显示前50个结果
                            if isinstance(result, dict):
                                file_path = result.get("file", "")
                                line_num = result.get("line", "")
                                content = result.get("content", "")
                                lines.append(f"\n`{file_path}:{line_num}`: {content}")
                            else:
                                lines.append(f"  {result}")
                        if len(results) > 50:
                            lines.append(f"\n... 还有 {len(results) - 50} 个结果")
                elif "output_text" in data:
                    # 文本输出模式
                    lines.append(f"**搜索结果**:\n{data['output_text']}")

            elif is_glob_tool:
                # glob/search_files 工具：显示完整文件列表
                if "files" in data:
                    files = data["files"]
                    count = data.get("count", len(files))
                    lines.append(f"**找到的文件** (共 {count} 个):")
                    if isinstance(files, list):
                        for file in files[:100]:  # 最多显示前100个文件
                            lines.append(f"  - {file}")
                        if len(files) > 100:
                            lines.append(f"\n... 还有 {len(files) - 100} 个文件")

            elif is_list_dir_tool:
                # list_directory 工具：显示完整目录列表
                if "entries" in data:
                    entries = data["entries"]
                    count = data.get("count", len(entries))
                    lines.append(f"**目录内容** (共 {count} 项):")
                    if isinstance(entries, list):
                        for entry in entries[:100]:  # 最多显示前100项
                            if isinstance(entry, dict):
                                name = entry.get("name", "")
                                entry_type = entry.get("type", "")
                                size = entry.get("size", "")
                                type_icon = "📁" if entry_type == "directory" else "📄"
                                size_str = f" ({size} bytes)" if size else ""
                                lines.append(f"  {type_icon} {name}{size_str}")
                            else:
                                lines.append(f"  {entry}")
                        if len(entries) > 100:
                            lines.append(f"\n... 还有 {len(entries) - 100} 项")

            # 对于 bash 工具，包含完整的 stdout/stderr
            elif "stdout" in data or "stderr" in data:
                if "stdout" in data and data["stdout"]:
                    # 完整输出，不截断
                    lines.append(f"**命令输出**:\n{data['stdout']}")

                if "stderr" in data and data["stderr"]:
                    lines.append(f"**错误输出**:\n{data['stderr']}")

                if "exit_code" in data:
                    lines.append(f"**退出码**: {data['exit_code']}")

                if "command" in data:
                    lines.append(f"**执行命令**: {data['command']}")

        # ✅ 数据查询工具：显示采样后的数据列表
        elif success and "data" in observation and isinstance(observation["data"], list):
            data_list = observation["data"]
            metadata = observation.get("metadata", {})

            # 检查是否应用了采样
            sampling_applied = metadata.get("sampling_applied", False)
            original_count = metadata.get("original_record_count", len(data_list))
            sampled_count = len(data_list)

            if data_list:
                # 显示数据预览信息
                if sampling_applied:
                    lines.append(f"**数据预览** (采样{sampled_count}条/共{original_count}条):")
                    sampling_info = metadata.get("sampling_info", {})
                    strategy = sampling_info.get("strategy", "unknown")
                    if strategy == "head_tail_middle_sampling":
                        head = sampling_info.get("head_samples", 0)
                        middle = sampling_info.get("middle_samples", 0)
                        tail = sampling_info.get("tail_samples", 0)
                        lines.append(f"  采样策略: 头部{head}条 + 中间{middle}条 + 尾部{tail}条")
                else:
                    lines.append(f"**完整数据** ({sampled_count}条):")

                # 显示数据内容（JSON格式）
                lines.append(f"```json\n{json.dumps(data_list, ensure_ascii=False, indent=2, default=str)}\n```")

                # 如果有data_id，提示可以加载完整数据
                data_id = observation.get("data_id")
                if data_id and sampling_applied:
                    lines.append(f"\n💡 完整数据({original_count}条)已存储在: `{data_id}`")
                    lines.append(f"   可使用 load_data_from_memory(data_id=\"{data_id}\") 加载完整数据")

        # 摘要（作为补充，不是主要信息源）
        if "summary" in observation:
            lines.append(f"**摘要**: {observation['summary']}")

        return "\n".join(lines)

    def _format_observation_sub(self, observation: Dict[str, Any], tool_name: str = "") -> List[str]:
        """
        格式化子观察结果为字符串列表（用于并行工具执行）

        Args:
            observation: 观察结果字典
            tool_name: 工具名称（可选）

        Returns:
            格式化的字符串列表
        """
        lines = []

        # 状态
        success = observation.get("success", False)
        lines.append(f"**状态**: {'成功' if success else '失败'}")

        # 数据处理
        if success and "data" in observation and isinstance(observation["data"], dict):
            data = observation["data"]
            metadata = observation.get("metadata", {})
            generator = metadata.get("generator", "")

            # 特殊处理：办公助理工具
            is_image_tool = generator == "analyze_image"
            is_file_tool = generator == "read_file"
            is_office_tool = generator in ["word_processor", "excel_processor", "ppt_processor"]
            is_grep_tool = generator == "grep"
            is_glob_tool = generator in ["glob", "search_files"]
            is_list_dir_tool = generator == "list_directory"

            if is_image_tool and "analysis" in data:
                # analyze_image 工具：显示完整的图片分析结果
                lines.append(f"**完整分析结果**:\n{data['analysis']}")

            elif is_file_tool:
                # read_file 工具：根据文件类型显示不同内容
                file_type = data.get("type", "")
                if file_type == "image":
                    # 图片文件：显示分析结果
                    if "analysis" in data:
                        lines.append(f"**图片分析结果**:\n{data['analysis']}")
                    elif "analysis_error" in data:
                        lines.append(f"**分析失败**: {data['analysis_error']}")
                    # 显示图片信息
                    lines.append(f"\n**图片信息**:")
                    lines.append(f"  路径: `{data.get('path', 'N/A')}`")
                    lines.append(f"  格式: {data.get('format', 'N/A')}")
                    lines.append(f"  大小: {data.get('size', 0)} bytes")
                elif "content" in data:
                    # 文本文件：显示完整的文件内容
                    lines.append(f"**文件内容**:\n{data['content']}")

            elif is_office_tool:
                # Word/Excel/PPT 工具：显示完整文档内容
                if "content" in data:
                    lines.append(f"**文档内容**:\n```\n{data['content']}\n```")
                elif "images" in data:
                    # extract_images 操作：显示完整图片列表
                    images = data["images"]
                    if isinstance(images, list):
                        lines.append(f"**提取的图片数量**: {len(images)}")
                        for img in images:
                            lines.append(f"\n**图片 {img['index']}**:")
                            lines.append(f"  路径: `{img['path']}`")
                            lines.append(f"  尺寸: {img['width']} x {img['height']}")

            elif is_grep_tool:
                # grep 工具：显示完整搜索结果
                if "results" in data:
                    results = data["results"]
                    total_matches = data.get("total_matches", 0)
                    lines.append(f"**搜索结果** (共 {total_matches} 处匹配):")
                    if isinstance(results, list):
                        for result in results[:50]:
                            if isinstance(result, dict):
                                file_path = result.get("file", "")
                                line_num = result.get("line", "")
                                content = result.get("content", "")
                                lines.append(f"\n`{file_path}:{line_num}`: {content}")
                            else:
                                lines.append(f"  {result}")
                        if len(results) > 50:
                            lines.append(f"\n... 还有 {len(results) - 50} 个结果")
                elif "output_text" in data:
                    lines.append(f"**搜索结果**:\n{data['output_text']}")

            elif is_glob_tool:
                # glob/search_files 工具：显示完整文件列表
                if "files" in data:
                    files = data["files"]
                    count = data.get("count", len(files))
                    lines.append(f"**找到的文件** (共 {count} 个):")
                    if isinstance(files, list):
                        for file in files[:100]:
                            lines.append(f"  - {file}")
                        if len(files) > 100:
                            lines.append(f"\n... 还有 {len(files) - 100} 个文件")

            elif is_list_dir_tool:
                # list_directory 工具：显示完整目录列表
                if "entries" in data:
                    entries = data["entries"]
                    count = data.get("count", len(entries))
                    lines.append(f"**目录内容** (共 {count} 项):")
                    if isinstance(entries, list):
                        for entry in entries[:100]:
                            if isinstance(entry, dict):
                                name = entry.get("name", "")
                                entry_type = entry.get("type", "")
                                size = entry.get("size", "")
                                type_icon = "📁" if entry_type == "directory" else "📄"
                                size_str = f" ({size} bytes)" if size else ""
                                lines.append(f"  {type_icon} {name}{size_str}")
                            else:
                                lines.append(f"  {entry}")
                        if len(entries) > 100:
                            lines.append(f"\n... 还有 {len(entries) - 100} 项")

            elif "stdout" in data or "stderr" in data:
                # bash 工具
                if "stdout" in data and data["stdout"]:
                    lines.append(f"**命令输出**:\n{data['stdout']}")
                if "stderr" in data and data["stderr"]:
                    lines.append(f"**错误输出**:\n{data['stderr']}")

        # ✅ 数据查询工具：显示采样后的数据列表
        elif success and "data" in observation and isinstance(observation["data"], list):
            data_list = observation["data"]
            metadata = observation.get("metadata", {})

            # 检查是否应用了采样
            sampling_applied = metadata.get("sampling_applied", False)
            original_count = metadata.get("original_record_count", len(data_list))
            sampled_count = len(data_list)

            if data_list:
                # 显示数据预览信息
                if sampling_applied:
                    lines.append(f"**数据预览** (采样{sampled_count}条/共{original_count}条):")
                else:
                    lines.append(f"**完整数据** ({sampled_count}条):")

                # 显示数据内容（JSON格式）
                lines.append(f"```json\n{json.dumps(data_list, ensure_ascii=False, indent=2, default=str)}\n```")

                # 如果有data_id，提示可以加载完整数据
                data_id = observation.get("data_id")
                if data_id and sampling_applied:
                    lines.append(f"\n💡 完整数据({original_count}条)已存储在: `{data_id}`")

        # 摘要
        if "summary" in observation:
            lines.append(f"**摘要**: {observation['summary']}")

        return lines

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

