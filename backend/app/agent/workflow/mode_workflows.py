"""Fixed workflows for latency-sensitive Agent modes.

The model chooses query arguments, while the runtime owns phase transitions,
tool visibility, retry bounds, and the final delivery boundary.
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Sequence

from .catalog import (
    FixedWorkflowDefinition,
    WorkflowPhaseDefinition,
    workflow_catalog,
)


_SESSION_INPUT_TOOLS = (
    "list_session_resources",
    "read_session_resource",
    "read_file",
)

_MONITORING_QUERY_TOOLS = (
    "query_xcai_city_history",
    "execute_sql_query",
    "execute_crawler_sql_query",
    "execute_postgres_sql_query",
    "query_airdata_platform",
    "airdata_calc_report_summary",
    "xuchang_station_catalog",
    "query_national_city_air_quality",
    "resolve_station_geo",
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


def _query_definition(
    name: str,
    query_tools: tuple[str, ...],
    description: str,
) -> FixedWorkflowDefinition:
    return FixedWorkflowDefinition(
        name=name,
        entrypoint="agent_mode",
        version="1",
        description=description,
        phases=(
            WorkflowPhaseDefinition(
                name="acquire",
                description=(
                    "一次规划完整取数范围，并在同一轮发出全部相互独立的查询。"
                    "不同数据库或接口使用多个工具调用；同库关联数据使用一条合法的 JOIN/UNION/CTE 查询。"
                    "禁止多语句 SQL。若首轮有失败，第二轮只修复失败项，不得重查成功项或扩大范围。"
                ),
                allowed_tools=tuple(dict.fromkeys((*_SESSION_INPUT_TOOLS, *query_tools))),
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
        "空气质量监测数据固定问数流程",
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
