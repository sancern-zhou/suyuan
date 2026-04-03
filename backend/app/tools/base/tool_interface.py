"""
LLM Tool Interface

LLM工具的基础接口

Updated to support ExecutionContext for context-based data access.
Tools can now optionally receive an ExecutionContext parameter for:
- Loading data by reference (data_id)
- Saving results for downstream tools
- Accessing session metadata
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING
from enum import Enum
import structlog

if TYPE_CHECKING:
    from app.agent.context import ExecutionContext

logger = structlog.get_logger()


class ToolCategory(Enum):
    """工具类别"""
    QUERY = "query"                 # 查询工具（从数据库读取）
    ANALYSIS = "analysis"           # 分析工具（执行计算）
    VISUALIZATION = "visualization" # 可视化工具（生成配置）
    TASK_MANAGEMENT = "task_management"  # 任务管理工具（创建、更新、查询任务）
    PLANNING = "planning"           # 规划工具（生成执行计划）


class ToolStatus(Enum):
    """工具状态"""
    IDLE = "idle"
    RUNNING = "running"
    DISABLED = "disabled"
    ERROR = "error"


class LLMTool(ABC):
    """
    LLM工具基类

    所有LLM可调用的工具都应继承此类

    Version 2.0 Changes:
    - Tools can now optionally accept an ExecutionContext parameter
    - Enables context-based data access without passing full payloads through LLM
    - Backward compatible: context parameter is optional

    Example (New Context-Aware Tool):
        async def execute(
            self,
            context: ExecutionContext,
            station_name: str,
            data_id: str
        ):
            # Load data by reference
            vocs_data = context.get_data(data_id, expected_schema="vocs")
            # Process...
            result_id = context.save_data(result, schema="pmf_result")
            return {"success": True, "data_id": result_id}

    Example (Legacy Tool - Still Works):
        async def execute(self, station_name: str, pollutant: str):
            # Traditional implementation without context
            return {"success": True, "data": result}
    """

    def __init__(
        self,
        name: str,
        description: str,
        category: ToolCategory,
        function_schema: Optional[Dict[str, Any]] = None,
        version: str = "1.0.0",
        requires_context: bool = False
    ):
        self.name = name
        self.description = description
        self.category = category
        self.function_schema = function_schema
        self.version = version
        self.enabled = True
        self.status = ToolStatus.IDLE
        self.requires_context = requires_context  # New: indicate if tool needs context

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """
        执行工具（LLM调用此方法）

        Args:
            **kwargs: 工具参数
                - May include 'context: ExecutionContext' for context-aware tools
                - Other business parameters as defined in function_schema

        Returns:
            Any: 工具执行结果
                Standard format: {"success": bool, "data_id": str, "summary": str, ...}
        """
        pass

    def get_function_schema(self) -> Dict[str, Any]:
        """
        获取OpenAI Function Calling格式的函数定义

        Returns:
            Dict: 函数定义JSON
        """
        if self.function_schema:
            return self.function_schema

        # 默认schema
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }

    def is_available(self) -> bool:
        """检查工具是否可用"""
        return self.enabled and self.status != ToolStatus.ERROR

    def disable(self, reason: str = ""):
        """禁用工具"""
        self.enabled = False
        self.status = ToolStatus.DISABLED
        logger.info(f"tool_disabled", tool=self.name, reason=reason)

    def enable(self):
        """启用工具"""
        self.enabled = True
        self.status = ToolStatus.IDLE
        logger.info(f"tool_enabled", tool=self.name)

    async def run(self, **kwargs) -> Any:
        """运行工具（由LLM调用）"""
        if not self.is_available():
            logger.warning(
                "tool_not_available",
                tool=self.name,
                status=self.status.value
            )
            return None

        self.status = ToolStatus.RUNNING
        logger.info("tool_started", tool=self.name, params=kwargs)

        try:
            result = await self.execute(**kwargs)
            self.status = ToolStatus.IDLE
            logger.info("tool_completed", tool=self.name)
            return result
        except Exception as e:
            self.status = ToolStatus.ERROR
            logger.error(
                "tool_failed",
                tool=self.name,
                error=str(e),
                exc_info=True
            )
            return None
