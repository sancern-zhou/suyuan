"""Runtime tool classification helpers.

These helpers intentionally sit in the runtime layer. Tool categories already
exist on the registry; the agent loop needs to consume them to distinguish
business progress from housekeeping state updates.
"""

from __future__ import annotations

from typing import Iterable


HOUSEKEEPING_TOOL_NAMES = frozenset({
    "TaskCreate",
    "TaskUpdate",
    "TaskList",
    "TaskGet",
})

def is_housekeeping_tool(tool_name: str) -> bool:
    """True for tools that update agent/session state rather than task output."""
    return tool_name in HOUSEKEEPING_TOOL_NAMES


def all_housekeeping_tools(tool_names: Iterable[str]) -> bool:
    names = [name for name in tool_names if name]
    return bool(names) and all(is_housekeeping_tool(name) for name in names)
