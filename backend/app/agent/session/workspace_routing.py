"""Routing contracts for persistent specialist workspaces."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


PERSISTENT_WORKSPACE_MODES = frozenset({"board", "ppt", "report"})

_WORKSPACE_MODE_ALIASES = {
    "board": ("board", "画板", "白板", "流程图", "架构图"),
    "ppt": ("ppt", "ppt模式", "幻灯片", "演示文稿"),
    "report": ("report", "报告", "报告模式", "报告工作空间"),
}


def is_workspace_switch_only_request(query: str, target_mode: str) -> bool:
    """Return whether the request only asks to enter a workspace."""
    if target_mode not in PERSISTENT_WORKSPACE_MODES or not isinstance(query, str):
        return False

    normalized = re.sub(r"[\s，。！？、,.!?：:；;]+", "", query).lower()
    aliases = _WORKSPACE_MODE_ALIASES[target_mode]
    action_prefixes = ("切换到", "切换至", "切换", "进入", "打开", "转到", "换到", "换成", "使用")
    suffixes = ("", "模式", "工作空间", "agent", "智能体")
    return any(
        normalized == f"{prefix}{alias}{suffix}"
        for prefix in action_prefixes
        for alias in aliases
        for suffix in suffixes
    )


def build_workspace_promotion(
    *,
    target_mode: str,
    session_id: str,
    artifact_id: Optional[str] = None,
    workspace_type: Optional[str] = None,
    reason: str = "artifact_editing",
) -> Dict[str, Any]:
    """Build the metadata exchanged by the router and the client."""
    if target_mode not in PERSISTENT_WORKSPACE_MODES:
        raise ValueError(f"unsupported persistent workspace mode: {target_mode}")
    if not session_id:
        raise ValueError("workspace promotion requires a session_id")
    return {
        "promoted": True,
        "target_mode": target_mode,
        "workspace_type": workspace_type or target_mode,
        "session_id": session_id,
        "artifact_id": artifact_id,
        "reason": reason,
        "sticky": True,
    }


def is_workspace_promotion(value: Any) -> bool:
    """Validate untrusted metadata before changing client session state."""
    return (
        isinstance(value, dict)
        and value.get("promoted") is True
        and value.get("sticky") is True
        and value.get("target_mode") in PERSISTENT_WORKSPACE_MODES
        and isinstance(value.get("session_id"), str)
        and bool(value["session_id"].strip())
    )


def build_workspace_approval_request(
    *,
    promotion: Dict[str, Any],
    goal: str,
    context_str: Optional[str] = None,
    workspace_path: Optional[str] = None,
    skill_ids: Optional[list[str]] = None,
    resume_after_approval: bool = True,
) -> Dict[str, Any]:
    """Build the serializable deferred invocation stored until approval."""
    return {
        "target_mode": promotion["target_mode"],
        "goal": goal,
        "context_str": context_str,
        "workspace_path": workspace_path,
        "session_id": promotion["session_id"],
        "skill_ids": list(dict.fromkeys(skill_ids or [])),
        "resume_after_approval": resume_after_approval,
    }


def bind_workspace_request_to_source_query(
    pending_request: Dict[str, Any],
    source_query: str,
) -> Dict[str, Any]:
    """Bind deferred execution to the user's request instead of an LLM rewrite."""
    bound = dict(pending_request)
    goal = source_query.strip() if isinstance(source_query, str) else ""
    if goal:
        bound["goal"] = goal
    bound["resume_after_approval"] = not is_workspace_switch_only_request(
        bound.get("goal", ""),
        bound.get("target_mode", ""),
    )
    return bound


def is_workspace_approval_required(value: Any) -> bool:
    """Validate a deferred workspace request before exposing it to clients."""
    return (
        isinstance(value, dict)
        and value.get("kind") == "approval"
        and isinstance(value.get("promotion"), dict)
        and is_workspace_promotion(value["promotion"])
        and isinstance(value.get("pending_request"), dict)
        and isinstance(value["pending_request"].get("goal"), str)
        and bool(value["pending_request"]["goal"].strip())
    )
