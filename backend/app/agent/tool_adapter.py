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
# 工具依赖配置（用于生成工具摘要时的依赖提示）
# ========================================
# 格式: {工具名: "依赖说明"}
TOOL_DEPENDENCIES = {
    # 分析工具依赖
    "calculate_pm_pmf": "需先调用结构化查询工具：get_pm25_ionic（水溶性离子小时粒度数据）和 get_pm25_carbon（碳组分OC/EC小时粒度数据），分别作为data_id和gas_data_id参数",
    "calculate_vocs_pmf": "需先调用 get_vocs_data 获取小时粒度的 VOCs 数据（必须包含关键臭氧前体物：乙烯、丙烯、苯、甲苯等）",
    "calculate_obm_full_chemistry": "需先分别调用 get_vocs_data（VOCs小时粒度数据）、get_air_quality（获取NOx和O3小时粒度数据），分别传入vocs_data_id、nox_data_id、o3_data_id参数",
    "analyze_upwind_enterprises": "需先调用 get_weather_data 获取气象数据（包含风向风速信息），传入weather_data_id参数",
    "meteorological_trajectory_analysis": "独立工具，直接输入经纬度和时间参数即可，无需预先获取数据（内部调用NOAA HYSPLIT API）",
    "analyze_trajectory_sources": "独立工具，直接输入经纬度和分析参数即可（内部自动调用HYSPLIT轨迹计算和企业源清单API）",
    "calculate_reconstruction": "需先调用结构化查询工具获取完整颗粒物组分数据：get_pm25_ionic（离子）、get_pm25_carbon（碳组分）、get_pm25_crustal（地壳元素）",
    "calculate_carbon": "需先调用 get_pm25_carbon 获取碳组分数据（OC和EC字段），作为carbon_data_id参数",
    "calculate_soluble": "需先调用 get_pm25_ionic 获取水溶性离子数据（SO4、NO3、NH4等字段），作为data_id参数",
    "calculate_crustal": "需先调用 get_pm25_crustal 获取地壳元素数据（Ca、Fe、Al等元素），作为data_id参数",
    "calculate_trace": "需先调用 get_pm25_crustal 获取微量元素数据（包含重金属等），作为data_id参数",
    "calculate_iaqi": "需先调用 get_air_quality 获取污染物浓度数据（包含PM2.5、PM10、SO2、NO2、CO、O3等），传入pollutant_data参数",
    "predict_air_quality": "需先调用 get_air_quality 获取历史空气质量数据（至少7天以上历史数据用于训练模型）",

    # 可视化工具依赖
    "smart_chart_generator": "需要 data_id（来自分析工具或数据查询工具的返回结果，如PMF的data_id或VOCs的data_id）",
    "revise_chart": "需要原图表的chart_id（来自之前生成的图表）和修订指令",
    "generate_map": "需要先调用 get_nearby_stations 或 query_station_info 获取站点经纬度信息",

    # 其他工具
    "load_data_from_memory": "需要先有 data_id（由其他工具返回的数据引用ID，格式如 vocs_unified:xxx 或 pmf_result:xxx）",
}


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

        # 注入data_context_manager（如果工具需要且kwargs中没有）
        if data_context_manager is not None:
            # 检查工具是否需要data_context_manager
            # 从工具的requires_context属性判断（即使requires_context=False，也可能需要data_context_manager读取数据）
            tool_data = global_tool_registry.get_tool_data(tool_name)
            requires_context = tool_data.get("requires_context", False) if tool_data else False

            # 对于需要读取data的工具（如calculate_soluble），即使requires_context=False，也需要data_context_manager
            # 通过检查工具名称来判断
            TOOLS_NEEDING_DATA_CONTEXT = {
                "calculate_soluble", "calculate_carbon", "calculate_crustal", "calculate_trace",
                "calculate_reconstruction", "calculate_pm_pmf", "calculate_vocs_pmf",
                "calculate_obm_full_chemistry"
            }

            if (requires_context or tool_name in TOOLS_NEEDING_DATA_CONTEXT) and 'data_context_manager' not in exec_kwargs:
                exec_kwargs['data_context_manager'] = data_context_manager
                logger.debug(
                    "data_context_manager_injected_for_tool",
                    tool=tool_name,
                    has_manager=data_context_manager is not None
                )

        # 执行工具
        # 【关键修复】检查工具是否真的需要 context（尊重 requires_context 标志）
        # 避免 Office 工具（word_processor, excel_processor, ppt_processor）和 bash 工具
        # 因为不需要 context 而收到参数冲突错误
        tool_data = global_tool_registry.get_tool_data(tool_name)
        requires_context = tool_data.get("requires_context", False) if tool_data else False

        if execution_context is not None and requires_context:
            # 工具需要 context：作为位置参数传递
            # execute(self, context, ...)
            result = await tool.execute(execution_context, **exec_kwargs)
            logger.debug(
                "tool_executed_with_context",
                tool=tool_name,
                has_context=True
            )
        else:
            # 工具不需要 context 或没有 context：只传递关键字参数
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
        status = result.get("status", "success")
        # ✅ 修复：根据 status 字段推断 success 值，而不是默认为 True
        # 如果工具没有返回 success 字段，通过 status 推断
        if "success" in result:
            success = result["success"]
        else:
            # 如果有 error 字段，标记为失败
            if "error" in result:
                success = False
                status = result.get("status", "failed")
            else:
                # 根据 status 推断
                success = (status == "success")

        # 处理数据字段
        data = result.get("data")
        visuals = result.get("visuals")
        metadata = result.get("metadata", {})

        # ✅ 修复：根据 success 状态生成默认 summary
        if "summary" in result:
            summary = result["summary"]
        else:
            if success:
                summary = f"✅ {tool_name} 执行完成"
            else:
                summary = f"❌ {tool_name} 执行失败"
                if "error" in result:
                    summary += f": {result['error'][:50]}"

        # 【修复】保留 data_id 字段（用于参数绑定）
        data_id = result.get("data_id")
        if data_id and "data_id" not in metadata:
            metadata["data_id"] = data_id

        # 确保metadata包含必要信息
        if "tool_name" not in metadata:
            metadata["tool_name"] = tool_name
        if "execution_time" not in metadata:
            metadata["execution_time"] = execution_time

        # 构建标准格式
        standard_result = {
            "status": status,
            "success": success,
            "metadata": metadata,
            "summary": summary
        }

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
    智能采样数据（用于load_data_from_memory工具）

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
    for tool_name in global_tool_registry.list_tools():
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

    # ========================================
    # 3. 数据加载工具（内置工具）
    # ========================================
    async def load_data_from_memory(data_id: str, max_records: int = 100, context=None, **kwargs):
        """
        从外部化存储读取数据（智能采样，避免token超限）

        Args:
            data_id: 数据引用ID（完整ID，如 'vocs_unified:v1:abc123'）
            max_records: 最大返回记录数（默认100，用于控制token消耗）
            context: ExecutionContext实例
            **kwargs: 其他参数

        Returns:
            包含采样后数据的字典
        """
        if not context:
            return {
                "status": "failed",
                "success": False,
                "error": "需要ExecutionContext来加载数据",
                "data": [],
                "summary": "❌ 缺少上下文"
            }

        try:
            data = context.get_data(data_id)
            original_count = len(data) if isinstance(data, list) else 1
            truncated = False
            sampling_info = None

            # 智能采样：如果数据量超过max_records，进行智能采样
            if isinstance(data, list) and len(data) > max_records:
                truncated = True
                logger.info(
                    "load_data_sampling_required",
                    data_id=data_id,
                    original_count=original_count,
                    max_records=max_records
                )

                # 使用智能采样策略
                sampled_data, sampling_info = _smart_sample_data_for_load(data, max_records)

                logger.info(
                    "load_data_sampling_completed",
                    data_id=data_id,
                    original_count=original_count,
                    sampled_count=len(sampled_data),
                    strategy=sampling_info.get("strategy"),
                    retention_ratio=sampling_info.get("retention_ratio")
                )

                data = sampled_data

            return {
                "status": "success",
                "success": True,
                "data": data,
                "metadata": {
                    "data_id": data_id,
                    "original_count": original_count,
                    "loaded_at": datetime.now().isoformat(),
                    "truncated": truncated,
                    "sampling_info": sampling_info
                },
                "summary": f"✅ 成功加载数据 {data_id}（共{original_count}条记录，返回{len(data) if isinstance(data, list) else 1}条）"
            }
        except Exception as e:
            return {
                "status": "failed",
                "success": False,
                "error": str(e),
                "data": [],
                "summary": f"❌ 数据加载失败: {str(e)[:50]}"
            }

    tool_registry["load_data_from_memory"] = load_data_from_memory

    logger.info(
        "react_agent_tool_registry_created",
        total_tools=len(tool_registry),
        tools=list(tool_registry.keys())
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

    # ========================================
    # 3. 添加数据加载工具 schema（内置工具）
    # ========================================
    schemas.append({
        "name": "load_data_from_memory",
        "description": (
            "从外部化存储读取数据（智能采样，避免token超限）。"
            "当你在观察结果中看到'data_id: schema:v1:hash'格式的数据引用时，"
            "说明数据已被外部化存储，使用此工具可以加载数据。"
            "工具会自动智能采样：保留首尾30%数据+中间40%均匀采样，适合时间序列分析。"
            "例如: 如果看到'data_id: pmf_result:v1:a1b2c3d4e5f6789012345678901234567890abcd'，"
            "调用 load_data_from_memory(data_id='pmf_result:v1:a1b2c3d4e5f6789012345678901234567890abcd', max_records=100) 可以加载数据。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_id": {
                    "type": "string",
                    "description": (
                        "数据引用ID（完整的data_id值）。"
                        "通常在观察结果中显示为'data_id: schema:v1:hash'格式，"
                        "例如：'pmf_result:v1:abc123'或'vocs_unified:v1:def456'"
                    )
                },
                "max_records": {
                    "type": "integer",
                    "description": (
                        "最大返回记录数，用于控制token消耗（默认100）。"
                        "如果数据总量超过此值，工具会智能采样："
                        "- 保留前30%数据（时间序列起点）"
                        "- 保留后30%数据（时间序列终点）"
                        "- 中间40%均匀采样"
                        "对于小数据集（<max_records），返回全部数据。"
                        "建议值：50-200，根据需要调整"
                    ),
                    "default": 100
                }
            },
            "required": ["data_id"]
        }
    })

    logger.info("tool_schemas_generated", count=len(schemas))

    return schemas


