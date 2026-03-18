"""
任务管理工具

提供简化的任务清单管理能力（TodoWrite），让LLM可以在ReAct循环中：
- 创建任务清单（完整替换模式）
- 更新任务状态
- 查看任务进度

核心特性：
- 单一工具（TodoWrite）
- 3个字段（content, status, activeForm）
- 约束规则（最多20项、同时只能1个in_progress）
- 简洁文本渲染输出
"""

from .todo_write import todo_write_tool

__all__ = [
    "todo_write_tool",
]
