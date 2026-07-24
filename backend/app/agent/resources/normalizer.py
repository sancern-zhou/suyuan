"""Normalize the explicit resource list returned by a tool."""
from __future__ import annotations

from typing import Any

from .contracts import ResourceDeclaration


def normalize_tool_resources(
    *,
    result: Any,
) -> tuple[list[ResourceDeclaration], list[dict[str, str]]]:
    """Validate only the explicit top-level resources contract."""
    if not isinstance(result, dict):
        return [], []
    resources = result.get("resources")
    if resources is None:
        return [], []
    if not isinstance(resources, list):
        return [], [{"field": "resources", "reason": "must_be_a_list"}]

    accepted: list[ResourceDeclaration] = []
    rejected: list[dict[str, str]] = []
    for index, item in enumerate(resources):
        try:
            accepted.append(ResourceDeclaration.model_validate(item))
        except (TypeError, ValueError) as exc:
            rejected.append({"field": f"resources[{index}]", "reason": str(exc)[:200]})
    return accepted, rejected
