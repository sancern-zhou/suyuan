"""
Browser Action Handlers

Action handlers for browser operations.
"""
from .lifecycle import handle_start, handle_stop, handle_status

__all__ = [
    "handle_start",
    "handle_stop",
    "handle_status",
]
