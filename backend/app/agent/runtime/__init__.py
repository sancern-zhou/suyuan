"""
Agent runtime package.

This package contains the decomposed execution path used by ReActLoop.  The
legacy loop module remains as a compatibility shell while runtime components
own streaming, tool execution, transcript writes, and finalization.
"""

from .agent_runtime import AgentRuntime, AgentRuntimeConfig

__all__ = ["AgentRuntime", "AgentRuntimeConfig"]
