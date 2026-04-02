"""
Tool Adapter for ReAct Agent - 单一注册源适配器

将global_tool_registry中的工具（LLMTool）适配为ReAct Agent可用的格式。

核心功能：
1. 统一从 global_tool_registry 读取工具
2. 标准化输入输出格式（符合UDF v1.0和v3.0规范）
3. 提供工具描述和schema
4. 自动记录调用统计和性能指标

注意：现在是完全单一注册源，不允许独立注册工具。
"""

from typing import Dict, Any, List, Optional, Callable, Tuple
from datetime import datetime
import structlog

# 单一工具注册源
from app.tools import global_tool_registry

# 导入观察天气工具（特殊的工具，从独立的 observed_tool_registry）
from app.tools.observed_weather_tool import observed_tool_registry
from app.tools.openmeteo_current_tool import openmeteo_current_tool
from app.tools.weatherapi_com_tool import weatherapi_com_tool

logger = structlog.get_logger()


# ========================================
# 核心工具适配器（基于LLMTool）
# ========================================

async def call_llm_tool(tool_name: str, context=None, **kwargs) -> Dict[str, Any]:
    """
    通用LLM工具调用适配器（符合UDF v1.0规范）

    Args:
        tool_name: 工具名称（从 global_tool_registry 获取）
        context: ExecutionContext实例（可选）
        **kwargs: 工具参数

    Returns:
        {
            "status": "success|failed|partial|empty",
            "success": bool,
            "data": Any,
            "metadata": Dict,
            "summary": str
        }
    """
    start_time = datetime.now()
    try:
        # 对知识库检索统一收敛 top_k，避免返回过多结果
        if tool_name == "search_knowledge_base":
            orig_top_k = kwargs.get("top_k")
            capped_top_k = min(int(orig_top_k) if orig_top_k else 3, 3)
            kwargs["top_k"] = capped_top_k
            logger.info("normalized_top_k_for_kb_search", orig_top_k=orig_top_k, effective_top_k=capped_top_k)

        # 从单一注册源获取工具
        tool = global_tool_registry.get_tool(tool_name)

        if not tool:
            error_msg = f"工具不存在: {tool_name}"
            logger.error(
                "llm_tool_not_found",
                tool=tool_name,
                available_tools=global_tool_registry.list_tools()
            )
            return {
                "status": "failed",
                "success": False,
                "error": error_msg,
                "data": [],
                "metadata": {
                    "tool_name": tool_name,
                    "available_tools": global_tool_registry.list_tools()
                },
                "summary": f"❌ {error_msg}"
            }

        if not tool.is_available():
            error_msg = f"工具不可用: {tool_name}"
            logger.warning(
                "llm_tool_not_available",
                tool=tool_name,
                status=getattr(tool, 'status', 'unknown')
            )
            return {
                "status": "failed",
                "success": False,
                "error": error_msg,
                "data": [],
                "metadata": {
                    "tool_name": tool_name,
                    "status": getattr(tool, 'status', 'unknown')
                },
                "summary": f"❌ {error_msg}"
            }

        # 执行工具（传递context，如果工具需要的话）
        # 【修复】对于需要data_context_manager的工具，正确处理已注入的data_context_manager
        # 注意：expert_executor通过位置参数传递execution_context，需要在这里正确处理
        execution_context = context  # 重命名便于理解
        data_context_manager = None

        # 【关键修复】首先检查kwargs中是否已经有data_context_manager（从expert_executor注入）
        if 'data_context_manager' in kwargs:
            data_context_manager = kwargs['data_context_manager']
            logger.debug(
                "data_context_manager_from_kwargs",
                tool=tool_name,
                source="expert_executor_injection"
            )
        # 如果kwargs中没有，才从execution_context提取
        elif execution_context is not None:
            # 【修复】ExecutionContext 的属性是 data_manager，不是 data_context_manager
            if hasattr(execution_context, 'data_manager'):
                data_context_manager = execution_context.data_manager
                logger.debug(
                    "data_context_manager_extracted",
                    tool=tool_name,
                    has_data_manager=data_context_manager is not None,
                    data_manager_type=type(data_context_manager).__name__ if data_context_manager else None
                )
            elif hasattr(execution_context, 'get_data_manager'):
                data_context_manager = execution_context.get_data_manager()

        # 准备执行参数
        exec_kwargs = kwargs.copy()
        # 移除 data_context_manager（如果来自 kwargs），后续按工具类型选择性注入
        exec_kwargs.pop('data_context_manager', None)

        # 注入依赖（基于工具属性动态判断）
        if data_context_manager is not None:
            tool_data = global_tool_registry.get_tool_data(tool_name)
            requires_context = tool_data.get("requires_context", False) if tool_data else False

            # ✅ 只为数据分析工具注入 data_context_manager
            # 判断逻辑：
            # 1. requires_context=True（数据分析工具）
            # 2. 且工具没有 requires_task_list 属性（排除任务管理工具）
            tool_instance = tool_data.get("tool") if tool_data else None
            requires_task_list = getattr(tool_instance, "requires_task_list", False) if tool_instance else False

            if requires_context and not requires_task_list and 'data_context_manager' not in exec_kwargs:
                exec_kwargs['data_context_manager'] = data_context_manager
                logger.debug(
                    "data_context_manager_injected",
                    tool=tool_name,
                    requires_context=requires_context,
                    requires_task_list=requires_task_list
                )

        # 执行工具
        # 根据 requires_context 标志决定是否传递 ExecutionContext
        tool_data = global_tool_registry.get_tool_data(tool_name)
        requires_context = tool_data.get("requires_context", False) if tool_data else False

        if execution_context is not None and requires_context:
            # 数据分析工具：需要 ExecutionContext
            # execute(self, context, ...)
            result = await tool.execute(execution_context, **exec_kwargs)
            logger.debug(
                "tool_executed_with_context",
                tool=tool_name,
                has_context=True
            )
        else:
            # 办公助手工具、任务管理工具：不需要 ExecutionContext
            # execute(self, **kwargs)
            result = await tool.execute(**exec_kwargs)
            logger.debug(
                "tool_executed_without_context",
                tool=tool_name,
                has_context=False,
                requires_context=requires_context
            )

        # 标准化返回格式（符合UDF v1.0）
        execution_time = (datetime.now() - start_time).total_seconds()
        return _standardize_tool_result(tool_name, result, execution_time)

    except Exception as e:
        execution_time = (datetime.now() - start_time).total_seconds()
        error_msg = f"工具 {tool_name} 执行失败: {str(e)}"

        logger.error(
            "llm_tool_call_failed",
            tool=tool_name,
            error=str(e),
            execution_time=execution_time,
            exc_info=True
        )

        return {
            "status": "failed",
            "success": False,
            "error": str(e),
            "data": [],
            "metadata": {
                "tool_name": tool_name,
                "execution_time": execution_time,
                "error_type": type(e).__name__
            },
            "summary": f"❌ {error_msg[:50]}"
        }


