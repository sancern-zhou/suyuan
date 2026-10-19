"""Discover the active project's real surfaces; this catalog grants no authority."""

import json
from hashlib import sha256


def capability_catalog():
    from app.agent.prompts.tool_registry import get_tools_by_mode
    from app.agent.workflow.delegation import delegation_error
    from app.agent.workflow.target_mode_contract import TARGET_MODE_CONTRACTS, _active_contracts
    from app.project_config.loader import load_project_context
    from app.tools import global_tool_registry
    from config.settings import settings

    manifest = load_project_context(settings.project_id).manifest

    def tools_for(mode):
        try:
            allowed = get_tools_by_mode(mode)
        except ValueError as exc:
            if str(exc).startswith("Unknown mode:"):
                return []
            raise
        return sorted(
            name for name in allowed if global_tool_registry.get_tool_status(name) == "enabled"
        )

    result = {}

    def add(kind, target, description, tools, *, contract=None, parameters=None):
        if not tools:
            return
        item = {
            "capability_id": f"{kind}:{target}",
            "kind": kind,
            "target": target,
            "description": description,
            "tools": tools,
            "source": "active_project_manifest_and_enabled_tool_registry",
        }
        if contract:
            item["contract"] = {
                key: contract[key] for key in ("scope", "boundary", "outputs") if key in contract
            }
        if parameters is not None:
            item["required_parameters"] = list(parameters.get("required", []))
        if target == "manage_assistant_followups" and kind == "tool":
            item["available_execution_actions"] = ["remind"]
            if settings.assistant_analysis_enabled:
                item["available_execution_actions"].append("analyze")
        item["revision"] = sha256(
            json.dumps(item, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        result[item["capability_id"]] = item

    social_tools = tools_for("social")
    for name in social_tools:
        if name == "manage_assistant_coaching":
            continue
        tool = global_tool_registry.get_tool(name)
        if tool is not None:
            schema = getattr(tool, "function_schema", None) or {}
            add(
                "tool",
                name,
                getattr(tool, "description", ""),
                [name],
                parameters=schema.get("parameters", {}),
            )
    for mode in manifest.frontend.agent_modes:
        if mode in {"assistant", "social"}:
            continue
        spec = TARGET_MODE_CONTRACTS.get(mode, {})
        override = manifest.frontend.agent_mode_overrides.get(mode, {})
        description = override.get("description") or spec.get("positioning") or mode
        add("workspace", mode, str(description), tools_for(mode), contract=spec)
    if "call_sub_agent" in social_tools:
        for mode, spec in _active_contracts().items():
            if mode == "social" or delegation_error("social", [mode]):
                continue
            add("delegate", mode, spec["positioning"], tools_for(mode), contract=spec)
    return result


def next_action(capability, recommendation):
    """An executable route for the current Agent, never a synthetic user message."""
    return {
        "kind": capability["kind"],
        "target": capability["target"],
        "goal": recommendation["goal"],
        "suggested_prompt": recommendation["suggested_prompt"],
        "missing_inputs": recommendation["missing_inputs"],
        "execution_state": "not_started",
        "instruction": {
            "tool": "在当前用户授权范围内直接使用此工具；缺必要参数先补齐。",
            "delegate": "仅在工作量值得委派时使用 call_sub_agent，保留用户范围和已有资源。",
            "workspace": "向用户给出专业模式与可用提问文本；当前工具不会切换界面或启动该模式。",
        }[capability["kind"]],
    }
