"""
StreamingToolExecutor - 流式工具执行器

参考 Claude Code 的 StreamingToolExecutor 实现，在 LLM 流式输出过程中
就开始执行工具，无需等待整个响应结束。

核心特性：
1. 工具即时启动：content_block_stop (tool_use) 后立即启动执行
2. 并发安全分组：只读工具并行执行，写入工具串行执行
3. 结果异步收集：getCompletedResults() / getRemainingResults()
4. 中断安全：支持 abort 信号，丢弃未开始/中断正在执行的工具
5. 错误隔离：单个工具失败不影响其他工具

时序对比：
  旧流程：LLM 完整输出 → 逐个执行工具 → 返回结果
  新流程：LLM 输出 tool_use → 立即启动工具 → 流中返回已完成结果
"""

import asyncio
import json
import structlog
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = structlog.get_logger()


class ToolStatus(Enum):
    """工具执行状态"""
    PENDING = "pending"        # 已添加，等待执行
    RUNNING = "running"        # 正在执行
    COMPLETED = "completed"    # 执行完成
    FAILED = "failed"          # 执行失败
    CANCELLED = "cancelled"    # 被取消


@dataclass
class ToolExecution:
    """单次工具执行的完整记录"""
    tool_use_id: str
    tool_name: str
    tool_input: Dict[str, Any]
    status: ToolStatus = ToolStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    is_concurrency_safe: bool = False
    task: Optional[asyncio.Task] = None
    _completion_event: asyncio.Event = field(default_factory=asyncio.Event)

    def mark_completed(self, result: Dict[str, Any]):
        self.status = ToolStatus.COMPLETED
        self.result = result
        self._completion_event.set()

    def mark_failed(self, error: str):
        self.status = ToolStatus.FAILED
        self.error = error
        self._completion_event.set()

    def mark_cancelled(self):
        self.status = ToolStatus.CANCELLED
        self._completion_event.set()

    async def wait(self):
        """等待执行完成"""
        await self._completion_event.wait()


# 默认并发安全的工具列表（只读操作）
DEFAULT_CONCURRENCY_SAFE_TOOLS = frozenset({
    "read_file", "grep", "glob", "search_files", "list_directory",
    "get_weather_data", "get_vocs_data", "get_pm25_ionic",
    "get_pm25_carbon", "get_pm25_elements", "get_guangdong_regular_stations",
    "analyze_image", "list_skills",
})


