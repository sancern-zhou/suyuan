"""Runtime tool classification helpers.

These helpers intentionally sit in the runtime layer. Tool categories already
exist on the registry; the agent loop needs to consume them to distinguish
business progress from housekeeping state updates.
"""

from __future__ import annotations

from typing import Any, Iterable


HOUSEKEEPING_TOOL_NAMES = frozenset({
    "TodoWrite",
})

HOUSEKEEPING_CATEGORIES = frozenset({
    "task_management",
})


def _category_value(category: Any) -> Any:
    return getattr(category, "value", category)


def get_tool_category(tool_name: str) -> Any:
    """Return a registered tool category, if known."""
    from app.tools import global_tool_registry

    tool_data = global_tool_registry.get_tool_data(tool_name)
    if not tool_data:
        return None
    return tool_data.get("category")


def is_housekeeping_tool(tool_name: str) -> bool:
    """True for tools that update agent/session state rather than task output."""
    if tool_name in HOUSEKEEPING_TOOL_NAMES:
        return True
    category = get_tool_category(tool_name)
    return category in HOUSEKEEPING_CATEGORIES or _category_value(category) in HOUSEKEEPING_CATEGORIES


def all_housekeeping_tools(tool_names: Iterable[str]) -> bool:
    names = [name for name in tool_names if name]
    return bool(names) and all(is_housekeeping_tool(name) for name in names)
