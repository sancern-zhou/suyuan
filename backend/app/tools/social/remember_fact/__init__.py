"""
记忆添加工具（remember_fact）

让LLM主动添加重要信息到长期记忆（MEMORY.md）
"""

from app.tools.social.remember_fact.tool import RememberFactTool

__all__ = ["RememberFactTool"]
