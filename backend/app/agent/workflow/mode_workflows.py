"""Fixed workflows for latency-sensitive Agent modes.

The model chooses query arguments, while the runtime owns phase transitions,
tool visibility, retry bounds, and the final delivery boundary.
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Sequence

import structlog

from .catalog import (
    FixedWorkflowDefinition,
    WorkflowPhaseDefinition,
    workflow_catalog,
)

logger = structlog.get_logger()


_STATION_CONTRACT_TABLES = ("StationHour", "StationDay", "Station")
_CITY_CONTRACT_TABLES = ("CityHour", "CityDay", "CitySandDay", "CityYearPm25Avg")

_MONITORING_QUERY_TOOLS = (
    "query_xcai_city_history",
    "execute_sql_query",
    "execute_crawler_sql_query",
    "execute_postgres_sql_query",
    "query_airdata_platform",
    "xuchang_station_catalog",
    "monitoring_station_catalog",
    # 组分站名录/某城市有无组分站属于目录事实问题，监测子流程也要能解析
    # （该目录只含可取数的 38 个超站组分站，含 VOCs/PM2.5 组分能力标注，
    # 与监测/运维台账口径不同源）。
    "component_station_catalog",
    "airdata_calc_report_summary",
    "query_national_city_air_quality",
)

# 站点层级问数：国控站走采集库 SQL；乡镇站/中台口径走"目录解析编码 → 取数"
# （编码不可猜，该串行为必要轮次）。站点地理工具按体系各用各的：许昌=
# xuchang_station_catalog+中台查询成对；广东=monitoring_station_catalog
# （监测平台唯一编码，名称/城市用于过滤采集库 SQL），不混用运维台账目录；
# 组分站名录/组分类型用 component_station_catalog。
# 广东报表包视图与 5 分钟数据（query_station_standard_report 等，仅广东注册）
# 服务报告 DAG 站点取数节点；其他项目未注册时为静默死条目，无害。
_MONITORING_STATION_QUERY_TOOLS = (
    "execute_crawler_sql_query",
    "xuchang_station_catalog",
    "monitoring_station_catalog",
    "component_station_catalog",
    "query_airdata_platform",
    "query_station_standard_report",
    "query_station_standard_yoy_report",
    "get_5min_data",
)

# 城市层级问数：城市小时/日/年均值 + SQL Server 城市发布历史 + 中台接口。
# 站点目录工具不进入本表（站点任务归 query_monitoring_station）。
# 广东报表包视图（query_city_standard_report 等，仅广东注册）服务报告 DAG
# 城市取数节点；其他项目未注册时为静默死条目，无害。
_MONITORING_CITY_QUERY_TOOLS = (
    "query_xcai_city_history",
    "execute_sql_query",
    "execute_crawler_sql_query",
    "execute_postgres_sql_query",
    "query_airdata_platform",
    "airdata_calc_report_summary",
    "query_national_city_air_quality",
    "query_gd_suncere_city_hour",
    "query_gd_suncere_city_day",
    "query_gd_suncere_district_day",
    "query_city_standard_report",
    "query_city_standard_yoy_report",
    "query_gd_suncere_district_report",
)

_FORECAST_QUERY_TOOLS = (
    "get_weather_data",
    "get_current_weather",
    "get_weather_forecast",
    "query_airdata_platform",
    "xuchang_station_catalog",
    "monitoring_station_catalog",
    "execute_postgres_sql_query",
)

# 组分问数：广东省超级站组分取数（水溶性离子/碳组分/地壳元素/微量元素/
# VOCs 类别/物种/OFP/官方重构）；站点名→编码映射内置于取数工具，城市展开
# 用组分体系目录 component_station_catalog（与取数工具同一 38 站清单）。
_COMPONENT_QUERY_TOOLS = (
    "get_vocs_data",
    "get_vocs_species",
    "get_vocs_ofp",
    "get_ofp_top10",
    "get_pm25_ionic",
    "get_pm25_carbon",
    "get_pm25_crustal",
    "get_pm25_recovery",
    "get_pm25_trace",
    "component_station_catalog",
)

_NORMALIZE_TOOLS = (
    "execute_python",
    "read_session_resource",
    "write_file",
    "publish_session_file",
)

# normalize 只有"真正动手"的工具才推进阶段；调用失败不推进、留在本阶段修复
# （预算内），读结果文件属于输入动作不消耗轮次，避免读手册/预览烧掉机会。
_NORMALIZE_ADVANCE_TOOLS = (
    "execute_python",
    "write_file",
    "publish_session_file",
)


def _table_contract_block(table_names: Sequence[str]) -> str:
    """按表清单渲染采集库契约文本，注入 acquire 阶段说明（避免模型猜字段）。"""
    try:
        from app.tools.query.execute_crawler_sql_query.table_contracts import (
            render_table_contracts,
        )

        block = render_table_contracts(table_names=list(table_names))
    except Exception as exc:  # noqa: BLE001 — 契约缺失时退化为工具描述内嵌契约
        logger.warning("mode_workflow_contract_block_unavailable", error=str(exc))
        return ""
    return block


def _query_definition(
    name: str,
    query_tools: tuple[str, ...],
    description: str,
    *,
    scope_line: str = "",
    context_block: str = "",
) -> FixedWorkflowDefinition:
    acquire_description = (
        "一次规划完整取数范围，并在同一轮发出全部相互独立的查询。"
        "不同数据库或接口使用多个工具调用；同库关联数据使用一条合法的 JOIN/UNION/CTE 查询。"
        "禁止多语句 SQL，禁止取数前逐表探查或健康检查，质量统计只留到归一化阶段。"
        "若首轮有失败，第二轮只修复失败项，不得重查成功项或扩大范围。"
        "查询结果为 0 行属于无数据：如实说明时间范围与缺口即可，不要怀疑表结构，"
        "也不要重查或试探字段。"
    )
    if scope_line:
        acquire_description = f"{scope_line}\n{acquire_description}"
    if context_block:
        acquire_description = f"{acquire_description}{context_block}"
    return FixedWorkflowDefinition(
        name=name,
        entrypoint="agent_mode",
        version="1",
        description=description,
        phases=(
            WorkflowPhaseDefinition(
                name="acquire",
                description=acquire_description,
                allowed_tools=query_tools,
                advance_tools=query_tools,
                max_attempts=4,
                allow_completion=False,
            ),
            WorkflowPhaseDefinition(
                name="normalize",
                description=(
                    "检查成功结果的时间范围、记录数、字段和缺口。聚合、分箱、统计与"
                    "多步计算可分多轮调用 execute_python 完成；禁止新增数据源查询。"
                ),
                allowed_tools=_NORMALIZE_TOOLS,
                advance_tools=_NORMALIZE_ADVANCE_TOOLS,
                max_attempts=15,
                allow_completion=True,
            ),
            WorkflowPhaseDefinition(
                name="deliver",
                description=(
                    "停止调用分析类工具，输出最终交付文本。本轮请求除交付工具 submit_result 外"
                    "没有其他工具，任何其他工具调用或调用标记语法（如 DSML/XML/JSON 标签）都会"
                    "失败或被当作正文，导致交付失败。带 result_schema 的调用方应改用 submit_result"
                    " 提交结构化结果。file_path 引用上方工具结果中已保存的路径即可，无需执行代码验证；"
                    "同时给出字段说明、时间与区域口径、记录数以及数据缺口。"
                    "不做机制分析，不重新查询。"
                ),
                allowed_tools=(),
                max_attempts=1,
                allow_completion=True,
            ),
        ),
    )


for _definition in (
    _query_definition(
        "query_monitoring",
        _MONITORING_QUERY_TOOLS,
        "空气质量监测固定问数流程",
        scope_line="本节点同时覆盖站点与城市层级；层级明确时应优先拆分为 query_monitoring_station / query_monitoring_city。",
        context_block=_table_contract_block(_STATION_CONTRACT_TABLES + _CITY_CONTRACT_TABLES),
    ),
    _query_definition(
        "query_monitoring_station",
        _MONITORING_STATION_QUERY_TOOLS,
        "国控站点层级空气质量监测固定问数流程",
        scope_line=(
            "聚焦站点层级取数：国控站小时/日历史用采集库 SQL 直接查询"
            "（StationHour/StationDay，按名称或区域 LIKE 过滤，无需解析编码）；"
            "乡镇站编码不可猜：先用站点地理工具解析（xuchang_station_catalog / "
            "monitoring_station_catalog，按部署可用；支持按名称模糊、按区县/城市"
            "展开下辖站点），再按可用工具取数（query_airdata_platform 中台查询，"
            "或以站点名称/城市过滤采集库 SQL）。"
            "站点日报/同比等报表包视图（query_station_standard_report / "
            "query_station_standard_yoy_report）与站点 5 分钟数据（get_5min_data）"
            "按部署可用，报告取数任务优先使用。"
        ),
        context_block=_table_contract_block(_STATION_CONTRACT_TABLES),
    ),
    _query_definition(
        "query_monitoring_city",
        _MONITORING_CITY_QUERY_TOOLS,
        "城市层级空气质量监测固定问数流程",
        scope_line=(
            "聚焦城市层级取数：城市小时/日/年均值、城市发布历史与全国对比，"
            "主要使用 CityHour/CityDay/CityYearPm25Avg 表，扣沙天用 CitySandDay 清单过滤；"
            "城市发布历史（CityAQIPublishHistory）用 query_xcai_city_history。"
            "城市/区域日报与同比报表包视图（query_city_standard_report / "
            "query_city_standard_yoy_report / query_gd_suncere_district_report 等）"
            "按部署可用，报告取数与排名数据优先使用报表包视图字段口径。"
        ),
        context_block=_table_contract_block(_CITY_CONTRACT_TABLES),
    ),
    _query_definition(
        "query_forecast",
        _FORECAST_QUERY_TOOLS,
        "气象实况、气象预报与空气质量预报固定问数流程",
    ),
    _query_definition(
        "query_component",
        _COMPONENT_QUERY_TOOLS,
        "超站组分数据固定问数流程",
        scope_line=(
            "聚焦广东省超级站组分取数：水溶性离子、碳组分（OC/EC）、地壳元素、微量元素/重金属、"
            "VOCs 类别与 117 物种、VOCs 类别 OFP、物种 OFP Top10 与累计贡献、PM2.5 官方质量重构，"
            "多站点多组分批量并发查询；组分站点不接受城市名，站点清单见组分问数提示词；"
            "碳组分、地壳元素与微量元素数值仅小时粒度（地壳/微量元素需审核口径 data_type=1），"
            "VOCs 物种/OFP 小时窗口不超过 24 小时。"
        ),
    ),
):
    workflow_catalog.register(_definition)


def get_mode_workflow(mode: str) -> FixedWorkflowDefinition | None:
    """Return the fixed workflow for an Agent mode, if one is registered."""
    return workflow_catalog.get("agent_mode", mode)


def current_phase(
    definition: FixedWorkflowDefinition,
    progress: Mapping[str, Any],
) -> WorkflowPhaseDefinition:
    index = min(
        max(int(progress.get("phase_index") or 0), 0),
        len(definition.phases) - 1,
    )
    return definition.phases[index]


def render_phase_prompt(
    definition: FixedWorkflowDefinition,
    progress: Mapping[str, Any],
    *,
    has_submit_result: bool = False,
) -> str:
    phase = current_phase(definition, progress)
    attempt = int(progress.get("phase_attempt") or 0) + 1
    remaining = max(phase.max_attempts - attempt + 1, 0)
    prompt = (
        f"## 固定工作流阶段：{phase.name}\n"
        f"{phase.description}\n"
        f"这是本阶段第 {attempt}/{phase.max_attempts} 次机会，剩余 {remaining} 次。"
        "运行时只暴露本阶段允许的工具，并负责推进阶段；不要自行重复或回退阶段。"
    )
    if not phase.allowed_tools:
        if has_submit_result:
            # 交付阶段由调用方动态注入 submit_result：它不是"空工具"阶段，
            # 提交成功即结束本轮（runtime 交付边界），不会再要求额外纯文本轮。
            prompt += (
                "硬性约束：本轮只暴露交付工具 submit_result；"
                "请基于已有证据调用 submit_result 提交结构化结果，"
                "不要再调用分析/取数工具。"
            )
        else:
            prompt += (
                "硬性约束：本轮请求 tools 为空，你必须直接输出一段纯文本答案；"
                "输出任何工具调用（含手写调用标记）都会导致本轮失败。"
            )
    return prompt


def allowed_tools(
    definition: FixedWorkflowDefinition,
    progress: Mapping[str, Any],
) -> set[str]:
    return set(current_phase(definition, progress).allowed_tools)


def can_complete(
    definition: FixedWorkflowDefinition,
    progress: Mapping[str, Any],
) -> bool:
    return current_phase(definition, progress).allow_completion


def observe_tool_results(
    definition: FixedWorkflowDefinition,
    progress: MutableMapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> None:
    """Advance a workflow after one bounded tool turn.

    Every phase with advance tools gets repair turns while failures remain
    (bounded by phase.max_attempts); a fully successful batch advances
    immediately. This keeps the normalize phase from moving on to delivery
    with only a failed computation in hand.
    """
    if not records:
        return
    phase = current_phase(definition, progress)
    phase_records = [
        record
        for record in records
        if str(record.get("tool_name") or "") in phase.advance_tools
    ]
    if not phase_records:
        return
    attempt = int(progress.get("phase_attempt") or 0) + 1
    progress["phase_attempt"] = attempt
    failures = [
        record for record in phase_records if _result_failed(record.get("result"))
    ]
    progress["last_failed_tools"] = [
        str(record.get("tool_name") or "") for record in failures
    ]

    # 失败即留在当前阶段修复（受 max_attempts 预算约束），全批成功或预算
    # 耗尽才推进——acquire 与 normalize 语义一致，避免带着失败结果进交付。
    should_advance = not failures or attempt >= phase.max_attempts
    if should_advance:
        progress["phase_index"] = min(
            int(progress.get("phase_index") or 0) + 1,
            len(definition.phases) - 1,
        )
        progress["phase_attempt"] = 0


def _result_failed(result: Any) -> bool:
    if not isinstance(result, Mapping):
        return True
    if result.get("success") is False:
        return True
    return str(result.get("status") or "").lower() in {
        "failed",
        "error",
        "cancelled",
        "invalid_result",
    }
