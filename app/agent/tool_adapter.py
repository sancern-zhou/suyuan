"""
Compatibility wrapper for the canonical backend tool adapter.

All business logic lives in `backend.app.agent.tool_adapter`.
This module exists only to keep legacy imports working.
"""

from backend.app.agent.tool_adapter import *  # noqa: F401,F403

