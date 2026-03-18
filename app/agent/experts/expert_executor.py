"""
专家执行器基类 (ExpertExecutor)

职责：执行工具计划 + 错误重试 + 专业总结

执行流程：
1. 接收主Agent生成的工具计划
2. 按计划执行工具链（支持依赖和并发）
3. 失败时调用轻量LLM修正参数并重试（最多1次）
4. 提取统计摘要
5. 调用总结LLM生成专业分析
6. 返回结果
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field
import structlog
import asyncio
import json
import copy
from datetime import datetime, date

from app.services.llm_service import llm_service
from app.agent.core.expert_plan_generator import ExpertTask, ToolCallPlan
from app.agent.core.parameter_binder import ParameterBinder, ToolResult, create_parameter_binder
from app.agent.core.tool_dependency_graph import (
    ToolDependencyGraph,
    ToolExecutionResult,
    ToolTaskStatus,
    create_tool_dependency_graph
)

logger = structlog.get_logger()


class ExecutionSummary(BaseModel):
    """执行摘要"""
    tools_executed: int = 0
    tools_succeeded: int = 0
    tools_failed: int = 0
    retry_used: bool = False
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class ExpertAnalysis(BaseModel):
    """专家分析结论"""
    summary: str = ""
    key_findings: List[str] = Field(default_factory=list)
    data_quality: str = "unknown"
    confidence: float = 0.0
    section_content: str = ""  # 带预设标识的章节内容（Markdown格式）


class ExpertResult(BaseModel):
    """专家执行结果"""
    status: str = "pending"  # success / partial / failed
    expert_type: str = ""
    task_id: str = ""
    data_ids: List[str] = Field(default_factory=list)
    skip_viz_data_ids: List[str] = Field(default_factory=list)  # 需要跳过可视化的data_id列表
    execution_summary: ExecutionSummary = Field(default_factory=ExecutionSummary)
    analysis: ExpertAnalysis = Field(default_factory=ExpertAnalysis)
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)
    visuals: List[Dict[str, Any]] = Field(default_factory=list)  # 聚合所有工具的visuals传递给前端
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class ExpertExecutor(ABC):
    """专家执行器基类"""
    
    def __init__(self, expert_type: str):
        self.expert_type = expert_type
        # 加载原始工具类和注册表
        self.original_tools = self._load_tools()
        # 获取已注册的包装工具
        self.tools = self._get_registered_tools()
        self.max_retries = 1
        # 初始化参数绑定器
        self.parameter_binder = create_parameter_binder()

        logger.info(
            "expert_executor_initialized",
            expert_type=expert_type,
            tools=list(self.tools.keys()),
            original_count=len(self.original_tools),
            wrapped_count=len(self.tools)
        )
    
    @abstractmethod
    def _load_tools(self) -> Dict[str, Any]:
        """加载专家可用的工具"""
        pass

    def _get_registered_tools(self) -> Dict[str, Any]:
        """
        获取已注册的包装工具（从ReAct Agent工具注册表）

        这些包装工具会自动处理context参数传递，避免"missing required positional argument"错误
        """
        try:
            from app.agent.tool_adapter import get_react_agent_tool_registry

            # 获取ReAct Agent的工具注册表
            registered_tools = get_react_agent_tool_registry()

            # 筛选出当前专家可用的工具
            available_tools = {}
            for tool_name in self.original_tools.keys():
                if tool_name in registered_tools:
                    available_tools[tool_name] = registered_tools[tool_name]
                    logger.debug(
                        "tool_wrapped_successfully",
                        expert_type=self.expert_type,
                        tool_name=tool_name
                    )
                else:
                    # 如果工具未注册，创建包装函数来调用原始工具的execute方法
                    original_tool = self.original_tools[tool_name]
                    
                    # 创建包装函数（使用闭包捕获tool实例）
                    def make_tool_wrapper(tool_instance, name: str):
                        async def tool_wrapper(context=None, **kwargs):
                            """包装原始工具的execute方法

                            注意：工具的execute方法签名是 execute(self, context, ...)，
                            其中context是位置参数，不是关键字参数
                            """
                            try:
                                # 调用工具的execute方法
                                if hasattr(tool_instance, 'execute'):
                                    if context is not None:
                                        # 【修复】context作为位置参数传递（execute(self, context, ...)）
                                        result = await tool_instance.execute(context, **kwargs)
                                    else:
                                        result = await tool_instance.execute(**kwargs)
                                    return result
                                else:
                                    return {
                                        "status": "error",
                                        "error": f"工具 {name} 没有execute方法",
                                        "success": False
                                    }
                            except Exception as e:
                                logger.error(
                                    "original_tool_execute_failed",
                                    tool=name,
                                    error=str(e)
                                )
                                return {
                                    "status": "error",
                                    "error": str(e),
                                    "success": False
                                }
                        tool_wrapper.__name__ = name
                        return tool_wrapper
                    
                    available_tools[tool_name] = make_tool_wrapper(original_tool, tool_name)
                    logger.warning(
                        "tool_not_in_registry",
                        expert_type=self.expert_type,
                        tool_name=tool_name,
                        message="Created wrapper for original tool (fallback mode)"
                    )

            logger.info(
                "registered_tools_loaded",
                expert_type=self.expert_type,
                available_count=len(available_tools),
                wrapped_count=len([t for t in available_tools.values() if t in registered_tools.values()])
            )

            return available_tools

        except Exception as e:
            logger.error(
                "failed_to_load_registered_tools",
                expert_type=self.expert_type,
                error=str(e),
                message="Using original tools only"
            )
            # 如果无法获取注册表，返回原始工具（向后兼容）
            return self.original_tools

    @abstractmethod
    def _get_summary_prompt(self) -> str:
        """获取专家特定的总结提示词"""
        pass
    
    @abstractmethod
    def _extract_summary_stats(self, tool_results: List[Dict]) -> Dict[str, Any]:
        """从工具结果中提取统计摘要（专家特定）"""
        pass
    
    async def execute(self, task: ExpertTask, execution_context=None) -> ExpertResult:
        """
        执行专家任务

        Args:
            task: 专家任务（包含工具计划）
            execution_context: ExecutionContext对象（可选，如果未提供则从task.context创建）

        Returns:
            ExpertResult: 执行结果
        """
        logger.info(
            "expert_execution_started",
            expert_type=self.expert_type,
            task_id=task.task_id,
            tool_count=len(task.tool_plan),
            has_execution_context=execution_context is not None
        )

        result = ExpertResult(
            status="pending",
            expert_type=self.expert_type,
            task_id=task.task_id
        )

        try:
            # 如果没有提供ExecutionContext，尝试从task.context创建
            if execution_context is None:
                # task.context可能是ExecutionContext对象或字典
                from app.agent.context import ExecutionContext
                if isinstance(task.context, ExecutionContext):
                    # 已经是ExecutionContext对象，直接使用
                    execution_context = task.context
                elif isinstance(task.context, dict):
                    # 是字典，创建ExecutionContext
                    context_dict = task.context.copy()
                    context_dict["session_id"] = context_dict.get("session_id", f"expert_{self.expert_type}_{task.task_id}")
                    execution_context = self._create_execution_context(context_dict)
                else:
                    # 其他情况，创建新的ExecutionContext
                    execution_context = self._create_execution_context({"session_id": f"expert_{self.expert_type}_{task.task_id}"})

            # 1. 执行工具链（传递ExecutionContext）
            tool_results = await self._execute_tool_chain(
                task.tool_plan,
                task.context or {}
            )
            result.tool_results = tool_results

            # 2. 自动为区域对比数据生成可视化（后置处理）
            tool_results = await self._auto_generate_regional_comparison_visuals(
                tool_results, execution_context
            )
            result.tool_results = tool_results

            # 3. 聚合所有工具的 visuals 字段传递给前端
            result.visuals = self._aggregate_visuals(tool_results)

            # 4. 构建执行摘要
            result.execution_summary = self._build_execution_summary(tool_results)

            # 5. 提取data_ids
            result.data_ids = self._extract_data_ids(tool_results)

            # 6. 提取skip_viz_data_ids（根据tool_plan中的skip_viz标记）
            result.skip_viz_data_ids = self._extract_skip_viz_data_ids(
                tool_results, task.tool_plan
            )

            # 7. 提取统计摘要
            summary_stats = self._extract_summary_stats(tool_results)

            # 7. 生成专业总结
            result.analysis = await self._generate_summary(
                task.task_description,
                summary_stats,
                tool_results,
                task  # 传递task对象给子类的_generate_summary
            )

            # 8. 确定最终状态
            result.status = self._determine_status(result.execution_summary)

            logger.info(
                "expert_execution_completed",
                expert_type=self.expert_type,
                task_id=task.task_id,
                status=result.status,
                data_ids=result.data_ids
            )

        except Exception as e:
            logger.error(
                "expert_execution_failed",
                expert_type=self.expert_type,
                task_id=task.task_id,
                error=str(e),
                exc_info=True
            )
            result.status = "failed"
            result.errors.append({"type": "execution_error", "message": str(e)})

        return result
    
    async def _execute_tool_chain(
        self,
        tool_plans: List[ToolCallPlan],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """执行工具链（使用ToolDependencyGraph进行智能调度）"""

        # 将Dict context转换为ExecutionContext对象
        execution_context = self._create_execution_context(context)

        # 创建工具依赖图
        tool_graph = create_tool_dependency_graph(self.expert_type)

        # 定义工具执行函数
        async def execute_tool(index: int, tool_name: str, params: Dict[str, Any], context: Dict[str, Any], upstream_results: Optional[List[ToolResult]] = None):
            """工具执行包装函数（支持降级场景）"""
            plan = tool_plans[index]

            # 【降级支持】检查是否是降级调用（tool_name != plan.tool）
            is_fallback_call = (tool_name != plan.tool)

            if is_fallback_call:
                # 降级场景：直接使用传入的params，不使用plan中的配置
                final_params = params.copy()
                logger.info(
                    "fallback_tool_execution",
                    expert_type=self.expert_type,
                    original_tool=plan.tool,
                    fallback_tool=tool_name,
                    fallback_params=list(final_params.keys())
                )
            else:
                # 正常场景：使用plan.params和tool_dependency_graph传入的bound_params
                final_params = plan.params.copy()

                # 【修复】首先合并tool_dependency_graph传入的params（已绑定的参数）
                if params:
                    final_params.update(params)
                    logger.info(
                        "tool_graph_params_merged",
                        tool=tool_name,
                        graph_params_count=len(params),
                        graph_params_keys=list(params.keys())
                    )

                # 【关键修复】移除旧参数名，避免与新参数名冲突
                # 当存在xxx_data_id参数时，移除对应的xxx_data参数（如vocs_data）
                params_to_remove = []
                for param_name in list(final_params.keys()):
                    # 如果存在xxx_data参数，且对应的xxx_data_id也存在，则移除xxx_data
                    if param_name.endswith("_data") and not param_name.endswith("_data_id"):
                        data_id_param = f"{param_name}_id"
                        if data_id_param in final_params:
                            params_to_remove.append(param_name)
                            logger.info(
                                "removing_deprecated_param",
                                tool=tool_name,
                                deprecated_param=param_name,
                                replacement_param=data_id_param
                            )

                for param_name in params_to_remove:
                    del final_params[param_name]

                # 使用上游工具结果进行额外参数绑定（如果plan有input_bindings）
                tool_results_for_binding = upstream_results or []

                if plan.input_bindings:
                    bound_params = self.parameter_binder.bind_parameters(
                        tool_name=tool_name,
                        input_bindings=plan.input_bindings,
                        context=context,
                        tool_results=tool_results_for_binding
                    )
                    final_params.update(bound_params)  # 合并绑定参数
                    logger.info(
                        "parameter_binding_with_upstream_results",
                        tool=tool_name,
                        upstream_count=len(tool_results_for_binding),
                        bound_params_count=len(bound_params)
                    )

                # 输出参数生成日志
                logger.info(
                    "tool_parameter_generation",
                    expert_type=self.expert_type,
                    tool=tool_name,
                    plan_params=plan.params,
                    plan_input_bindings=plan.input_bindings if plan.input_bindings else {},
                    graph_bound_params=params if params else {},  # 来自tool_dependency_graph的绑定
                    final_params=final_params,
                    purpose=plan.purpose,
                    upstream_tool_results=[{
                        "tool_name": r.tool_name,
                        "index": r.index,
                        "has_data_id": bool(r.data_id)
                    } for r in (upstream_results or [])]
                )

            # 执行工具
            result = await self._try_execute_tool(tool_name, final_params, execution_context)

            # 【修复】处理None结果
            if result is None:
                return {
                    "tool_name": tool_name,
                    "status": "error",
                    "success": False,
                    "error": f"工具 {tool_name} 执行失败",
                    "data": None,
                    "data_id": None,
                    "metadata": {}
                }

            # 【修复】返回更完整的结果，保留原始字段以便降级检查
            # 保留 success, data, summary, metadata, visuals 等字段用于降级判断和前端展示
            # 扁平化结构，不嵌套 result 层（符合 UDF v2.0 规范）
            if result.get("status") == "success" or result.get("success") is not False:
                return {
                    "tool_name": tool_name,
                    "status": "success",
                    "success": result.get("success", True),
                    "data": result.get("data"),
                    "visuals": result.get("visuals") or [],
                    "data_id": result.get("data_id") or result.get("metadata", {}).get("data_id") if isinstance(result.get("metadata"), dict) else None,
                    "summary": result.get("summary"),
                    "metadata": result.get("metadata") or {}
                }
            else:
                return {
                    "tool_name": tool_name,
                    "status": "error",
                    "success": result.get("success", False),
                    "error": result.get("error"),
                    "data": result.get("data"),
                    "visuals": result.get("visuals") or [],
                    "data_id": result.get("data_id") or result.get("metadata", {}).get("data_id") if isinstance(result.get("metadata"), dict) else None,
                    "summary": result.get("summary"),
                    "metadata": result.get("metadata") or {}
                }

        # 使用工具依赖图执行工具链
        try:
            execution_results = await tool_graph.execute_tool_chain(
                tool_plan=tool_plans,
                tool_executor_func=execute_tool,
                execution_context=context,
                initial_tool_results=[]
            )

            # 转换为扁平化格式（符合 UDF v2.0 规范）
            results = []
            for exec_result in execution_results:
                if exec_result.status == ToolTaskStatus.SUCCESS:
                    results.append({
                        "tool": exec_result.tool_name,
                        "status": "success",
                        "success": True,
                        "data": exec_result.result.get("data") if isinstance(exec_result.result, dict) else None,
                        "visuals": exec_result.result.get("visuals") if isinstance(exec_result.result, dict) else [],
                        "data_id": exec_result.data_id,
                        "summary": exec_result.result.get("summary") if isinstance(exec_result.result, dict) else None,
                        "metadata": exec_result.result.get("metadata") if isinstance(exec_result.result, dict) else {},
                        "bound_params": exec_result.bound_params
                    })
                else:
                    results.append({
                        "tool": exec_result.tool_name,
                        "status": "error",
                        "success": False,
                        "error": exec_result.error,
                        "data": None,
                        "visuals": [],
                        "data_id": None,
                        "summary": None,
                        "metadata": {},
                        "retry_count": exec_result.retry_count
                    })

            # 记录执行摘要
            summary = tool_graph.get_execution_summary()
            logger.info(
                "tool_chain_executed_with_dependency_graph",
                expert_type=self.expert_type,
                total_tools=summary["total_tools"],
                completed=summary["completed_tools"],
                failed=summary["failed_tools"],
                success_rate=summary["success_rate"]
            )

            return results

        except Exception as e:
            logger.error(
                "tool_dependency_graph_execution_failed",
                expert_type=self.expert_type,
                error=str(e)
            )
            # 降级到原来的执行方式
            logger.info("falling_back_to_original_execution")
            return await self._execute_tool_chain_fallback(tool_plans, context)

    async def _execute_tool_chain_fallback(
        self,
        tool_plans: List[ToolCallPlan],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """降级执行工具链（原版本）"""

        # 将Dict context转换为ExecutionContext对象
        execution_context = self._create_execution_context(context)

        results = [None] * len(tool_plans)
        executed = [False] * len(tool_plans)

        while not all(executed):
            # 找出可执行的工具（依赖已满足）
            ready_indices = []
            for i, plan in enumerate(tool_plans):
                if executed[i]:
                    continue
                if all(executed[dep] for dep in plan.depends_on):
                    ready_indices.append(i)

            if not ready_indices:
                logger.error("tool_chain_deadlock")
                break

            # 并发执行就绪的工具
            tasks = [
                self._execute_single_tool(tool_plans[i], results, execution_context)
                for i in ready_indices
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # 更新结果
            for i, idx in enumerate(ready_indices):
                if isinstance(batch_results[i], Exception):
                    results[idx] = {
                        "tool": tool_plans[idx].tool,
                        "status": "error",
                        "error": str(batch_results[i])
                    }
                else:
                    results[idx] = batch_results[i]
                executed[idx] = True

        return [r for r in results if r is not None]

    def _create_execution_context(self, context: Dict[str, Any]):
        """
        将Dict context转换为ExecutionContext对象

        Args:
            context: 包含session_id, iteration, data_manager等信息的字典

        Returns:
            ExecutionContext对象或None（如果转换失败）
        """
        try:
            # 从context字典中提取必要信息
            session_id = context.get("session_id", f"expert_{self.expert_type}")

            # 尝试获取或创建DataContextManager
            data_manager = context.get("data_manager")
            if not data_manager and hasattr(self, "_data_manager"):
                data_manager = self._data_manager

            if not data_manager:
                logger.warning(
                    "no_data_manager_available",
                    expert_type=self.expert_type,
                    message="Tools requiring context will fail"
                )
                return None

            # 创建ExecutionContext
            from app.agent.context import ExecutionContext

            execution_context = ExecutionContext(
                session_id=session_id,
                iteration=context.get("iteration", 0),
                data_manager=data_manager
            )

            logger.debug(
                "execution_context_created_for_expert",
                expert_type=self.expert_type,
                session_id=session_id
            )

            return execution_context

        except Exception as e:
            logger.error(
                "execution_context_creation_failed",
                expert_type=self.expert_type,
                error=str(e)
            )
            return None

    def _tool_requires_context(self, tool_name: str) -> bool:
        """
        检查工具是否需要context作为位置参数

        Args:
            tool_name: 工具名称

        Returns:
            bool: 如果工具需要context作为位置参数，返回True
        """
        try:
            # 获取原始工具（LLMTool实例）
            original_tool = self.original_tools.get(tool_name)

            # 检查工具是否设置了requires_context属性
            if hasattr(original_tool, 'requires_context'):
                if original_tool.requires_context:
                    logger.debug(
                        "tool_requires_context_as_positional",
                        tool=tool_name,
                        requires_context=original_tool.requires_context
                    )
                    return True

            # 对于包装工具，检查包装后的函数签名
            registered_tool = self.tools.get(tool_name)
            if hasattr(registered_tool, '__annotations__'):
                # 检查函数签名中是否有context参数
                import inspect
                sig = inspect.signature(registered_tool)
                params = sig.parameters

                # 如果第一个参数不是'context'或'kwargs'，可能是需要context的工具
                # 通过检查工具的具体类型判断
                if tool_name in ['get_air_quality', 'calculate_pm_pmf', 'calculate_vocs_pmf']:
                    return True

            # 默认值：认为需要context的工具
            logger.debug(
                "tool_context_requirement_unknown",
                tool=tool_name,
                default=True
            )
            return True

        except Exception as e:
            logger.warning(
                "tool_context_check_failed",
                tool=tool_name,
                error=str(e),
                default=True
            )
            return True  # 默认返回True以确保不遗漏需要context的工具

    async def _execute_single_tool(
        self,
        plan: ToolCallPlan,
        previous_results: List[Optional[Dict]],
        execution_context
    ) -> Dict[str, Any]:
        """执行单个工具（支持重试）"""

        tool_name = plan.tool
        params = self._resolve_params(plan.params, previous_results, execution_context)

        # 第一次尝试
        result = await self._try_execute_tool(tool_name, params, execution_context)

        # 如果失败且有重试机会，尝试修正参数
        if result["status"] == "error" and self.max_retries > 0:
            logger.warning(
                "tool_execution_failed_retrying",
                tool=tool_name,
                error=result.get("error")
            )

            # 使用轻量LLM修正参数
            tool = self.tools.get(tool_name)
            corrected_params = await self._correct_params(
                tool_name,
                params,
                result.get("error", ""),
                self._get_tool_schema(tool)
            )

            if corrected_params and corrected_params != params:
                # 重试
                result = await self._try_execute_tool(tool_name, corrected_params, execution_context)
                result["retry_used"] = True

        result["tool"] = tool_name
        result["purpose"] = plan.purpose

        return result
    
    async def _try_execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        execution_context
    ) -> Dict[str, Any]:
        """
        尝试执行工具（修复：使用已注册的包装工具，正确传递ExecutionContext和data_context_manager）

        核心修复：
        - 识别需要data_context_manager参数的工具
        - 从execution_context中提取data_manager并正确传递

        Args:
            tool_name: 工具名称
            params: 工具参数
            execution_context: ExecutionContext对象
        """
        # 【调试日志】入口
        logger.info(
            "try_execute_tool_entry",
            tool=tool_name,
            params_keys=list(params.keys()) if params else [],
            has_context=execution_context is not None
        )

        try:
            # 获取已注册的工具（包装工具）
            registered_tool = self.tools.get(tool_name)

            if not registered_tool:
                logger.error("tool_not_found_in_registry", tool=tool_name)
                return {
                    "status": "error",
                    "error": f"工具 {tool_name} 不存在"
                }

            # 使用包装后的工具（会自动处理context参数传递）
            logger.debug(
                "executing_wrapped_tool",
                tool=tool_name,
                has_context=execution_context is not None
            )

            # 【修复】需要data_context_manager的工具列表
            TOOLS_REQUIRING_DATA_CONTEXT_MANAGER = {
                "calculate_soluble",
                "calculate_carbon",
                "calculate_crustal",
                "calculate_trace",
                "calculate_reconstruction",
                "calculate_pm_pmf",
                "calculate_vocs_pmf",
                "calculate_obm_full_chemistry",
            }

            # 【修复】提取data_context_manager并注入到params中
            data_context_manager = None
            if execution_context is not None:
                # 从execution_context中提取data_manager
                if hasattr(execution_context, 'data_manager'):
                    data_context_manager = execution_context.data_manager
                elif hasattr(execution_context, 'get_data_manager'):
                    data_context_manager = execution_context.get_data_manager()

                # 如果工具需要data_context_manager，将其注入到params
                if tool_name in TOOLS_REQUIRING_DATA_CONTEXT_MANAGER:
                    if data_context_manager is not None:
                        # 检查params中是否已经有data_id但没有data_context_manager
                        if 'data_id' in params and 'data_context_manager' not in params:
                            params['data_context_manager'] = data_context_manager
                            logger.info(
                                "data_context_manager_injected",
                                tool=tool_name,
                                data_id=params.get('data_id')
                            )

            # 【修复】根据工具是否需要context智能传递参数
            if execution_context is not None:
                # 检查原始工具是否需要context（通过属性或函数签名）
                needs_context = self._tool_requires_context(tool_name)

                # 【调试日志】准备调用工具
                logger.info(
                    "about_to_call_tool",
                    tool=tool_name,
                    needs_context=needs_context,
                    params_count=len(params),
                    params_keys=list(params.keys())
                )

                if needs_context:
                    # 需要context的工具，将context作为位置参数传递
                    tool_result = await registered_tool(execution_context, **params)
                else:
                    # 不需要context的工具，context作为关键字参数
                    tool_result = await registered_tool(context=execution_context, **params)
            else:
                # 【调试日志】没有ExecutionContext
                logger.warning(
                    "calling_tool_without_context",
                    tool=tool_name,
                    params_count=len(params)
                )
                # 如果没有ExecutionContext，只传递参数（向后兼容）
                tool_result = await registered_tool(**params)

            # 【调试日志】记录工具原始返回
            logger.info(
                "[DEBUG_TOOL_RESULT] 工具返回原始结果",
                tool=tool_name,
                result_type=type(tool_result).__name__,
                result_is_dict=isinstance(tool_result, dict),
                result_keys=list(tool_result.keys()) if isinstance(tool_result, dict) else None,
                has_visuals=isinstance(tool_result, dict) and "visuals" in tool_result,
                visuals_count=len(tool_result.get("visuals", [])) if isinstance(tool_result, dict) and tool_result.get("visuals") is not None else None
            )

            # 处理结果
            if tool_result is None:
                # 工具返回None，表示执行失败
                logger.warning(
                    "tool_returned_none",
                    tool=tool_name,
                    params=params
                )
                return {
                    "status": "error",
                    "error": f"工具 {tool_name} 执行返回空结果",
                    "success": False,
                    "data": None,
                    "data_id": None,
                    "metadata": {}
                }
            elif isinstance(tool_result, dict):
                # 检查工具返回的success字段
                tool_success = tool_result.get("success")
                tool_status = tool_result.get("status", "success")
                if tool_success is False or tool_status in ["failed", "error"]:
                    # 失败情况：扁平化结构，不嵌套 result
                    return {
                        "status": "error",
                        "success": False,
                        "error": tool_result.get("error"),
                        "data": tool_result.get("data"),
                        "visuals": tool_result.get("visuals") or [],
                        "data_id": tool_result.get("data_id") or tool_result.get("metadata", {}).get("data_id") if isinstance(tool_result.get("metadata"), dict) else None,
                        "summary": tool_result.get("summary"),
                        "metadata": tool_result.get("metadata") or {}
                    }
                # 成功情况：扁平化结构，不嵌套 result（符合 UDF v2.0 规范）
                # 直接从 tool_result 提取各字段，不额外包装 result 层
                return {
                    "status": "success",
                    "success": tool_result.get("success", True),
                    "data": tool_result.get("data"),
                    "visuals": tool_result.get("visuals") or [],
                    "data_id": tool_result.get("data_id") or tool_result.get("metadata", {}).get("data_id") if isinstance(tool_result.get("metadata"), dict) else None,
                    "summary": tool_result.get("summary"),
                    "metadata": tool_result.get("metadata") or {}
                }
            else:
                # 处理Pydantic对象（如UnifiedData）
                if hasattr(tool_result, 'dict'):
                    result_dict = tool_result.dict()
                    tool_success = result_dict.get("success")
                    tool_status = str(result_dict.get("status", "success")).lower()
                    # 从metadata中获取data_id
                    metadata = result_dict.get("metadata") or {}
                    data_id = metadata.get("data_id") if isinstance(metadata, dict) else None

                    if tool_success is False or tool_status in ["failed", "error"]:
                        return {
                            "status": "error",
                            "success": False,
                            "error": result_dict.get("error"),
                            "data": result_dict.get("data"),
                            "visuals": result_dict.get("visuals") or [],
                            "data_id": data_id,
                            "summary": result_dict.get("summary"),
                            "metadata": metadata
                        }
                    return {
                        "status": "success",
                        "success": True,
                        "data": result_dict.get("data"),
                        "visuals": result_dict.get("visuals") or [],
                        "data_id": data_id,
                        "summary": result_dict.get("summary"),
                        "metadata": metadata
                    }
                return {
                    "status": "success",
                    "success": True,
                    "data": tool_result,
                    "visuals": [],
                    "data_id": None,
                    "summary": f"工具 {tool_name} 执行成功",
                    "metadata": {}
                }

        except TypeError as e:
            # 参数错误（通常是缺少context或参数不匹配）
            logger.error(
                "tool_argument_error",
                tool=tool_name,
                error=str(e),
                has_context=execution_context is not None,
                provided_params=list(params.keys())
            )
            return {
                "status": "error",
                "error": f"参数错误: {str(e)}",
                "error_type": "TypeError"
            }
        except Exception as e:
            logger.error(
                "tool_execution_error",
                tool=tool_name,
                error=str(e),
                exc_info=True
            )
            return {
                "status": "error",
                "error": str(e)
            }
    
    def _resolve_params(
        self,
        params: Dict[str, Any],
        previous_results: List[Optional[Dict]],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """解析参数中的引用（使用ParameterBinder进行智能绑定）"""

        # 转换为工具结果格式
        tool_results = []
        for i, result in enumerate(previous_results):
            if result and isinstance(result, dict):
                tool_name = result.get("tool", f"tool_{i}")
                tool_results.append(ToolResult(
                    tool_name=tool_name,
                    index=i,
                    result=result
                ))

        # 使用参数绑定器进行绑定（简化版本：直接返回参数，不使用input_bindings）
        # TODO: 在Phase 3中集成完整的input_bindings支持
        resolved = {}

        for key, value in params.items():
            if isinstance(value, str):
                # 处理 $N 引用（前序工具结果）- 扁平化结构
                if value.startswith("$"):
                    try:
                        idx = int(value[1:])
                        if idx < len(previous_results) and previous_results[idx]:
                            prev = previous_results[idx]
                            # 扁平化结构：data_id, data 在顶层
                            if prev.get("data_id"):
                                resolved[key] = prev["data_id"]
                            elif prev.get("data"):
                                resolved[key] = prev["data"]
                            else:
                                resolved[key] = value
                        else:
                            resolved[key] = value
                    except ValueError:
                        resolved[key] = value
                # 处理 {field} 引用（上下文）
                elif value.startswith("{") and value.endswith("}"):
                    field = value[1:-1]
                    resolved[key] = context.get(field, value)
                else:
                    resolved[key] = value
            else:
                resolved[key] = value

        # 记录参数解析日志
        logger.debug(
            "params_resolved",
            original_count=len(params),
            resolved_count=len(resolved),
            tool_results_count=len(tool_results)
        )

        return resolved

    def _bind_parameters_with_binder(
        self,
        tool_name: str,
        input_bindings: Dict[str, Any],
        context: Dict[str, Any],
        tool_results: List[ToolResult]
    ) -> Dict[str, Any]:
        """
        使用ParameterBinder进行智能参数绑定

        Args:
            tool_name: 工具名称
            input_bindings: 输入绑定配置
            context: 执行上下文
            tool_results: 工具结果列表

        Returns:
            绑定后的参数字典
        """
        try:
            bound_params = self.parameter_binder.bind_parameters(
                tool_name=tool_name,
                input_bindings=input_bindings,
                context=context,
                tool_results=tool_results
            )

            logger.info(
                "parameters_bound_successfully",
                tool=tool_name,
                param_count=len(bound_params),
                binding_type="intelligent"
            )

            return bound_params

        except Exception as e:
            logger.error(
                "parameter_binding_failed",
                tool=tool_name,
                error=str(e)
            )
            # 绑定失败时返回空字典
            return {}
    
    async def _correct_params(
        self,
        tool_name: str,
        original_params: Dict[str, Any],
        error: str,
        tool_schema: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """使用轻量LLM修正参数"""
        
        schema_str = json.dumps(tool_schema, ensure_ascii=False, indent=2) if tool_schema else "无"
        
        prompt = f"""你是参数修正助手。工具调用失败，请根据错误信息修正参数。

