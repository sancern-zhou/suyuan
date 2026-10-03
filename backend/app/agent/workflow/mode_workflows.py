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
_CITY_CONTRACT_TABLES = ("CityHour", "CityDay", "CityYearPm25Avg")

_MONITORING_QUERY_TOOLS = (
    "query_xcai_city_history",
    "execute_sql_query",
    "execute_crawler_sql_query",
    "execute_postgres_sql_query",
    "query_airdata_platform",
    "xuchang_station_catalog",
    "airdata_calc_report_summary",
    "query_national_city_air_quality",
)

# 站点层级问数：国控站走采集库 SQL；乡镇站/中台口径走"目录解析编码 → 中台查询"
# （编码不可猜，该串行为必要轮次）。目录工具与中台工具必须成对配置。
_MONITORING_STATION_QUERY_TOOLS = (
    "execute_crawler_sql_query",
    "xuchang_station_catalog",
    "query_airdata_platform",
)

# 城市层级问数：城市小时/日/年均值 + SQL Server 城市发布历史 + 中台接口。
_MONITORING_CITY_QUERY_TOOLS = (
    "query_xcai_city_history",
    "execute_sql_query",
    "execute_crawler_sql_query",
    "execute_postgres_sql_query",
    "query_airdata_platform",
    "airdata_calc_report_summary",
    "query_national_city_air_quality",
)

_FORECAST_QUERY_TOOLS = (
    "get_weather_data",
    "get_current_weather",
    "get_weather_forecast",
    "query_airdata_platform",
    "xuchang_station_catalog",
    "resolve_station_geo",
    "execute_postgres_sql_query",
)

_NORMALIZE_TOOLS = (
    "execute_python",
    "read_file",
    "read_session_resource",
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
                max_attempts=2,
                allow_completion=False,
            ),
            WorkflowPhaseDefinition(
                name="normalize",
                description=(
                    "检查成功结果的时间范围、记录数、字段和缺口。只有确需合并或补充质量统计时，"
                    "才调用一次 execute_python；否则直接交付。禁止新增数据源查询。"
                ),
                allowed_tools=_NORMALIZE_TOOLS,
                advance_tools=_NORMALIZE_TOOLS,
                max_attempts=1,
                allow_completion=True,
            ),
            WorkflowPhaseDefinition(
                name="deliver",
                description=(
                    "停止调用工具，直接交付 file_path、字段说明、时间与区域口径、记录数以及数据缺口。"
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
            "（StationHour/StationDay，按名称或区域 LIKE 过滤，无需解析目录）；"
            "乡镇站与中台口径数据先用 xuchang_station_catalog 解析编码"
            "（支持按名称模糊、按区县展开下辖站点），再调 query_airdata_platform 查询。"
        ),
        context_block=_table_contract_block(_STATION_CONTRACT_TABLES),
    ),
    _query_definition(
        "query_monitoring_city",
        _MONITORING_CITY_QUERY_TOOLS,
        "城市层级空气质量监测固定问数流程",
        scope_line=(
            "聚焦城市层级取数：城市小时/日/年均值、城市发布历史与全国对比，"
            "主要使用 CityHour/CityDay/CityYearPm25Avg 表；"
            "城市发布历史（CityAQIPublishHistory）用 query_xcai_city_history。"
        ),
        context_block=_table_contract_block(_CITY_CONTRACT_TABLES),
    ),
    _query_definition(
        "query_forecast",
        _FORECAST_QUERY_TOOLS,
        "气象实况、气象预报与空气质量预报固定问数流程",
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
) -> str:
    phase = current_phase(definition, progress)
    attempt = int(progress.get("phase_attempt") or 0) + 1
    remaining = max(phase.max_attempts - attempt + 1, 0)
    return (
        f"## 固定工作流阶段：{phase.name}\n"
        f"{phase.description}\n"
        f"这是本阶段第 {attempt}/{phase.max_attempts} 次机会，剩余 {remaining} 次。"
        "运行时只暴露本阶段允许的工具，并负责推进阶段；不要自行重复或回退阶段。"
    )


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

    Acquisition gets one repair turn only when at least one call failed. A
    successful batch advances immediately. Normalization always advances after
    its single optional tool turn.
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

    should_advance = phase.name != "acquire" or not failures or attempt >= phase.max_attempts
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
