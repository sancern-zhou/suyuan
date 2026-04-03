"""
格式化器注册表

管理所有观察结果格式化器的注册和查找。
"""

from typing import Dict, Any, Type, Optional, List
import structlog

from .base import ObservationFormatter


logger = structlog.get_logger()


class FormatterRegistry:
    """格式化器注册表（参考 ToolRegistry 设计）"""

    def __init__(self):
        self._formatters: Dict[str, Type[ObservationFormatter]] = {}
        self._priority_order: List[tuple] = []

    def register(self, formatter: Type[ObservationFormatter]) -> None:
        """注册格式化器（自动按优先级排序）

        Args:
            formatter: 格式化器类
        """
        formatter_name = formatter.__name__
        priority = formatter.get_priority()

        self._formatters[formatter_name] = formatter
        self._priority_order.append((priority, formatter_name))

        # 按优先级排序（数字越小优先级越高）
        self._priority_order.sort(key=lambda x: x[0])

        logger.info(
            "formatter_registered",
            formatter=formatter_name,
            priority=priority,
            total_formatters=len(self._formatters)
        )

    def get_formatter(self, generator: str, data: Dict[str, Any]) -> Optional[Type[ObservationFormatter]]:
        """根据工具名称和数据获取合适的格式化器

        Args:
            generator: 工具生成器名称（如 "analyze_image", "read_file"）
            data: 工具返回的 data 字段

        Returns:
            合适的格式化器类，如果没有找到则返回 None
        """
        for priority, formatter_name in self._priority_order:
            formatter = self._formatters[formatter_name]
            try:
                if formatter.can_handle(generator, data):
                    logger.debug(
                        "formatter_matched",
                        generator=generator,
                        formatter=formatter_name,
                        priority=priority
                    )
                    return formatter
            except Exception as e:
                logger.warning(
                    "formatter_check_failed",
                    formatter=formatter_name,
                    generator=generator,
                    error=str(e)
                )

        logger.debug(
            "no_formatter_matched",
            generator=generator,
            data_keys=list(data.keys()) if data else []
        )
        return None

    def list_formatters(self) -> List[str]:
        """列出所有已注册的格式化器名称（按优先级排序）

        Returns:
            格式化器名称列表（按优先级升序排列）
        """
        return [name for priority, name in self._priority_order]

    def get_formatter_count(self) -> int:
        """获取已注册的格式化器数量

        Returns:
            格式化器数量
        """
        return len(self._formatters)
