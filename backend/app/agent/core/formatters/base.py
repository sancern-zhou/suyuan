"""
观察结果格式化器基类

定义格式化器接口和通用工具方法。
"""

from typing import Dict, Any, List
from abc import ABC, abstractmethod
import json


class ObservationFormatter(ABC):
    """观察结果格式化器基类"""

    @classmethod
    @abstractmethod
    def can_handle(cls, generator: str, data: Dict[str, Any]) -> bool:
        """判断是否可以处理该工具的结果

        Args:
            generator: 工具生成器名称（如 "analyze_image", "read_file"）
            data: 工具返回的 data 字段

        Returns:
            是否可以处理该工具
        """
        pass

    @classmethod
    @abstractmethod
    def format(cls, data: Dict[str, Any], metadata: Dict[str, Any]) -> List[str]:
        """格式化工具结果为字符串列表

        Args:
            data: 工具返回的 data 字段
            metadata: 工具返回的 metadata 字段

        Returns:
            格式化的字符串列表
        """
        pass

    @classmethod
    def get_priority(cls) -> int:
        """获取格式化器优先级（数字越小优先级越高）

        Returns:
            优先级（默认100）
        """
        return 100

    @classmethod
    def _add_status_line(cls, lines: List[str], success: bool) -> None:
        """添加状态行（通用方法）

        Args:
            lines: 字符串列表
            success: 是否成功
        """
        lines.append(f"**状态**: {'成功' if success else '失败'}")

    @classmethod
    def _add_error_line(cls, lines: List[str], error: str) -> None:
        """添加错误行（通用方法）

        Args:
            lines: 字符串列表
            error: 错误信息
        """
        lines.append(f"**错误**: {error}")

    @classmethod
    def _add_summary_line(cls, lines: List[str], summary: str) -> None:
        """添加摘要行（通用方法）

        Args:
            lines: 字符串列表
            summary: 摘要信息
        """
        if summary:
            lines.append(f"**摘要**: {summary}")

    @classmethod
    def _format_json_block(cls, lines: List[str], title: str, data: Any) -> None:
        """格式化JSON代码块（通用方法）

        Args:
            lines: 字符串列表
            title: 标题
            data: 要格式化的数据
        """
        lines.append(f"**{title}**:")
        lines.append(f"```json\n{json.dumps(data, ensure_ascii=False, indent=2, default=str)}\n```")
