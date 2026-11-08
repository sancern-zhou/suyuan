"""Project-owned leaf capabilities and bounded workflow contracts."""

from copy import deepcopy


def active_backend():
    from app.project_config.loader import load_project_context
    from config.settings import settings

    return load_project_context(settings.project_id).manifest.backend


def child_modes():
    return active_backend().agent_workflow_modes


def parent_policy(mode):
    return active_backend().agent_workflow_parents.get(mode)


def scope_delegation_schema(schema, parent_mode):
    """Expose only the configured child roles to a project orchestrator."""
    policy = parent_policy(parent_mode)
    if policy is None:
        return schema
    schema = deepcopy(schema)
    properties = schema["parameters"]["properties"]
    if schema["name"] == "call_sub_agent":
        target = properties["target_mode"]
    else:
        target = properties["workflow"]["properties"]["nodes"]["items"]["properties"]["target_mode"]
    from app.agent.workflow.delegation import PARENT_CHILD_MODES, PRIMARY_ONLY_MODES

    enabled_modes = [mode for mode in policy.child_modes if mode not in PRIMARY_ONLY_MODES]
    shared_children = PARENT_CHILD_MODES.get(parent_mode) or set()
    # 混合父模式（既有共享子模式又有项目子模式，如 assistant）：项目子模式在前，
    # 共享可委派子模式追加在后；纯项目父模式（共享父边界无记录）行为不变。
    for mode in sorted(shared_children):
        if mode not in PRIMARY_ONLY_MODES and mode not in enabled_modes:
            enabled_modes.append(mode)
    target["enum"] = enabled_modes
    from app.agent.workflow.target_mode_contract import TARGET_MODE_CONTRACTS

    # 项目子模式契约优先，共享子模式回退共享契约表；两类条目分别是
    # pydantic 模型与 dict，字段读取统一在此收口。
    contracts = {**TARGET_MODE_CONTRACTS, **child_modes()}

    def _contract_field(mode: str, name: str) -> str:
        spec = contracts[mode]
        value = spec.get(name) if isinstance(spec, dict) else getattr(spec, name)
        return str(value).strip().rstrip("。")

    is_direct_call = schema["name"] == "call_sub_agent"
    if shared_children and not is_direct_call:
        # 混合父模式（如 assistant）的 DAG 工具只收窄 enum：子模式定位与边界
        # 已在同父模式的 call_sub_agent 承载，双份注入属重复计费。
        return schema

    # 一行制定位+边界：完整 scope/outputs 由子模式自身提示词承载，
    # 不再重复注入（此前同一段全文同时进 target 描述与工具描述，双份计费）。
    description = "\n".join(
        f"- {mode}：{_contract_field(mode, 'positioning')}"
        f"；边界：{_contract_field(mode, 'boundary')}"
        for mode in enabled_modes
    )
    target["description"] = description
    if shared_children:
        # 混合父模式保留原工具描述：后台委派、describe_mode 等委派语义仍是
        # 该父模式的主路径；goal 与按需 result_schema 承载具体任务要求。
        schema["description"] = (
            str(schema.get("description") or "").rstrip()
            + "\n项目子模式用 goal 完整描述问题、范围和预期交付；父侧整合并成稿，简单问题直接执行。"
        )
    else:
        schema["description"] = (
            "项目内部子 Agent 工作流：按独立问题分配任务，dependencies 复用共享资源，"
            "无依赖节点并行，已知条件用 when，首轮结束后仅对具体缺口使用 extension 补图。"
            "节点用 goal 描述独立问题、范围和预期交付，可按需传 result_schema。"
            "父 Agent 整合并成稿，简单问题直接执行。"
            f"允许子模式：{', '.join(enabled_modes)}。"
        )
    return schema


def prepare_node(node):
    """Apply project-owned execution limits and optional evidence requirements."""
    policy = child_modes().get(str(node.get("target_mode") or ""))
    if policy is None:
        return
    for field in ("max_iterations", "timeout_seconds"):
        limit = getattr(policy, field)
        node[field] = min(node.get(field) or limit, limit)
    node["iteration_cap"] = policy.max_iterations
    node["timeout_cap"] = policy.timeout_seconds
    if node.get("result_schema") or not policy.require_counter_evidence:
        return
    node["result_schema"] = {
        "type": "object",
        "required": ["findings", "evidence"],
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["statement", "evidence_ids", "counter_evidence", "alternative_explanations"],
                    "properties": {
                        "statement": {"type": "string"},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                        "counter_evidence": {"type": "array", "items": {"type": "string"}},
                        "alternative_explanations": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "evidence": {"type": "array", "items": {"type": "object"}},
        },
        "x-evidence-references": True,
        "additionalProperties": True,
    }


def apply_workflow_limits(parent_mode, definition, max_concurrency):
    policy = parent_policy(parent_mode)
    if policy is None:
        return max_concurrency
    budget = dict(definition.get("budget") or {})
    for field in ("max_nodes", "max_retries", "max_extensions", "timeout_seconds"):
        limit = getattr(policy, field)
        budget[field] = min(budget.get(field, limit), limit)
    definition["budget"] = budget
    return min(max_concurrency, policy.max_concurrency)
