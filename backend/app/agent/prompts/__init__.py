"""
提示词模块

提供各个专家的专业提示词
"""

# 导出 react_prompts 以支持相对导入
from . import react_prompts

__all__ = ['react_prompts', 'get_system_prompt']


def get_system_prompt(manual_mode: str, available_tools: list) -> str:
    """
    根据模式获取系统提示词

    Args:
        manual_mode: 模式标识
        available_tools: 可用工具列表

    Returns:
        系统提示词
    """
    if manual_mode == "memory_consolidator":
        from .memory_consolidator_prompt import build_memory_consolidator_prompt
        return build_memory_consolidator_prompt(available_tools)
    else:
        # 其他模式暂不支持
        raise ValueError(f"Unsupported mode: {manual_mode}. Only 'memory_consolidator' is supported by get_system_prompt().")
