"""
动作处理器模块

提供模块化的动作处理功能，替代 loop.py 中硬编码的动作处理逻辑。
"""

from .base import ActionHandler

__all__ = [
    "ActionHandler",
]