失败工具: {tool_name}
原始参数: {json.dumps(original_params, ensure_ascii=False)}
错误信息: {error}
参数规范: {schema_str}

只返回修正后的参数JSON，不要解释。"""

        try:
            response = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            
            # 解析JSON
            corrected = self._parse_json_response(response)
            if corrected:
                logger.info(
                    "params_corrected",
                    tool=tool_name,
                    original=original_params,
                    corrected=corrected
                )
                return corrected
                
        except Exception as e:
            logger.error("param_correction_failed", error=str(e))
        
        return None
    
    def _get_tool_schema(self, tool: Any) -> Optional[Dict]:
        """获取工具的参数schema"""
        if hasattr(tool, 'function_schema'):
            return tool.function_schema.get('parameters', {})
        return None

    def _extract_tool_data_for_llm(
        self,
        tool_results: List[Dict],
        max_records: int = 20
    ) -> List[Dict[str, Any]]:
        """
        提取工具原始数据供LLM分析（带截断保护）- 扁平化结构

        Args:
            tool_results: 工具执行结果列表
            max_records: 每个工具最大保留记录数（默认20）

        Returns:
            提取后的数据列表，每个元素包含工具名称、记录数、是否截断、数据内容
        """
        extracted = []
        heavy_tools = {
            "get_air_quality",
            "get_vocs_data",
            "get_particulate_data",
            "calculate_obm_full_chemistry",
            "calculate_pm_pmf",
            "calculate_vocs_pmf",
        }

        for r in tool_results:
            if r is None or not isinstance(r, dict):
                continue
            if r.get("status") != "success":
                continue

            tool_name = r.get("tool", "unknown")
            # 扁平化结构：data, metadata, visuals 在顶层
            result_data = r

            # 创建深拷贝，避免修改原始数据
            result_for_llm = copy.deepcopy(result_data)

            # 清理大体积的图片字段，只保留概要信息（操作的是副本）
            visuals_info = None
            if isinstance(result_for_llm, dict) and result_for_llm.get("visuals"):
                visuals = result_for_llm.get("visuals") or []
                visuals_info = [
                    {"id": v.get("id"), "type": v.get("type"), "title": v.get("title")}
                    for v in visuals
                    if isinstance(v, dict)
                ]
                result_for_llm = {k: v for k, v in result_for_llm.items() if k != "visuals"}
                result_for_llm["visuals_summary"] = visuals_info
                logger.info(
                    "tool_visuals_removed_for_llm",
                    tool=tool_name,
                    visuals_count=len(visuals_info)
                )

            # 重型工具直接省略原始数据，避免提示词爆炸
            if tool_name in heavy_tools:
                original_count = None
                data_field = result_for_llm.get("data")
                if isinstance(data_field, list):
                    original_count = len(data_field)
                extracted.append({
                    "tool": tool_name,
                    "record_count": original_count,
                    "truncated": True,
                    "truncated_to": 0,
                    "data": "omitted_for_llm_due_to_size",
                    "summary": result_for_llm.get("summary", ""),
                    "metadata": self._convert_datetime_to_string(result_for_llm.get("metadata", {})),
                    "visuals_summary": visuals_info,
                })
                logger.info(
                    "tool_data_omitted_for_llm",
                    tool=tool_name,
                    reason="heavy_tool",
                    record_count=original_count
                )
                continue

            if not isinstance(result_for_llm, dict):
                # 非字典结果，直接记录
                extracted.append({
                    "tool": tool_name,
                    "record_count": 1,
                    "truncated": False,
                    "data": self._convert_datetime_to_string(result_for_llm),
                    "summary": ""
                })
                continue

            # 提取核心数据
            data = result_for_llm.get("data", [])
            original_count = len(data) if isinstance(data, list) else 1
            truncated = False

            # 【关键修复】处理UnifiedDataRecord的measurements字段
            # 将measurements字段展开到顶层，便于LLM读取
            if isinstance(data, list) and data:
                first_record = data[0]
                logger.info(
                    "llm_data_extraction_check",
                    tool=tool_name,
                    record_count=len(data),
                    first_record_keys=list(first_record.keys())[:20] if isinstance(first_record, dict) else [],
                    has_measurements="measurements" in first_record if isinstance(first_record, dict) else False,
                    measurements_sample=first_record.get("measurements") if isinstance(first_record, dict) else None
                )

                if isinstance(first_record, dict) and "measurements" in first_record:
                    # 展开measurements字段
                    expanded_data = []
                    expanded_count = 0
                    for record in data:
                        if isinstance(record, dict) and "measurements" in record:
                            # 将measurements字段展开到顶层
                            expanded_record = {**record}
                            measurements = record.pop("measurements", {})
                            expanded_record.update(measurements)
                            expanded_data.append(expanded_record)
                            expanded_count += 1
                        else:
                            expanded_data.append(record)
                    data = expanded_data
                    logger.info(
                        "measurements_field_expanded",
                        tool=tool_name,
                        total_records=len(data),
                        expanded_records=expanded_count,
                        expanded_sample_keys=list(data[0].keys())[:20] if data else [],
                        has_PM2_5="PM2_5" in data[0] if data else False,
                        has_PM10="PM10" in data[0] if data else False
                    )

            if isinstance(data, list) and len(data) > max_records:
                # 截断策略：保留首尾各 10 条（总计 20 条）
                head_tail = max_records // 2  # 10
                data = data[:head_tail] + data[-head_tail:]
                truncated = True
                logger.info(
                    "tool_data_truncated_for_llm",
                    tool=tool_name,
                    original_count=original_count,
                    truncated_count=len(data),
                    max_records=max_records
                )

            extracted.append({
                "tool": tool_name,
                "record_count": original_count,
                "truncated": truncated,
                "truncated_to": len(data) if truncated else None,
                "data": self._convert_datetime_to_string(data),
                "summary": result_for_llm.get("summary", ""),
                "metadata": self._convert_datetime_to_string(result_for_llm.get("metadata", {}))
            })

        return extracted

    def _convert_datetime_to_string(self, obj):
        """
        递归地将对象中的datetime对象和numpy类型转换为JSON可序列化类型

        Args:
            obj: 要转换的对象（可能是dict、list或其他类型）

        Returns:
            转换后的对象，datetime对象和numpy类型已被转换
        """
        # 处理numpy类型（用于JSON序列化）
        # NumPy 2.0兼容：np.int_ 和 np.float_ 已被移除，使用 np.integer 和 np.floating
        try:
            import numpy as np
            if isinstance(obj, np.bool_):
                return bool(obj)
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass

        if isinstance(obj, dict):
            return {key: self._convert_datetime_to_string(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_datetime_to_string(item) for item in obj]
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, date):
            return obj.isoformat()
        else:
            return obj

    async def _generate_summary(
        self,
        task_description: str,
        summary_stats: Dict[str, Any],
        tool_results: List[Dict],
        task: Any = None  # 可选参数，子类可使用
    ) -> ExpertAnalysis:
        """
        生成专业总结

        Args:
            task_description: 任务描述
            summary_stats: 统计摘要
            tool_results: 工具执行结果（包含原始数据）
        """
        # 提取工具原始数据供LLM分析
        tool_data_for_llm = self._extract_tool_data_for_llm(tool_results, max_records=20)

        # 构建总结输入
        summary_input = {
            "task_purpose": task_description,
            "summary_stats": summary_stats,
            "tool_count": len(tool_results),
            "success_count": sum(1 for r in tool_results if r.get("status") == "success")
        }

        # 构建原始数据部分的提示词
        raw_data_section = ""
        if tool_data_for_llm:
            raw_data_section = f"""

