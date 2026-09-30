"""Canonical tool names for persisted configurations and legacy calls."""

TOOL_NAME_ALIASES = {"create_report_chart": "create_business_chart"}


def canonical_tool_name(name: str) -> str:
    return TOOL_NAME_ALIASES.get(name, name)
