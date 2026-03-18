"""
工具级依赖图调度系统 (ToolDependencyGraph)

基于现有专家级dependency_graph，实现工具级别的依赖关系调度：
- 支持工具级并行执行
- 自动参数绑定和依赖传递
- 失败恢复机制
- 集成ParameterBinder进行智能参数绑定
"""

from typing import Dict, Any, List, Set, Optional, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import structlog
from datetime import datetime
import uuid

from .parameter_binder import ParameterBinder, ToolResult, create_parameter_binder
from .tool_dependencies import TOOL_DEPENDENCY_GRAPHS
from .expert_plan_generator import ToolCallPlan

logger = structlog.get_logger()


class ToolTaskStatus(Enum):
    """工具任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class RetryStrategy(Enum):
    """重试策略枚举 (复用专家级定义)"""
    NONE = "none"
    EXPONENTIAL = "exponential"
    FIXED = "fixed"
    SKIP_ON_FAIL = "skip_on_fail"


@dataclass
class FallbackConfig:
    """降级配置"""
    tool: str  # 降级目标工具名称
    condition: str = "data_empty_or_error"  # 触发条件
    param_mapping: Dict[str, Any] = field(default_factory=dict)  # 参数映射
    description: str = ""  # 描述


@dataclass
class ToolNode:
    """工具节点定义"""
    tool_name: str
    index: int  # 工具在计划中的索引
    expert_type: str
    input_bindings: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[int] = field(default_factory=list)  # 依赖的工具索引
    retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: float = 60.0
    optional: bool = False
    fallback_enabled: bool = True
    fallback_config: Optional[FallbackConfig] = None  # 降级配置
    requires_context: bool = False  # 是否需要ExecutionContext
    role: Optional[str] = None  # 工具角色标识（如 water-soluble, carbon, crustal, trace）


@dataclass
class ToolExecutionResult:
    """工具执行结果"""
    tool_name: str
    index: int
    status: ToolTaskStatus
    result: Optional[Dict[str, Any]] = None
    data_id: Optional[str] = None
    error: Optional[str] = None
    diagnostics: Optional[Dict[str, Any]] = None
    execution_time: float = 0.0
    retry_count: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    bound_params: Optional[Dict[str, Any]] = None  # 绑定的参数


class ToolDependencyGraph:
    """工具级依赖图调度器"""

    def __init__(self, expert_type: str):
        """
        初始化工具依赖图

        Args:
            expert_type: 专家类型 (weather, component, viz, report)
        """
        self.expert_type = expert_type
        self.nodes: Dict[int, ToolNode] = {}
        self.tool_status: Dict[int, ToolTaskStatus] = {}
        self.execution_history: List[ToolExecutionResult] = []
        self.completed_tools: Set[int] = set()
        self.failed_tools: Set[int] = set()
        self.parameter_binder: ParameterBinder = create_parameter_binder()
        self.execution_context: Dict[str, Any] = {}

        # 加载工具依赖图配置
        self.tool_graph_config = TOOL_DEPENDENCY_GRAPHS.get(expert_type, {})
        logger.info(
            "tool_dependency_graph_initialized",
            expert_type=expert_type,
            has_config=bool(self.tool_graph_config)
        )

    def build_from_tool_plan(self, tool_plan: List[ToolCallPlan], context: Dict[str, Any]) -> List[ToolNode]:
        """
        从工具计划构建依赖图节点

        Args:
            tool_plan: 工具调用计划列表
            context: 执行上下文

        Returns:
            构建的节点列表
        """
        nodes = []

        # 如果有依赖图配置，使用配置
        if self.tool_graph_config and "tools" in self.tool_graph_config:
            config_tools = self.tool_graph_config["tools"]

            for i, plan in enumerate(tool_plan):
                if plan.tool in config_tools:
                    tool_config = config_tools[plan.tool]

                    # 解析降级配置
                    fallback_config = None
                    if "fallback" in tool_config:
                        fb = tool_config["fallback"]
                        fallback_config = FallbackConfig(
                            tool=fb.get("tool", ""),
                            condition=fb.get("condition", "data_empty_or_error"),
                            param_mapping=fb.get("param_mapping", {}),
                            description=fb.get("description", "")
                        )
                        logger.info(
                            "fallback_config_loaded",
                            tool=plan.tool,
                            fallback_tool=fallback_config.tool,
                            condition=fallback_config.condition
                        )

                    # 构建节点
                    node = ToolNode(
                        tool_name=plan.tool,
                        index=i,
                        expert_type=self.expert_type,
                        input_bindings=tool_config.get("input_bindings", {}),
                        dependencies=plan.depends_on or [],
                        optional=plan.tool in self.tool_graph_config.get("optional_tools", []),
                        retry_strategy=RetryStrategy.EXPONENTIAL,
                        max_retries=tool_config.get("max_retries", 3),  # 从配置读取重试次数，默认3次
                        timeout=tool_config.get("timeout", 60.0),  # 从配置读取超时，默认60秒
                        fallback_config=fallback_config,
                        requires_context=tool_config.get("requires_context", False),
                        role=plan.role  # 从计划中提取角色标识
                    )
                    nodes.append(node)
                else:
                    # 如果工具不在配置中，创建基本节点
                    nodes.append(ToolNode(
                        tool_name=plan.tool,
                        index=i,
                        expert_type=self.expert_type,
                        dependencies=plan.depends_on or []
                    ))
        else:
            # 没有配置时，基于ToolCallPlan创建简单节点
            for i, plan in enumerate(tool_plan):
                nodes.append(ToolNode(
                    tool_name=plan.tool,
                    index=i,
                    expert_type=self.expert_type,
                    dependencies=plan.depends_on or []
                ))

        # 添加到图
        for node in nodes:
            self.add_node(node)

        logger.info(
            "tool_graph_built",
            expert_type=self.expert_type,
            tool_count=len(nodes),
            nodes=[n.tool_name for n in nodes]
        )

        return nodes

    def add_node(self, node: ToolNode):
        """添加工具节点"""
        self.nodes[node.index] = node
        self.tool_status[node.index] = ToolTaskStatus.PENDING
        logger.debug(
            "tool_node_added",
            tool=node.tool_name,
            index=node.index,
            dependencies=node.dependencies
        )

    def get_ready_tools(self) -> List[int]:
        """获取所有就绪工具（依赖已满足）"""
        ready_tools = []
        for index, node in self.nodes.items():
            if self.tool_status[index] != ToolTaskStatus.PENDING:
                continue

            # 检查所有依赖是否已完成
            dependencies_met = all(
                self.tool_status.get(dep) == ToolTaskStatus.SUCCESS
                for dep in node.dependencies
            )

            if dependencies_met:
                ready_tools.append(index)

        logger.debug("ready_tools_identified", ready_tools=ready_tools)
        return ready_tools

    def can_skip_tool(self, index: int) -> bool:
        """判断工具是否可以跳过"""
        node = self.nodes[index]
        if not node.optional:
            return False

        # 检查下游任务
        downstream_tools = self.get_downstream_tools(index)
        for downstream in downstream_tools:
            downstream_node = self.nodes[downstream]
            if not downstream_node.optional:
                return False

        logger.debug("tool_can_be_skipped", tool=node.tool_name, index=index)
        return True

    def get_downstream_tools(self, index: int) -> List[int]:
        """获取依赖指定工具的所有下游工具"""
        downstream = []
        for idx, node in self.nodes.items():
            if index in node.dependencies:
                downstream.append(idx)
        return downstream

    async def execute_tool_chain(
        self,
        tool_plan: List[ToolCallPlan],
        tool_executor_func: Callable,
        execution_context: Dict[str, Any],
        initial_tool_results: Optional[List[ToolResult]] = None
    ) -> List[ToolExecutionResult]:
        """
        执行工具链（支持并行和顺序执行）

        Args:
            tool_plan: 工具计划
            tool_executor_func: 工具执行函数 (index, tool_name, params, context, upstream_results) -> result
                          接收5个参数：工具索引、工具名称、绑定参数、执行上下文、上游工具结果列表
            execution_context: 执行上下文
            initial_tool_results: 初始工具结果

        Returns:
            工具执行结果列表
        """
        logger.info(
            "tool_chain_execution_started",
            expert_type=self.expert_type,
            tool_count=len(tool_plan)
        )

        # 构建依赖图
        self.build_from_tool_plan(tool_plan, execution_context)
        self.execution_context = execution_context

        # 转换初始结果
        tool_results_map = self._convert_to_tool_results_map(initial_tool_results or [])

        results = []
        max_iterations = len(self.nodes) * 2
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            ready_indices = self.get_ready_tools()

            if not ready_indices:
                logger.info("no_ready_tools", iteration=iteration)
                break

            # 并行执行就绪工具
            logger.info(
                "executing_ready_tools_batch",
                tools=[self.nodes[i].tool_name for i in ready_indices],
                iteration=iteration
            )

            # 执行工具
            batch_results = await asyncio.gather(
                *[self._execute_single_tool(i, tool_executor_func, tool_results_map)
                  for i in ready_indices],
                return_exceptions=True
            )

            # 处理结果
            for i, result in enumerate(batch_results):
                index = ready_indices[i]

                if isinstance(result, Exception):
                    logger.error("tool_exception", tool=self.nodes[index].tool_name, error=str(result))
                    results.append(ToolExecutionResult(
                        tool_name=self.nodes[index].tool_name,
                        index=index,
                        status=ToolTaskStatus.FAILED,
                        error=str(result)
                    ))
                    self.tool_status[index] = ToolTaskStatus.FAILED
                    self.failed_tools.add(index)
                else:
                    results.append(result)

                    # 更新工具结果映射
                    if result.status == ToolTaskStatus.SUCCESS:
                        self.tool_status[index] = ToolTaskStatus.SUCCESS
                        self.completed_tools.add(index)

                        # 【修复】转换为ToolResult并添加到映射 - 确保传递完整的result字典
                        # 由于现在返回的是扁平化结构（无嵌套result层），
                        # 直接使用execution_result作为result
                        execution_result = result.result if isinstance(result.result, dict) else {}
                        if result.data_id:
                            execution_result["data_id"] = result.data_id

                        tool_result = ToolResult(
                            tool_name=result.tool_name,
                            index=index,
                            result=execution_result,
                            role=self.nodes[index].role if index in self.nodes else None
                        )
                        tool_results_map[index] = tool_result

                        # 【调试】输出ToolResult的data_id
                        logger.info(
                            "tool_result_created",
                            tool=result.tool_name,
                            index=index,
                            role=self.nodes[index].role if index in self.nodes else None,
                            data_id=tool_result.data_id,
                            has_data_id=bool(tool_result.data_id),
                            result_type=type(execution_result).__name__,
                            result_keys=list(execution_result.keys()) if isinstance(execution_result, dict) else None
                        )

        # 检查执行结果
        if len(self.completed_tools) == len(self.nodes):
            logger.info("tool_chain_completed", total_tools=len(self.nodes))
        else:
            logger.warning(
                "tool_chain_incomplete",
                completed=len(self.completed_tools),
                total=len(self.nodes),
                failed=list(self.failed_tools)
            )

        # 按索引排序结果
        results.sort(key=lambda x: x.index)
        return results

    async def _execute_single_tool(
        self,
        index: int,
        tool_executor_func: Callable,
        tool_results_map: Dict[int, ToolResult]
    ) -> ToolExecutionResult:
        """执行单个工具（带重试、参数绑定和降级支持）"""
        node = self.nodes[index]
        start_time = datetime.utcnow()

        self.tool_status[index] = ToolTaskStatus.RUNNING
        logger.info(
            "tool_started",
            tool=node.tool_name,
            index=index,
            retry_count=0
        )

        retry_count = 0
        last_error = None
        execution_result = None
        bound_params = {}

        while retry_count <= node.max_retries:
            try:
                # 构建参数
                bound_params = await self._bind_tool_parameters(
                    node,
                    tool_results_map,
                    self.execution_context
                )

                # 记录工具执行开始
                logger.info(
                    "tool_execution_start",
                    tool=node.tool_name,
                    index=index,
                    timeout=node.timeout,
                    attempt=retry_count + 1,
                    max_retries=node.max_retries,
                    has_upstream=len(tool_results_map) > 0 if tool_results_map else False,
                    upstream_count=len(tool_results_map) if tool_results_map else 0
                )

                # 【修复】执行工具时传递上游工具结果
                # 将tool_results_map转换为列表传递给execute_tool函数
                upstream_tool_results = list(tool_results_map.values())
                execution_result = await asyncio.wait_for(
                    tool_executor_func(index, node.tool_name, bound_params, self.execution_context, upstream_tool_results),
                    timeout=node.timeout
                )

                # 检查工具返回的错误状态
                if isinstance(execution_result, dict):
                    result_status = execution_result.get("status")
                    result_success = execution_result.get("success")
                    if result_status in ["error", "failed"] or result_success is False:
                        error_msg = execution_result.get("error") or execution_result.get("summary") or "工具返回错误状态"
                        logger.warning(
                            "tool_returned_error_status",
                            tool=node.tool_name,
                            attempt=retry_count + 1,
                            status=result_status,
                            success=result_success,
                            error=error_msg
                        )
                        # 对于某些错误类型，应该抛出异常以触发重试
                        # 但对于明确的错误（如参数错误），不应该重试
                        if retry_count < node.max_retries:
                            # 检查是否是应该重试的错误类型
                            error_type = execution_result.get("error_type", "")
                            # 如果是API调用失败、网络错误等，应该重试
                            if error_type in ["api_failed", "timeout", "network_error"] or "API" in error_msg or "超时" in error_msg or "网络" in error_msg:
                                raise Exception(f"工具返回可重试的错误: {error_msg}")

                # 【修复】在降级检查之前，先提取data_id到顶层，以便正确判断
                if isinstance(execution_result, dict) and not execution_result.get("data_id"):
                    # 尝试从metadata中提取data_id
                    if "metadata" in execution_result and isinstance(execution_result["metadata"], dict):
                        extracted_id = execution_result["metadata"].get("data_id")
                        if extracted_id:
                            execution_result["data_id"] = extracted_id
                    # 尝试从result字段提取
                    elif "result" in execution_result and isinstance(execution_result["result"], dict):
                        extracted_id = execution_result["result"].get("data_id")
                        if not extracted_id and "metadata" in execution_result["result"]:
                            extracted_id = execution_result["result"]["metadata"].get("data_id")
                        if extracted_id:
                            execution_result["data_id"] = extracted_id

                # 检查是否需要触发降级
                if self._should_trigger_fallback(node, execution_result):
                    logger.info(
                        "fallback_triggered",
                        tool=node.tool_name,
                        fallback_tool=node.fallback_config.tool,
                        reason="data_empty_or_error"
                    )
                    # 执行降级工具
                    fallback_result = await self._execute_fallback_tool(
                        node=node,
                        original_params=bound_params,
                        tool_executor_func=tool_executor_func,
                        tool_results_map=tool_results_map
                    )
                    if fallback_result:
                        execution_result = fallback_result
                        logger.info(
                            "fallback_succeeded",
                            tool=node.tool_name,
                            fallback_tool=node.fallback_config.tool
                        )

                # 构建成功结果
                execution_time = (datetime.utcnow() - start_time).total_seconds()

                # 【修复】从execution_result中提取data_id，支持多种字段格式
                extracted_data_id = None
                if isinstance(execution_result, dict):
                    # 1. 首先尝试从顶层获取data_id
                    extracted_data_id = execution_result.get("data_id")

                    # 2. 如果没有，尝试从data字段获取data_id（分析工具返回格式）
                    if not extracted_data_id and "data" in execution_result:
                        data_field = execution_result["data"]
                        if isinstance(data_field, dict):
                            extracted_data_id = data_field.get("data_id")

                    # 3. 如果没有，尝试从metadata中获取xxx_result_id或data_id
                    if not extracted_data_id and "metadata" in execution_result:
                        metadata = execution_result["metadata"]
                        if isinstance(metadata, dict):
                            # 优先获取具体结果ID（pmf_result_id, obm_result_id等）
                            for key in ["pmf_result_id", "obm_result_id", "chart_data_id", "result_id"]:
                                if key in metadata and metadata[key]:
                                    extracted_data_id = metadata[key]
                                    break
                            # 最后尝试获取通用data_id（可能是输入数据ID，不是结果ID）
                            if not extracted_data_id:
                                extracted_data_id = metadata.get("data_id")

                result = ToolExecutionResult(
                    tool_name=node.tool_name,
                    index=index,
                    status=ToolTaskStatus.SUCCESS,
                    # 【修复】当工具返回格式中没有嵌套result字段时，直接使用完整的execution_result
                    # 这样可以保留data_id等顶层字段，确保ParameterBinder能正确绑定
                    result=execution_result if isinstance(execution_result, dict) else None,
                    data_id=extracted_data_id,
                    execution_time=execution_time,
                    retry_count=retry_count,
                    bound_params=bound_params
                )

                logger.info(
                    "tool_completed",
                    tool=node.tool_name,
                    execution_time=execution_time,
                    retry_count=retry_count
                )

                return result

            except Exception as e:
                # 记录详细的异常信息
                error_type = type(e).__name__
                error_msg = str(e) if str(e) else f"{error_type} (no message)"
                error_repr = repr(e)
                last_error = e
                retry_count += 1

                # 特殊处理超时错误，提供更详细的诊断信息
                if error_type == "TimeoutError":
                    logger.error(
                        "tool_timeout_detailed",
                        tool=node.tool_name,
                        attempt=retry_count,
                        timeout_seconds=node.timeout,
                        error=error_msg,
                        error_type=error_type,
                        bound_params=bound_params,
                        upstream_tools=[r.tool_name for r in tool_results_map.values()] if tool_results_map else [],
                        diagnostic_hint="工具执行超时。可能原因：1) 数据库连接池满 2) 外部API响应慢 3) 数据量过大 4) 网络延迟",
                        exc_info=True
                    )
                else:
                    logger.warning(
                        "tool_failed",
                        tool=node.tool_name,
                        attempt=retry_count,
                        error=error_msg,
                        error_type=error_type,
                        error_repr=error_repr,
                        exc_info=True  # 记录完整的堆栈跟踪
                    )

                # 检查是否应该重试
                if retry_count > node.max_retries:
                    break

                # 等待后重试
                if node.retry_strategy == RetryStrategy.EXPONENTIAL:
                    delay = node.retry_delay * (2 ** (retry_count - 1))
                elif node.retry_strategy == RetryStrategy.FIXED:
                    delay = node.retry_delay
                else:
                    delay = 0

                if delay > 0:
                    logger.info(
                        "tool_retrying",
                        tool=node.tool_name,
                        delay=delay,
                        attempt=retry_count
                    )
                    await asyncio.sleep(delay)

        # 所有重试均失败，尝试降级
        if node.fallback_config and node.fallback_config.tool:
            logger.info(
                "fallback_triggered_after_retries",
                tool=node.tool_name,
                fallback_tool=node.fallback_config.tool,
                reason="all_retries_failed"
            )
            try:
                fallback_result = await self._execute_fallback_tool(
                    node=node,
                    original_params=bound_params,
                    tool_executor_func=tool_executor_func,
                    tool_results_map=tool_results_map
                )
                if fallback_result and self._is_fallback_successful(fallback_result):
                    execution_time = (datetime.utcnow() - start_time).total_seconds()

                    # 提取data_id
                    extracted_data_id = None
                    if isinstance(fallback_result, dict):
                        extracted_data_id = fallback_result.get("data_id")
                        if not extracted_data_id and "metadata" in fallback_result:
                            extracted_data_id = fallback_result["metadata"].get("data_id")

                    result = ToolExecutionResult(
                        tool_name=node.tool_name,
                        index=index,
                        status=ToolTaskStatus.SUCCESS,
                        result=fallback_result,
                        data_id=extracted_data_id,
                        execution_time=execution_time,
                        retry_count=retry_count,
                        bound_params=bound_params,
                        diagnostics={"fallback_used": node.fallback_config.tool}
                    )

                    logger.info(
                        "fallback_succeeded_after_retries",
                        tool=node.tool_name,
                        fallback_tool=node.fallback_config.tool,
                        data_id=extracted_data_id
                    )

                    return result
            except Exception as fallback_error:
                logger.error(
                    "fallback_failed",
                    tool=node.tool_name,
                    fallback_tool=node.fallback_config.tool,
                    error=str(fallback_error)
                )
                last_error = f"原工具失败: {last_error}; 降级工具失败: {str(fallback_error)}"

        # 所有重试和降级均失败
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        result = ToolExecutionResult(
            tool_name=node.tool_name,
            index=index,
            status=ToolTaskStatus.FAILED,
            error=last_error,
            execution_time=execution_time,
            retry_count=retry_count
        )

        self.tool_status[index] = ToolTaskStatus.FAILED
        self.failed_tools.add(index)

        logger.error(
            "tool_failed_permanently",
            tool=node.tool_name,
            attempts=retry_count,
            error=last_error
        )

        return result

    def _should_trigger_fallback(self, node: ToolNode, execution_result: Dict[str, Any]) -> bool:
        """判断是否需要触发降级"""
        if not node.fallback_config or not node.fallback_config.tool:
            return False

        condition = node.fallback_config.condition

        if condition == "data_empty_or_error":
            # 检查是否数据为空或有错误
            if not isinstance(execution_result, dict):
                return True

            # 检查success标志（支持多种格式）
            if execution_result.get("success") is False:
                logger.info("fallback_trigger_reason", reason="success=False", tool=node.tool_name)
                return True

            # 检查status标志
            if execution_result.get("status") == "error":
                logger.info("fallback_trigger_reason", reason="status=error", tool=node.tool_name)
                return True

            # 检查data_id是否包含error标志
            data_id = execution_result.get("data_id", "")
            if isinstance(data_id, str) and "error" in data_id.lower():
                logger.info("fallback_trigger_reason", reason=f"data_id contains error: {data_id}", tool=node.tool_name)
                return True

            # 检查数据是否为空（直接触发降级，不再检查summary）
            data = execution_result.get("data")
            if data is not None:
                if isinstance(data, list) and len(data) == 0:
                    logger.info("fallback_trigger_reason", reason="data is empty list", tool=node.tool_name)
                    return True
                if isinstance(data, dict) and len(data) == 0:
                    logger.info("fallback_trigger_reason", reason="data is empty dict", tool=node.tool_name)
                    return True

            # 检查是否有明确的警告信息
            summary = execution_result.get("summary", "")
            if summary and ("[WARN]" in summary or "没有" in summary or "不可用" in summary or "无数据" in summary):
                logger.info("fallback_trigger_reason", reason=f"warning in summary: {summary[:50]}", tool=node.tool_name)
                return True

            return False

        elif condition == "always":
            return True

        elif condition == "error_only":
            if not isinstance(execution_result, dict):
                return True
            return execution_result.get("success") is False or "error" in str(execution_result.get("data_id", "")).lower()

        return False

    def _is_fallback_successful(self, fallback_result: Dict[str, Any]) -> bool:
        """判断降级结果是否成功"""
        if not isinstance(fallback_result, dict):
            return False

        # 检查success标志
        if fallback_result.get("success") is False:
            return False

        # 检查是否有数据
        data = fallback_result.get("data")
        if data is None:
            # 某些工具可能不返回data，但有data_id
            if fallback_result.get("data_id"):
                return True
            return False

        return True

    async def _execute_fallback_tool(
        self,
        node: ToolNode,
        original_params: Dict[str, Any],
        tool_executor_func: Callable,
        tool_results_map: Dict[int, ToolResult]
    ) -> Optional[Dict[str, Any]]:
        """执行降级工具"""
        if not node.fallback_config:
            return None

        fallback_tool = node.fallback_config.tool
        param_mapping = node.fallback_config.param_mapping

        # 构建降级工具的参数
        fallback_params = {}

        # 1. 应用参数映射
        for source_key, target_key in param_mapping.items():
            if source_key == "_defaults":
                continue  # 单独处理默认值
            if source_key in original_params:
                fallback_params[target_key] = original_params[source_key]
            elif source_key in self.execution_context:
                fallback_params[target_key] = self.execution_context[source_key]

        # 2. 应用默认值
        defaults = param_mapping.get("_defaults", {})
        for key, value in defaults.items():
            if key not in fallback_params:
                fallback_params[key] = value

        # 3. 从执行上下文补充必要参数（lat, lon等）
        for key in ["lat", "lon", "station_name"]:
            if key not in fallback_params and key in self.execution_context:
                fallback_params[key] = self.execution_context[key]

        logger.info(
            "executing_fallback_tool",
            original_tool=node.tool_name,
            fallback_tool=fallback_tool,
            fallback_params=list(fallback_params.keys())
        )

        try:
            # 执行降级工具
            upstream_tool_results = list(tool_results_map.values())
            fallback_result = await asyncio.wait_for(
                tool_executor_func(
                    node.index,  # 使用原工具的索引
                    fallback_tool,
                    fallback_params,
                    self.execution_context,
                    upstream_tool_results
                ),
                timeout=node.timeout
            )

            # 标记结果来自降级
            if isinstance(fallback_result, dict):
                # 【修复】检查metadata是否为None或不存在
                if not fallback_result.get("metadata"):
                    fallback_result["metadata"] = {}
                fallback_result["metadata"]["fallback_from"] = node.tool_name
                fallback_result["metadata"]["fallback_tool"] = fallback_tool

            return fallback_result

        except Exception as e:
            logger.error(
                "fallback_tool_execution_failed",
                fallback_tool=fallback_tool,
                error=str(e)
            )
            raise

    async def _bind_tool_parameters(
        self,
        node: ToolNode,
        tool_results_map: Dict[int, ToolResult],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """为工具绑定参数"""
        try:
            if node.input_bindings:
                # 收集所有可用的tool_results
                # 【防御】确保tool_results_map不为None
                all_tool_results = list(tool_results_map.values()) if tool_results_map else []

                # 【调试】输出tool_results状态
                logger.info(
                    "parameter_binding_tool_results",
                    tool=node.tool_name,
                    index=node.index,
                    input_bindings=node.input_bindings,
                    tool_results_count=len(all_tool_results),
                    tool_results=[{
                        "tool_name": r.tool_name,
                        "index": r.index,
                        "has_data_id": bool(r.data_id),
                        "data_id": r.data_id[:20] + "..." if r.data_id and len(r.data_id) > 20 else r.data_id
                    } for r in all_tool_results if r is not None]
                )

                # 【防御】检查是否有任何工具结果为None
                none_count = sum(1 for r in all_tool_results if r is None)
                if none_count > 0:
                    logger.warning(
                        "parameter_binding_none_tool_results",
                        tool=node.tool_name,
                        index=node.index,
                        none_count=none_count,
                        total_count=len(all_tool_results)
                    )

                # 使用ParameterBinder进行智能绑定
                bound_params = self.parameter_binder.bind_parameters(
                    tool_name=node.tool_name,
                    input_bindings=node.input_bindings,
                    context=context,
                    tool_results=all_tool_results
                )

                logger.info(
                    "parameters_bound",
                    tool=node.tool_name,
                    param_count=len(bound_params),
                    bound_params_keys=list(bound_params.keys()) if bound_params else []
                )

                return bound_params
            else:
                # 没有绑定配置，返回空字典
                logger.info(
                    "no_parameter_bindings",
                    tool=node.tool_name,
                    index=node.index
                )
                return {}

        except TypeError as e:
            # 捕获TypeError（特别是NoneType的len错误）
            logger.error(
                "parameter_binding_type_error",
                tool=node.tool_name,
                index=node.index,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True
            )
            return {}

        except Exception as e:
            logger.error(
                "parameter_binding_failed",
                tool=node.tool_name,
                index=node.index,
                error=str(e),
                exc_info=True
            )
            return {}

    def _convert_to_tool_results_map(
        self,
        tool_results: List[ToolResult]
    ) -> Dict[int, ToolResult]:
        """将工具结果列表转换为索引映射"""
        results_map = {}
        for result in tool_results:
            results_map[result.index] = result
        return results_map

    def get_execution_summary(self) -> Dict[str, Any]:
        """获取执行摘要"""
        return {
            "expert_type": self.expert_type,
            "total_tools": len(self.nodes),
            "completed_tools": len(self.completed_tools),
            "failed_tools": len(self.failed_tools),
            "success_rate": len(self.completed_tools) / len(self.nodes) if self.nodes else 0,
            "execution_history": [
                {
                    "tool": r.tool_name,
                    "index": r.index,
                    "status": r.status.value,
                    "execution_time": r.execution_time,
                    "retry_count": r.retry_count,
                    "timestamp": r.timestamp.isoformat(),
                    "has_data_id": bool(r.data_id)
                }
                for r in self.execution_history
            ]
        }


def create_tool_dependency_graph(expert_type: str) -> ToolDependencyGraph:
    """创建工具依赖图实例"""
    return ToolDependencyGraph(expert_type)
