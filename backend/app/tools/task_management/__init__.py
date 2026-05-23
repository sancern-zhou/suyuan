"""
任务管理工具

提供简化的任务清单状态管理能力（TodoWrite），让LLM可以在ReAct循环中：
- 创建任务清单（完整替换模式）
- 更新任务状态
- 查看任务进度

核心特性：
- 单一工具（TodoWrite）
- 2个字段（content, status）
- 约束规则（最多20项、同时只能1个in_progress）
- 简洁文本渲染输出
- housekeeping工具：不代表业务进展，不应连续重复调用
"""

from .todo_write import todo_write_tool

__all__ = [
    "todo_write_tool",
]