def _standardize_tool_result(tool_name: str, result: Any, execution_time: float) -> Dict[str, Any]:
    """
    验证工具返回结果是否符合UDF v1.0或v2.0统一数据格式

    支持两种标准格式：
    1. UDF v1.0: status, success, data, metadata, summary
    2. UDF v2.0: status, success, data或visuals, metadata, summary

    核心要求：
    - status: success|failed|partial|empty
    - success: bool
    - metadata: 工具元信息（必须包含schema_version字段）
    - summary: 摘要信息
    - data或visuals: 数据内容（v2.0工具使用visuals，v1.0工具使用data）
    """
    # 验证标准格式
    if isinstance(result, dict):
        # 检查核心必需字段
        required_core_fields = ["status", "success", "metadata", "summary"]
        has_core_fields = all(key in result for key in required_core_fields)

        # 检查是否有数据字段（data或visuals）
        has_data_field = "data" in result or "visuals" in result

        # 验证schema_version（v2.0要求）
        schema_version = result.get("metadata", {}).get("schema_version")
        is_v2_format = schema_version in ["v2.0", "2.0", "v2"]

        if has_core_fields and has_data_field:
            # ✅ 标准格式验证通过
            global_tool_registry.record_success(tool_name)
            global_tool_registry._update_execution_time(tool_name, execution_time)
            return result
        else:
            # ❌ 非标准格式，需要转换
            missing_fields = [k for k in required_core_fields if k not in result]
            if not has_data_field:
                missing_fields.append("data或visuals")

            logger.warning(
                "tool_result_format_conversion",
                tool=tool_name,
                missing_fields=missing_fields,
                current_format="non-standard",
                schema_version=schema_version,
                message="Converting non-standard format to UDF v1.0"
            )

            # 转换为标准格式
            converted_result = _convert_to_standard_format(result, tool_name, execution_time)
            return converted_result

    # 非字典结果，包装为标准格式（容错处理）
    logger.warning(
        "tool_result_not_dict",
        tool=tool_name,
        result_type=type(result).__name__,
        message="Wrapping non-dict result into standard format"
    )

    return {
        "status": "success",
        "success": True,
        "data": result,
        "metadata": {
            "tool_name": tool_name,
            "execution_time": execution_time
        },
        "summary": f"✅ {tool_name} 执行成功"
    }


