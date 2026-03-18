"""
Agent Memory System

简化记忆架构（长期记忆已移除）：
- SessionMemory: 会话记忆（压缩 + 文件外部化）
- HybridMemoryManager: 混合记忆管理器（内联 recent_iterations）

Note: 长期记忆（向量检索）已因效果不佳而移除
Note: WorkingMemory 已合并进 HybridMemoryManager
"""

from .session_memory import SessionMemory
from .hybrid_manager import HybridMemoryManager

__all__ = [
    "SessionMemory",
    "HybridMemoryManager"
]
