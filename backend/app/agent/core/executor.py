"""
Tool Executor for ReAct Agent

工具执行器，负责执行 LLM 决定的工具调用。

核心职责：
1. 验证工具调用请求
2. 执行工具
3. 处理错误和异常
4. 返回标准化的观察结果

V2 Updates:
- Supports ExecutionContext injection for context-aware tools
- Creates DataContextManager for data reference management
- Backward compatible with legacy tools

V3 Updates (并行执行):
- 支持并行执行多个独立工具调用 (execute_tools_parallel)
"""

from typing import Dict, Any, Optional, Callable, List, TYPE_CHECKING, Union
import structlog
import traceback
import asyncio

if TYPE_CHECKING:
    from app.agent.memory.hybrid_manager import HybridMemoryManager
    from app.agent.context.data_context_manager import DataContextManager
    from app.agent.context.execution_context import ExecutionContext

logger = structlog.get_logger()


class ToolExecutor:
    """
    工具执行器 - ReAct Agent 的执行层（V2 with ExecutionContext）

    负责：
    - 验证工具调用的合法性
    - 创建并注入 ExecutionContext（对于需要的工具）
    - 执行工具并捕获结果
    - 标准化错误处理
    - 返回观察结果（Observation）
    """

    def __init__(
        self,
        tool_registry: Optional[Dict[str, Callable]] = None,
        memory_manager: Optional["HybridMemoryManager"] = None,
        task_list: Optional[Any] = None,
        llm_planner: Optional[Any] = None  # ✅ 新增：用于call_sub_agent
    ):
        """
        初始化工具执行器

        Args:
            tool_registry: 工具注册表
                格式: {"tool_name": callable_function}
            memory_manager: 混合内存管理器（用于创建 DataContextManager）
            task_list: 任务列表实例（用于任务管理工具）
            llm_planner: LLM规划器（用于call_sub_agent创建子Agent）
        """
        self.tool_registry = tool_registry or {}
        self.memory_manager = memory_manager
        self.data_context_manager: Optional["DataContextManager"] = None
        self.task_list = task_list
        self.llm_planner = llm_planner  # ✅ 存储llm_planner

        # Initialize DataContextManager if memory_manager provided
        if memory_manager:
            from app.agent.context.data_context_manager import DataContextManager
            self.data_context_manager = DataContextManager(memory_manager)
            logger.info(
                "data_context_manager_initialized",
                session_id=memory_manager.session_id
            )

        # 只在未提供 tool_registry 时才注册内置工具
        if not tool_registry:
            self._register_builtin_tools()
        else:
            # 注册特殊工具（FINISH_SUMMARY）
            self._register_special_tools()

        logger.info(
            "tool_executor_initialized",
            tool_count=len(self.tool_registry),
            has_context_manager=self.data_context_manager is not None
        )

    def refresh_tools(self):
        """
        刷新工具注册表（从 global_tool_registry 重新加载所有工具）

        使用场景：
        - 动态添加/删除工具后需要刷新 Agent 实例
        - 工具注册表更新后需要重新加载
        """
        logger.info("refreshing_tool_registry")

        # 清空当前注册表
        self.tool_registry.clear()

        # 重新注册所有工具
        self._register_builtin_tools()

        logger.info(
            "tool_registry_refreshed",
            tool_count=len(self.tool_registry),
            tools=list(self.tool_registry.keys())
        )

    def _register_builtin_tools(self):
        """注册内置工具"""
        try:
            # 导入工具适配器
            from app.agent.tool_adapter import get_react_agent_tool_registry

            # 获取所有适配后的工具
            real_tools = get_react_agent_tool_registry()

            # 注册到本地注册表
            for tool_name, tool_func in real_tools.items():
                self.tool_registry[tool_name] = tool_func

            # 🔍 调试日志：输出已注册的工具
            registered_tools = list(real_tools.keys())
            logger.info(
                "builtin_tools_registered",
                tools=registered_tools,
                count=len(real_tools),
                has_unpack_office="unpack_office" in registered_tools
            )

            # 注册特殊工具：FINISH_SUMMARY 和 FINISH
            self._register_special_tools()

        except ImportError as e:
            logger.warning(
                "failed_to_import_real_tools",
                error=str(e),
                message="Using empty tool registry"
            )
        except Exception as e:
            logger.error(
                "failed_to_register_builtin_tools",
                error=str(e),
                exc_info=True
            )

    def _register_special_tools(self):
        """注册特殊工具（仅 FINISH_SUMMARY）"""

        async def finish_summary_tool(context=None, data_id: Optional[Union[str, List[str]]] = None) -> Dict[str, Any]:
            """
            FINISH_SUMMARY 特殊工具

            功能：生成数据分析报告（基于指定的 data_id 加载数据）

            Args:
                context: 执行上下文（系统自动注入）
                data_id: 数据ID或数据ID列表（用于加载要分析的数据）

            Returns:
                包含 action_type 和 data_id 的结果
            """
            # 接收 data_id 参数并返回给 loop.py 处理
            # 实际的数据加载和报告生成在 loop.py 中完成
            return {
                "success": True,
                "action_type": "FINISH_SUMMARY",
                "data_id": data_id,
                "summary": "FINISH_SUMMARY: 系统将基于指定数据生成详细分析报告"
            }

        # 注册特殊工具
        self.tool_registry["FINISH_SUMMARY"] = finish_summary_tool

        logger.info(
            "special_tools_registered",
            tools=["FINISH_SUMMARY"]
        )

    def register_tool(self, name: str, func: Callable):
        """
        注册新工具

        Args:
            name: 工具名称
            func: 工具函数（必须是 async 函数）
        """
        if name in self.tool_registry:
            logger.warning(
                "tool_overwrite",
                tool_name=name
            )

        self.tool_registry[name] = func

        logger.info(
            "tool_registered",
            tool_name=name,
            total_tools=len(self.tool_registry)
        )

    def set_memory_manager(self, memory_manager: "HybridMemoryManager", task_list: Optional[Any] = None):
        """
        动态设置 memory_manager 并初始化 DataContextManager

        用于在 ToolExecutor 创建后更新 memory_manager (例如在 analyze() 中)

        Args:
            memory_manager: 混合内存管理器
            task_list: 任务列表实例（可选）
        """
        self.memory_manager = memory_manager

        # 初始化 DataContextManager
        if memory_manager and not self.data_context_manager:
            from app.agent.context.data_context_manager import DataContextManager
            self.data_context_manager = DataContextManager(memory_manager)
            logger.info(
                "data_context_manager_initialized_in_set_memory_manager",
                session_id=memory_manager.session_id
            )

        # 更新 task_list（如果提供）
        if task_list is not None:
            self.task_list = task_list
            logger.debug(
                "task_list_updated_in_executor",
                has_task_list=True
            )

        # Initialize DataContextManager
        from app.agent.context.data_context_manager import DataContextManager
        self.data_context_manager = DataContextManager(memory_manager)

        logger.info(
            "memory_manager_updated",
            session_id=memory_manager.session_id,
            has_context_manager=True
        )

    async def execute_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        iteration: int = 0
    ) -> Dict[str, Any]:
        """
        执行工具调用（V2 with ExecutionContext support）

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            iteration: 当前迭代次数（用于 ExecutionContext）

        Returns:
            观察结果：
            {
                "success": bool,
                "data": Any (if success),
                "data_id": str (if using context),
                "error": str (if failed),
                "summary": str
            }
        """
        # 防护：确保 tool_args 不是 None
        if tool_args is None:
            tool_args = {}

        logger.info(
            "executing_tool_v2",
            tool_name=tool_name,
            args_keys=list(tool_args.keys()) if isinstance(tool_args, dict) else [],
            iteration=iteration,
            has_context_manager=self.data_context_manager is not None
        )

        # Step 0: 准备Input Adapter和 Execution Context
        execution_context = self._create_execution_context(iteration)
        adapter_context = self._create_adapter_context(execution_context)

        # Step 1: 验证工具存在
        if tool_name not in self.tool_registry:
            # 🔍 调试日志：工具不存在时详细输出注册表状态
            available_tools = list(self.tool_registry.keys())
            logger.error(
                "tool_not_found",
                tool_name=tool_name,
                available_tools=available_tools,
                has_unpack_office="unpack_office" in available_tools,
                registry_size=len(self.tool_registry)
            )

            return {
                "success": False,
                "error": f"工具不存在: {tool_name}",
                "summary": f"❌ 工具 {tool_name} 未注册",
                "available_tools": available_tools
            }

        # ✅ Step 2: Input Adapter 规范化（Phase 2.2 新增）
        try:
            from app.agent.input_adapter import InputAdapterEngine, InputValidationError

            adapter = InputAdapterEngine()
            normalized_args, adapter_report = adapter.normalize(
                tool_name=tool_name,
                raw_args=tool_args,
                context=adapter_context  # TODO: 未来可以传入更多上下文
            )

            logger.info(
                "input_adapter_success",
                tool_name=tool_name,
                corrections=len(adapter_report.get("corrections", [])),
                inferences=len(adapter_report.get("inferences", []))
            )

            # 使用规范化后的参数替换原始参数
            tool_args = normalized_args

        except InputValidationError as e:
            # ✅ 返回结构化错误（供 Reflexion 使用）
            logger.error(
                "input_validation_failed",
                tool_name=tool_name,
                error=str(e),
                missing_fields=e.missing_fields
            )

            return {
                "success": False,
                "error_type": "INPUT_VALIDATION_FAILED",
                "error": str(e),
                "tool_name": tool_name,
                "missing_fields": e.missing_fields,
                "invalid_fields": e.invalid_fields,
                "expected_schema": e.expected_schema,
                "suggested_call": e.suggested_call,
                "summary": f"❌ 工具 {tool_name} 参数验证失败: {', '.join(e.missing_fields)}"
            }

        except Exception as e:
            # 其他适配错误，记录但不中断流程
            logger.warning(
                "input_adapter_error",
                tool_name=tool_name,
                error=str(e),
                message="Continuing with raw args"
            )
            # 继续使用原始参数

        # Step 3: 执行工具
        try:
            tool_func = self.tool_registry[tool_name]

            # ========================================
            # 详细调试信息：显示工具调用前
            # ========================================
            logger.info("="*80)
            logger.info("[TOOL_CALL] 即将执行工具调用")
            logger.info("="*80)
            logger.info(f"Tool Name: {tool_name}")
            logger.info(f"Has Context: {execution_context is not None}")
            logger.info("-"*80)
            logger.info("Tool Args:")
            import json
            logger.info(json.dumps(tool_args, ensure_ascii=False, indent=2))
            logger.info("="*80)
            # ========================================

            # Inject context if available (tool will ignore if not needed)
            if execution_context:
                result = await tool_func(context=execution_context, **tool_args)
            else:
                result = await tool_func(**tool_args)

            # Step 4: 标准化返回结果
            observation = self._normalize_result(tool_name, result)

            # ========================================
            # 详细调试信息：显示工具调用后
            # ========================================
            logger.info("="*80)
            logger.info("[TOOL_RESULT] 工具执行完成")
            logger.info("="*80)
            logger.info(f"Tool Name: {tool_name}")
            logger.info(f"Success: {observation.get('success', 'N/A')}")
            logger.info("-"*80)
            logger.info("Tool Result:")
            try:
                # 尝试序列化结果，如果包含datetime对象会报错
                logger.info(json.dumps(observation, ensure_ascii=False, indent=2, default=str))
            except Exception as e:
                # 如果序列化失败，用字符串表示
                logger.info(f"[无法JSON序列化: {str(e)}]")
                logger.info(f"Result Type: {type(observation)}")
                logger.info(f"Result: {observation}")
            logger.info("="*80)
            # ========================================

            logger.info(
                "tool_execution_success",
                tool_name=tool_name,
                has_data="data" in observation,
                has_data_id="data_id" in observation
            )

            return observation

        except TypeError as e:
            # 参数错误 (可能是缺少context或参数不匹配)
            error_msg = str(e)
            logger.error(
                "tool_argument_error",
                tool_name=tool_name,
                error=error_msg,
                exc_info=True
            )

            # 构建错误结果
            error_result = {
                "success": False,
                "error": f"参数错误: {error_msg}",
                "summary": f"❌ 工具 {tool_name} 参数不匹配",
                "provided_args": list(tool_args.keys())
            }

            return error_result

        except Exception as e:
            # 工具执行错误
            logger.error(
                "tool_execution_failed",
                tool_name=tool_name,
                error=str(e),
                traceback=traceback.format_exc()
            )

            return {
                "success": False,
                "error": str(e),
                "summary": f"❌ 工具 {tool_name} 执行失败: {str(e)[:100]}",
                "traceback": traceback.format_exc()
            }

    def _normalize_result(
        self,
        tool_name: str,
        result: Any
    ) -> Dict[str, Any]:
        """
        标准化工具返回结果（含智能采样）

        Args:
            tool_name: 工具名称
            result: 工具返回的原始结果

        Returns:
            标准化的观察结果（data字段已采样）
        """
        # 如果工具已经返回标准格式
        if isinstance(result, dict) and "success" in result:
            # ✅ 增强：为失败的参数错误添加详细提示
            if not result.get("success", True):
                result = self._enhance_error_with_hint(tool_name, result)

            # ✅ 数据查询工具记录数限制：智能采样（Head-Tail-Middle策略）
            # 对数据查询工具的data字段进行采样，避免传递给LLM的token过多
            result = self._apply_smart_sampling_for_query_tools(tool_name, result)

            # 添加摘要（如果没有）
            # 对于返回 result 字段的工具（详细结果已传递给LLM），不需要添加 summary
            if "summary" not in result and "result" not in result:
                result["summary"] = self._generate_summary(tool_name, result)

            # ✅ 增强：处理v3.0图表格式数据
            # 方案A：工具直接返回v3.0格式在data字段，data_id在metadata中
            chart_config = None
            is_chart_result = False

            # Case 1: data字段本身就是v3.0图表格式 (方案A：工具直接输出v3.0)
            if "data" in result and isinstance(result.get("data"), dict):
                data = result["data"]
                # 检查是否是v3.0图表格式：包含type、id、data字段
                if data.get("type") and data.get("id") and ("data" in data or "series" in data or "x" in data):
                    chart_config = data
                    is_chart_result = True
                    logger.info(
                        "detected_v3_chart_format_direct",
                        chart_type=chart_config.get("type"),
                        chart_id=chart_config.get("id")
                    )

            # Case 2: 兼容旧版本：工具返回chart_config字段
            elif "chart_config" in result:
                chart_config = result["chart_config"]
                is_chart_result = True

            # Case 3: 兼容旧版本：工具返回chart字段
            elif "chart" in result:
                chart_config = result["chart"]
                is_chart_result = True

            if is_chart_result and chart_config:
                data_id = result.get("metadata", {}).get("data_id")
                data_id_display = data_id[:16] if data_id else 'N/A'
                chart_type = chart_config.get("type", "unknown")

                result["summary"] = (
                    f"✅ {tool_name} 成功生成图表: {chart_type} 类型"
                    f", 数据ID: {data_id_display}..."
                )
                result["has_chart"] = True
                result["chart_config"] = chart_config  # 设置chart_config字段，供loop.py使用
                result["chart_summary"] = {
                    "chart_type": chart_type,
                    "source_data_id": result.get("metadata", {}).get("source_data_id"),
                    "schema_type": result.get("metadata", {}).get("schema_type"),
                    "chart_id": chart_config.get("id") if chart_config else None
                }

            return result

        # 否则包装为标准格式
        observation = {
            "success": True,
            "data": result,
            "summary": self._generate_summary(tool_name, {"data": result})
        }

        return observation

    def _apply_smart_sampling_for_query_tools(
        self,
        tool_name: str,
        result: Dict[str, Any],
        max_records: int = 24
    ) -> Dict[str, Any]:
        """
        对数据查询工具的返回结果进行智能采样

        策略：Head-Tail-Middle采样（30% 头部 + 40% 中间均匀采样 + 30% 尾部）
        - 只对数据查询工具生效
        - 完整数据已存储在data_id中
        - 采样后的数据传递给LLM，减少token消耗

        Args:
            tool_name: 工具名称
            result: 工具返回结果
            max_records: 最大保留记录数（默认24）

        Returns:
            采样后的结果
        """
        # 识别数据查询工具
        query_tools = {
            "get_jining_regular_stations",
            "get_air_quality",
            "get_vocs_data",
            "get_pm25_ionic",
            "get_pm25_carbon",
            "get_pm25_crustal",
            "get_weather_data",
        }

        # 只对数据查询工具进行采样
        generator = result.get("metadata", {}).get("generator", "")
        is_query_tool = tool_name in query_tools or generator in query_tools

        if not is_query_tool:
            return result

        # 检查data字段是否为列表且需要采样
        data = result.get("data")
        if not isinstance(data, list):
            return result

        original_count = len(data)
        if original_count <= max_records:
            # 数据量不超过阈值，无需采样
            return result

        # 调用tool_adapter中的智能采样函数
        from app.agent.tool_adapter import _smart_sample_data_for_load

        sampled_data, sampling_info = _smart_sample_data_for_load(data, max_records)

        # 更新result
        result["data"] = sampled_data

        # 在metadata中记录采样信息
        if "metadata" not in result:
            result["metadata"] = {}

        result["metadata"]["sampling_applied"] = True
        result["metadata"]["original_record_count"] = original_count
        result["metadata"]["sampled_record_count"] = len(sampled_data)
        result["metadata"]["sampling_info"] = sampling_info

        logger.info(
            "smart_sampling_applied_for_query_tool",
            tool=tool_name,
            original_count=original_count,
            sampled_count=len(sampled_data),
            strategy=sampling_info.get("strategy"),
            retention_ratio=sampling_info.get("retention_ratio")
        )

        return result

    def _generate_summary(
        self,
        tool_name: str,
        result: Dict[str, Any]
    ) -> str:
        """
        生成执行摘要

        Args:
            tool_name: 工具名称
            result: 结果数据

        Returns:
            摘要字符串
        """
        if not result.get("success", True):
            error = result.get("error", "未知错误")
            return f"❌ {tool_name} 失败: {error[:50]}"

        # 尝试生成有意义的摘要
        data = result.get("data")

        if data is None:
            return f"✅ {tool_name} 成功"

        if isinstance(data, list):
            return f"✅ {tool_name} 成功，获取 {len(data)} 条记录"

        if isinstance(data, dict):
            keys = list(data.keys())[:3]
            return f"✅ {tool_name} 成功，返回数据包含: {', '.join(keys)}"

        if isinstance(data, str):
            return f"✅ {tool_name} 成功，返回 {len(data)} 字符"

    def _enhance_error_with_hint(
        self,
        tool_name: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        为工具执行失败的结果增强错误消息，添加参数提示

        策略：
        - 检测参数错误
        - 添加参数提示（bash工具除外）
        - 保持错误消息简洁但信息完整

        Args:
            tool_name: 工具名称
            result: 工具返回的原始结果

        Returns:
            增强后的结果字典
        """
        # bash工具不需要参数提示
        if tool_name == "bash":
            return result

        error = result.get("error", "")
        error_type = result.get("error_type", "")

        # 检测是否是参数错误
        is_param_error = (
            "不支持的" in error or
            "无效" in error or
            "Invalid" in error_type or
            "Missing" in error_type or
            "required" in error.lower() or
            "参数" in error
        )

        if is_param_error:
            # 提取工具的参数信息（如果有的话）
            tool_info = self._get_tool_param_info(tool_name, result)
            param_hint = tool_info.get("hint", "")
            valid_values = tool_info.get("valid_values", "")

            # 构建增强的错误消息
            enhanced_error = error

            if param_hint:
                enhanced_error += f"\n\n{param_hint}"

            if valid_values:
                enhanced_error += f"\n\n支持的值: {', '.join(valid_values)}"

            result["error"] = enhanced_error

        return result

    def _get_tool_param_info(self, tool_name: str, result: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        获取工具的参数信息（用于生成错误提示）

        Args:
            tool_name: 工具名称
            result: 工具执行结果（可选，用于从错误消息推断参数类型）

        Returns:
            {
                "hint": "参数说明",
                "valid_values": ["end", "start", ...]
            }
        """
        # 定义常见工具的参数提示信息
        tool_hints = {
            "word_edit": {
                "insert": {
                    "position": {
                        "hint": "⚠️ position 参数说明:\n  - end: 文档末尾\n  - start: 文档开头\n  - after: 在目标文本之后（需提供target参数）\n  - before: 在目标文本之前（需提供target参数）",
                        "valid_values": ["end", "start", "after", "before"]
                    }
                }
            }
        }

        # 尝试从错误消息中推断参数类型
        if result and isinstance(result, dict):
            error = result.get("error", "")
            if "position" in error and tool_name in tool_hints:
                return tool_hints[tool_name].get("insert", {}).get("position", {})

        return {}

        return f"✅ {tool_name} 成功"

    def list_available_tools(self) -> List[str]:
        """
        列出可用工具

        Returns:
            工具名称列表
        """
        return list(self.tool_registry.keys())

    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        获取工具信息

        Args:
            tool_name: 工具名称

        Returns:
            工具信息字典，如果不存在返回 None
        """
        if tool_name not in self.tool_registry:
            return None

        func = self.tool_registry[tool_name]

        return {
            "name": tool_name,
            "callable": func.__name__,
            "doc": func.__doc__ or "无描述",
            "module": func.__module__
        }

    def __repr__(self) -> str:
        return f"<ToolExecutor tools={len(self.tool_registry)}>"

    def _create_execution_context(self, iteration: int):
        """创建 ExecutionContext（如果可用）"""
        if not (self.data_context_manager and self.memory_manager):
            return None

        try:
            from app.agent.context.execution_context import ExecutionContext

            context = ExecutionContext(
                session_id=self.memory_manager.session_id,
                iteration=iteration,
                data_manager=self.data_context_manager,
                task_list=self.task_list
            )

            # ✅ 为 call_sub_agent 工具添加额外的依赖
            context.memory_manager = self.memory_manager
            context.llm_planner = self.llm_planner
            context.tool_executor = self

            logger.debug(
                "execution_context_created",
                session_id=context.session_id,
                iteration=iteration,
                has_task_list=self.task_list is not None
            )
            return context
        except Exception as exc:
            logger.warning(
                "execution_context_creation_failed",
                error=str(exc)
            )
            return None

    def _create_adapter_context(self, execution_context):
        """为 InputAdapter 构造上下文代理"""
        if not self.memory_manager:
            return None

        try:
            from app.agent.context.input_adapter_context import InputAdapterContext

            return InputAdapterContext(
                memory_manager=self.memory_manager,
                execution_context=execution_context
            )
        except Exception as exc:
            logger.warning(
                "input_adapter_context_creation_failed",
                error=str(exc)
            )
            return None

    async def execute_tools_parallel(
        self,
        tools: List[Dict[str, Any]],
        iteration: int = 0
    ) -> Dict[str, Any]:
        """
        并行执行多个工具调用（增强版 V3.1）

        新增特性：
        - 独立追踪每个工具的结果（tool_results字段）
        - 自动检测部分成功（partial_success）
        - 提供工具级别的错误隔离
        - 记录并行执行总时间

        Args:
            tools: 工具调用列表 [{"tool": "name", "args": {...}}, ...]
            iteration: 当前迭代次数

        Returns:
            合并的观察结果：
            {
                "success": bool,
                "partial_success": bool,
                "parallel": True,
                "success_count": int,
                "total_count": int,
                "execution_time": float,
                "tool_results": [...],
                "failed_tools": [...],
                "data": [...],
                "visuals": [...],
                "data_ids": [...],
                "summary": str
            }
        """
        logger.info(
            "executing_tools_parallel_v31",
            tool_count=len(tools),
            tool_names=[t.get("tool", "unknown") for t in tools],
            iteration=iteration
        )

        # 记录并行执行开始时间
        import time
        start_time = time.time()

        async def execute_single(tool_call: Dict[str, Any]) -> Dict[str, Any]:
            """执行单个工具调用"""
            tool_name = tool_call.get("tool", "unknown")
            tool_args = tool_call.get("args") or {}  # 处理 None 的情况

            try:
                result = await self.execute_tool(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    iteration=iteration
                )
                return {
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result
                }
            except Exception as e:
                logger.error(
                    "parallel_tool_execution_failed",
                    tool=tool_name,
                    error=str(e)
                )
                return {
                    "tool": tool_name,
                    "args": tool_args,
                    "result": {
                        "success": False,
                        "error": str(e),
                        "summary": f"❌ {tool_name} 并行执行失败: {str(e)[:100]}"
                    }
                }

        # 并行执行所有工具
        results = await asyncio.gather(
            *[execute_single(tc) for tc in tools],
            return_exceptions=True
        )

        # 计算并行执行总时间
        total_time = time.time() - start_time

        # 分类结果：成功 vs 失败
        successful_results = []
        failed_results = []

        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                # 捕获异常
                tool_name = tools[idx].get("tool", "unknown")
                failed_results.append({
                    "tool": tool_name,
                    "args": tools[idx].get("args", {}),
                    "error": str(res),
                    "success": False
                })
                logger.error(
                    "parallel_tool_exception",
                    tool=tool_name,
                    error=str(res)
                )
            elif res.get("result", {}).get("success", False):
                successful_results.append(res)
            else:
                failed_results.append(res)

        # 合并数据和图表
        merged_data = []
        merged_visuals = []
        merged_data_ids = []

        for res in successful_results:
            result = res.get("result", {})
            if result.get("data"):
                merged_data.extend(
                    result["data"] if isinstance(result["data"], list) else [result["data"]]
                )
            if result.get("visuals"):
                merged_visuals.extend(result["visuals"])
            if result.get("data_id"):
                merged_data_ids.append(result["data_id"])

        # 判断执行状态
        success_count = len(successful_results)
        total_count = len(tools)
        is_full_success = success_count == total_count
        is_partial_success = 0 < success_count < total_count

        # 构建返回结果（增强版）
        return {
            "success": is_full_success,
            "partial_success": is_partial_success,
            "parallel": True,  # 标记为并行执行
            "success_count": success_count,
            "total_count": total_count,
            "execution_time": round(total_time, 2),  # 新增：总执行时间

            # 新增：分别追踪成功和失败的工具
            "tool_results": successful_results,
            "failed_tools": failed_results,

            # 合并后的数据
            "data": merged_data if merged_data else None,
            "visuals": merged_visuals if merged_visuals else None,
            "data_ids": merged_data_ids if merged_data_ids else None,

            # 生成摘要
            "summary": self._generate_parallel_summary(
                successful_results, failed_results, total_time
            )
        }

    def _generate_parallel_summary(
        self,
        successful: List[Dict],
        failed: List[Dict],
        time: float
    ) -> str:
        """生成并行执行摘要"""
        success_tools = [r["tool"] for r in successful]
        failed_tools = [r["tool"] for r in failed]

        summary_lines = [
            f"✅ **并行执行完成** ({len(successful)}/{len(successful) + len(failed)} 成功，耗时 {time:.2f}s)"
        ]

        if success_tools:
            summary_lines.append(f"  成功工具: {', '.join(success_tools)}")

            # 添加每个工具的摘要信息
            for res in successful:
                tool_summary = res.get("result", {}).get("summary", "")
                if tool_summary:
                    # 清理摘要格式（移除多余的换行和空格）
                    clean_summary = tool_summary.strip().replace("\n", " ")
                    summary_lines.append(f"    - {res['tool']}: {clean_summary}")

        if failed_tools:
            summary_lines.append(f"  失败工具: {', '.join(failed_tools)}")
            for fail in failed:
                error_msg = fail.get("error", fail.get("result", {}).get("error", "Unknown error"))
                summary_lines.append(f"    - {fail['tool']}: {error_msg[:80]}")

        return "\n".join(summary_lines)



# =========================
# 临时测试工具（用于开发阶段）
# =========================

async def _test_get_weather_data(
    location: str,
    start_time: str,
    end_time: str
) -> Dict[str, Any]:
    """
    测试工具：获取气象数据

    Args:
        location: 地点
        start_time: 开始时间
        end_time: 结束时间

    Returns:
        模拟的气象数据
    """
    logger.info(
        "test_tool_weather_data",
        location=location,
        start_time=start_time,
        end_time=end_time
    )

    return {
        "success": True,
        "data": [
            {
                "time": start_time,
                "wind_speed": 3.5,
                "wind_direction": 135,
                "temperature": 25.3,
                "humidity": 65
            }
        ],
        "summary": f"✅ 获取 {location} 气象数据成功"
    }


async def _test_get_air_quality(
    location: str,
    pollutant: str,
    start_time: str,
    end_time: str
) -> Dict[str, Any]:
    """
    测试工具：获取空气质量数据

    Args:
        location: 地点
        pollutant: 污染物
        start_time: 开始时间
        end_time: 结束时间

    Returns:
        模拟的空气质量数据
    """
    logger.info(
        "test_tool_air_quality",
        location=location,
        pollutant=pollutant
    )

    return {
        "success": True,
        "data": [
            {
                "time": start_time,
                "pollutant": pollutant,
                "value": 85.2,
                "unit": "μg/m³"
            }
        ],
        "summary": f"✅ 获取 {location} {pollutant} 数据成功"
    }


def create_test_executor() -> ToolExecutor:
    """
    创建测试用的工具执行器（包含模拟工具）

    Returns:
        配置了测试工具的 ToolExecutor 实例
    """
    executor = ToolExecutor()

    # 注册测试工具
    executor.register_tool("get_weather_data", _test_get_weather_data)
    executor.register_tool("get_air_quality", _test_get_air_quality)

    logger.info(
        "test_executor_created",
        tools=executor.list_available_tools()
    )

    return executor
