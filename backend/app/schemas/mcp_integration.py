"""
MCP Tool Integration Framework - MCP工具集成框架

支持新MCP工具快速接入和使用统一数据格式

主要功能：
1. MCP工具自动注册
2. 数据格式自动转换
3. 工具链编排
4. 错误处理和回退机制
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Callable, Tuple
from enum import Enum
import asyncio
import structlog

from app.schemas.unified import UnifiedData, DataType, DataStatus
from app.schemas.data_adapter import DataAdapter, auto_convert

logger = structlog.get_logger()


class MCPToolType(str, Enum):
    """MCP工具类型"""
    QUERY = "query"  # 数据查询
    ANALYSIS = "analysis"  # 数据分析
    VISUALIZATION = "visualization"  # 可视化
    CUSTOM = "custom"  # 自定义


class MCPTool:
    """MCP工具包装器

    将外部MCP工具包装为本地工具，支持统一数据格式
    """

    def __init__(
        self,
        name: str,
        tool_type: MCPToolType,
        description: str,
        input_schema: Dict[str, Any],
        output_schema: Dict[str, Any],
        data_type: DataType,
        handler: Optional[Callable] = None,
        **kwargs
    ):
        self.name = name
        self.tool_type = tool_type
        self.description = description
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.data_type = data_type
        self.handler = handler
        self.kwargs = kwargs
        self.enabled = True

    async def execute(self, input_data: Dict[str, Any]) -> UnifiedData:
        """
        执行MCP工具

        Args:
            input_data: 输入数据

        Returns:
            UnifiedData: 统一格式的输出
        """
        try:
            logger.info(
                "mcp_tool_execute_start",
                tool_name=self.name,
                tool_type=self.tool_type.value
            )

            # 如果有本地处理器，直接调用
            if self.handler:
                result = await self.handler(input_data)
                # 转换为统一格式
                return auto_convert(result)

            # 如果是外部MCP工具，需要通过MCP协议调用
            # 这里模拟调用过程
            mcp_result = await self._call_external_mcp(input_data)

            # 转换为统一格式
            unified = auto_convert(mcp_result)

            logger.info(
                "mcp_tool_execute_complete",
                tool_name=self.name,
                success=unified.success,
                record_count=len(unified.data)
            )

            return unified

        except Exception as e:
            logger.error(
                "mcp_tool_execute_failed",
                tool_name=self.name,
                error=str(e),
                exc_info=True
            )

            return UnifiedData(
                status=DataStatus.FAILED,
                success=False,
                error=str(e),
                data=[],
                metadata=self._create_error_metadata(),
                summary=f"❌ MCP工具 {self.name} 执行失败"
            )

    async def _call_external_mcp(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """调用外部MCP工具（模拟）"""
        # 这里应该实现实际的MCP协议调用
        # 暂时返回模拟数据
        await asyncio.sleep(0.1)  # 模拟网络调用

        return {
            "success": True,
            "data": [
                {"time": "2025-11-06 10:00:00", "result": "MCP工具处理结果"}
            ],
            "summary": f"MCP工具 {self.name} 处理完成"
        }

    def _create_error_metadata(self) -> "DataMetadata":
        """创建错误元数据"""
        from app.schemas.unified import DataMetadata
        return DataMetadata(
            data_id=f"mcp_error:{self.name}:{id(self)}",
            data_type=self.data_type,
            source=f"mcp:{self.name}"
        )


class MCPOrchestrator:
    """MCP工具编排器

    支持工具链编排和依赖管理
    """

    def __init__(self):
        self.tools: Dict[str, MCPTool] = {}
        self.execution_history: List[Dict] = []

    def register_tool(self, tool: MCPTool) -> None:
        """注册MCP工具"""
        self.tools[tool.name] = tool
        logger.info(
            "mcp_tool_registered",
            tool_name=tool.name,
            tool_type=tool.tool_type.value,
            data_type=tool.data_type.value
        )

    async def execute_tool(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        use_unified_format: bool = True
    ) -> UnifiedData:
        """执行单个工具"""
        if tool_name not in self.tools:
            raise ValueError(f"未找到工具: {tool_name}")

        tool = self.tools[tool_name]
        result = await tool.execute(input_data)

        # 记录执行历史
        self.execution_history.append({
            "tool": tool_name,
            "timestamp": result.metadata.created_at,
            "success": result.success,
            "record_count": len(result.data)
        })

        return result

    async def execute_tool_chain(
        self,
        chain_config: List[Dict[str, Any]]
    ) -> List[UnifiedData]:
        """
        执行工具链

        Args:
            chain_config: 工具链配置
                [
                    {"tool": "get_vocs_data", "params": {...}},
                    {"tool": "calculate_pmf", "depends_on": "get_vocs_data", "params": {...}}
                ]

        Returns:
            List[UnifiedData]: 各工具的执行结果
        """
        results = []
        context = {}  # 工具间共享上下文

        for step in chain_config:
            tool_name = step["tool"]
            params = step.get("params", {})
            depends_on = step.get("depends_on")

            # 如果有依赖，传递上下文数据
            if depends_on and depends_on in [r.metadata.data_id for r in results]:
                # 找到依赖结果
                dep_result = next(
                    (r for r in results if r.metadata.data_id == depends_on),
                    None
                )
                if dep_result:
                    # 转换数据格式
                    if params.get("data_id"):
                        params["data_id"] = dep_result.metadata.data_id
                    else:
                        # 将数据嵌入参数
                        params["data"] = dep_result.to_dict()

            # 执行工具
            result = await self.execute_tool(tool_name, params)
            results.append(result)

            # 如果执行失败，可以选择停止或继续
            if not result.success and not step.get("continue_on_error", False):
                logger.warning(
                    "tool_chain_stopped_on_error",
                    tool=tool_name,
                    error=result.error
                )
                break

        return results

    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """获取工具信息"""
        if tool_name not in self.tools:
            return None

        tool = self.tools[tool_name]
        return {
            "name": tool.name,
            "type": tool.tool_type.value,
            "description": tool.description,
            "data_type": tool.data_type.value,
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
            "enabled": tool.enabled
        }

    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有工具"""
        return [self.get_tool_info(name) for name in self.tools.keys()]

    def get_execution_history(self) -> List[Dict]:
        """获取执行历史"""
        return self.execution_history


