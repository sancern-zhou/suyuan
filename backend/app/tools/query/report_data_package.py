from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import structlog

from app.agent.context.execution_context import ExecutionContext

logger = structlog.get_logger()


def stats_dict_to_view_rows(
    stats: Optional[Dict[str, Any]],
    name_field: str,
    *,
    exclude_keys: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Convert keyed report statistics into explicit rows for Agent reads."""
    rows: List[Dict[str, Any]] = []
    excluded = exclude_keys or set()
    for name, values in (stats or {}).items():
        if name in excluded:
            continue
        if isinstance(values, dict):
            rows.append({name_field: name, **values})
        else:
            rows.append({name_field: name, "value": values})
    return rows


def save_report_data_package(
    *,
    context: Optional[ExecutionContext],
    tool_name: str,
    query: Dict[str, Any],
    result: Dict[str, Any],
    metadata: Dict[str, Any],
    primary_view_name: str,
    primary_name_field: str,
    primary_stats: Optional[Dict[str, Any]] = None,
    extra_views: Optional[Dict[str, Any]] = None,
    exclude_primary_keys: Optional[Set[str]] = None,
    package_kind: str = "standard_report",
) -> Optional[str]:
    """Persist a structured statistical report package and return its file path.

    Statistical report tools should not save raw daily records. If downstream
    analysis needs daily details, call the dedicated daily data query tools.
    """
    try:
        views: Dict[str, Any] = {
            primary_view_name: stats_dict_to_view_rows(
                primary_stats or {},
                primary_name_field,
                exclude_keys=exclude_primary_keys,
            ),
            "result": result.get("result"),
        }
        for view_name, view_data in (extra_views or {}).items():
            if view_data is not None:
                views[view_name] = view_data

        package = {
            "kind": package_kind,
            "tool_name": tool_name,
            "query": query,
            "summary": result.get("summary"),
            "metadata": metadata,
            "views": views,
            "source_note": "统计报表包只保存汇总/对比结果；如需日报明细，请调用对应城市或站点日数据查询工具。",
        }

        if context is None:
            raise ValueError("ExecutionContext is required to save a report data file")
        file_path = context.save_data(
            package,
            schema="standard_report_package",
            metadata={
                **metadata,
                "session_id": context.session_id,
                "tool_name": tool_name,
                "package_kind": package_kind,
                "data_role": "statistical_report",
            },
        )
        logger.info(
            "report_data_file_saved",
            report_file_path=file_path,
            tool_name=tool_name,
            package_kind=package_kind,
        )
        return file_path
    except Exception as e:
        logger.warning("failed_to_save_report_data_package", error=str(e), tool_name=tool_name)
        return None


def attach_report_data_id(
    result: Dict[str, Any],
    report_data_id: Optional[str],
    *,
    summary_label: str = "统计报表",
) -> Dict[str, Any]:
    """Attach a report file path to a UDF-style tool result."""
    if not report_data_id:
        return result
    metadata = result.setdefault("metadata", {})
    metadata["report_file_path"] = report_data_id
    result["report_file_path"] = report_data_id
    result["summary"] = f"{result.get('summary', '')} | {summary_label}已保存为 report_file_path: {report_data_id}"
    return result