def get_tool_summaries() -> str:
    """
    获取所有工具的简短摘要（用于第一阶段工具选择）

    优化策略：
    - bash和Office工具：直接展示规范化参数示例（免二次调用）
    - 数据查询和分析工具：标记需要详细参数说明（强制二次调用）
    Returns:
        格式化的工具摘要字符串
    """
    # ========================================================================
    # 自然语言查询工具配置（参数简单直观，免二次调用）
    # ========================================================================
    NLQ_TOOLS = {
        "get_air_quality": {
            "desc": "空气质量数据（全国城市，只作为备用，广东省和济宁市的空气质量查询优先调用下述工具）",
            "example": "查询山东省2025-01-15至2025-01-16的小时空气质量数据"
        },
        "get_vocs_data": {
            "desc": "VOCs组分数据（广东省的VOCs组分站点级数据）",
            "example": "查询广州2025-01-15至2025-01-16的日度VOCs组分数据"
        },
        # get_particulate_data 已隐藏，请使用结构化查询工具：
        # - get_pm25_ionic (水溶性离子)
        # - get_pm25_carbon (碳组分 OC/EC)
        # - get_pm25_crustal (地壳元素)
        "get_guangdong_regular_stations": {
            "desc": "广东省区域空气质量数据",
            "example": "查询广东省各城市2025年1月的日度PM2.5浓度数据"
        },
        "get_jining_regular_stations": {
            "desc": "济宁市区域空气质量数据",
            "example": "查询济宁市各区县2025年1月的日度PM2.5浓度数据"
        }
    }

    # 简单工具（参数直观，免二次调用）
    # 注意：bash 工具已在提示词中直接描述，不需要两阶段加载
    SIMPLE_TOOLS = {
        "bash": {
            "desc": "执行安全的 Bash 命令（跨平台兼容，支持文件操作、数据处理、系统监控）。💡 查看目录内容请优先使用 read_file 工具（path=\"目录路径\"），而不是 dir/ls 命令",
            "example": 'command="python script.py" | command="npm install" | command="git status"',
            "params": "command(命令,必填), timeout(超时秒,可选,默认60), working_dir(工作目录,可选)"
        },
        "read_file": {
            "desc": "读取文件内容（纯文本和图片），图片文件会自动调用Vision API分析。支持查看目录内容（列出文件和子目录）。⚠️ 不支持docx、excel和PPT格式文件的读取",
            "example": 'path="D:/data.txt" | path="D:/chart.png"（自动分析）| path="D:/folder"（查看目录内容）| path="D:/doc.png", analysis_type="ocr"',
            "params": "path(文件或目录路径,必填), encoding(编码,可选,默认utf-8), auto_analyze(自动分析,可选,默认True), analysis_type(分析类型,可选:ocr/describe/chart/analyze)"
        },
        "analyze_image": {
            "desc": "使用通义千问VL模型分析图片（OCR/描述/图表分析）",
            "example": 'path="D:/chart.png", operation="chart", prompt="XX分析" | path="D:/doc.png", operation="ocr"',
            "params": "path(路径,必填), operation(操作,可选:ocr/describe/chart/analyze,默认analyze), prompt(自定义提示,尽量给出指导信息以获得更准确的分析结果)"
        },
        "search_knowledge_base": {
            "desc": "检索项目知识库文档",
            "example": 'query="臭氧污染来源分析"'
        }
        # ✅ 修复：Office 工具移到 COMPLEX_TOOLS，强制两阶段加载
        # 原因：避免 LLM 从 operation="list_sheets"/"list_slides" 类比出 "list_files"
    }

    # 必须二次调用的复杂工具（参数复杂或有隐式依赖）
    COMPLEX_TOOLS = {
        "calculate_pm_pmf",
        "calculate_vocs_pmf",
        "calculate_obm_full_chemistry",
        "get_weather_data",
        "analyze_upwind_enterprises",
        "get_pm25_ionic",  # 需要结构化参数：start_time, end_time, locations/code
        "get_pm25_carbon",  # 需要结构化参数
        "get_pm25_crustal",  # 需要结构化参数
        # ✅ Office 工具：支持分页读取，但仍需两阶段加载以展示所有操作类型和参数
        "word_processor",  # 支持操作: read（分页）, insert（插入文本）, search_and_replace（支持通配符）, tables, stats, batch_replace
        "excel_processor",  # 支持操作: list_sheets, read_range（分页）, write_range, stats
        "ppt_processor"  # 支持操作: list_slides, read（分页）, search_and_replace, stats
    }

    # 工具分类
    office_assist_tools = []  # 办公助理类工具
    query_tools = []
    analysis_tools = []
    viz_tools = []
    special_tools = []

    # 从 global_tool_registry 获取工具
    for tool_data in global_tool_registry.get_all_tools():
        tool = tool_data["tool"]
        if tool.is_available():
            schema = tool.get_function_schema()
            name = schema["name"]
            desc = schema.get("description", "")
            summary = desc.split('\n')[0].split('。')[0] if desc else name

            # ====================================================================
            # 判断工具类型并生成对应的工具摘要行
            # ====================================================================
            if name in NLQ_TOOLS:
                # 自然语言查询工具：直接展示规范化参数示例
                tool_info = NLQ_TOOLS[name]
                tool_line = f"  • {name}: {tool_info['desc']}（自然语言查询）"
                tool_line += f"\n    └─ 参数: question=\"{tool_info['example']}\""

            elif name in SIMPLE_TOOLS:
                # 简单工具：展示参数示例（包括可选的params说明）
                tool_info = SIMPLE_TOOLS[name]
                tool_line = f"  • {name}: {tool_info['desc']}"
                tool_line += f"\n    └─ 示例: {tool_info['example']}"
                # 如果有params说明，添加参数说明
                if 'params' in tool_info:
                    tool_line += f"\n    └─ 参数: {tool_info['params']}"

            elif name in COMPLEX_TOOLS:
                # 复杂工具：标记需要详细说明

                # ✅ Office 工具的完整说明（包含最佳实践）
                if name in ["word_processor", "excel_processor", "ppt_processor"]:
                    # word_processor: 添加完整description
                    if name == "word_processor":
                        tool_line = """  • word_processor: Word文档编辑工具（Windows）
    └─ 操作说明:
       • read: 读取文档
         必填: path, operation
         可选: start_index(起始段), end_index(结束段), max_chars(最大字符数)
         示例: {"path": "D:\\\\docs.docx", "operation": "read", "start_index": 0, "end_index": 100}
       • insert: 插入文本（支持在表格/图片前后插入）
         必填: path, operation, content, position

         【重要】定位表格/图片时必须同时指定target_type和target_index:
         示例1(表格前): {"operation": "insert", "position": "before", "target_type": "table", "target_index": 0, "content": "表1标题"}
         示例2(表格后): {"operation": "insert", "position": "after", "target_type": "table", "target_index": 0, "content": "分析"}
         示例3(文档末尾): {"operation": "insert", "position": "end", "content": "追加内容"}

         参数说明:
         - position: end(末尾)/start(开头)/after(后)/before(前)
         - target_type: text(默认,用target参数)/table(表格,需target_index)/image(图片,需target_index)
         - target_index: 表格/图片索引(0开始, target_type=table/image时必填)
         - target: 目标文本(target_type=text时必填,需精确匹配)

         错误示例: {"operation": "insert", "position": "before"} # 缺少content
         错误示例: {"operation": "insert", "position": "before", "content": "..."} # 缺少target或target_type+target_index
       • search_and_replace: 搜索替换
         必填: path, operation, search_text
         可选: replace_text(默认空即删除), use_wildcards(支持*和[]通配符), match_case, match_whole_word
         示例: {"path": "D:\\\\docs.docx", "operation": "search_and_replace", "search_text": "查找", "replace_text": "替换"}
       • tables: 读取表格（返回完整数据）
         必填: path, operation
         示例: {"path": "D:\\\\docs.docx", "operation": "tables"}
       • extract_images: 提取文档中的所有图片
         必填: path, operation
         可选: output_dir(输出目录,默认backend_data_registry/temp_images)
         示例: {"path": "D:\\\\docs.docx", "operation": "extract_images"}
         返回: {"status": "success", "images": [{"index": 0, "path": "...", "width": 800, "height": 600}], "count": 3}
       • extract_tables: 提取文档中的所有表格（结构化数据）
         必填: path, operation
         可选: output_format(输出格式,默认json,可选csv/xlsx)
         示例: {"path": "D:\\\\docs.docx", "operation": "extract_tables", "output_format": "json"}
         返回: {"status": "success", "tables": [{"index": 0, "rows": [...], "columns": 3}], "count": 2}
       • stats: 统计信息
         必填: path, operation
         示例: {"path": "D:\\\\docs.docx", "operation": "stats"}
       【insert最佳实践】
       1. 定位表格/图片前先用tables操作查看文档结构，获取正确的target_index
       2. 在表格/图片前后插入分析使用target_type="table"/"image"+target_index定位
       3. 文本目标需精确匹配，建议先read查看文档再复制准确文本作为target
       4. 对已存在的文档，优先使用索引定位而非文本匹配
       【提取功能说明】
       1. extract_images: 提取文档中所有图片并保存到指定目录,返回图片路径列表和尺寸信息
       2. extract_tables: 提取文档中所有表格并返回结构化数据,支持json/csv/xlsx格式 | 仅Windows"""
                    elif name == "excel_processor":
                        tool_line = f"  • {name}: {summary}\n    └─ Excel工作簿编辑（read/write/analysis）| 仅Windows"
                    elif name == "ppt_processor":
                        tool_line = f"  • {name}: {summary}\n    └─ PowerPoint演示文稿编辑（read/insert/replace）| 仅Windows"
                else:
                    tool_line = f"  • {name}: {summary}"
                    tool_line += f"\n    └─ ⚠️ 必须先查看详细参数说明"

                # 获取依赖信息
                dependency = TOOL_DEPENDENCIES.get(name, "")
                if dependency:
                    tool_line += f" | 前置: {dependency}"

            else:
                # 其他工具：显示依赖（如果有）
                dependency = TOOL_DEPENDENCIES.get(name, "")
                if dependency:
                    tool_line = f"  • {name}: {summary}"
                    tool_line += f"\n    └─ 前置: {dependency}"
                else:
                    tool_line = f"  • {name}: {summary}"

            # 分类
            if any(kw in name for kw in ["bash", "read_file", "analyze_image", "word_processor", "excel_processor", "ppt_processor"]):
                # 办公助理类：bash、文件读取、图片分析、Office工具
                office_assist_tools.append(tool_line)
            elif any(kw in name for kw in ["get_", "search_", "universal_"]):
                query_tools.append(tool_line)
            elif any(kw in name for kw in ["calculate_", "analyze_", "iaqi_", "ml_", "gfs_", "trajectory_"]):
                analysis_tools.append(tool_line)
            elif any(kw in name for kw in ["generate_", "smart_chart"]):
                viz_tools.append(tool_line)

    # 特殊工具
    special_tools.append("  • FINISH_SUMMARY: 生成数据分析报告（用于对数据查询和分析工具的结果进行专业分析，⚠️ 禁止在Office工具后调用，参数：data_id=\"数据ID\" 或 data_id=[\"id1\", \"id2\"]）")
    special_tools.append("  • FINISH: 简单完成（问候、确认类回复，参数：answer=\"回复内容\"）")
    special_tools.append("  • get_observed_weather: 获取实时天气观测数据")
    special_tools.append("  • load_data_from_memory: 从存储加载完整数据（参数：data_id）")
    # 注意：bash 工具已在提示词 TOOL_DESCRIPTIONS 中详细描述

    # 组装摘要
    result = "## 可用工具概览\n\n"

    if office_assist_tools:
        result += "**办公助理** (Office Assistant Tools):\n" + "\n".join(office_assist_tools) + "\n\n"

    if query_tools:
        result += "**查询工具** (Query Tools):\n" + "\n".join(query_tools) + "\n\n"

    if analysis_tools:
        result += "**分析工具** (Analysis Tools):\n" + "\n".join(analysis_tools) + "\n\n"

    if viz_tools:
        result += "**可视化工具** (Visualization Tools):\n" + "\n".join(viz_tools) + "\n\n"

    if special_tools:
        result += "**特殊工具** (Special Tools):\n" + "\n".join(special_tools) + "\n\n"

    result += """**使用说明**:
- 自然语言查询工具（含示例）：直接调用，参数格式为 question="城市+时间范围+时间粒度+数据类型"
- 标记 ⚠️ 的工具：必须先输出 args: null 请求详细参数（禁止直接猜测或编造参数）
- 其他工具：有参数示例的可直接调用
- **bash 工具**：已在系统提示词的 TOOL_DESCRIPTIONS 中详细说明（参数：command、timeout可选、working_dir可选），直接调用即可

⚠️ **重要提醒**：对于标记 ⚠️ 的工具（包括 Office 工具）：
1. 第一次调用：必须输出 "args": null 或 "args": {}"
2. 系统会返回详细的参数说明（包括所有可用的操作和分页选项）
3. 第二次调用：使用详细说明中的正确参数
❌ 禁止：直接猜测参数（如 operation="search"）或编造不存在的参数

📋 **完成工具使用指南**：
- **FINISH_SUMMARY**：用于对数据查询和分析工具的结果进行专业分析（需要 data_id）
  - ✅ 适用场景：PMF分析、OBM分析、化学组分分析等分析工具完成后
  - ✅ 适用场景：数据查询工具（get_air_quality、get_vocs_data 等）完成后需要专业报告
  - ❌ **禁止场景：Office 工具（word_processor/excel_processor/ppt_processor）执行后禁止调用**
    - Office 工具（文档读取/编辑/插入/替换）属于文档操作，不是数据分析任务
    - Office 工具完成后应使用 FINISH 工具进行简单说明或确认
    - Office 工具不需要以数据分析报告形式结束任务
- **FINISH**：用于简单回复和确认（直接在 answer 字段提供回复）
  - ✅ 适用场景：Office 工具执行完成后的操作确认和结果说明
  - ✅ 适用场景：简单问候、确认、说明性回复
  - ✅ 适用场景：文档编辑操作的完成说明（如"已插入新章节"、"已删除指定内容"等）
"""

    logger.info("tool_summaries_generated",
                query_count=len(query_tools),
                analysis_count=len(analysis_tools),
                viz_count=len(viz_tools),
                special_count=len(special_tools))

    return result


def get_detailed_schemas_for_tools(tool_names: List[str]) -> List[Dict[str, Any]]:
    """
    按需获取指定工具的详细Schema（第二阶段）

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

