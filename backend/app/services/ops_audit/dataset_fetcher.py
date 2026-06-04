"""Dataset extraction helpers for operations work order audits."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.ops_audit.audit_window import calculate_weekly_created_window
from app.services.ops_audit.config import load_audit_window_config
from app.services.ops_audit.evidence_builder import build_dataset_evidence, build_summary_evidence
from app.services.ops_work_order_audit_engine import OUTPUT_DIR, WorkOrderDatasetFilter, fetch_dataset


@dataclass
class DatasetFetchRequest:
    """Request parameters for a work order dataset fetch."""

    limit: int = 200
    order_statuses: list[str] | None = None
    create_time_start: str | None = None
    create_time_end: str | None = None
    finish_time_start: str | None = None
    finish_time_end: str | None = None
    audit_window_preset: str | None = "weekly_created"
    station_ids: list[str] | None = None
    order_types: list[str] | None = None
    maintenance_types: list[str] | None = None
    working_order_codes: list[str] | None = None
    evidence_level: str = "summary"
    output_dir: Path | None = None
    persist_dataset: bool = True


def fetch_ops_audit_dataset(request: DatasetFetchRequest) -> dict[str, Any]:
    """Fetch a dataset using creation-time centric audit windows."""

    request = _apply_window_defaults(request)
    dataset = fetch_dataset(
        WorkOrderDatasetFilter(
            limit=max(1, min(int(request.limit or 200), 3000)),
            order_statuses=request.order_statuses,
            create_time_start=request.create_time_start,
            create_time_end=request.create_time_end,
            finish_time_start=request.finish_time_start,
            finish_time_end=request.finish_time_end,
            station_ids=request.station_ids,
            order_types=request.order_types,
            maintenance_types=request.maintenance_types,
            working_order_codes=request.working_order_codes,
        )
    )

    output_dir = (request.output_dir or OUTPUT_DIR).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = output_dir / "latest_finished_work_orders_dataset.json"
    if request.persist_dataset:
        import json

        dataset_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = _build_dataset_summary(dataset)
    evidence = build_dataset_evidence(dataset, evidence_level=request.evidence_level)
    return {
        "success": True,
        "dataset_path": str(dataset_path),
        "query_info": dataset.get("query_info", {}),
        "audit_window": _current_audit_window(request),
        "coverage": _dataset_coverage(dataset),
        "summary": summary,
        "evidence": evidence,
        "sample_orders": dataset.get("orders", [])[:8],
    }


def _apply_window_defaults(request: DatasetFetchRequest) -> DatasetFetchRequest:
    has_explicit_time = any(
        [
            request.create_time_start,
            request.create_time_end,
            request.finish_time_start,
            request.finish_time_end,
            request.working_order_codes,
        ]
    )
    preset = (request.audit_window_preset or "").strip().lower()
    if preset in {"", "none", "off", "disabled"} or has_explicit_time:
        return request
    if preset != "weekly_created":
        raise ValueError(f"不支持的审核窗口预设：{request.audit_window_preset}")

    window_config = load_audit_window_config().get("audit_window", {})
    anchor_weekday = _weekday_index(window_config.get("anchor_weekday", "Wednesday"))
    window = calculate_weekly_created_window(
        timezone=str(window_config.get("timezone") or "Asia/Shanghai"),
        anchor_weekday=anchor_weekday,
        created_start_offset_days=int(window_config.get("created_start_offset_days", 14)),
        created_end_offset_days=int(window_config.get("created_end_offset_days", 7)),
        order_statuses=list(window_config.get("order_statuses", ["Finish"])),
    )
    request.create_time_start = window.create_time_start
    request.create_time_end = window.create_time_end
    if not request.order_statuses:
        request.order_statuses = window.order_statuses
    return request


def _current_audit_window(request: DatasetFetchRequest) -> dict[str, Any] | None:
    if not request.create_time_start and not request.create_time_end:
        return None
    return {
        "preset": request.audit_window_preset,
        "create_time_start": request.create_time_start,
        "create_time_end": request.create_time_end,
        "finish_time_start": request.finish_time_start,
        "finish_time_end": request.finish_time_end,
        "order_statuses": request.order_statuses,
    }


def _weekday_index(name: Any) -> int:
    value = str(name or "").strip().lower()
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    return weekdays.get(value, 2)


def _build_dataset_summary(dataset: dict[str, Any]) -> dict[str, Any]:
    orders = dataset.get("orders", [])
    details = dataset.get("details", [])
    attachments = dataset.get("attachments", [])
    wo_commonfile = dataset.get("wo_commonfile", [])
    devices = dataset.get("devices", [])
    device_history = dataset.get("device_history") or {}
    rf_forms = dataset.get("rf_forms", {})
    rf_table_counts = {
        table: len([row for row in rows if not row.get("_query_error")])
        for table, rows in rf_forms.items()
        if any(not row.get("_query_error") for row in rows)
    }
    order_type_counts = _count_field(orders, "DDWORKINGORDERTYPE")
    maintenance_type_counts = _count_field(orders, "MAINTENANCETYPE")
    return {
        "order_count": len(orders),
        "detail_count": len(details),
        "attachment_count": len(attachments),
        "wo_commonfile_count": len(wo_commonfile),
        "device_count": len(devices),
        "device_history_order_count": len(device_history.get("orders", [])),
        "rf_record_count": sum(rf_table_counts.values()),
        "order_type_counts": order_type_counts,
        "maintenance_type_counts": maintenance_type_counts,
        "rf_table_counts": rf_table_counts,
    }


def _dataset_coverage(dataset: dict[str, Any]) -> dict[str, Any]:
    orders = dataset.get("orders", [])
    create_times = sorted(str(order.get("CREATETIME")) for order in orders if order.get("CREATETIME"))
    finish_times = sorted(str(order.get("FINISHTIME")) for order in orders if order.get("FINISHTIME"))
    station_ids = {str(order.get("STATIONID")) for order in orders if order.get("STATIONID")}
    return {
        "query_info": dataset.get("query_info", {}),
        "actual_create_time_start": create_times[0] if create_times else None,
        "actual_create_time_end": create_times[-1] if create_times else None,
        "actual_finish_time_start": finish_times[0] if finish_times else None,
        "actual_finish_time_end": finish_times[-1] if finish_times else None,
        "station_count": len(station_ids),
        "station_sample": sorted(station_ids)[:20],
        "has_orders": bool(orders),
    }


def _count_field(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        key = str(record.get(field) or "<空>")
        counts[key] = counts.get(key, 0) + 1
    return counts
