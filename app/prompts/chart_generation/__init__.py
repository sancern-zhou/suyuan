"""
Chart Generation Prompt Library

提供可复用、模块化的图表生成提示词模板。
"""

from .base import BaseChartPrompt
from .registry import PromptRegistry, get_prompt_registry

__all__ = [
    "BaseChartPrompt",
    "PromptRegistry",
    "get_prompt_registry"
]
