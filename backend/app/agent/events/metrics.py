"""
Metrics Collector - 工具执行指标收集器

Phase 3.2: 订阅 EventBus 事件，收集工具执行指标
"""

from typing import Dict, List
from dataclasses import dataclass, field
from datetime import datetime
import structlog

logger = structlog.get_logger()


@dataclass
class ToolMetric:
    """工具执行指标

    Attributes:
        tool_name: 工具名称
        call_count: 调用次数
        success_count: 成功次数
        failure_count: 失败次数
        avg_duration_ms: 平均执行时间（毫秒）
        total_duration_ms: 总执行时间（毫秒）
        last_execution: 最后执行时间
    """
    tool_name: str
    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_duration_ms: float = 0.0
    total_duration_ms: float = 0.0
    last_execution: Optional[datetime] = None


class MetricsCollector:
    """指标收集器（订阅 EventBus 事件）

    订阅工具生命周期事件，收集性能指标和统计信息。
    """

    def __init__(self, event_bus):
        """初始化指标收集器

        Args:
            event_bus: EventBus 实例
        """
        self._metrics: Dict[str, ToolMetric] = {}
        self.event_bus = event_bus

        # 订阅事件
        self.event_bus.subscribe("tool_execution_start", self._on_start)
        self.event_bus.subscribe("tool_execution_end", self._on_end)
        self.event_bus.subscribe("tool_error", self._on_error)

        logger.info("metrics_collector_initialized")

    def _on_start(self, data: Dict):
        """工具开始执行

        Args:
            data: 事件数据
        """
        tool_name = data["toolName"]
        if tool_name not in self._metrics:
            self._metrics[tool_name] = ToolMetric(tool_name=tool_name)

    def _on_end(self, data: Dict):
        """工具执行完成

        Args:
            data: 事件数据
        """
        tool_name = data["toolName"]
        duration_ms = data["duration_ms"]

        if tool_name in self._metrics:
            metric = self._metrics[tool_name]
            metric.call_count += 1
            metric.success_count += 1
            metric.total_duration_ms += duration_ms
            metric.avg_duration_ms = metric.total_duration_ms / metric.call_count
            metric.last_execution = datetime.now()

            logger.debug(
                "tool_metric_updated",
                tool_name=tool_name,
                call_count=metric.call_count,
                avg_duration_ms=metric.avg_duration_ms
            )

    def _on_error(self, data: Dict):
        """工具执行错误

        Args:
            data: 事件数据
        """
        tool_name = data["toolName"]
        if tool_name in self._metrics:
            self._metrics[tool_name].failure_count += 1

    def get_metrics(self, tool_name: str) -> Optional[ToolMetric]:
        """获取特定工具的指标

        Args:
            tool_name: 工具名称

        Returns:
            工具指标，如果不存在则返回 None
        """
        return self._metrics.get(tool_name)

    def get_all_metrics(self) -> List[ToolMetric]:
        """获取所有指标

        Returns:
            所有工具指标列表
        """
        return list(self._metrics.values())
