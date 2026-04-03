"""
动作处理器基类

定义 ReAct 循环中各种动作类型的处理接口。
"""

from typing import Dict, Any, AsyncGenerator
from abc import ABC, abstractmethod


class ActionHandler(ABC):
    """动作处理器基类"""

    def __init__(self, loop_instance):
        """初始化处理器

        Args:
            loop_instance: ReActLoop 实例
        """
        self.loop = loop_instance
        self.memory = loop_instance.memory
        self.planner = loop_instance.planner
        self.executor = loop_instance.executor
        self.formatter_registry = loop_instance.formatter_registry

    @abstractmethod
    async def handle(self, action: Dict[str, Any], **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        """处理动作

        Args:
            action: 动作字典
            **kwargs: 额外参数（如 iteration, enhanced_query 等）

        Yields:
            流式事件
        """
        pass

    @property
    @abstractmethod
    def action_type(self) -> str:
        """返回该处理器处理的动作类型

        Returns:
            动作类型字符串（如 "FINAL_ANSWER", "TOOL_CALL"）
        """
        pass

    def _format_observation(self, observation: Dict[str, Any]) -> str:
        """格式化观察结果（便捷方法）

        Args:
            observation: 观察结果字典

        Returns:
            格式化的字符串
        """
        return self.loop._format_observation(observation)
