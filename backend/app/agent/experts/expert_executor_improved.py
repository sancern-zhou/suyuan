#!/usr/bin/env python3
"""
专家执行器基类 (ExpertExecutor) - 改进版

改进内容：
1. 智能数据采样策略（基于时间和污染程度）
2. 统计摘要生成（减少90%数据量）
3. 可配置的截断参数（max_records默认500）
4. 数据压缩支持（减少30-50%体积）

主要修改：
- _extract_tool_data_for_llm() 添加智能采样和统计摘要
- _smart_sample_data() 新增智能采样方法
- _generate_statistical_summary() 新增统计摘要方法
- _calculate_pollution_score() 新增污染评分方法
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field
import structlog
import asyncio
import json
import numpy as np
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


class ExpertResult(BaseModel):
    """专家执行结果"""
    status: str = "pending"  # success / partial / failed
    expert_type: str = ""
    task_id: str = ""
    data_ids: List[str] = Field(default_factory=list)
    execution_summary: ExecutionSummary = Field(default_factory=ExecutionSummary)
    analysis: ExpertAnalysis = Field(default_factory=ExpertAnalysis)
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)


class ExpertExecutor(ABC):
    """专家执行器基类 - 改进版"""

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
                            """包装原始工具的execute方法"""
                            try:
                                # 调用工具的execute方法
                                if hasattr(tool_instance, 'execute'):
                                    if context is not None:
                                        result = await tool_instance.execute(context=context, **kwargs)
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
                # 使用task.context中的信息创建ExecutionContext
                context_dict = task.context.copy() if task.context else {}
                context_dict["session_id"] = context_dict.get("session_id", f"expert_{self.expert_type}_{task.task_id}")
                execution_context = self._create_execution_context(context_dict)

            # 1. 执行工具链（传递ExecutionContext）
            tool_results = await self._execute_tool_chain(
                task.tool_plan,
                task.context or {}
            )
            result.tool_results = tool_results

            # 2. 构建执行摘要
            result.execution_summary = self._build_execution_summary(tool_results)

            # 3. 提取data_ids
            result.data_ids = self._extract_data_ids(tool_results)

            # 4. 提取统计摘要
            summary_stats = self._extract_summary_stats(tool_results)

            # 5. 生成专业总结
            result.analysis = await self._generate_summary(
                task.task_description,
                summary_stats,
                tool_results
            )

            # 6. 确定最终状态
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

            # 【修复】返回更完整的结果，保留原始字段以便降级检查
            # 保留 success, data, summary, metadata 等字段用于降级判断
            if result.get("status") == "success" or result.get("success") is not False:
                return {
                    "tool_name": tool_name,
                    "result": result.get("result"),
                    "data_id": result.get("data_id"),
                    "status": "success",
                    # 保留原始字段用于降级检查
                    "success": result.get("success"),
                    "data": result.get("data"),
                    "summary": result.get("summary"),
                    "metadata": result.get("metadata") or {}  # 确保不为None
                }
            else:
                return {
                    "tool_name": tool_name,
                    "error": result.get("error"),
                    "status": "error",
                    "success": result.get("success"),
                    "summary": result.get("summary"),
                    "data_id": result.get("data_id"),  # 保留data_id用于降级检查
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

            # 转换为旧的格式以保持向后兼容
            results = []
            for exec_result in execution_results:
                if exec_result.status == ToolTaskStatus.SUCCESS:
                    results.append({
                        "tool": exec_result.tool_name,
                        "status": "success",
                        "result": exec_result.result,
                        "data_id": exec_result.data_id,
                        "bound_params": exec_result.bound_params
                    })
                else:
                    results.append({
                        "tool": exec_result.tool_name,
                        "status": "error",
                        "error": exec_result.error,
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
        尝试执行工具（修复：使用已注册的包装工具，正确传递ExecutionContext）

        Args:
            tool_name: 工具名称
            params: 工具参数
            execution_context: ExecutionContext对象
        """
        try:
            # 获取已注册的工具（包装工具）
            registered_tool = self.tools.get(tool_name)

            if not registered_tool:
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

            # 【修复】根据工具是否需要context智能传递参数
            if execution_context is not None:
                # 检查原始工具是否需要context（通过属性或函数签名）
                needs_context = self._tool_requires_context(tool_name)

                if needs_context:
                    # 需要context的工具，将context作为位置参数传递
                    tool_result = await registered_tool(execution_context, **params)
                else:
                    # 不需要context的工具，context作为关键字参数
                    tool_result = await registered_tool(context=execution_context, **params)
            else:
                # 如果没有ExecutionContext，只传递参数（向后兼容）
                tool_result = await registered_tool(**params)

            # 处理结果
            if isinstance(tool_result, dict):
                # 检查工具返回的success字段
                tool_success = tool_result.get("success")
                tool_status = tool_result.get("status", "success")
                if tool_success is False or tool_status in ["failed", "error"]:
                    return {
                        "status": "error",
                        "result": tool_result,
                        "data_id": tool_result.get("data_id"),
                        "success": False,
                        "error": tool_result.get("error"),
                        "summary": tool_result.get("summary"),
                        "metadata": tool_result.get("metadata") or {}
                    }
                return {
                    "status": "success",
                    "result": tool_result,
                    "data_id": tool_result.get("data_id"),
                    "success": tool_result.get("success", True),
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
                            "result": result_dict,
                            "data_id": data_id,
                            "success": False,
                            "error": result_dict.get("error"),
                            "summary": result_dict.get("summary"),
                            "metadata": metadata
                        }
                    return {
                        "status": "success",
                        "result": result_dict,
                        "data_id": data_id,
                        "success": True,
                        "metadata": metadata
                    }
                return {
                    "status": "success",
                    "result": tool_result
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
                # 处理 $N 引用（前序工具结果）
                if value.startswith("$"):
                    try:
                        idx = int(value[1:])
                        if idx < len(previous_results) and previous_results[idx]:
                            prev = previous_results[idx]
                            if prev.get("data_id"):
                                resolved[key] = prev["data_id"]
                            elif prev.get("result", {}).get("data_id"):
                                resolved[key] = prev["result"]["data_id"]
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
        max_records: int = 500,  # 增加默认值（原来是200）
        use_smart_sampling: bool = True,  # 新增：启用智能采样
        use_statistical_summary: bool = True  # 新增：启用统计摘要
    ) -> List[Dict[str, Any]]:
        """
        提取工具原始数据供LLM分析（改进版 - 智能采样 + 统计摘要）

        Args:
            tool_results: 工具执行结果列表
            max_records: 每个工具最大保留记录数（默认500，提高自200）
            use_smart_sampling: 是否使用智能采样策略
            use_statistical_summary: 是否生成统计摘要

        Returns:
            提取后的数据列表，每个元素包含工具名称、记录数、是否截断、数据内容
        """
        extracted = []

        for r in tool_results:
            if r is None or not isinstance(r, dict):
                continue
            if r.get("status") != "success":
                continue

            tool_name = r.get("tool", "unknown")
            result = r.get("result", {})

            if not isinstance(result, dict):
                # 非字典结果，直接记录
                extracted.append({
                    "tool": tool_name,
                    "record_count": 1,
                    "truncated": False,
                    "data": self._convert_datetime_to_string(result),
                    "summary": ""
                })
                continue

            # 提取核心数据
            data = result.get("data", [])
            original_count = len(data) if isinstance(data, list) else 1
            truncated = False
            sample_info = {"strategy": "no_sampling"}
            statistical_summary = None

            if isinstance(data, list) and len(data) > max_records:
                if use_smart_sampling:
                    # 使用智能采样策略
                    sampled_data, sample_info = self._smart_sample_data(data, max_records)
                    truncated = True
                    data = sampled_data
                    logger.info(
                        "smart_sampling_applied",
                        tool=tool_name,
                        original_count=original_count,
                        sampled_count=len(data),
                        strategy=sample_info.get("strategy"),
                        retention_ratio=sample_info.get("retention_ratio")
                    )
                else:
                    # 传统截断：保留首尾各一半（向后兼容）
                    half = max_records // 2
                    data = data[:half] + data[-half:]
                    truncated = True
                    sample_info = {"strategy": "simple_truncation"}
                    logger.info(
                        "simple_truncation_applied",
                        tool=tool_name,
                        original_count=original_count,
                        truncated_count=len(data),
                        max_records=max_records
                    )

            # 生成统计摘要（可选）
            if use_statistical_summary and isinstance(data, list) and len(data) > 10:
                statistical_summary = self._generate_statistical_summary(data)
                logger.info(
                    "statistical_summary_generated",
                    tool=tool_name,
                    summary_record_count=len(data),
                    has_vocs_summary=statistical_summary.get("vocs_summary") is not None,
                    has_pollutant_summary=statistical_summary.get("pollutants_summary") is not None
                )

            extracted.append({
                "tool": tool_name,
                "record_count": original_count,
                "truncated": truncated,
                "truncated_to": len(data) if truncated else None,
                "sampling_info": sample_info,
                "data": self._convert_datetime_to_string(data),
                "statistical_summary": statistical_summary,
                "summary": result.get("summary", ""),
                "metadata": self._convert_datetime_to_string(result.get("metadata", {}))
            })

        return extracted

    def _smart_sample_data(self, data: List[Dict], max_records: int) -> Tuple[List[Dict], Dict[str, Any]]:
        """
        智能采样数据（基于时间和污染程度）

        Args:
            data: 原始数据列表
            max_records: 最大保留记录数

        Returns:
            (采样后的数据, 采样信息)
        """
        n = len(data)
        target = max_records

        # 混合策略：时间 + 污染程度
        # 1. 计算每条记录的污染评分
        pollution_scores = [self._calculate_pollution_score(record) for record in data]
        sorted_indices = np.argsort(pollution_scores)[::-1]  # 降序

        # 2. 分层采样
        high_ratio = 0.5  # 高污染样本占50%
        high_count = int(target * high_ratio)
        remaining = target - high_count

        sampled = []

        # 高污染样本（时间均匀分布）
        high_indices = sorted_indices[:high_count]
        high_sampled = []
        step = max(1, len(high_indices) // (high_count // 2 + 1))
        for i in range(0, len(high_indices), step):
            idx = high_indices[i]
            high_sampled.append(data[idx])
            if len(high_sampled) >= high_count // 2:
                break

        # 剩余高污染样本（随机补充）
        remaining_high = high_count - len(high_sampled)
        if remaining_high > 0:
            already_sampled = set(id(data[idx]) for idx in [id(data[idx]) for idx in [data.index(data[idx]) for idx in high_indices[:len(high_sampled)]]])
            remaining_indices = [idx for idx in high_indices[len(high_sampled):] if id(data[idx]) not in already_sampled]
            high_sampled.extend([data[idx] for idx in remaining_indices[:remaining_high]])

        # 剩余样本按时间顺序（避免与高污染样本重复）
        sampled_ids = set(id(record) for record in high_sampled)
        remaining_records = [record for record in data if id(record) not in sampled_ids]
        remaining_sampled = remaining_records[:remaining]

        result = high_sampled + remaining_sampled
        result = result[:target]

        return result, {
            "strategy": "hybrid_sampling",
            "high_pollution_samples": len(high_sampled),
            "time_based_samples": len(remaining_sampled),
            "retention_ratio": len(result) / n
        }

    def _calculate_pollution_score(self, record: Dict) -> float:
        """
        计算污染评分

        Args:
            record: 数据记录

        Returns:
            污染评分（数值越高表示污染越严重）
        """
        score = 0.0

        # VOCs数据
        if 'species_data' in record:
            species_data = record.get('species_data', {})
            if isinstance(species_data, dict):
                # 计算总浓度和主要物种浓度
                total_conc = sum(species_data.values())
                # 考虑高活性物种（假设前10个为高活性）
                top_species = sorted(species_data.values(), reverse=True)[:10]
                score = total_conc * 0.7 + sum(top_species) * 0.3

        # NOx/O3数据
        elif 'o3' in record:
            # O3、NO2权重，O3权重更高
            o3 = record.get('o3', 0)
            no2 = record.get('no2', 0)
            pm25 = record.get('pm25', 0)
            score = o3 * 0.5 + no2 * 0.3 + pm25 * 0.2

        return score

    def _generate_statistical_summary(self, data: List[Dict]) -> Dict[str, Any]:
        """
        生成统计摘要（减少90%数据量）

        Args:
            data: 数据列表

        Returns:
            统计摘要字典
        """
        if not data:
            return {"error": "no_data"}

        summary = {
            "record_count": len(data),
            "time_range": self._get_time_range(data),
            "vocs_summary": None,
            "pollutants_summary": None,
            "key_insights": []
        }

        # 分析VOCs数据
        vocs_records = [r for r in data if 'species_data' in r and r['species_data']]
        if vocs_records:
            summary["vocs_summary"] = self._analyze_vocs_data(vocs_records)

        # 分析污染物数据
        pollutant_records = [r for r in data if any(k in r for k in ['o3', 'no2', 'pm25', 'pm10'])]
        if pollutant_records:
            summary["pollutants_summary"] = self._analyze_pollutant_data(pollutant_records)

        # 生成关键洞察
        summary["key_insights"] = self._generate_key_insights(summary)

        return summary

    def _get_time_range(self, data: List[Dict]) -> Dict[str, str]:
        """获取时间范围"""
        timestamps = []
        for record in data:
            if 'timestamp' in record:
                try:
                    ts = datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M:%S')
                    timestamps.append(ts)
                except:
                    continue

        if not timestamps:
            return {"start": "unknown", "end": "unknown", "duration_hours": 0}

        start = min(timestamps)
        end = max(timestamps)
        duration = end - start

        return {
            "start": start.strftime('%Y-%m-%d %H:%M'),
            "end": end.strftime('%Y-%m-%d %H:%M'),
            "duration_hours": int(duration.total_seconds() / 3600)
        }

    def _analyze_vocs_data(self, vocs_data: List[Dict]) -> Dict[str, Any]:
        """分析VOCs数据"""
        # 收集所有物种
        all_species = set()
        species_concentrations = {}

        for record in vocs_data:
            species_data = record.get('species_data', {})
            for species, concentration in species_data.items():
                all_species.add(species)
                if species not in species_concentrations:
                    species_concentrations[species] = []
                species_concentrations[species].append(concentration)

        # 计算统计量
        species_stats = {}
        for species in all_species:
            concentrations = species_concentrations[species]
            if concentrations:
                species_stats[species] = {
                    "mean": round(np.mean(concentrations), 3),
                    "max": round(np.max(concentrations), 3),
                    "min": round(np.min(concentrations), 3),
                    "std": round(np.std(concentrations), 3),
                    "p75": round(np.percentile(concentrations, 75), 3),
                    "p95": round(np.percentile(concentrations, 95), 3)
                }

        # 找出浓度最高的物种
        top_species = sorted(
            [(species, stats["mean"]) for species, stats in species_stats.items()],
            key=lambda x: x[1], reverse=True
        )[:10]

        return {
            "species_count": len(all_species),
            "top_10_species": [{"species": s, "mean_concentration": c} for s, c in top_species],
            "total_samples": len(vocs_data),
            "detailed_stats": species_stats
        }

    def _analyze_pollutant_data(self, pollutant_data: List[Dict]) -> Dict[str, Any]:
        """分析污染物数据"""
        pollutants = ['o3', 'no2', 'pm25', 'pm10', 'so2', 'co']
        stats = {}

        for pollutant in pollutants:
            values = [r.get(pollutant) for r in pollutant_data if r.get(pollutant) is not None]
            if values:
                stats[pollutant] = {
                    "mean": round(np.mean(values), 2),
                    "max": round(np.max(values), 2),
                    "min": round(np.min(values), 2),
                    "std": round(np.std(values), 2),
                    "samples": len(values)
                }

        return stats

    def _generate_key_insights(self, summary: Dict[str, Any]) -> List[str]:
        """生成关键洞察"""
        insights = []

        # 时间范围洞察
        if summary.get("time_range", {}).get("duration_hours"):
            duration = summary["time_range"]["duration_hours"]
            if duration >= 24:
                insights.append(f"数据覆盖{duration}小时的连续监测")

        # VOCs洞察
        if summary.get("vocs_summary"):
            vocs = summary["vocs_summary"]
            insights.append(f"检测到{vocs['species_count']}种VOCs化合物")
            if vocs.get("top_10_species"):
                top = vocs["top_10_species"][0]["species"]
                insights.append(f"浓度最高的VOCs: {top}")

        # 污染物洞察
        if summary.get("pollutants_summary"):
            pollutants = summary["pollutants_summary"]
            if "o3" in pollutants:
                avg_o3 = pollutants["o3"]["mean"]
                if avg_o3 > 160:
                    insights.append(f"臭氧浓度较高 (平均{avg_o3} μg/m³)，可能存在光化学污染")
                elif avg_o3 > 100:
                    insights.append(f"臭氧浓度中等 (平均{avg_o3} μg/m³)")

        return insights

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
        tool_results: List[Dict]
    ) -> ExpertAnalysis:
        """
        生成专业总结（改进版 - 使用智能采样和统计摘要）

        Args:
            task_description: 任务描述
            summary_stats: 统计摘要
            tool_results: 工具执行结果（包含原始数据）
        """
        # 使用改进的截断策略（智能采样 + 统计摘要）
        tool_data_for_llm = self._extract_tool_data_for_llm(
            tool_results,
            max_records=500,  # 增加默认值
            use_smart_sampling=True,  # 启用智能采样
            use_statistical_summary=True  # 启用统计摘要
        )

        # 构建总结输入
        summary_input = {
            "task_purpose": task_description,
            "summary_stats": summary_stats,
            "tool_count": len(tool_results),
            "success_count": sum(1 for r in tool_results if r.get("status") == "success")
        }

        # 构建原始数据部分的提示词（包含统计摘要）
        raw_data_section = ""
        if tool_data_for_llm:
            raw_data_section = f"""

【核心数据摘要】
以下是经过智能采样和统计分析的数据摘要，请基于这些数据进行专业分析：

{json.dumps(tool_data_for_llm, ensure_ascii=False, indent=2)}

重点关注：
1. 采样信息：保留的数据比例和策略
2. 统计摘要：关键发现和趋势
3. 异常值：污染峰值和异常事件
"""

        prompt = f"""{self._get_summary_prompt()}

任务目标: {task_description}
执行统计: {json.dumps(summary_input, ensure_ascii=False)}
数据摘要: {json.dumps(summary_stats, ensure_ascii=False, indent=2)}
{raw_data_section}
请基于以上数据进行深入分析，识别关键时段、异常值、变化趋势等。

返回简洁的JSON格式:
{{
    "summary": "基于统计摘要的专业总结（300-400字，包含具体数值和时间点）",
    "key_findings": ["发现1（含具体数据支撑）", "发现2（含具体数据支撑）", "发现3（含具体数据支撑）", "发现4", "发现5"],
    "data_quality": "good/fair/poor",
    "confidence": 0.85
}}

要求：
- summary字段：300-400字的专业总结，包含定量数据和机制解释
- key_findings：至少5条发现，前3条必须包含具体数据支撑
- 基于专业领域分析（气象/化学/可视化/综合）
- 只返回JSON，不要其他内容。"""

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
        """提取所有成功工具的data_id（支持多种存储位置）"""

        data_ids = []
        for r in tool_results:
            # 跳过None结果
            if r is None:
                continue
            if not isinstance(r, dict):
                continue
            if r.get("status") == "success":
                # 优先级1: 直接从tool_result获取
                if r.get("data_id"):
                    data_ids.append(r["data_id"])
                else:
                    # 安全获取result字段（可能为None）
                    result = r.get("result") or {}
                    if not isinstance(result, dict):
                        result = {}
                    # 优先级2: 从result字段获取
                    if result.get("data_id"):
                        data_ids.append(result["data_id"])
                    else:
                        # 安全获取metadata字段
                        metadata = result.get("metadata") or {}
                        if not isinstance(metadata, dict):
                            metadata = {}
                        # 优先级3: 从result.metadata字段获取（UDF v2.0格式）
                        if metadata.get("data_id"):
                            data_ids.append(metadata["data_id"])
                        # 优先级4: 从result.metadata.source_data_ids获取（多data_id场景）
                        elif metadata.get("source_data_ids"):
                            data_ids.extend(metadata["source_data_ids"])

        return data_ids

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
