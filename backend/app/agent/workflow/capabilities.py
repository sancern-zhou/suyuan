"""Capability policy for child Agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Set


class RestrictedToolRegistry(dict):
    """Mapping that remains intentionally truthy even when no tools are allowed.

    ``ToolExecutor`` treats a falsey mapping as a request to register every
    built-in tool.  A restricted child must never silently fall back to that
    behavior, including for an empty capability set.
    """

    def __bool__(self) -> bool:
        return True


@dataclass(frozen=True)
class ChildCapabilityPolicy:
    """Allow/deny policy applied before a child runtime is created."""

    allowed_tools: Optional[frozenset[str]] = None
    denied_tools: frozenset[str] = frozenset()
    allow_delegation: bool = True

    def filter_registry(self, registry: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        if not registry:
            return {}
        denied = set(self.denied_tools)
        if not self.allow_delegation:
            denied.add("call_sub_agent")
        allowed = set(self.allowed_tools) if self.allowed_tools is not None else None
        return RestrictedToolRegistry({
            name: tool
            for name, tool in registry.items()
            if (allowed is None or name in allowed) and name not in denied
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed_tools": sorted(self.allowed_tools) if self.allowed_tools is not None else None,
            "denied_tools": sorted(self.denied_tools),
            "allow_delegation": self.allow_delegation,
        }


def build_child_capability_policy(
    *,
    allowed_tools: Optional[Iterable[str]] = None,
    denied_tools: Optional[Iterable[str]] = None,
    allow_delegation: bool = True,
) -> ChildCapabilityPolicy:
    return ChildCapabilityPolicy(
        allowed_tools=(frozenset(str(name) for name in allowed_tools) if allowed_tools is not None else None),
        denied_tools=frozenset(str(name) for name in (denied_tools or [])),
        allow_delegation=bool(allow_delegation),
    )