# ============================================================================
# 预定义MCP工具模板
# ============================================================================

def create_mcp_query_tool(
    name: str,
    data_type: DataType,
    description: str,
    query_fields: List[str]
) -> MCPTool:
    """创建MCP查询工具模板"""

    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "查询描述"
            },
            "time_range": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"}
                }
            },
            "location": {
                "type": "object",
                "properties": {
                    "station": {"type": "string"},
                    "city": {"type": "string"}
                }
            }
        },
        "required": ["query"]
    }

    return MCPTool(
        name=name,
        tool_type=MCPToolType.QUERY,
        description=description,
        input_schema=input_schema,
        output_schema={"data": "array", "success": "boolean"},
        data_type=data_type
    )


def create_mcp_analysis_tool(
    name: str,
    data_type: DataType,
    description: str,
    required_inputs: List[str]
) -> MCPTool:
    """创建MCP分析工具模板"""

    input_schema = {
        "type": "object",
        "properties": {
            "data": {
                "type": "array",
                "description": "输入数据"
            },
            "parameters": {
                "type": "object",
                "description": "分析参数"
            }
        },
        "required": required_inputs
    }

    return MCPTool(
        name=name,
        tool_type=MCPToolType.ANALYSIS,
        description=description,
        input_schema=input_schema,
        output_schema={"result": "object", "success": "boolean"},
        data_type=data_type
    )


# ============================================================================
# 示例：创建自定义MCP工具
# ============================================================================

"""
示例1: 创建VOCs数据查询MCP工具
```python
from app.schemas.mcp_integration import MCPOrchestrator, MCPTool, MCPToolType, DataType
import asyncio

# 初始化编排器
orchestrator = MCPOrchestrator()

# 创建MCP工具
vocs_query_tool = MCPTool(
    name="mcp_vocs_query",
    tool_type=MCPToolType.QUERY,
    description="MCP接口的VOCs数据查询",
    input_schema={
        "type": "object",
        "properties": {
            "station": {"type": "string"},
            "time_range": {"type": "object"}
        }
    },
    output_schema={"data": "array"},
    data_type=DataType.VOCs,
    handler=None  # 将通过MCP协议调用
)

# 注册工具
orchestrator.register_tool(vocs_query_tool)

# 执行工具
result = await orchestrator.execute_tool("mcp_vocs_query", {
    "station": "深圳南山站",
    "time_range": {
        "start": "2025-08-09 00:00:00",
        "end": "2025-08-10 00:00:00"
    }
})

print(f"执行结果: {result.success}")
print(f"数据记录数: {len(result.data)}")
```

示例2: 工具链编排
```python
# 配置工具链
tool_chain = [
    {
        "tool": "get_component_data",
        "params": {"question": "获取深圳VOCs数据"}
    },
    {
        "tool": "calculate_pmf",
        "depends_on": "get_component_data",  # 依赖上一步结果
        "params": {
            "station_name": "深圳",
            "pollutant_type": "VOCs"
        }
    },
    {
        "tool": "smart_chart_generator",
        "depends_on": "calculate_pmf",  # 依赖PMF结果
        "params": {
            "chart_type": "pie",
            "title": "污染源贡献率"
        }
    }
]

# 执行工具链
results = await orchestrator.execute_tool_chain(tool_chain)

for i, result in enumerate(results):
    print(f"步骤{i+1} - {result.metadata.source}: {result.success}")
```

示例3: 新MCP工具快速接入
```python
from app.schemas.mcp_integration import create_mcp_query_tool, DataType

# 快速创建MCP工具
custom_tool = create_mcp_query_tool(
    name="mcp_satellite_data",
    data_type=DataType.CUSTOM,
    description="卫星数据查询",
    query_fields=["lat", "lon", "time_range", "sensor_type"]
)

# 注册并使用
orchestrator.register_tool(custom_tool)
```
"""
