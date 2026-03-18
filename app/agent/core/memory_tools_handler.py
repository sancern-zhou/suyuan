"""
Memory Tools Handler Module (简化版)

处理内存相关工具的注册。

✅ 统一架构实施后，所有分析工具都使用 Context-Aware V2，
不再需要旧包装器相关的代码。
"""
import structlog

logger = structlog.get_logger()


class MemoryToolsHandler:
    """
    内存工具处理器 (简化版)

    仅负责注册与记忆相关的工具。

    ✅ 统一架构：所有分析工具现在都使用 Context-Aware V2，
    不再需要旧包装器 (wrap_analysis_tool) 和数据解析相关方法，
    冗余代码已完全移除。

    保留功能:
    - register_memory_tools(): 注册 load_data_from_memory 工具
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
        """注册与记忆相关的工具 - 仅保留 load_data_from_memory"""
        try:
            from app.agent.tools.load_data_from_memory import load_data_from_memory

            # 创建一个闭包,绑定memory_manager - 接受但忽略 context 参数
            async def load_data_wrapper(data_id: str, context=None, **kwargs):
                return await load_data_from_memory(
                    data_id=data_id,
                    _memory_manager=self.memory
                )

            # 注册到executor
            self.executor.register_tool("load_data_from_memory", load_data_wrapper)

            logger.info("memory_tools_registered", tools=["load_data_from_memory"])

            # 统一架构已完全实施
            logger.info(
                "unified_architecture_active",
                architecture="Input Adapter + Context-Aware V2",
                context_aware_tools=["calculate_pmf", "calculate_obm_full_chemistry", "get_component_data"]
            )

        except Exception as e:
            logger.warning(
                "failed_to_register_memory_tools",
                error=str(e),
                message="Agent will not be able to load externalized data"
            )
