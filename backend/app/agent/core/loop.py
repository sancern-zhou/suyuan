"""
ReAct Loop Engine (Refactored)

ReAct 循环引擎，实现 Thought → Action → Observation 循环。

重构后的模块化结构：
- ReflexionHandler: 失败分析和智能重试
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
from .reflexion_handler import ReflexionHandler
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
        enable_reflexion: bool = True,
        max_reflections: int = 2,
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
            enable_reflexion: 是否启用 Reflexion 反思机制
            max_reflections: 最大反思次数
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
        self.enable_reflexion = enable_reflexion
        self.single_step_mode = single_step_mode  # V4优化
        self.is_interruption = is_interruption  # ✅ 保存中断标志

        # 初始化处理器模块
        self.reflexion_handler = ReflexionHandler(max_reflections=max_reflections)
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

        logger.info(
            "react_loop_initialized",
            session_id=memory_manager.session_id,
            max_iterations=max_iterations,
            plan_mode=plan_mode,
            enable_reflexion=enable_reflexion,
            token_limit=token_limit,
            agent_logging=enable_agent_logging,
            enable_reasoning=enable_reasoning,
            single_step_mode=single_step_mode  # V4优化
        )

    async def run(
        self,
        user_query: str,
        enhance_with_history: bool = True,
        debug_mode: bool = False
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行单步模式 ReAct 循环（V4版）

        Args:
            user_query: 用户查询
            enhance_with_history: 是否使用长期记忆增强
            debug_mode: 调试模式

        Yields:
            流式事件
        """
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
                debug_mode
            ):
                yield event

    async def _run_react_loop(
        self,
        user_query: str,
        enhance_with_history: bool = True,
        debug_mode: bool = False
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

            # 重置 Reflexion 计数器
            self.reflexion_handler.reset_count()

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
                        iterations = self.memory.working.get_iterations()
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
                        conversation_history=conversation_history
                    )

                    # Phase 3: think_and_action（单次LLM调用）
                    # 注意：传递system_prompt和user_conversation分别作为system和user消息
                    think_action_result = await self.planner.think_and_action_v2(
                        query=enhanced_query,
                        system_prompt=context_result["system_prompt"],
                        user_conversation=context_result["user_conversation"],
                        iteration=iteration_count,
                        latest_observation=latest_observation
                    )

                    thought = think_action_result["thought"]
                    action = think_action_result["action"]

                    # Yield thought事件
                    yield {
                        "type": "thought",
                        "data": {
                            "iteration": iteration_count,
                            "thought": thought,
                            "reasoning": think_action_result.get("reasoning"),
                            "timestamp": datetime.now().isoformat()
                        }
                    }

                    action_type = action.get("type", "FINISH")
                    logger.info("action_decided", action_type=action_type, iteration=iteration_count)

                    # FINISH: 任务完成（直接回复）
                    if action_type == "FINISH":
                        # 如果没有 answer，自动转换为 FINISH_SUMMARY
                        if not action.get("answer"):
                            logger.info("FINISH_without_answer_auto_convert_to_FINISH_SUMMARY")
                            action_type = "FINISH_SUMMARY"

                    # FINISH_SUMMARY: 结束并生成最终答案
                    if action_type == "FINISH_SUMMARY":
                        task_completed = True

                        # 获取工具结果数据（使用简化版上下文）
                        tool_results = self.memory.get_context_for_llm(include_raw_data=False)

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

                        self.memory.working.add_iteration(
                            thought=thought,
                            action={"type": "FINISH_SUMMARY"},
                            observation={"success": True, "summary": "FINISH_SUMMARY: 生成最终答案"}
                        )

                        if final_answer:
                            self.memory.session.add_assistant_message(final_answer)

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

                    # FINISH (有 answer): 任务完成（直接回复）
                    if action.get("type") == "FINISH" and action.get("answer"):
                        task_completed = True
                        final_answer = action.get("answer")

                        self.memory.working.add_iteration(
                            thought=thought,
                            action=action,
                            observation={"success": True, "summary": "任务完成"}
                        )

                        self.memory.session.add_assistant_message(final_answer)

                        yield {
                            "type": "observation",
                            "data": {
                                "iteration": iteration_count,
                                "observation": {"success": True, "summary": "任务完成"},
                                "timestamp": datetime.now().isoformat()
                            }
                        }

                        logger.info("task_completed", iterations=iteration_count)
                        break

                    # 如果是 FINISH 但没有 answer（理论上不应发生，因为前面已经转换了）
                    if action.get("type") == "FINISH" and not action.get("answer"):
                        logger.warning("FINISH_without_answer_and_not_converted", action=action)
                        # 回退到 FINISH_SUMMARY
                        action_type = "FINISH_SUMMARY"

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
                                self.memory.working.add_chart_observation({
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

                        # 检查是否是特殊工具（FINISH_SUMMARY 或 FINISH）
                        if observation.get("action_type") in ["FINISH_SUMMARY", "FINISH"]:
                            # 特殊工具：转换为对应的 action_type
                            special_action_type = observation["action_type"]
                            logger.info(
                                "special_tool_detected",
                                tool_name=tool_name,
                                action_type=special_action_type
                            )

                            # 使用特殊工具的 action_type
                            action_type = special_action_type

                            # 复用现有的 FINISH/FINISH_SUMMARY 处理逻辑
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
                                    for iteration in self.memory.working.get_iterations():
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
                                    tool_results = self.memory.get_context_for_llm(include_raw_data=True)

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

                                self.memory.working.add_iteration(
                                    thought=thought,
                                    action={"type": "FINISH_SUMMARY"},
                                    observation={"success": True, "summary": "FINISH_SUMMARY: 生成最终答案"}
                                )

                                if final_answer:
                                    self.memory.session.add_assistant_message(final_answer)

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

                            elif action_type == "FINISH":
                                # FINISH 工具：直接返回 answer
                                task_completed = True
                                final_answer = observation.get("answer", "任务已完成")

                                self.memory.working.add_iteration(
                                    thought=thought,
                                    action={"type": "FINISH"},
                                    observation={"success": True, "summary": "任务完成"}
                                )

                                self.memory.session.add_assistant_message(final_answer)

                                yield {
                                    "type": "observation",
                                    "data": {
                                        "iteration": iteration_count,
                                        "observation": {"success": True, "summary": "任务完成"},
                                        "timestamp": datetime.now().isoformat()
                                    }
                                }

                                logger.info("task_completed", iterations=iteration_count)
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

                        self.memory.session.add_assistant_message(full_message)

                    # 早停检查
                    if await self.reflexion_handler.should_early_stop(
                        self.memory.working.get_iterations(),
                        enable_reflexion=self.enable_reflexion
                    ):
                        logger.warning("early_stop_triggered", iteration=iteration_count)
                        break

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
                    self.memory.working.get_iterations(),
                    user_query
                )

                # Note: 长期记忆保存已移除

                yield {
                    "type": "complete",
                    "data": {
                        "answer": final_answer,
                        "iterations": iteration_count,
                        "session_id": self.memory.session_id,
                        "timestamp": datetime.now().isoformat()
                    }
                }

            else:
                logger.warning(
                    "react_loop_max_iterations",
                    iterations=iteration_count,
                    session_id=self.memory.session_id
                )

                # 新增：记录超时日志
                if self.agent_logger:
                    self.agent_logger.end_run(
                        status="timeout",
                        metadata={"iterations": iteration_count, "reason": "max_iterations_reached"}
                    )

                # 生成部分答案
                partial_answer = await self._generate_partial_answer()

                # 记录助手回复
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
        base_context = self.memory.get_context_for_llm(include_raw_data=False)

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
        current_context = self.memory.get_context_for_llm(include_raw_data=False)

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
                "type": "FINISH",
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

        # ✅ Phase 3.1: 检查是否是输入验证错误
        if (not observation.get("success") and
            observation.get("error_type") == "INPUT_VALIDATION_FAILED"):
            logger.warning(
                "input_validation_error_detected",
                tool_name=tool_name,
                missing_fields=observation.get("missing_fields", []),
                iteration=iteration
            )

            # ✅ 调用 Reflexion Handler 生成重试建议
            try:
                retry_suggestion = await self.reflexion_handler.handle_input_adaptation_error(
                    error=observation,
                    tool_name=tool_name,
                    raw_args=action.get("args", {})
                )

                # ✅ 将重试建议添加到观察结果
                observation["reflexion_suggestion"] = retry_suggestion
                observation["can_retry"] = retry_suggestion.get("should_retry", False)
                observation["suggestions"] = retry_suggestion.get("suggestions", [])

                logger.info(
                    "reflexion_suggestion_generated",
                    tool_name=tool_name,
                    should_retry=retry_suggestion.get("should_retry"),
                    suggestions_count=len(retry_suggestion.get("suggestions", []))
                )

            except Exception as e:
                logger.error(
                    "reflexion_handler_failed",
                    tool_name=tool_name,
                    error=str(e),
                    exc_info=True
                )
                # Reflexion失败时，仍然保留原始错误信息
                observation["reflexion_error"] = str(e)

        logger.info(
            "tool_executed",
            tool=tool_name,
            success=observation.get("success"),
            has_data="data" in observation,
            has_reflexion="reflexion_suggestion" in observation
        )

        return observation

    async def _generate_partial_answer(self) -> str:
        """
        生成部分答案（当达到最大迭代次数时）

        Returns:
            部分答案字符串
        """
        context = self.memory.get_context_for_llm()

        try:
            partial_answer = await self.planner.generate_partial_answer(context)
            return partial_answer
        except Exception as e:
            logger.error(
                "partial_answer_generation_failed",
                error=str(e)
            )
            return "抱歉，由于达到最大迭代次数，无法完成完整分析。请尝试简化查询或分步提问。"

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        获取记忆统计信息

        Returns:
            统计信息字典
        """
        return {
            "working_iterations": len(self.memory.working),
            "compressed_iterations": len(self.memory.session.compressed_iterations),
            "data_files": len(self.memory.session.data_files),
            "estimated_tokens": self.memory.estimate_total_tokens(),
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
                        iterations = self.memory.working.get_iterations()
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
                        conversation_history=conversation_history
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

                    # Yield thought 事件
                    yield {
                        "type": "thought",
                        "data": {
                            "iteration": iteration_count,
                            "thought": thought,
                            "reasoning": think_action_result.get("reasoning"),
                            "timestamp": datetime.now().isoformat()
                        }
                    }

                    # Phase 2: 执行 Action
                    action_type = action.get("type", "FINISH")

                    logger.info(
                        "single_step_action_decided",
                        action_type=action_type,
                        iteration=iteration_count
                    )

                    # FINISH: 如果没有 answer，自动转换为 FINISH_SUMMARY
                    if action_type == "FINISH" and not action.get("answer"):
                        logger.info("FINISH_without_answer_auto_convert_to_FINISH_SUMMARY")
                        action_type = "FINISH_SUMMARY"

                    # FINISH_SUMMARY: 结束并生成最终答案
                    if action_type == "FINISH_SUMMARY":
                        task_completed = True

                        # 获取工具结果数据（使用简化版上下文）
                        tool_results = self.memory.get_context_for_llm(include_raw_data=False)

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
                        self.memory.working.add_iteration(
                            thought=thought,
                            action=action,
                            observation={"success": True, "summary": "FINISH_SUMMARY: 生成最终答案"}
                        )

                        if final_answer:
                            self.memory.session.add_assistant_message(final_answer)

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
                                self.memory.working.add_chart_observation({
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

                        self.memory.session.add_assistant_message(full_message)

                    # 早停检查
                    recent_iterations = self.memory.working.get_iterations()
                    if await self.reflexion_handler.should_early_stop(
                        recent_iterations,
                        enable_reflexion=self.enable_reflexion
                    ):
                        logger.warning("early_stop_triggered", iteration=iteration_count)
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
                    self.memory.working.get_iterations(),
                    user_query
                )

                # Note: 长期记忆保存已移除

                yield {
                    "type": "complete",
                    "data": {
                        "answer": final_answer,
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
            # 包括：Office 工具、analyze_image、read_file
            is_office_tool = generator in ["word_processor", "excel_processor", "ppt_processor"]
            is_image_tool = generator == "analyze_image"
            is_file_tool = generator == "read_file"

            # 🔍 详细日志：验证工具识别
            if is_image_tool or is_file_tool or is_office_tool:
                logger.info(
                    "office_tool_detected",
                    generator=generator,
                    is_image_tool=is_image_tool,
                    is_file_tool=is_file_tool,
                    is_office_tool=is_office_tool,
                    has_analysis="analysis" in data,
                    has_content="content" in data,
                    data_type=data.get("type", "unknown"),
                    analysis_length=len(data.get("analysis", "")) if "analysis" in data else 0
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
                import json
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
                import json
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

            elif "stdout" in data or "stderr" in data:
                # bash 工具
                if "stdout" in data and data["stdout"]:
                    lines.append(f"**命令输出**:\n{data['stdout']}")
                if "stderr" in data and data["stderr"]:
                    lines.append(f"**错误输出**:\n{data['stderr']}")

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