【原始数据详情】
以下是各工具返回的原始数据，请基于这些数据进行专业分析：

{json.dumps(tool_data_for_llm, ensure_ascii=False, indent=2)}

注意：如果数据标记为 truncated=true，表示数据已截断（保留首尾各100条），原始记录数见 record_count。
"""

        prompt = f"""{self._get_summary_prompt()}

任务目标: {task_description}
执行统计: {json.dumps(summary_input, ensure_ascii=False)}
数据摘要: {json.dumps(summary_stats, ensure_ascii=False, indent=2)}
{raw_data_section}
请基于以上原始数据进行深入分析，识别关键时段、异常值、变化趋势等。

返回简洁的JSON格式:
{{
    "summary": "基于原始数据的专业总结（300-400字，包含具体数值和时间点）",
    "key_findings": ["发现1（含具体数据支撑）", "发现2（含具体数据支撑）", "发现3（含具体数据支撑）", "发现4", "发现5"],
    "data_quality": "good/fair/poor",
    "confidence": 0.85
}}

要求：
- summary字段：300-400字的专业总结，包含定量数据和机制解释
- key_findings：至少5条发现，前3条必须包含具体数据支撑
- 基于专业领域分析（气象/化学/可视化/综合）
- 只返回JSON，不要其他内容。"""

        # 如果提示词过长，省略原始数据段，只保留摘要
        if len(prompt) > 60000:
            raw_data_section = "\n【原始数据详情】数据量过大，已省略，仅基于统计摘要生成结论。\n"
            prompt = f"""{self._get_summary_prompt()}

