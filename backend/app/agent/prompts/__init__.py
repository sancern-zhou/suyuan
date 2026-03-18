"""
提示词模块

提供各个专家的专业提示词
"""

from .data_viz_prompt import get_data_viz_prompt
from .general_agent_prompt import get_general_agent_prompt

# 导出 react_prompts 以支持相对导入
from . import react_prompts

__all__ = ['get_data_viz_prompt', 'get_general_agent_prompt', 'react_prompts']
