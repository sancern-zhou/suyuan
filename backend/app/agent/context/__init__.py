"""
Context management module

简化版上下文管理
"""

from .execution_context import ExecutionContext
from .simplified_context_builder import SimplifiedContextBuilder

__all__ = ["ExecutionContext", "SimplifiedContextBuilder"]
