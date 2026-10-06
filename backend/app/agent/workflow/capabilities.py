"""Capability policy for child Agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Set

# 子 Agent 一律不配置记忆编辑工具：业务执行中途写记忆每次烧掉一整轮 LLM 决策
# （实测单节点 14 次 ≈ 7 分钟纯开销），记忆沉淀由任务结束后的记忆整合器批量完成。
# 注意：memory_consolidator 模式本身不受此限制。
MEMORY_EDIT_TOOL_NAMES = frozenset({"remember_fact", "replace_memory", "remove_memory"})


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
            denied.update({"call_sub_agent", "run_agent_workflow"})
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
    target_mode: Optional[str] = None,
    allowed_tools: Optional[Iterable[str]] = None,
    denied_tools: Optional[Iterable[str]] = None,
    allow_delegation: bool = True,
) -> ChildCapabilityPolicy:
    denied = {str(name) for name in (denied_tools or [])}
    # 记忆整合器本身就是干这个的，不剥夺其工具
    if str(target_mode or "") != "memory_consolidator":
        denied |= MEMORY_EDIT_TOOL_NAMES
    return ChildCapabilityPolicy(
        allowed_tools=(frozenset(str(name) for name in allowed_tools) if allowed_tools is not None else None),
        denied_tools=frozenset(denied),
        allow_delegation=bool(allow_delegation),
    )
