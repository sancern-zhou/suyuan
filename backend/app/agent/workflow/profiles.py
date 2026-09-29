"""Declarative capability profiles for child Agents.

Profiles keep mode-specific tool policy out of the call site.  The policy is
still intersected with the caller's explicit allow/deny lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Iterable, Optional


PLAN_TOOLS = frozenset({"enter_plan_mode", "exit_plan_mode", "plan_mode"})


@dataclass(frozen=True)
class AgentProfile:
    name: str
    allow_delegation: bool
    read_only: bool = False
    denied_tools: FrozenSet[str] = frozenset()


PROFILES = {
    "general-purpose": AgentProfile(
        name="general-purpose",
        allow_delegation=False,
        denied_tools=PLAN_TOOLS,
    ),
    "orchestrator": AgentProfile(
        name="orchestrator",
        allow_delegation=True,
        denied_tools=PLAN_TOOLS,
    ),
    "explore": AgentProfile(
        name="explore",
        allow_delegation=False,
        read_only=True,
        denied_tools=PLAN_TOOLS | frozenset({
            "write_file", "edit_file", "edit_file_v2", "bash", "shell",
        }),
    ),
}

# Business modes retain their existing domain tool registry.  ``explore`` is an
# explicit profile for genuinely read-only tasks; these modes are not mapped to
# it because several existing registries intentionally include file exports.
MODE_PROFILES = {
    "assistant": "orchestrator",
    "query": "general-purpose",
    "report": "orchestrator",
    "social": "orchestrator",
    "chart": "general-purpose",
    "expert": "general-purpose",
    "ops": "orchestrator",
    "board": "orchestrator",
    "ppt": "general-purpose",
}


def get_agent_profile(mode: Optional[str], *, profile: Optional[str] = None) -> AgentProfile:
    key = profile or MODE_PROFILES.get(str(mode or ""), "general-purpose")
    return PROFILES.get(key, PROFILES["general-purpose"])


def merge_denied_tools(profile: AgentProfile, denied_tools: Optional[Iterable[str]]) -> FrozenSet[str]:
    return frozenset(profile.denied_tools | frozenset(str(name) for name in (denied_tools or [])))