def _convert_to_standard_format(result: Dict[str, Any], tool_name: str, execution_time: float) -> Dict[str, Any]:
    """
    将非标准格式的工具结果转换为UDF标准格式

    Args:
        result: 原始工具结果
        tool_name: 工具名称
        execution_time: 执行时间

    Returns:
        转换后的标准格式结果
    """
    try:
        # 提取基本信息
        # ✅ 修复：更安全的默认值策略
        # 如果工具返回了 success 字段，优先使用它来推断 status
        if "success" in result:
            success = result["success"]
            # 如果 success 为 False，默认 status 为 "failed"
            if result.get("status"):
                status = result["status"]
            else:
                status = "failed" if not success else "success"
        else:
            # 如果工具没有返回 success 字段，根据 status 推断
            status = result.get("status", "success")
            # 如果有 error 字段，标记为失败
            if "error" in result:
                success = False
                status = "failed"
            else:
                # 根据 status 推断
                success = (status == "success")

        # 处理数据字段
        data = result.get("data")
        visuals = result.get("visuals")
        metadata = result.get("metadata", {})

        # ✅ 修复：根据 success 状态生成默认 summary
        # 对于返回 result 字段的工具（详细结果已传递给LLM），不需要 summary
        if "summary" in result:
            summary = result["summary"]
        elif "result" in result:
            # 有 result 字段，不生成 summary（不添加到返回结果中）
            summary = None
        else:
            if success:
                summary = f"✅ {tool_name} 执行完成"
            else:
                summary = f"❌ {tool_name} 执行失败"
                if "error" in result:
                    # ✅ 修复：增加截断长度到200字符，确保 data_id 等关键信息完整
                    summary += f": {result['error'][:200]}"

        # 【修复】保留 data_id 字段（用于参数绑定）
        data_id = result.get("data_id")
        if data_id and "data_id" not in metadata:
            metadata["data_id"] = data_id

        # 确保metadata包含必要信息
        if "tool_name" not in metadata:
            metadata["tool_name"] = tool_name
        if "execution_time" not in metadata:
            metadata["execution_time"] = execution_time
        # ✅ 修复：自动添加 generator 字段（用于 loop.py 中识别工具类型）
        # generator 字段在 UDF v2.0 规范中广泛使用，表示"生成这个结果的工具"
        if "generator" not in metadata:
            metadata["generator"] = tool_name

        # 构建标准格式
        standard_result = {
            "status": status,
            "success": success,
            "metadata": metadata
        }

        # 只在 summary 非空时才添加（对于返回 result 字段的工具，summary 为 None）
        if summary is not None:
            standard_result["summary"] = summary

        # 【修复】保留 data_id 到顶层（供 parameter_binder 使用）
        if data_id:
            standard_result["data_id"] = data_id

        # 添加数据字段（优先使用visuals，如果不存在则使用data）
        if visuals is not None:
            standard_result["visuals"] = visuals
            standard_result["data"] = None  # v2.0格式不使用data
        elif data is not None:
            standard_result["data"] = data
            standard_result["visuals"] = []  # v1.0格式不包含visuals

        # 保留 result 字段（包含详细的结构化数据，如对比结果）
        # 例如：compare_standard_reports 工具返回的详细对比数据
        if "result" in result:
            standard_result["result"] = result["result"]

        logger.info(
            "tool_result_converted_to_standard_format",
            tool=tool_name,
            original_fields=list(result.keys()),
            converted_fields=list(standard_result.keys()),
            has_visuals="visuals" in standard_result,
            has_data="data" in standard_result
        )

        return standard_result

    except Exception as e:
        logger.error(
            "tool_result_conversion_failed",
            tool=tool_name,
            error=str(e),
            exc_info=True
        )

        # 转换失败，返回错误格式
        return {
            "status": "failed",
            "success": False,
            "data": None,
            "visuals": [],
            "metadata": {
                "tool_name": tool_name,
                "execution_time": execution_time,
                "error": f"Format conversion failed: {str(e)}"
            },
            "summary": f"❌ {tool_name} 格式转换失败: {str(e)[:50]}"
        }


