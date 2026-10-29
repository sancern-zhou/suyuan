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
        "warning": (
            "报告 Agent（report 父模式）不再调用综合 query 子代理："
            "监测历史数据改用 query_monitoring，气象与预报数据改用 query_forecast。"
        ),
    },
    "query_monitoring": {
        "positioning": "常规空气质量监测问数 Agent：面向国控/省控监测数据的取数与核算。",
        "scope": "城市与站点小时/日历史、AQI 与六参数统计核算、同比环比、站点目录、全国城市对比、数据质量核对。",
        "boundary": "只取数与统计核算，不做气象归因与污染成因研判（归 expert_meteorology/expert_analysis），不产出报告包。",
        "outputs": "结构化数据文件（file_path）+ 数据口径、时间范围和缺口说明。",
        "warning": (
            "运行时限定批量取数、可选归一化、交付三个阶段，最多一次失败项补查。"
            "SQL 字段以上下文内嵌表契约为准（大小写敏感）；查询失败返回的错误会附真实字段清单，直接据此修正。"
            "报告 DAG 已禁用本模式：层级不明确时报告 Agent 先向用户确认口径，再拆分为 query_monitoring_station / query_monitoring_city。"
        ),
    },
    "query_monitoring_station": {
        "positioning": "站点层级监测问数 Agent：面向国控站与乡镇站小时/日历史、站点目录的取数与核算。",
        "scope": "国控站小时/日历史（StationHour/StationDay）、乡镇站与中台口径数据、按区县/名称解析站点目录、站点口径六参数统计、站点数据质量核对。",
        "boundary": "聚焦站点层级取数与统计核算，城市口径任务优先归 query_monitoring_city；不做气象归因与污染成因研判，不产出报告包。",
        "outputs": "结构化数据文件（file_path）+ 站点清单、数据口径、时间范围和缺口说明。",
        "warning": (
            "运行时限定批量取数、可选归一化、交付三个阶段，最多一次失败项补查。"
            "国控站直接 SQL 查询无需解析目录；乡镇站编码不可猜，先 xuchang_station_catalog 解析再调 query_airdata_platform。"
            "站点表字段契约已注入上下文，写 SQL 前逐字核对，不要试探字段。"
        ),
    },
    "query_monitoring_city": {
        "positioning": "城市层级监测问数 Agent：面向城市小时/日历史、城市发布历史与全国对比的取数与核算。",
        "scope": "城市小时/日历史与年均值（CityHour/CityDay/CityYearPm25Avg，扣沙天清单 CitySandDay）、城市发布历史、中台接口、全国城市对比、城市口径统计核算。",
        "boundary": "聚焦城市层级取数与统计核算，站点明细任务优先归 query_monitoring_station；不做气象归因与污染成因研判，不产出报告包。",
        "outputs": "结构化数据文件（file_path）+ 城市清单、数据口径、时间范围和缺口说明。",
        "warning": (
            "运行时限定批量取数、可选归一化、交付三个阶段，最多一次失败项补查。"
            "城市表字段契约已注入上下文，写 SQL 前逐字核对，不要试探字段。"
        ),
    },
    "query_forecast": {
        "positioning": "气象与空气质量预报问数 Agent：面向气象与预报产品的取数与整理。",
        "scope": "气象实况与多时效预报取数、空气质量预报产品查询、预报要素时间序列落盘、起报时间与时效标注。",
        "boundary": "只取数与轻量整理，不做气象条件研判与污染潜势评估（归 expert_meteorology），不产出报告包。",
        "outputs": "结构化数据文件（file_path）+ 起报时间/时效/要素口径说明。",
        "warning": (
            "运行时限定批量取数、可选归一化、交付三个阶段，最多一次失败项补查。"
            "预报数据的分析结论（如静稳形势、扩散条件）由 expert_meteorology 完成，本模式只交付数据。"
        ),
    },
    "query_component": {
        "positioning": "组分问数 Agent：面向广东省超级站组分数据（水溶性离子、碳组分、地壳元素、VOCs）的取数与整理。",
        "scope": "超站组分站点的离子、OC/EC、地壳元素、VOCs 类别小时数据，多站点批量取数、占比与简单统计核算、数据质量口径与缺口说明。",
        "boundary": "只取数与整理，不做组分化学成因研判与来源指向结论（归 expert_component）；不取常规六参数监测与气象数据，不产出报告包。",
        "outputs": "结构化组分数据文件（file_path）+ 站点清单、时间粒度、数据质量口径（原始/审核）和缺口说明。",
        "warning": (
            "运行时限定批量取数、可选归一化、交付三个阶段，最多一次失败项补查。"
            "组分站点与常规监测站点是两套体系，站点名→编码映射内置于工具；"
            "用户给城市时先按站点清单换算为具体组分站点，该市无组分站点时如实说明。"
        ),
    },
    "expert": {
        "positioning": "专家 Agent：面向机制、成因与判断依据的专业研判。",
        "scope": "气象/遥感/轨迹/源解析等专业分析、证据解释、适用条件和证据缺口说明。",
        "boundary": "不负责报告排版与报告包收口。",
        "outputs": "结论 + 证据 + 不确定性（findings/evidence）。",
        "warning": (
            "专家自身也具备取数工具；同一数据源若已有 query 节点产出，"
            "必须用 dependencies 复用其 file_path，禁止重复取数。"
        ),
    },
    "expert_meteorology": {
        "positioning": "气象专家 Agent：面向气象条件与输送过程的专业研判。",
        "scope": "地面/高空观测与预报气象、边界层与静稳条件、后向轨迹与输送通道、气象型归类、污染潜势的气象条件评估。",
        "boundary": "职责聚焦气象条件与输送过程；污染物化学成因、源解析定量和报告包分别交由对应专家与主报告 Agent。",
        "outputs": "结构化气象结论、证据与不确定性；内容较长时可附一份已发布的 Markdown 分析备忘录。",
        "warning": (
            "气象专家只拥有气象数据工具；同一数据源若已有 query 节点产出，"
            "通过 dependencies 复用已有 file_path，并以该产物作为同源数据的首选依据。"
        ),
    },
    "expert_analysis": {
        "positioning": "常规分析专家 Agent：面向空气质量监测数据的专业研判。",
        "scope": "六参数浓度特征与超标统计、AQI 与首要污染物变化、站点和城市时空对比、污染过程分段、本地累积与区域同步性的初步研判、判断依据和证据缺口说明。",
        "boundary": "职责聚焦常规监测数据；离子、碳组分、地壳元素、VOCs/OFP 由组分专家（expert_component）承担，气象判断引用上游气象节点，源解析定量和报告包由对应节点完成。",
        "outputs": "结构化监测分析结论、证据与不确定性；内容较长时可附一份已发布的 Markdown 分析备忘录。",
        "warning": (
            "常规分析专家不配置气象与轨迹工具；需要气象结论时依赖 expert_meteorology 上游节点，"
            "同一数据源已有 query 节点产出时，通过 dependencies 复用其 file_path。"
        ),
    },
    "expert_component": {
        "positioning": "组分专家 Agent：面向 PM2.5 组分化学与 VOCs 组成的专业研判。",
        "scope": "二次无机盐（SO4²⁻/NO₃⁻/NH₄⁺ 与 SOR/NOR）、碳组分一次二次拆分（OC/EC、SOC）、地壳元素与扬尘指向、VOCs 物种活性与 OFP、组分重构与来源指向性判断、证据与缺口说明。",
        "boundary": "职责聚焦组分化学与来源指向；气象条件引用 expert_meteorology 上游结论，常规六参数研判归 expert_analysis，定量源解析谱与正式报告由对应节点完成。",
        "outputs": "结构化组分分析结论、证据与不确定性；内容较长时可附一份已发布的 Markdown 分析备忘录。",
        "warning": (
            "组分专家自带超站组分取数与分析工具；同一数据源若已有 query 节点产出，"
            "通过 dependencies 复用其 file_path，禁止重复取数。"
        ),
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
    "office": {
        "positioning": "办公模式：助手专属的日常轻办公子 Agent。",
        "scope": "文档阅读、文件整理、普通文件编辑、表格清洗核对、轻量计算与 HTML 交付。",
        "boundary": "仅由 assistant 委派，不再次委派；不取业务或气象数据，不做业务图表、专业研判、知识问答和正式报告。",
        "outputs": "经核对的办公文件、处理说明和资源引用。",
    },
}