任务目标: {task_description}
执行统计: {json.dumps(summary_input, ensure_ascii=False)}
数据摘要: {json.dumps(summary_stats, ensure_ascii=False, indent=2)}
{raw_data_section}
请基于以上摘要进行专业分析，并返回JSON。
"""

        # 记录提示词体积（字符数）便于排查上下文过长
        logger.info(
            "llm_summary_prompt_size",
            prompt_chars=len(prompt),
            raw_data_records=len(tool_data_for_llm),
            max_records_per_tool=20
        )

        try:
            response = await llm_service.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            parsed = self._parse_json_response(response)
            if parsed:
                return ExpertAnalysis(
                    summary=parsed.get("summary", ""),
                    key_findings=parsed.get("key_findings", []),
                    data_quality=parsed.get("data_quality", "unknown"),
                    confidence=parsed.get("confidence", 0.0)
                )

        except Exception as e:
            logger.error("summary_generation_failed", error=str(e))

        return ExpertAnalysis(
            summary="总结生成失败",
            data_quality="unknown",
            confidence=0.0
        )
    
    def _build_execution_summary(self, tool_results: List[Dict]) -> ExecutionSummary:
        """构建执行摘要"""
        
        succeeded = sum(1 for r in tool_results if r.get("status") == "success")
        failed = sum(1 for r in tool_results if r.get("status") == "error")
        retry_used = any(r.get("retry_used") for r in tool_results)
        
        errors = [
            {"tool": r.get("tool"), "error": r.get("error")}
            for r in tool_results
            if r.get("status") == "error"
        ]
        
        return ExecutionSummary(
            tools_executed=len(tool_results),
            tools_succeeded=succeeded,
            tools_failed=failed,
            retry_used=retry_used,
            errors=errors
        )
    
    def _extract_data_ids(self, tool_results: List[Dict]) -> List[str]:
        """提取所有成功工具的data_id（支持多种存储位置）- 扁平化结构"""

        data_ids = []
        for r in tool_results:
            # 跳过None结果
            if r is None:
                continue
            if not isinstance(r, dict):
                continue
            if r.get("status") == "success":
                # 扁平化结构：data_id, metadata 在顶层
                if r.get("data_id"):
                    data_ids.append(r["data_id"])
                else:
                    # 从顶层metadata获取（UDF v2.0格式）
                    metadata = r.get("metadata") or {}
                    if not isinstance(metadata, dict):
                        metadata = {}
                    if metadata.get("data_id"):
                        data_ids.append(metadata["data_id"])
                    # 从顶层metadata.source_data_ids获取（多data_id场景）
                    elif metadata.get("source_data_ids"):
                        data_ids.extend(metadata["source_data_ids"])

        return data_ids

    def _extract_skip_viz_data_ids(
        self,
        tool_results: List[Dict],
        tool_plans: List[ToolCallPlan]
    ) -> List[str]:
        """
        根据tool_plan中的skip_viz标记，提取对应的data_id列表

        Args:
            tool_results: 工具执行结果列表
            tool_plans: 工具调用计划列表

        Returns:
            需要跳过可视化的data_id列表
        """
        skip_viz_data_ids = []

        for idx, result in enumerate(tool_results):
            if result is None or not isinstance(result, dict):
                continue
            if result.get("status") != "success":
                continue

            # 获取对应的tool_plan
            if idx >= len(tool_plans):
                continue

            plan = tool_plans[idx]

            # 检查是否设置了skip_viz标记
            if not plan.skip_viz:
                continue

            # 提取data_id
            data_id = result.get("data_id")
            if data_id:
                skip_viz_data_ids.append(data_id)
                logger.debug(
                    "skip_viz_data_id_collected",
                    tool=plan.tool,
                    data_id=data_id,
                    purpose=plan.purpose[:50] if plan.purpose else ""
                )

        return skip_viz_data_ids
    
    def _determine_status(self, summary: ExecutionSummary) -> str:
        """确定执行状态"""
        
        if summary.tools_failed == 0:
            return "success"
        elif summary.tools_succeeded > 0:
            return "partial"
        else:
            return "failed"
    
    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """解析JSON响应"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # 尝试提取JSON代码块
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            if end > start:
                try:
                    return json.loads(response[start:end].strip())
                except json.JSONDecodeError:
                    pass

        # 尝试提取花括号内容
        start = response.find("{")
        end = response.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(response[start:end+1])
            except json.JSONDecodeError:
                pass

        return None

    async def _auto_generate_regional_comparison_visuals(
        self,
        tool_results: List[Dict],
        execution_context
    ) -> List[Dict]:
        """
        自动为区域对比数据生成可视化图表（后置处理）

        当检测到工具返回区域对比数据（包含chart_title）时，自动调用smart_chart_generator生成时序对比图

        Args:
            tool_results: 工具执行结果列表
            execution_context: ExecutionContext对象

        Returns:
            处理后的工具结果列表（包含自动生成的可视化结果）
        """
        from app.agent.context import ExecutionContext

        # 检查是否具备可视化工具
        smart_chart_tool = self.tools.get("smart_chart_generator")
        if not smart_chart_tool:
            logger.debug("smart_chart_generator not available, skipping auto-visualization")
            return tool_results

        if not isinstance(execution_context, ExecutionContext):
            logger.warning("execution_context not available, skipping auto-visualization")
            return tool_results

        # 用于收集需要生成可视化的情况
        visualizations_to_generate = []

        for i, result in enumerate(tool_results):
            if result is None or not isinstance(result, dict):
                continue
            if result.get("status") != "success":
                continue

            tool_name = result.get("tool", "")
            # 扁平化结构：data, metadata, visuals 在顶层
            result_data = result

            if not isinstance(result_data, dict):
                continue

            # 检查是否为区域对比数据（包含chart_title）
            metadata = result_data.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}

            chart_title = metadata.get("chart_title")
            data_id = result.get("data_id") or result_data.get("data_id")

            # 检测区域对比类型
            schema_type = metadata.get("schema_type", "")
            is_regional_data = (
                chart_title and
                data_id and
                ("regional" in schema_type.lower() or
                 "comparison" in schema_type.lower() or
                 "nearby" in schema_type.lower() or
                 "周边" in str(chart_title) or
                 "对比" in str(chart_title))
            )

            if is_regional_data and data_id:
                # 确定图表类型
                if "nearby_stations" in schema_type.lower() or "站点" in str(chart_title):
                    chart_type = "timeseries"
                elif "city" in schema_type.lower() or "城市" in str(chart_title):
                    chart_type = "timeseries"
                else:
                    chart_type = "timeseries"  # 默认时序图

                visualizations_to_generate.append({
                    "index": i,
                    "tool_name": tool_name,
                    "data_id": data_id,
                    "chart_title": chart_title,
                    "chart_type": chart_type,
                    "metadata": metadata,
                    "detected_schema_type": schema_type  # 记录检测到的schema类型
                })

                logger.info(
                    "regional_comparison_data_detected",
                    tool=tool_name,
                    data_id=data_id,
                    chart_title=chart_title
                )

        # 如果没有需要生成可视化的情况，直接返回
        if not visualizations_to_generate:
            return tool_results

        # 执行可视化生成
        for viz_request in visualizations_to_generate:
            try:
                viz_params = {
                    "data_id": viz_request["data_id"],
                    "chart_type": viz_request["chart_type"],
                    "title": viz_request["chart_title"],
                    "schema_type": viz_request["metadata"].get("schema_type", "regional_comparison"),
                    "show_legend": True,
                    "generate_report": False
                }

                logger.info(
                    "auto_generating_regional_comparison_visual",
                    tool=viz_request["tool_name"],
                    chart_type=viz_request["chart_type"],
                    title=viz_request["chart_title"]
                )

                # 调用智能图表生成工具
                viz_result = await smart_chart_tool(execution_context, **viz_params)

                # 将可视化结果添加到工具结果中
                if viz_result and isinstance(viz_result, dict):
                    viz_status = viz_result.get("status") or viz_result.get("success", False)
                    if viz_status:
                        # 合并可视化结果到原始结果（扁平化结构）
                        result = tool_results[viz_request["index"]]
                        result_data = result  # 直接使用顶层结果

                        # 合并visuals
                        original_visuals = result_data.get("visuals", [])
                        new_visuals = viz_result.get("visuals", [])
                        if isinstance(original_visuals, list) and isinstance(new_visuals, list):
                            result_data["visuals"] = original_visuals + new_visuals
                        elif isinstance(new_visuals, list):
                            result_data["visuals"] = new_visuals

                        # 更新metadata
                        result_metadata = result_data.get("metadata", {})
                        if isinstance(result_metadata, dict):
                            result_metadata["visualization_auto_generated"] = True
                            if "auto_generated_visuals" not in result_metadata:
                                result_metadata["auto_generated_visuals"] = []
                            result_metadata["auto_generated_visuals"].append({
                                "type": viz_request["chart_type"],
                                "title": viz_request["chart_title"],
                                "source_tool": viz_request["tool_name"]
                            })

                        logger.info(
                            "regional_comparison_visual_generated_success",
                            tool=viz_request["tool_name"],
                            charts_count=len(new_visuals) if isinstance(new_visuals, list) else 0
                        )
                    else:
                        logger.warning(
                            "regional_comparison_visual_generation_failed",
                            tool=viz_request["tool_name"],
                            error=viz_result.get("error", "Unknown error")
                        )
                else:
                    logger.warning(
                        "regional_comparison_visual_result_invalid",
                        tool=viz_request["tool_name"]
                    )

            except Exception as e:
                logger.error(
                    "regional_comparison_visual_generation_error",
                    tool=viz_request["tool_name"],
                    error=str(e)
                )

        return tool_results

    def _aggregate_visuals(self, tool_results: List[Dict]) -> List[Dict[str, Any]]:
        """
        从所有工具结果中聚合 visuals 字段，传递给前端展示

        Args:
            tool_results: 工具执行结果列表

        Returns:
            聚合后的 visuals 列表
        """
        aggregated_visuals = []
        seen_ids = set()  # 用于去重

        for idx, result in enumerate(tool_results):
            if result is None or not isinstance(result, dict):
                logger.debug(
                    "aggregate_visuals_skip_none",
                    idx=idx,
                    reason="result is None or not dict"
                )
                continue

            # 由于现在是扁平化结构（无嵌套result层），直接使用result作为数据
            result_data = result  # 直接使用顶层结果
            tool_name = result.get("tool_name", f"tool_{idx}")

            # 【关键调试日志】记录 result_data 的详细信息
            logger.info(
                "[DEBUG_AGGREGATE_VISUALS]",
                idx=idx,
                tool=tool_name,
                result_data_type=type(result_data).__name__,
                has_result_dict=isinstance(result_data, dict),
                has_visuals_key=isinstance(result_data, dict) and "visuals" in result_data
            )

            if not isinstance(result_data, dict):
                logger.info(
                    "[DEBUG_AGGREGATE_VISUALS] SKIP - result is not dict",
                    idx=idx,
                    tool=tool_name,
                    result_data_type=type(result_data).__name__,
                    result_data=repr(result_data)[:200]
                )
                continue

            # 从 result.visuals 中提取（现在visuals在顶层）
            visuals = result_data.get("visuals", [])

            # 【关键调试日志】记录 visuals 提取情况
            logger.info(
                "[DEBUG_AGGREGATE_VISUALS] Visuals提取结果",
                idx=idx,
                tool=tool_name,
                visuals_type=type(visuals).__name__,
                visuals_count=len(visuals) if isinstance(visuals, list) else None,
                visuals_keys=list(result_data.keys()) if isinstance(result_data, dict) else None
            )

            if not isinstance(visuals, list):
                logger.info(
                    "[DEBUG_AGGREGATE_VISUALS] SKIP - visuals is not list",
                    idx=idx,
                    tool=tool_name,
                    visuals_type=type(visuals).__name__
                )
                continue

            # 遍历 visuals 列表
            for visual_idx, visual in enumerate(visuals):
                if not isinstance(visual, dict):
                    logger.info(
                        "[DEBUG_AGGREGATE_VISUALS] SKIP - visual is not dict",
                        idx=idx,
                        tool=tool_name,
                        visual_idx=visual_idx,
                        visual_type=type(visual).__name__
                    )
                    continue

                visual_id = visual.get("id")
                has_data = bool(visual.get("data") or visual.get("payload", {}).get("data"))

                logger.info(
                    "[DEBUG_AGGREGATE_VISUALS] Visual详情",
                    idx=idx,
                    tool=tool_name,
                    visual_idx=visual_idx,
                    visual_id=visual_id,
                    visual_type=visual.get("type"),
                    has_data=has_data
                )

                # 去重
                if visual_id and visual_id in seen_ids:
                    logger.info(
                        "[DEBUG_AGGREGATE_VISUALS] SKIP - duplicate visual_id",
                        visual_id=visual_id
                    )
                    continue

                # 提取完整的 visual 配置
                # 优先使用 payload 中的数据（包含 base64 图片等完整信息）
                payload = visual.get("payload", {})

                aggregated_visual = {
                    "id": visual.get("id") or payload.get("id"),
                    "type": visual.get("type") or payload.get("type"),
                    "title": visual.get("title") or payload.get("title"),
                    "data": payload.get("data"),  # 优先使用 payload 中的 data（base64 图片）
                    "payload": payload,
                    "meta": visual.get("meta", {}),
                    "expert": tool_name,  # 记录来源工具
                }

                # 如果 payload 中没有 data，尝试从 visual 中获取
                if not aggregated_visual["data"] and visual.get("data"):
                    aggregated_visual["data"] = visual.get("data")

                # 【关键修复】保留有有效数据的 visual（包括交互式图表的 config 字典）
                # 条件：有 id 且有 data（data 可以是 base64 字符串或 ECharts 配置字典）
                if aggregated_visual["id"] and aggregated_visual["data"] is not None:
                    if visual_id:
                        seen_ids.add(visual_id)
                    aggregated_visuals.append(aggregated_visual)
                    logger.info(
                        "[DEBUG_AGGREGATE_VISUALS] ADDED visual",
                        visual_id=aggregated_visual["id"],
                        visual_type=aggregated_visual["type"],
                        data_type=type(aggregated_visual.get("data")).__name__,
                        data_length=len(str(aggregated_visual.get("data", ""))) if isinstance(aggregated_visual.get("data"), str) else "dict"
                    )

        logger.info(
            "visuals_aggregated",
            total=len(aggregated_visuals),
            from_tools=len(tool_results)
        )

        return aggregated_visuals