# ========================================
# 天气观测工具适配器（额外的工具）
# ========================================

async def get_observed_weather(
    lat: float,
    lon: float,
    station_id: Optional[str] = None,
    preferred_source: Optional[str] = None
) -> Dict[str, Any]:
    """
    获取实时天气观测数据（使用ObservedWeatherToolRegistry）

    Args:
        lat: 纬度
        lon: 经度
        station_id: 站点ID（可选）
        preferred_source: 优先数据源（可选）

    Returns:
        标准化结果
    """
    try:
        # 使用工具注册表获取数据
        result = await observed_tool_registry.fetch_current(
            lat=lat,
            lon=lon,
            station_id=station_id,
            preferred_tool=preferred_source
        )

        if result is None:
            return {
                "status": "failed",
                "success": False,
                "error": "无法获取天气观测数据",
                "data": [],
                "metadata": {
                    "tool_name": "get_observed_weather",
                    "location": f"({lat}, {lon})"
                },
                "summary": f"❌ 获取 ({lat}, {lon}) 天气观测数据失败"
            }

        # 转换为字典格式
        data_dict = result.to_dict()

        return {
            "status": "success",
            "success": True,
            "data": data_dict,
            "metadata": {
                "tool_name": "get_observed_weather",
                "location": f"({lat}, {lon})",
                "data_source": result.data_source,
                "temperature_2m": result.temperature_2m,
                "wind_speed_10m": result.wind_speed_10m
            },
            "summary": (
                f"✅ 获取天气观测数据成功: "
                f"温度 {result.temperature_2m}°C, "
                f"风速 {result.wind_speed_10m} km/h, "
                f"数据源 {result.data_source}"
            )
        }

    except Exception as e:
        logger.error(
            "get_observed_weather_failed",
            lat=lat,
            lon=lon,
            error=str(e),
            exc_info=True
        )

        return {
            "status": "failed",
            "success": False,
            "error": str(e),
            "data": [],
            "metadata": {
                "tool_name": "get_observed_weather",
                "location": f"({lat}, {lon})",
                "error_type": type(e).__name__
            },
            "summary": f"❌ 获取天气观测数据失败: {str(e)[:50]}"
        }


# ========================================
# 工具注册初始化
# ========================================

def register_observed_weather_tools():
    """
    注册所有天气观测工具到 ObservedWeatherToolRegistry
    """
    # 注册 OpenMeteo 工具（优先级最高）
    observed_tool_registry.register(
        tool=openmeteo_current_tool,
        priority=10
    )

    # 注册 WeatherAPI.com 工具（次优先级）
    observed_tool_registry.register(
        tool=weatherapi_com_tool,
        priority=20
    )

    logger.info(
        "observed_weather_tools_registered",
        tools=observed_tool_registry.list_tools()
    )