_ROUTING_RULES = (
    "选择规则：综合 query、expert、report 仅作主模式，不能作为子 Agent；正式报告由具备报告职责的主模式生成，助手 assistant 引导报告主入口；"
    "监测历史数据事实按层级拆分：站点小时/日与站点目录用 query_monitoring_station，"
    "城市口径与全国对比用 query_monitoring_city；层级混合拆成站点+城市两个节点，"
    "层级不明确先向用户确认口径，不要用 query_monitoring 兜底（报告 DAG 已禁用，仅限非报告父模式直接委托）；"
    "气象实况/预报与空气质量预报数据用 query_forecast；"
    "广东省超级站组分数据（离子/碳组分/地壳元素/VOCs）取数用 query_component；"
    "气象条件、输送通道与静稳形势用 expert_meteorology，六参数浓度/AQI/超标与时空变化用 expert_analysis，"
    "组分化学、SOC/OFP 与来源指向用 expert_component，"
    "三者可并行拆分，交叉归因（如气象导致组分累积）在 synthesis 或报告整合阶段完成；"
    "expert 需要 query 系数据时，把对应问数节点写入 dependencies 并复用其 file_path；"
    "无依赖的 source 节点并行且会话隔离；同源数据由一个节点获取，后续节点通过 dependencies 复用。"
)


def target_mode_values() -> list[str]:
    """已登记契约的 target_mode 取值（顺序稳定）。"""
    return list(_active_contracts())


def _active_contracts():
    from app.agent.workflow.project_policy import child_modes

    project = child_modes()
    overlap = set(project) & set(TARGET_MODE_CONTRACTS)
    if overlap:
        raise ValueError(f"project workflow modes shadow shared modes: {sorted(overlap)}")
    from app.agent.workflow.delegation import PRIMARY_ONLY_MODES

    return {**{name: spec for name, spec in TARGET_MODE_CONTRACTS.items() if name not in PRIMARY_ONLY_MODES}, **{
        name: policy.model_dump(include={"positioning", "scope", "boundary", "outputs"})
        for name, policy in project.items() if name not in PRIMARY_ONLY_MODES
    }}


def build_target_mode_contract() -> str:
    """构建 target_mode 能力/工具边界契约文本（供工具 schema 使用）。"""
    lines = ["子 Agent（target_mode）能力与工具边界："]
    for mode, spec in _active_contracts().items():
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
