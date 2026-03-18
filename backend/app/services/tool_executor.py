"""
工具执行器 - 通过ReAct Agent工具注册表调用
遵循Context-Aware V2架构
"""
from typing import Dict, Any, Optional
import structlog

from app.schemas.report_generation import ToolCall, ToolResult
from app.agent.context.execution_context import ExecutionContext

logger = structlog.get_logger()

class ToolExecutor:
    """工具执行器 - 通过ReAct Agent工具注册表调用"""

    def __init__(self, react_agent):
        """
        初始化工具执行器

        Args:
            react_agent: ReAct Agent实例，用于调用工具注册表
        """
        self.react_agent = react_agent

    async def execute_via_context(
        self,
        context: ExecutionContext,
        tool_call: ToolCall,
        max_retries: int = 2
    ) -> ToolResult:
        """
        通过ReAct Agent工具注册表执行工具

        遵循Context-Aware V2架构：
        1. 通过ReAct Agent的工具选择机制
        2. 自动存储结果到Context
        3. 返回字符串ID而非Handle对象

        Args:
            context: Context-Aware V2上下文
            tool_call: 工具调用信息
            max_retries: 最大重试次数

        Returns:
            ToolResult: 工具执行结果
        """
        import time
        start_time = time.time()

        try:
            logger.info(f"Executing tool: {tool_call.name}")

            # 通过ReAct Agent的工具选择机制调用
            # 这会自动处理工具选择、参数验证等
            result = await self.react_agent.call_tool(
                tool_name=tool_call.name,
                parameters=tool_call.params
            )

            execution_time = time.time() - start_time

            # 构建ToolResult
            tool_result = ToolResult(
                success=result.get('success', False),
                data=result.get('data'),
                error=result.get('error'),
                execution_time=execution_time
            )

            # 自动存储到Context-Aware V2（遵循架构）
            if tool_result.success and tool_result.data:
                try:
                    data_id = context.save_data(
                        data=tool_result.data,
                        schema=tool_call.schema or "report_data"
                    )
                    tool_result.data_id = data_id
                    logger.info(f"Data stored with ID: {data_id}")
                except Exception as e:
                    logger.warning(f"Failed to store data in context: {str(e)}")
                    # 数据存储失败不影响主流程

            return tool_result

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Tool execution failed: {str(e)}"
            logger.error(error_msg)

            # 返回失败结果
            return ToolResult(
                success=False,
                error=error_msg,
                execution_time=execution_time
            )

    async def execute_batch_via_context(
        self,
        context: ExecutionContext,
        tool_calls: list[ToolCall],
        parallel: bool = True
    ) -> list[ToolResult]:
        """
        批量执行工具调用

        Args:
            context: Context-Aware V2上下文
            tool_calls: 工具调用列表
            parallel: 是否并行执行

        Returns:
            list[ToolResult]: 执行结果列表
        """
        if parallel:
            # 并行执行
            import asyncio
            tasks = [
                self.execute_via_context(context, tool_call)
                for tool_call in tool_calls
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 处理异常
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    processed_results.append(ToolResult(
                        success=False,
                        error=str(result)
                    ))
                else:
                    processed_results.append(result)

            return processed_results
        else:
            # 顺序执行
            results = []
            for tool_call in tool_calls:
                result = await self.execute_via_context(context, tool_call)
                results.append(result)
            return results