# ========================================
# 智能采样辅助函数
# ========================================

def _smart_sample_data_for_load(data: List[Dict], max_records: int) -> Tuple[List[Dict], Dict[str, Any]]:
    """
    智能采样数据（用于大数据集采样）

    策略：
    1. 优先保留首尾数据（时间序列的起点和终点）
    2. 中间部分均匀采样

    Args:
        data: 原始数据列表
        max_records: 最大保留记录数

    Returns:
        (采样后的数据, 采样信息)
    """
    n = len(data)
    if n <= max_records:
        return data, {"strategy": "no_sampling", "retention_ratio": 1.0}

    # 分配采样比例
    head_ratio = 0.3  # 前30%的记录
    tail_ratio = 0.3  # 后30%的记录
    middle_ratio = 0.4  # 中间40%的记录

    head_count = int(max_records * head_ratio)
    tail_count = int(max_records * tail_ratio)
    middle_count = max_records - head_count - tail_count

    # 采样首部
    head_sample = data[:head_count]

    # 采样尾部
    tail_sample = data[-tail_count:] if tail_count > 0 else []

    # 采样中间部分（均匀采样）
    middle_start = head_count
    middle_end = n - tail_count
    middle_data = data[middle_start:middle_end]

    if middle_count > 0 and len(middle_data) > 0:
        step = max(1, len(middle_data) // middle_count)
        middle_sample = middle_data[::step][:middle_count]
    else:
        middle_sample = []

    sampled = head_sample + middle_sample + tail_sample
    sampled = sampled[:max_records]  # 确保不超过max_records

    return sampled, {
        "strategy": "head_tail_middle_sampling",
        "head_samples": len(head_sample),
        "middle_samples": len(middle_sample),
        "tail_samples": len(tail_sample),
        "retention_ratio": len(sampled) / n,
        "original_count": n,
        "sampled_count": len(sampled)
    }


def get_react_agent_tool_registry() -> Dict[str, Callable]:
    """
    获取ReAct Agent可用的工具注册表（单一注册源）

    Returns:
        工具字典 {"tool_name": async_function}
    """
    # 确保天气观测工具已注册
    register_observed_weather_tools()

    tool_registry = {}

    # ========================================
    # 1. 核心LLM工具（从单一注册源 global_tool_registry）
    # ========================================
    # 🔍 调试日志：输出全局工具注册表中的所有工具
    global_tools = global_tool_registry.list_tools()
    logger.info(
        "get_react_agent_tool_registry_debug",
        total_global_tools=len(global_tools),
        has_unpack_office="unpack_office" in global_tools,
        all_tools=global_tools
    )

    for tool_name in global_tools:
        # 为每个工具创建一个闭包，避免延迟绑定问题
        def make_tool_wrapper(name: str):
            async def tool_wrapper(context=None, **kwargs):
                return await call_llm_tool(name, context=context, **kwargs)
            tool_wrapper.__name__ = name
            # 从注册表获取工具描述
            tool_data = global_tool_registry.get_tool_data(name)
            description = tool_data.get("metadata", {}).get("description", f"Call {name} tool")
            tool_wrapper.__doc__ = description
            return tool_wrapper

        tool_wrapper = make_tool_wrapper(tool_name)
        tool_registry[tool_name] = tool_wrapper

    # ========================================
    # 2. 天气观测工具（特殊的独立工具）
    # ========================================
    # 包装 get_observed_weather 以支持 context 参数
    async def get_observed_weather_wrapper(context=None, **kwargs):
        """包装器：支持context参数但不使用它"""
        return await get_observed_weather(**kwargs)

    get_observed_weather_wrapper.__name__ = "get_observed_weather"
    get_observed_weather_wrapper.__doc__ = get_observed_weather.__doc__
    tool_registry["get_observed_weather"] = get_observed_weather_wrapper


    # 🔍 调试日志：输出最终工具注册表
    final_tools = list(tool_registry.keys())
    logger.info(
        "react_agent_tool_registry_created",
        total_tools=len(tool_registry),
        has_unpack_office="unpack_office" in final_tools,
        tools=final_tools
    )

    return tool_registry


# ========================================
# 工具Schema定义（用于LLM Function Calling）
# ========================================

def get_tool_schemas() -> List[Dict[str, Any]]:
    """
    获取所有工具的Schema定义（单一注册源）

    Returns:
        Schema列表，用于LLM Function Calling
    """
    schemas = []

    # ========================================
    # 1. 从 global_tool_registry 获取所有工具的 Schema
    # ========================================
    for tool_data in global_tool_registry.get_all_tools():
        tool = tool_data["tool"]
        if tool.is_available():
            # 特别处理图表工具的Schema，添加职责说明
            if tool.name in ["smart_chart_generator", "generate_chart"]:
                schema = tool.get_function_schema()
                # 在描述中添加职责分工信息
                if "description" in schema:
                    if tool.name == "smart_chart_generator":
                        schema["description"] = (
                            "智能图表生成器 - 固定格式数据专用\n"
                            "适用：PMF/OBM分析结果、组分数据、已存储数据（有data_id）\n"
                            "特征：从统一存储加载数据，智能推荐图表类型\n"
                            "决策：有data_id或需要智能推荐时使用此工具"
                        )
                    elif tool.name == "generate_chart":
                        schema["description"] = (
                            "通用图表生成工具 - 动态数据专用\n"
                            "适用：直接传入的原始数据、自定义场景、预定义场景模板\n"
                            "特征：直接传入数据，使用模板库+LLM生成\n"
                            "决策：无data_id或需要LLM分析数据特征时使用此工具"
                        )
                schemas.append(schema)
            else:
                schemas.append(tool.get_function_schema())

    # ========================================
    # 2. 添加天气观测工具 schema（特殊工具）
    # ========================================
    schemas.append({
        "name": "get_observed_weather",
        "description": "获取指定位置的实时天气观测数据（原始观测数据，非预报），包括温度、湿度、风速、风向、气压等信息",
        "parameters": {
            "type": "object",
            "properties": {
                "lat": {
                    "type": "number",
                    "description": "纬度，范围 -90 到 90"
                },
                "lon": {
                    "type": "number",
                    "description": "经度，范围 -180 到 180"
                },
                "station_id": {
                    "type": "string",
                    "description": "站点ID（可选），用于标识和记录"
                },
                "preferred_source": {
                    "type": "string",
                    "description": "优先数据源（可选），如 'openmeteo_current' 或 'weatherapi_com'"
                }
            },
            "required": ["lat", "lon"]
        }
    })


    logger.info("tool_schemas_generated", count=len(schemas))

    return schemas


def get_detailed_schemas_for_tools(tool_names: List[str]) -> List[Dict[str, Any]]:
    """
    按需获取指定工具的详细Schema

    Args:
        tool_names: 需要详细Schema的工具名称列表

    Returns:
        指定工具的完整Schema列表
    """
    all_schemas = get_tool_schemas()
    detailed_schemas = [
        schema for schema in all_schemas
        if schema["name"] in tool_names
    ]

    logger.info("detailed_schemas_loaded",
                requested=len(tool_names),
                found=len(detailed_schemas))

    return detailed_schemas


def get_tool_metadata() -> Dict[str, Any]:
    """
    获取所有工具的元数据（用于调试和监控）

    Returns:
        工具元数据字典
    """
    metadata = {}

    for tool_name in global_tool_registry.list_tools():
        tool_data = global_tool_registry.get_tool_data(tool_name)
        if tool_data:
            metadata[tool_name] = {
                "priority": tool_data.get("priority"),
                "version": tool_data.get("version"),
                "category": tool_data.get("category"),
                "requires_context": tool_data.get("requires_context"),
                "input_adapter_rules": tool_data.get("input_adapter_rules", {}),
                "return_schema": tool_data.get("return_schema", {}),
                "metadata": tool_data.get("metadata", {}),
                "test_samples": tool_data.get("test_samples", []),
                "registered_at": tool_data.get("registered_at"),
                "stats": global_tool_registry.get_stats().get(tool_name, {})
            }

    return metadata

