"""
Memory Tools Handler Module (简化版)

处理内存相关工具的注册。

✅ 统一架构实施后，所有分析工具都使用 Context-Aware V2，
不再需要旧包装器相关的代码。

注意：
- load_data_from_memory 工具已完全移除
- 此类保留用于架构兼容性，暂无实际注册的工具
"""
import structlog

logger = structlog.get_logger()


class MemoryToolsHandler:
    """
    内存工具处理器 (简化版)

    ✅ 统一架构：所有分析工具现在都使用 Context-Aware V2，
    不再需要旧包装器 (wrap_analysis_tool) 和数据解析相关方法，
    冗余代码已完全移除。

    注意：
    - load_data_from_memory 工具已完全移除
    - 此类保留用于架构兼容性，暂无实际注册的工具
    """

    def __init__(self, memory_manager, tool_executor):
        """
        初始化内存工具处理器

        Args:
            memory_manager: 混合记忆管理器
            tool_executor: 工具执行器
        """
        self.memory = memory_manager
        self.executor = tool_executor

    def register_memory_tools(self):
        """注册与记忆相关的工具 - 暂无工具"""
        # load_data_from_memory 工具已完全移除
        logger.info("memory_tools_registered", tools=[])

        # 统一架构已完全实施
        logger.info(
            "unified_architecture_active",
            architecture="Input Adapter + Context-Aware V2",
            context_aware_tools=["calculate_pmf", "get_component_data"]
        )
