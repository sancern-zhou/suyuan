"""子 Agent（target_mode）能力与工具边界契约。

单一事实来源：供 `run_agent_workflow` / `call_sub_agent` 的 target_mode 描述使用。
编排 Agent 据此选择节点类型、设计依赖并复用上游产物，而不是凭字面猜测各模式的分工。
"""

from __future__ import annotations

TARGET_MODE_CONTRACTS: dict[str, dict[str, str]] = {
    "query": {
        "positioning": "问数 Agent：面向数据本身的取数、统计与核算。",
        "scope": "SQL/平台数据/站点与报表查询、同比环比、分组聚合、数据质量核对。",
        "boundary": "不做机制研判与成因推断，不产出正式报告包。",
        "outputs": "结构化数据文件（file_path）。",
    },
    "expert": {
        "positioning": "专家 Agent：面向机制、成因与证据强弱的专业研判。",
        "scope": "气象/遥感/轨迹/源解析等专业分析、证据解释与置信度评估。",
        "boundary": "不负责报告排版与报告包收口。",
        "outputs": "结论 + 证据 + 不确定性（findings/evidence）。",
        "warning": (
            "专家自身也具备取数工具；同一数据源若已有 query 节点产出，"
            "必须用 dependencies 复用其 file_path，禁止重复取数。"
        ),
    },
    "report": {
        "positioning": "报告 Agent：面向成稿与交付收口。",
        "scope": "组织章节、生成图表、产出正式报告包（report.qmd/HTML/Word）。",
        "boundary": "不做业务取数，不替代 query/expert 的数据与研判工作。",
        "outputs": "报告包（report_id 与产物）。",
    },
    "chart": {
        "positioning": "可视化 Agent：面向专题图表与可视化叙事。",
        "scope": "趋势图、分布图、地图等可视化产物；独立使用时可补充必要的气象或 SQL 数据。",
        "boundary": "在 DAG 中优先复用 dependencies 已提供的数据，不重复查询，不产出正式报告包。",
        "outputs": "图表/可视化产物。",
    },
    "board": {
        "positioning": "画板 Agent：面向流程图、架构图、决策树等可编辑图形。",
        "scope": "draw.io 画板与图形文件。",
        "boundary": "不做数据分析与报告成稿。",
        "outputs": "可编辑图形文件。",
    },
    "ppt": {
        "positioning": "演示 Agent：面向 PPT 制作与多轮修改。",
        "scope": "演示文稿的生成与编辑。",
        "boundary": "不做业务取数与专业研判。",
        "outputs": "PPT 文件。",
    },
    "knowledge": {
        "positioning": "知识 Agent：面向制度、标准、授权资料与知识库依据。",
        "scope": "知识库检索与依据引用。",
        "boundary": "不做数据查询与专业研判。",
        "outputs": "带出处的知识依据。",
    },
    "ops": {
        "positioning": "运维 Agent：面向工单查询、审核判断、异常分析与闭环建议。",
        "scope": "工单/日志/处置方案。",
        "boundary": "不做正式报告包与专题可视化。",
        "outputs": "结构化处置结论与建议。",
    },
    "assistant": {
        "positioning": "助手 Agent：面向轻量办公任务。",
        "scope": "文档搜索阅读、普通文件编辑、轻量计算、网页检索抓取、HTML/报告包生成。",
        "boundary": "超出轻量范围的专业任务应委托对应模式。",
        "outputs": "轻量产物或路由结果。",
    },
    "social": {
        "positioning": "社交 Agent：面向社交平台交互任务。",
        "scope": "社交平台消息处理与广播。",
        "boundary": "不做专业数据分析与报告成稿。",
        "outputs": "社交任务结果。",
    },
}

_ROUTING_RULES = (
    "选择规则：数据事实用 query；机制/成因用 expert；成稿交付用 report；"
    "expert 需要 query 的数据时，把对应 query 节点写入 dependencies 并复用其 file_path；"
    "无依赖的 source 节点并行且会话隔离，拿不到彼此数据；禁止同一数据源由 query 与 expert 各查一遍。"
)


def target_mode_values() -> list[str]:
    """已登记契约的 target_mode 取值（顺序稳定）。"""
    return list(TARGET_MODE_CONTRACTS.keys())


def build_target_mode_contract() -> str:
    """构建 target_mode 能力/工具边界契约文本（供工具 schema 使用）。"""
    lines = ["子 Agent（target_mode）能力与工具边界："]
    for mode, spec in TARGET_MODE_CONTRACTS.items():
        parts = [f"- {mode}：{spec['positioning']}"]
        if spec.get("scope"):
            parts.append(f"能做：{spec['scope']}")
        if spec.get("boundary"):
            parts.append(f"边界：{spec['boundary']}")
        if spec.get("outputs"):
            parts.append(f"产出：{spec['outputs']}")
        if spec.get("warning"):
            parts.append(f"⚠️ {spec['warning']}")
        lines.append(" ".join(parts))
    lines.append(_ROUTING_RULES)
    return "\n".join(lines)
