"""Project-owned leaf capabilities and bounded workflow contracts."""

from copy import deepcopy
from collections.abc import Mapping


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
    target["enum"] = list(policy.child_modes)
    contracts = child_modes()
    description = "\n".join(
        f"{mode}: {contracts[mode].positioning}；{contracts[mode].scope}；边界：{contracts[mode].boundary}"
        for mode in policy.child_modes
    )
    target["description"] = description
    schema["description"] = (
        "项目内部子 Agent 工作流：按独立问题分配任务，dependencies 复用共享资源，"
        "无依赖节点并行，已知条件用 when，首轮结束后仅对具体缺口使用 extension 补图。"
        "节点 task_contract 必须含 protocol_version=workflow.v1、question、scope、required_evidence、"
        "deliverables（最多三项）。父 Agent 整合并成稿，简单问题直接执行。\n" + description
    )
    return schema


def prepare_node(node):
    """Require a bounded question and structured evidence before starting a child."""
    policy = child_modes().get(str(node.get("target_mode") or ""))
    if policy is None:
        return
    contract = node.get("task_contract")
    if not isinstance(contract, Mapping):
        raise ValueError("项目子节点必须提供 task_contract")
    for field in ("question", "scope", "required_evidence", "deliverables"):
        if not contract.get(field):
            raise ValueError(f"项目子节点 task_contract 缺少 {field}")
    if contract.get("protocol_version") != "workflow.v1":
        raise ValueError("项目子节点协议必须为 workflow.v1")
    if not isinstance(contract["question"], str) or not contract["question"].strip():
        raise ValueError("项目子节点 question 必须为非空字符串")
    if not isinstance(contract["scope"], Mapping):
        raise ValueError("项目子节点 scope 必须为对象，包含时间、站点范围及口径")
    for field in ("required_evidence", "deliverables"):
        values = contract[field]
        if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
            raise ValueError(f"项目子节点 {field} 必须为非空字符串列表")
    if len(contract["deliverables"]) > policy.max_deliverables:
        raise ValueError(f"项目子节点最多 {policy.max_deliverables} 项交付物，请按独立问题拆分")
    for field in ("max_iterations", "timeout_seconds"):
        limit = getattr(policy, field)
        node[field] = min(node.get(field) or limit, limit)
    node["iteration_cap"] = policy.max_iterations
    node["timeout_cap"] = policy.timeout_seconds
    # Caller schemas cannot weaken the evidence contract.
    from app.agent.workflow.protocol import EXPERT_ANALYSIS_RESULT_SCHEMA

    schema = deepcopy(EXPERT_ANALYSIS_RESULT_SCHEMA)
    schema["x-evidence-references"] = True
    schema["properties"]["findings"]["items"] = {
        "type": "object", "required": ["statement", "evidence_ids"],
        "properties": {"statement": {"type": "string"},
                       "evidence_ids": {"type": "array", "items": {"type": "string"}}},
    }
    schema["properties"]["evidence"]["items"] = {
        "type": "object", "required": ["id", "source", "locator"],
        "properties": {key: {"type": "string"} for key in ("id", "source", "locator")},
    }
    if policy.require_counter_evidence:
        finding = schema["properties"]["findings"]["items"]
        finding["required"] += ["counter_evidence", "alternative_explanations"]
        finding["properties"].update({
            field: {"type": "array", "items": {"type": "string"}}
            for field in ("counter_evidence", "alternative_explanations")
        })
    node["result_schema"] = schema
    node["task_contract"] = {**dict(contract), "result_schema": deepcopy(schema)}


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
