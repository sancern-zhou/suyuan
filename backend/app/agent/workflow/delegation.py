"""Shared delegation boundaries for DAG and direct child calls."""

from __future__ import annotations

QUERY_CHILD_MODES = frozenset({
    "query_monitoring_station", "query_monitoring_city", "query_forecast",
})
EXPERT_CHILD_MODES = QUERY_CHILD_MODES | frozenset({
    "expert_meteorology", "expert_analysis",
})
LEAF_MODES = EXPERT_CHILD_MODES | frozenset({"query_monitoring"})
PARENT_CHILD_MODES = {"query": QUERY_CHILD_MODES, "expert": EXPERT_CHILD_MODES}
DELEGATION_TOOLS = frozenset({"call_sub_agent", "run_agent_workflow"})


def delegation_error(parent_mode: str, target_modes: list[str]) -> str | None:
    if parent_mode in LEAF_MODES:
        return f"精简子 Agent {parent_mode} 只执行本节点任务，不支持再次委派或 DAG 编排。"
    allowed = PARENT_CHILD_MODES.get(parent_mode)
    if allowed is None:
        return None
    invalid = sorted(set(target_modes) - allowed)
    if invalid:
        return (
            f"{parent_mode} 父模式仅允许精简子 Agent：{', '.join(sorted(allowed))}；"
            f"越界模式：{', '.join(invalid)}。委派须保留父任务的地域、时间、指标与职责边界。"
        )
    return None


def build_delegation_contract(mode: str, available_tools: list[str]) -> str:
    """Include guidance only for an enabled parent, including project overrides."""
    if mode not in PARENT_CHILD_MODES or not DELEGATION_TOOLS.intersection(available_tools):
        return ""
    common = (
        "\n\n## 精简子 Agent 与依赖工作流\n"
        "简单任务直接使用本模式工具完成。同源、同口径的多城市或多时段查询，"
        "能一次批量取数时优先批量查询，不按城市或日期机械拆成多个 Agent。"
        "需要独立专业处理、隔离较大上下文或存在明确依赖的子任务，且工作量值得委派时，"
        "使用 run_agent_workflow 按任务依赖并行执行；DAG 会增加模型调用与结果整合成本。"
        "一次性委托可使用 call_sub_agent；已有数据优先交给子 Agent 分析，不重复取数。"
        "每个节点保留用户的地域、时间范围、指标口径和交付要求，不通过委派扩大本模式职责。"
        "站点数据使用 query_monitoring_station，城市数据与城市对比使用 query_monitoring_city，"
        "气象实况与预报数据使用 query_forecast；跨层级拆成独立节点。"
        "有上游输入时填写 dependencies，复用 file_path 和资源引用；父 Agent 完成跨源合并、"
        "核算、最终回答及用户交互，同源数据由一个节点获取。"
        "精简子 Agent 工具集固定，不再次编排。\n"
        "检查节点结果中的 data_gaps，只有缺口影响结论且现有查询不能直接补齐时，"
        "才由父 Agent 决定补图：再次调用 run_agent_workflow，workflow 只传原 workflow_id，"
        "extension 传 expected_revision（使用上次返回的 revision）、reason 和新 nodes。"
        "新节点可依赖已完成节点；不得修改旧节点、重复已有任务或突破累计预算。\n"
    )
    if mode == "expert":
        return common + (
            "气象与输送研判使用 expert_meteorology，常规监测数据分析使用 expert_analysis；"
            "一个专家节点回答一个问题，填写 task_contract 和 result_schema，交付结论、证据与缺口。"
            "取数节点与分析节点用 dependencies 连接；跨领域归因和专业结论由专家父 Agent 整合。"
            "已有数据直接复用，当前精简专家不覆盖的组分或源解析任务由父 Agent 的专业工具完成。"
        )
    return common + "问数子节点仅负责数据事实与核算；问数父 Agent 保持统计、导出与展示职责。"