class StreamingToolExecutor:
    """
    流式工具执行器

    在 LLM 流式输出过程中，每收到一个完整的 tool_use block
    就立即启动该工具的执行。已完成的工具结果可以通过
    getCompletedResults() 在流中获取，无需等待所有工具完成。

    用法：
        executor = StreamingToolExecutor(tool_executor=..., tool_registry=...)

        # 流式过程中，每收到一个 tool_use block
        executor.addTool(tool_block)

        # 流中持续检查已完成的结果
        for result in executor.getCompletedResults():
            yield result.message

        # 流式结束后，获取剩余结果
        async for update in executor.getRemainingResults():
            yield update.message

        # 如果需要丢弃（如中断或模型回退）
        executor.discard()
    """

    def __init__(
        self,
        tool_executor,
        tool_registry: Optional[Dict] = None,
        concurrency_safe_tools: Optional[frozenset] = None,
        max_concurrency: int = 10,
    ):
        """
        Args:
            tool_executor: ToolExecutor 实例，用于实际执行工具
            tool_registry: 工具注册表（用于判断是否并发安全）
            concurrency_safe_tools: 并发安全工具名称集合
            max_concurrency: 最大并发执行数
        """
        self.tool_executor = tool_executor
        self.tool_registry = tool_registry or {}
        self.concurrency_safe_tools = concurrency_safe_tools or DEFAULT_CONCURRENCY_SAFE_TOOLS
        self.max_concurrency = max_concurrency

        # 执行中的工具列表（保持添加顺序）
        self._executions: List[ToolExecution] = []
        # 已完成但尚未被消费的结果索引
        self._next_yield_index: int = 0
        # 信号量控制最大并发
        self._semaphore = asyncio.Semaphore(max_concurrency)
        # 是否已被丢弃
        self._discarded = False
        # 串行队列锁（非并发安全工具需要串行执行）
        self._serial_lock = asyncio.Lock()

    def _is_concurrency_safe(self, tool_name: str, tool_input: Dict[str, Any]) -> bool:
        """判断工具调用是否并发安全（只读操作）"""
        # 1. 先检查预设的安全列表
        if tool_name in self.concurrency_safe_tools:
            return True

        # 2. 检查工具自身声明的 isReadOnly
        tool_func = self.tool_registry.get(tool_name)
        if tool_func and hasattr(tool_func, 'is_read_only'):
            try:
                return bool(tool_func.is_read_only(tool_input))
            except Exception:
                pass

        # 3. 默认不安全
        return False

    def addTool(
        self,
        tool_use_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        iteration: int = 0,
    ) -> None:
        """
        添加一个工具调用并立即启动执行

        参考 Claude Code: streamingToolExecutor.addTool(toolBlock, message)
        在 content_block_stop 后调用此方法。

        Args:
            tool_use_id: tool_use block 的 ID
            tool_name: 工具名称
            tool_input: 工具输入参数
            iteration: 当前迭代次数
        """
        if self._discarded:
            logger.warning("streaming_tool_executor_discarded", tool_name=tool_name)
            return

        is_safe = self._is_concurrency_safe(tool_name, tool_input)

        execution = ToolExecution(
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            tool_input=tool_input,
            is_concurrency_safe=is_safe,
        )

        self._executions.append(execution)

        # 立即启动异步执行
        execution.task = asyncio.create_task(
            self._execute_with_semaphore(execution, iteration),
            name=f"streaming_tool_{tool_name}_{tool_use_id[:8]}",
        )

        logger.info(
            "streaming_tool_started",
            tool_name=tool_name,
            tool_use_id=tool_use_id[:12],
            is_concurrency_safe=is_safe,
            total_executions=len(self._executions),
        )

    async def _execute_with_semaphore(
        self,
        execution: ToolExecution,
        iteration: int,
    ) -> None:
        """带信号量控制的执行包装"""
        async with self._semaphore:
            if self._discarded:
                execution.mark_cancelled()
                return

            if execution.is_concurrency_safe:
                # 并发安全工具：直接执行
                await self._run_execution(execution, iteration)
            else:
                # 非并发安全工具：串行执行
                async with self._serial_lock:
                    if self._discarded:
                        execution.mark_cancelled()
                        return
                    await self._run_execution(execution, iteration)

    async def _run_execution(
        self,
        execution: ToolExecution,
        iteration: int,
    ) -> None:
        """执行单个工具调用"""
        execution.status = ToolStatus.RUNNING

        try:
            # 使用 ToolExecutor 的 execute_tool_with_retry 方法
            # 它已经包含了 InputAdapter + ExecutionContext + 重试逻辑
            result = await self.tool_executor.execute_tool_with_retry(
                tool_name=execution.tool_name,
                tool_args=execution.tool_input,
                tool_call_id=execution.tool_use_id,
                iteration=iteration,
            )

            execution.mark_completed(result)

            logger.info(
                "streaming_tool_completed",
                tool_name=execution.tool_name,
                tool_use_id=execution.tool_use_id[:12],
                success=result.get("success", False),
            )

        except asyncio.CancelledError:
            execution.mark_cancelled()
            logger.info(
                "streaming_tool_cancelled",
                tool_name=execution.tool_name,
            )

        except Exception as e:
            execution.mark_failed(str(e))
            logger.error(
                "streaming_tool_failed",
                tool_name=execution.tool_name,
                error=str(e),
            )

    def getCompletedResults(self) -> List[Dict[str, Any]]:
        """
        获取已完成但尚未被消费的工具结果

        参考 Claude Code: streamingToolExecutor.getCompletedResults()
        在流式循环中反复调用此方法，获取已完成的工具结果。

        Returns:
            结果列表，每项包含：
            {
                "message": Dict[str, Any],  # 可以 yield 给前端的事件
                "tool_use_id": str,
                "tool_name": str,
                "result": Dict[str, Any],
            }
        """
        results = []

        while self._next_yield_index < len(self._executions):
            execution = self._executions[self._next_yield_index]

            if execution.status in (ToolStatus.COMPLETED, ToolStatus.FAILED, ToolStatus.CANCELLED):
                self._next_yield_index += 1

                is_error = execution.status in (ToolStatus.FAILED, ToolStatus.CANCELLED)
                result_data = execution.result if execution.status == ToolStatus.COMPLETED else {
                    "success": False,
                    "error": execution.error or "工具执行被取消",
                    "summary": f"工具 {execution.tool_name} 执行{'失败' if execution.status == ToolStatus.FAILED else '被取消'}",
                }

                results.append({
                    "message": {
                        "type": "tool_result",
                        "data": {
                            "tool_use_id": execution.tool_use_id,
                            "tool_name": execution.tool_name,
                            "result": result_data,
                            "is_error": is_error,
                        },
                    },
                    "tool_use_id": execution.tool_use_id,
                    "tool_name": execution.tool_name,
                    "result": result_data,
                })
            else:
                # 还在执行中，停止消费（保持顺序）
                break

        return results

    async def getRemainingResults(self) -> Any:
        """
        获取所有尚未完成的工具结果（等待执行完成后返回）

        参考 Claude Code: streamingToolExecutor.getRemainingResults()
        在流式循环结束后调用此方法，等待所有工具完成。

        Yields:
            与 getCompletedResults() 格式相同的字典
        """
        # 等待所有执行完成
        pending = [
            exe for exe in self._executions
            if exe.status in (ToolStatus.PENDING, ToolStatus.RUNNING)
        ]

        if pending:
            await asyncio.gather(
                *[exe.wait() for exe in pending],
                return_exceptions=True,
            )

        # 返回所有尚未消费的结果
        while self._next_yield_index < len(self._executions):
            execution = self._executions[self._next_yield_index]

            if execution.status in (ToolStatus.COMPLETED, ToolStatus.FAILED, ToolStatus.CANCELLED):
                self._next_yield_index += 1

                is_error = execution.status in (ToolStatus.FAILED, ToolStatus.CANCELLED)
                result_data = execution.result if execution.status == ToolStatus.COMPLETED else {
                    "success": False,
                    "error": execution.error or "工具执行被取消",
                    "summary": f"工具 {execution.tool_name} 执行{'失败' if execution.status == ToolStatus.FAILED else '被取消'}",
                }

                yield {
                    "message": {
                        "type": "tool_result",
                        "data": {
                            "tool_use_id": execution.tool_use_id,
                            "tool_name": execution.tool_name,
                            "result": result_data,
                            "is_error": is_error,
                        },
                    },
                    "tool_use_id": execution.tool_use_id,
                    "tool_name": execution.tool_name,
                    "result": result_data,
                }
            else:
                # 不应该到达这里，因为已经等待了所有执行完成
                self._next_yield_index += 1
                logger.warning(
                    "streaming_tool_unexpected_status",
                    tool_name=execution.tool_name,
                    status=execution.status.value,
                )

    def discard(self) -> None:
        """
        丢弃所有未开始和正在执行的工具

        参考 Claude Code: streamingToolExecutor.discard()
        用于流式回退（fallback）或中断场景，取消所有待执行工具。

        已完成的工具结果仍然可以通过 getCompletedResults() 获取。
        """
        self._discarded = True

        cancelled_count = 0
        for execution in self._executions:
            if execution.status in (ToolStatus.PENDING, ToolStatus.RUNNING):
                if execution.task and not execution.task.done():
                    execution.task.cancel()
                execution.mark_cancelled()
                cancelled_count += 1

        logger.info(
            "streaming_tool_executor_discarded",
            total_executions=len(self._executions),
            cancelled_count=cancelled_count,
        )

    @property
    def has_pending_or_running(self) -> bool:
        """是否有正在执行或等待执行的工具"""
        return any(
            exe.status in (ToolStatus.PENDING, ToolStatus.RUNNING)
            for exe in self._executions
        )

    @property
    def completed_count(self) -> int:
        """已完成的工具数量"""
        return sum(
            1 for exe in self._executions
            if exe.status == ToolStatus.COMPLETED
        )

    @property
    def total_count(self) -> int:
        """总工具数量"""
        return len(self._executions)
