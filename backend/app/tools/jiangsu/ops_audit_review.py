"""Jiangsu non-fault operations work-order audit from the local ODS database.

This is the Jiangsu counterpart of the shared (SQL-Server backed) ops audit.
It reads routine work orders (巡检/现场检查/校准/质控/质量保证/数据录入) from the
local PostgreSQL ODS (jiangsu_ods, populated by the Jiangsu sync pipeline),
translates the generic ``rFCommon`` form matrix into named business fields via
the extracted form dictionaries, runs deterministic audit rules, and produces
a report input for the report package chain.

Data freshness is bounded by the sync watermark (``query_info.rf_common_watermark``);
there is deliberately no platform-API fallback — if the ODS has no matching rows
the fetch fails loudly so the gap is visible.

Two tools are exposed to the Agent:

- ``jiangsu_ops_audit_fetch_dataset``: ODS query + translate -> dataset JSON
- ``jiangsu_ops_audit_run_rules``: deterministic rules -> issues + report input
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, Optional

import asyncpg
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.jiangsu.ops_audit_form_fields import (
    component_name,
    device_identity,
    load_form,
    translate_rfcommon,
)
from app.tools.resource_refs import build_file_ref, merge_refs
from app.utils.path_config import format_agent_path, get_data_registry, resolve_agent_path

logger = structlog.get_logger()

AUDITABLE_ORDER_TYPES = ["Check", "SECCheck", "Calibration", "QC", "QA", "DataEntry"]
ORDER_TYPE_LABELS = {
    "Check": "巡检单", "SECCheck": "现场检查单", "Calibration": "校准单",
    "QC": "质控检查单", "QA": "质量保证单", "DataEntry": "数据录入",
}
WORKFLOW_STATUS_LABELS = {
    "待分配": "ToAssign", "待领取": "ToAccept", "处理中": "Doing", "已完成": "Finish", "已拒绝": "Reject",
}
ORDER_STATUS_LABELS = {
    "待处理": "Wait", "处理中": "Doing", "已完成": "Finish", "已作废": "Invalid",
}
FINISHED_ORDER_STATUSES = {"Finish", "已完成"}
MAX_FETCH = 300

# DB 取数(本地 ODS):非故障工单、任务项与 rFCommon 表单矩阵由江苏同步管线
# 落到本地 PostgreSQL(jiangsu_ods);同步水位之后的新单不在本工具覆盖范围。
DB_DSN_ENV = "OPS_MART_DATABASE_URL"
RF_COMMON_TABLE = "jiangsu_ods.rf_common"
# 同步回填窗口(sync_config.full_load_since)下界:rf_common 表单只有该窗口
# 之后的行,更早的工单即使主表在库也无表单可审,直接查不到比返回半截数据好。
DB_SYNC_WINDOW_START = "2026-07-01 00:00:00"
# 平台 rFCommon 键为驼峰/小写混合;同步引擎把列名统一小写,
# 从库行构造 rFCommon 时补回这些驼峰别名(字典按驼峰取值)。
RFCOMMON_CAMEL_KEYS = (
    "checkDate", "deviceBrand", "deviceCode", "deviceId", "deviceModel",
    "isCancel", "workingOrderCode",
)
DB_WORKFLOW_STATUS_CN = {code: cn for cn, code in WORKFLOW_STATUS_LABELS.items()}
DB_ORDER_STATUS_CN = {code: cn for cn, code in ORDER_STATUS_LABELS.items()}


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _as_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [part.strip() for part in values.split(",") if part.strip()]
    return [str(value).strip() for value in values if str(value).strip()]


def _normalize_statuses(values: Any, labels: dict[str, str]) -> list[str]:
    result = []
    for value in _as_list(values):
        result.append(labels.get(value, value))
    return result


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _parse_float(value: Any) -> float | None:
    text = _text(value).replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _status_is_bad(value: Any) -> bool | None:
    if value is True:
        return False
    if value is False:
        return True
    text = _text(value).lower()
    if text in {"否", "false", "0", "异常", "不合格", "不正常", "不通过"}:
        return True
    if text in {"是", "true", "1", "正常", "合格", "通过"}:
        return False
    return None


def _reference_bounds(reference_limit: Any) -> tuple[float, float] | None:
    """Parse a numeric interval from a reference-limit string, if present."""
    text = _text(reference_limit)
    if not text:
        return None
    interval = re.search(r"(-?\d+(?:\.\d+)?)\s*[~～\-—至]\s*(-?\d+(?:\.\d+)?)", text)
    if interval:
        low, high = float(interval.group(1)), float(interval.group(2))
        return (min(low, high), max(low, high))
    upper = re.search(r"[≤<]=?\s*(-?\d+(?:\.\d+)?)", text)
    lower = re.search(r"[≥>]=?\s*(-?\d+(?:\.\d+)?)", text)
    if upper and lower:
        return (float(lower.group(1)), float(upper.group(1)))
    if upper:
        return (float("-inf"), float(upper.group(1)))
    if lower:
        return (float(lower.group(1)), float("inf"))
    return None


def _scheduled_output_dir(context: Any) -> Path | None:
    scheduled = getattr(context, "scheduled_task_context", None)
    if not isinstance(scheduled, dict):
        return None
    task_id = _text(scheduled.get("task_id"))
    execution_id = _text(scheduled.get("execution_id"))
    if not task_id or not execution_id:
        return None
    return (
        get_data_registry() / "scheduled_tasks" / "executions"
        / re.sub(r"[^0-9A-Za-z_-]+", "_", task_id)
        / re.sub(r"[^0-9A-Za-z_-]+", "_", execution_id)
        / "jiangsu_ops_audit"
    ).resolve()


def _output_dir(context: Any, requested: str | None) -> Path:
    scheduled = _scheduled_output_dir(context)
    if scheduled is not None:
        return scheduled
    if requested:
        return resolve_agent_path(requested)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return (get_data_registry() / "ops_audit" / "jiangsu" / stamp).resolve()


def _normalize_task(
    item: dict[str, Any],
    *,
    order_type: str,
) -> dict[str, Any]:
    rfcommon = item.get("rFCommon") or {}
    tag = _text(item.get("ruleItemTag"))
    pollutant = _text(item.get("pollutantType"))
    form = load_form(tag, order_type=order_type, pollutant_type=pollutant)
    translated = translate_rfcommon(form, rfcommon)
    attachments = []
    for file in item.get("commonFile") or []:
        if not isinstance(file, dict):
            continue
        attachments.append(
            {
                "id": file.get("id"),
                "file_name": file.get("fileName"),
                "file_path": file.get("filePath"),
                "function_code": file.get("functionCode"),
                "type_code": file.get("typeCode"),
                "create_time": file.get("createTime"),
            }
        )
    return {
        "rule_item_tag": tag,
        "rule_item_name": _text(item.get("ruleItemName")),
        "pollutant_type": pollutant,
        "status": item.get("status"),
        "process_start": item.get("prosessSdtTime"),
        "process_end": item.get("prosessEdtTime"),
        "plan_finish_time": item.get("planFinishTime"),
        "detail_id": item.get("detailId"),
        "form_component": translated.get("component") or "",
        "form_matched": translated.get("matched", False),
        "device": device_identity(rfcommon),
        "fields": translated.get("fields", []),
        "rows": translated.get("rows", []),
        "attachments": attachments,
    }


def _db_dsn() -> str:
    dsn = os.getenv(DB_DSN_ENV, "")
    if not dsn:
        raise RuntimeError(f"{DB_DSN_ENV} 未配置")
    return dsn


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="milliseconds")
    return value


def _rfcommon_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """把 rf_common 库行转成与平台详情 API 一致的 rFCommon dict。

    同步列名全小写;字典按小写(string1/time1/remark1)与驼峰(deviceBrand 等)
    取值,这里统一补回驼峰别名。
    """
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key.startswith("_") or key in ("stringjson", "booljson", "remarkjson"):
            continue
        out[key] = _iso(value)
    for key in RFCOMMON_CAMEL_KEYS:
        low = key.lower()
        if low in out and out[low] is not None:
            out[key] = out[low]
    return out


def _component_type_key(rule_item_tag: str, pollutant_type: str) -> str:
    return component_name(rule_item_tag, pollutant_type).lower()


def _parse_dt(value: Any) -> datetime | None:
    """Parse a create-time filter string; None keeps the filter absent."""
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return None


async def _db_fetch_orders(
    pg: asyncpg.Connection,
    *,
    order_types: list[str],
    create_start: str | None,
    create_end: str | None,
    wf_values: list[str],
    order_values: list[str],
    order_codes: list[str],
    station_values: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    clauses = [
        "w.ordertype <> 'Fault'",
        "w.ordertype = ANY($1)",
        f"w.createtime >= '{DB_SYNC_WINDOW_START}'::timestamp",
    ]
    args: list[Any] = [order_types]

    def add(value: Any) -> str:
        args.append(value)
        return f"${len(args)}"

    if create_start:
        clauses.append(f"w.createtime >= {add(create_start)}")
    if create_end:
        clauses.append(f"w.createtime <= {add(create_end)}")
    if wf_values:
        clauses.append(f"w.workflowstatus = ANY({add(wf_values)})")
    if order_values:
        clauses.append(f"w.orderstatus = ANY({add(order_values)})")
    if order_codes:
        clauses.append(f"w.workingordercode ILIKE ANY({add([f'%{c}%' for c in order_codes])})")
    if station_values:
        clauses.append(f"w.stationcode = ANY({add(station_values)})")
    rows = await pg.fetch(
        f"""
        SELECT w.workingordercode, w.ordertype, w.orderstatus, w.workflowstatus,
               w.workflowid, w.stationid, w.stationcode, s.positionname AS station_name,
               c.name AS city_name, mu.name AS operation_unit_name,
               w.ordertitle, w.ordercontent, w.currentpoint,
               cp.taskname AS current_point_name,
               w.createtime, w.finishtime, w.planfinishtime,
               bd.devicecode, w.ismakeup
        FROM jiangsu_ods.mtc_working_order w
        LEFT JOIN jiangsu_ods.bsd_station s ON s.stationcode = w.stationcode
        LEFT JOIN jiangsu_ods.bsd_city c
               ON c.level = '2'
              AND c.code = CASE WHEN length(s.areacode) >= 4
                                THEN rpad(left(s.areacode, 4), 6, '0')
                                ELSE s.areacode END
        LEFT JOIN jiangsu_ods.bsd_maintenanceunit mu ON mu.code = w.operationunitid
        LEFT JOIN jiangsu_ods.wfl_workflowtask cp ON cp.guid = w.currentpoint
        LEFT JOIN LATERAL (
            SELECT d.devicecode FROM jiangsu_ods.bsd_device d WHERE d.id = w.deviceid LIMIT 1
        ) bd ON w.deviceid IS NOT NULL
        WHERE {' AND '.join(clauses)}
        ORDER BY w.createtime DESC
        LIMIT {add(limit)}
        """,
        *args,
    )
    return [dict(row) for row in rows]


async def _db_fetch_tasks(
    pg: asyncpg.Connection, codes: list[str]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    """按工单号返回 (tasks, process, attachments)。"""
    task_rows = await pg.fetch(
        """
        SELECT t.workingordercode, t.id AS task_item_id, t.ruleitemtag, t.pollutanttype,
               t.status, t.prosesssdttime, t.prosessedttime, t.planfinishtime, t.detailid,
               ri.ruleitemname AS rule_item_name
        FROM jiangsu_ods.mtc_taskitem t
        LEFT JOIN jiangsu_ods.rf_ruleitem ri
               ON ri.ruleitemtag = t.ruleitemtag AND ri.pollutanttype = t.pollutanttype
        WHERE t.workingordercode = ANY($1)
        ORDER BY t.id
        """,
        codes,
    )
    tasks_by_code: dict[str, list[dict[str, Any]]] = {}
    for row in task_rows:
        tasks_by_code.setdefault(row["workingordercode"], []).append(dict(row))

    process_rows = await pg.fetch(
        """
        SELECT d.workingordercode, d.processstep, d.processsdttime, d.processedttime,
               d.issubmit, d.submitremark
        FROM jiangsu_ods.mtc_working_order_detail d
        WHERE d.workingordercode = ANY($1)
        ORDER BY d.id
        """,
        codes,
    )
    process_by_code: dict[str, list[dict[str, Any]]] = {}
    for row in process_rows:
        process_by_code.setdefault(row["workingordercode"], []).append(dict(row))

    file_rows = await pg.fetch(
        """
        SELECT f.workingordercode, f.id, f.filename, f.filepath, f.functioncode,
               f.typecode, f.createtime
        FROM jiangsu_ods.wo_commonfile f
        WHERE f.workingordercode = ANY($1)
        ORDER BY f.id
        """,
        codes,
    )
    files_by_code: dict[str, list[dict[str, Any]]] = {}
    for row in file_rows:
        files_by_code.setdefault(row["workingordercode"], []).append(dict(row))
    return tasks_by_code, process_by_code, files_by_code


async def _db_fetch_rfcommon(
    pg: asyncpg.Connection, codes: list[str]
) -> tuple[dict[str, list[dict[str, Any]]], str | None]:
    rows = await pg.fetch(
        f"SELECT * FROM {RF_COMMON_TABLE} WHERE workingordercode = ANY($1) ORDER BY id",
        codes,
    )
    rf_by_code: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        entry = dict(row)
        code = entry.pop("workingordercode")
        rf_by_code.setdefault(code, []).append(entry)
    watermark = await pg.fetchval(f"SELECT max(_src_incremental) FROM {RF_COMMON_TABLE}")
    return rf_by_code, watermark


async def _db_fetch_workflow_steps(
    pg: asyncpg.Connection, workflow_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    rows = await pg.fetch(
        """
        SELECT wt.workflowid, wt.taskname, wt.formcode
        FROM jiangsu_ods.wfl_workflowtask wt
        WHERE wt.workflowid = ANY($1)
        ORDER BY wt.rank
        """,
        workflow_ids,
    )
    steps_by_workflow: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        steps_by_workflow.setdefault(row["workflowid"], []).append(dict(row))
    return steps_by_workflow


async def _fetch_dataset_from_db(
    context: Any,
    *,
    order_types: list[str] | None,
    create_time_start: str | None,
    create_time_end: str | None,
    workflow_statuses: list[str] | None,
    order_statuses: list[str] | None,
    working_order_codes: list[str] | None,
    station_codes: list[str] | None,
    limit: int,
) -> dict[str, Any]:
    """从本地 ODS 组装审核数据集;取不到数据直接抛错,不回退平台 API。"""
    requested_types = _as_list(order_types) or list(AUDITABLE_ORDER_TYPES)
    if "Fault" in requested_types:
        raise ValueError("本工具仅审核非故障工单；故障工单请使用故障工单审核链路")
    unsupported = [t for t in requested_types if t not in AUDITABLE_ORDER_TYPES]
    if unsupported:
        raise ValueError(f"不支持的工单类型：{unsupported}")

    wf_values = _normalize_statuses(workflow_statuses, WORKFLOW_STATUS_LABELS)
    order_values = _normalize_statuses(order_statuses, ORDER_STATUS_LABELS)
    order_codes = _as_list(working_order_codes)
    station_values = _as_list(station_codes)
    limit = max(1, min(int(limit or 50), MAX_FETCH))

    # asyncpg 参数按类型绑定,时间过滤先解析成 datetime。
    create_start = _parse_dt(create_time_start)
    create_end = _parse_dt(create_time_end)
    if create_time_start and create_start is None:
        raise ValueError("create_time_start 格式无法解析")
    if create_time_end and create_end is None:
        raise ValueError("create_time_end 格式无法解析")

    pg = await asyncpg.connect(_db_dsn())
    try:
        order_rows = await _db_fetch_orders(
            pg,
            order_types=requested_types,
            create_start=create_start,
            create_end=create_end,
            wf_values=wf_values,
            order_values=order_values,
            order_codes=order_codes,
            station_values=station_values,
            limit=limit,
        )
        if not order_rows:
            raise RuntimeError(
                "本地 ODS 无匹配工单（同步窗口自 2026-07-01 起，watermark 见 rf_common 同步水位）"
            )
        codes = [row["workingordercode"] for row in order_rows]
        workflow_ids = [_text(row["workflowid"]) for row in order_rows if _text(row["workflowid"])]
        tasks_by_code, process_by_code, files_by_code = await _db_fetch_tasks(pg, codes)
        rf_by_code, watermark = await _db_fetch_rfcommon(pg, codes)
        steps_by_workflow = await _db_fetch_workflow_steps(pg, workflow_ids)
    finally:
        await pg.close()

    orders: list[dict[str, Any]] = []
    for row in order_rows:
        code = _text(row["workingordercode"])
        order_type = _text(row["ordertype"])
        tasks_raw = tasks_by_code.get(code, [])
        rf_rows = rf_by_code.get(code, [])
        rf_by_detail = {entry["detailid"]: entry for entry in rf_rows}

        attachments_by_type: dict[str, list[dict[str, Any]]] = {}
        for entry in files_by_code.get(code, []):
            attachments_by_type.setdefault(_text(entry["typecode"]).lower(), []).append(entry)

        task_items = []
        for t in tasks_raw:
            tag = _text(t["ruleitemtag"])
            pollutant = _text(t["pollutanttype"])
            rf_row = rf_by_detail.get(_text(t["detailid"])) if _text(t["detailid"]) else None
            item = {
                "ruleItemTag": tag,
                "ruleItemName": _text(t.get("rule_item_name")),
                "pollutantType": pollutant,
                "status": t["status"],
                "prosessSdtTime": _iso(t["prosesssdttime"]),
                "prosessEdtTime": _iso(t["prosessedttime"]),
                "planFinishTime": _iso(t["planfinishtime"]),
                "detailId": t["detailid"],
                "rFCommon": _rfcommon_from_row(rf_row) if rf_row else {},
                "commonFile": [
                    {
                        "id": entry["id"],
                        "fileName": entry["filename"],
                        "filePath": entry["filepath"],
                        "functionCode": entry["functioncode"],
                        "typeCode": entry["typecode"],
                        "createTime": _iso(entry["createtime"]),
                    }
                    for entry in attachments_by_type.get(_component_type_key(tag, pollutant), [])
                ],
            }
            task_items.append(_normalize_task(item, order_type=order_type))

        workflow_id = _text(row["workflowid"])
        workflow_steps = [
            {"task_name": _text(s["taskname"]), "form_code": _text(s["formcode"])}
            for s in steps_by_workflow.get(workflow_id, [])
        ]
        step_names = {_text(s["formcode"]): _text(s["taskname"]) for s in steps_by_workflow.get(workflow_id, [])}
        process = [
            {
                "step": _text(p["processstep"]),
                "step_name": step_names.get(_text(p["processstep"]), _text(p["processstep"])),
                "submit_remark": _text(p["submitremark"]),
                "start": _iso(p["processsdttime"]),
                "end": _iso(p["processedttime"]),
                "is_submit": bool(p["issubmit"]),
            }
            for p in process_by_code.get(code, [])
        ]
        orders.append(
            {
                "working_order_code": code,
                "order_type": order_type,
                "order_type_str": ORDER_TYPE_LABELS.get(order_type, order_type),
                "station_id": row["stationid"],
                "station_code": _text(row["stationcode"]),
                "station_name": _text(row["station_name"]),
                "city": _text(row["city_name"]),
                "operation_unit_name": _text(row["operation_unit_name"]),
                "order_title": _text(row["ordertitle"]),
                "order_content": _text(row["ordercontent"]),
                "order_status": _text(row["orderstatus"]),
                "order_status_str": DB_ORDER_STATUS_CN.get(_text(row["orderstatus"]), _text(row["orderstatus"])),
                "workflow_status": _text(row["workflowstatus"]),
                "workflow_status_str": DB_WORKFLOW_STATUS_CN.get(_text(row["workflowstatus"]), _text(row["workflowstatus"])),
                "current_point_name": _text(row["current_point_name"]),
                "create_time": _iso(row["createtime"]),
                "finish_time": _iso(row["finishtime"]),
                "plan_finish_time": _iso(row["planfinishtime"]),
                "device_code": _text(row["devicecode"]),
                "is_makeup": row["ismakeup"],
                "workflow_steps": workflow_steps,
                "process": process,
                "tasks": task_items,
            }
        )

    task_total = sum(len(order["tasks"]) for order in orders)
    unmatched = sum(1 for order in orders for task in order["tasks"] if not task["form_matched"])
    attachment_total = sum(len(task["attachments"]) for order in orders for task in order["tasks"])
    return {
        "schema_version": "jiangsu_ops_audit_dataset.v1",
        "generated_at": _now_text(),
        "query_info": {
            "order_types": requested_types,
            "create_time_start": create_time_start,
            "create_time_end": create_time_end,
            "workflow_statuses": wf_values,
            "order_statuses": order_values,
            "working_order_codes": order_codes,
            "station_codes": station_values,
            "limit": limit,
            "source": "jiangsu_ods_db",
            "rf_common_watermark": _iso(watermark),
        },
        "summary": {
            "order_count": len(orders),
            "task_count": task_total,
            "unmapped_task_count": unmatched,
            "attachment_count": attachment_total,
            "order_type_counts": dict(Counter(o["order_type_str"] for o in orders)),
        },
        "orders": orders,
    }


def _save_dataset(dataset: dict[str, Any], context: Any, output_dir: str | None) -> Path:
    out_dir = _output_dir(context, output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / "jiangsu_ops_audit_dataset.json"
    dataset_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    return dataset_path


async def fetch_dataset(
    context: Any,
    *,
    order_types: list[str] | None = None,
    create_time_start: str | None = None,
    create_time_end: str | None = None,
    workflow_statuses: list[str] | None = None,
    order_statuses: list[str] | None = None,
    working_order_codes: list[str] | None = None,
    station_codes: list[str] | None = None,
    limit: int = 50,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """从本地 ODS 取数并落盘;取不到数据/库不可用时直接抛错。"""
    dataset = await _fetch_dataset_from_db(
        context,
        order_types=order_types,
        create_time_start=create_time_start,
        create_time_end=create_time_end,
        workflow_statuses=workflow_statuses,
        order_statuses=order_statuses,
        working_order_codes=working_order_codes,
        station_codes=station_codes,
        limit=limit,
    )
    dataset_path = _save_dataset(dataset, context, output_dir)
    orders = dataset["orders"]
    return {
        "dataset_path": format_agent_path(dataset_path),
        "summary": dataset["summary"],
        "query_info": dataset["query_info"],
        "sample_orders": [
            {
                "working_order_code": o["working_order_code"],
                "order_type_str": o["order_type_str"],
                "station_name": o["station_name"],
                "order_status_str": o["order_status_str"],
                "current_point_name": o["current_point_name"],
                "task_count": len(o["tasks"]),
            }
            for o in orders[:8]
        ],
    }


def _issue(
    rule_id: str,
    category: str,
    severity: str,
    order: dict[str, Any],
    task: dict[str, Any] | None,
    message: str,
    *,
    field_label: str = "",
    evidence: str = "",
    display_evidence: str = "",
    remark_entries: list[dict[str, str]] | None = None,
    remark_status: str = "",
) -> dict[str, Any]:
    issue = {
        "rule_id": rule_id,
        "category": category,
        "severity": severity,
        "working_order_code": order.get("working_order_code", ""),
        "station_name": order.get("station_name", ""),
        "city": order.get("city", ""),
        "operation_unit_name": order.get("operation_unit_name", ""),
        "order_type_str": order.get("order_type_str", ""),
        "rule_item_name": (task or {}).get("rule_item_name", ""),
        "rule_item_tag": (task or {}).get("rule_item_tag", ""),
        "field_label": field_label,
        "message": message,
        "display_evidence": display_evidence or message,
        "evidence": evidence,
    }
    if remark_entries:
        issue["remark_entries"] = remark_entries
    if remark_status:
        issue["remark_status"] = remark_status
    issue["issue_id"] = "JSI-" + sha1(
        json.dumps(
            [rule_id, issue["working_order_code"], issue["rule_item_tag"], field_label, message],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()[:12]
    return issue


def run_rules(dataset: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    coverage = {
        "orders": 0,
        "tasks": 0,
        "mapped_tasks": 0,
        "row_tasks": 0,
        "rows": 0,
        "attachments": 0,
    }

    for order in dataset.get("orders", []):
        coverage["orders"] += 1
        is_finished = (
            order.get("order_status") in FINISHED_ORDER_STATUSES
            or order.get("order_status_str") in FINISHED_ORDER_STATUSES
        )

        # Flow time order and finished-but-incomplete closure.
        unfinished_steps = []
        for entry in order.get("process", []):
            start, end = entry.get("start"), entry.get("end")
            if start and end and _text(end) < _text(start):
                step_name = entry.get("step_name") or entry.get("step") or ""
                issues.append(_issue(
                    "FLOW_TIME_ORDER", "流程完整性", "高", order, None,
                    f"{step_name} 节点完成时间早于开始时间。",
                    field_label=step_name,
                    evidence=f"start={start}; end={end}",
                    display_evidence=f"{step_name}：开始时间 {start}，完成时间 {end}，完成时间早于开始时间。",
                    remark_status="not_applicable",
                ))
            if is_finished and not entry.get("is_submit"):
                unfinished_steps.append(entry.get("step_name") or entry.get("step") or "")
        if is_finished and unfinished_steps:
            steps_text = "、".join(filter(None, unfinished_steps))
            issues.append(_issue(
                "FLOW_FINISH_INCOMPLETE", "流程闭环", "高", order, None,
                f"工单已完成但以下流程节点未提交：{steps_text}。",
                evidence="; ".join(filter(None, unfinished_steps)),
                display_evidence=f"工单已完成，但节点 {steps_text} 未提交办结。",
                remark_status="not_applicable",
            ))

        for task in order.get("tasks", []):
            coverage["tasks"] += 1
            if task.get("form_matched"):
                coverage["mapped_tasks"] += 1
            else:
                issues.append(_issue(
                    "FORM_UNMAPPED", "审核覆盖", "中", order, task,
                    f"表单 {task.get('rule_item_tag')} 未匹配到字段字典，本项未纳入规则审核。",
                    evidence=f"component={task.get('form_component')}",
                    display_evidence=f"检查项「{task.get('rule_item_name')}」的表单未纳入自动审核。",
                    remark_status="unavailable",
                ))
            coverage["attachments"] += len(task.get("attachments") or [])

            rows = task.get("rows") or []
            if rows:
                coverage["row_tasks"] += 1
            for row in rows:
                coverage["rows"] += 1
                label = row.get("label") or ""
                status_bad = _status_is_bad(row.get("status_value"))
                actual = row.get("actual_value")
                remark = row.get("remark_value")
                if status_bad is True and not _text(remark):
                    issues.append(_issue(
                        "TASK_ABNORMAL_NO_REMARK", "异常说明", "高", order, task,
                        f"{label}：检查结论为异常，但未填写异常处理记录。",
                        field_label=label, evidence=f"status={row.get('status_value')}",
                        display_evidence=(
                            f"{label}：检查结论为异常（{row.get('status_value')}），"
                            "异常处理记录未填写，需补充异常原因与处置情况。"
                        ),
                        remark_entries=[{"field_label": f"{label}-异常处理记录", "text": "", "status": "missing"}],
                        remark_status="missing",
                    ))
                bounds = _reference_bounds(row.get("reference_limit"))
                actual_value = _parse_float(actual)
                if bounds and actual_value is not None:
                    low, high = bounds
                    if actual_value < low or actual_value > high:
                        issues.append(_issue(
                            "TASK_VALUE_OUT_OF_RANGE", "数值合理性", "中", order, task,
                            f"{label}：实际值 {actual_value} 疑似超出参考范围 "
                            f"{row.get('reference_limit')}（待人工复核）。",
                            field_label=label,
                            evidence=f"actual={actual}; reference_limit={row.get('reference_limit')}",
                            display_evidence=(
                                f"{label}：实际值 {actual_value}，参考范围 {row.get('reference_limit')}，"
                                "实际值超出参考范围。"
                                + (f"异常处理记录：{_text(remark)}" if _text(remark) else "异常处理记录未填写。")
                            ),
                            remark_entries=[
                                {"field_label": f"{label}-异常处理记录", "text": _text(remark),
                                 "status": "provided" if _text(remark) else "missing"}
                            ],
                            remark_status="provided" if _text(remark) else "missing",
                        ))

            if task.get("status") in (1, True):
                for field in task.get("fields") or []:
                    label = field.get("label") or field.get("column")
                    if field.get("type") == "time" and field.get("value") in (None, ""):
                        issues.append(_issue(
                            "TASK_FIELD_MISSING", "记录完整性", "低", order, task,
                            f"{label}：检查项已完成，但时间字段为空（待人工复核）。",
                            field_label=label,
                            display_evidence=(
                                f"检查项「{task.get('rule_item_name')}」已完成，但时间字段“{label}”为空，"
                                "需核对该时间是否应当填写。"
                            ),
                            remark_status="not_applicable",
                        ))
                device = task.get("device") or {}
                if any(device.get(key) for key in ("device_brand", "device_model", "device_code")):
                    missing = [
                        label
                        for key, label in (("device_brand", "设备品牌"), ("device_model", "设备型号"), ("device_code", "设备编号"))
                        if not _text(device.get(key))
                    ]
                    if missing:
                        filled = "、".join(
                            label
                            for key, label in (("device_brand", "设备品牌"), ("device_model", "设备型号"), ("device_code", "设备编号"))
                            if _text(device.get(key))
                        )
                        issues.append(_issue(
                            "TASK_DEVICE_INCOMPLETE", "设备一致性", "中", order, task,
                            "检查项已完成，但设备信息不完整：" + "、".join(missing) + "。",
                            evidence=json.dumps(device, ensure_ascii=False),
                            display_evidence=(
                                f"检查项「{task.get('rule_item_name')}」已完成，但设备信息不完整："
                                f"{'、'.join(missing)}未填写"
                                + (f"；已填写：{filled}" if filled else "") + "。"
                            ),
                            remark_status="not_applicable",
                        ))

    severity_order = {"高": 0, "中": 1, "低": 2}
    issues.sort(key=lambda i: (severity_order.get(i["severity"], 3), i["working_order_code"]))
    rule_counts = Counter(i["rule_id"] for i in issues)
    affected_orders = sorted({i["working_order_code"] for i in issues})

    summary = {
        "issue_count": len(issues),
        "affected_order_count": len(affected_orders),
        "rule_counts": dict(rule_counts),
        "severity_counts": dict(Counter(i["severity"] for i in issues)),
        "coverage": coverage,
    }
    return {
        "issues": issues,
        "coverage": coverage,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# 报告输入（对齐共享版 report_input 口径：合并行 + report_ready 门禁）
# ---------------------------------------------------------------------------

_SEVERITY_RANK = {"高": 0, "中": 1, "低": 2}
_REMARK_STATUS_RANK = {"missing": 0, "unavailable": 1, "provided": 2, "not_applicable": 3}
_SEMANTIC_RANK = {"unresolved": 0, "needs_verification": 1, "valid_explanation": 2, "not_applicable": 3}


def _merged_remark_status(entries: list[dict[str, str]]) -> str:
    statuses = [_text(e.get("status")) or "unavailable" for e in entries] or ["unavailable"]
    return min(statuses, key=lambda s: _REMARK_STATUS_RANK.get(s, 9))


def _merge_semantic(semantic_blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    blocks = [b for b in semantic_blocks if isinstance(b, dict)]
    if not blocks:
        return None
    if any(not b.get("reviewed", False) for b in blocks):
        reviewed = [b for b in blocks if b.get("reviewed", False)]
        base = {
            "reviewed": False,
            "judgment": "unreviewed",
            "reason": "；".join(filter(None, (b.get("reason") for b in blocks if not b.get("reviewed"))))[:200]
            or "语义复核未覆盖。",
        }
    else:
        judgments = [(b.get("judgment") or "needs_verification") for b in blocks]
        base = {
            "reviewed": True,
            "judgment": min(judgments, key=lambda j: _SEMANTIC_RANK.get(j, 9)),
            "reason": "；".join(filter(None, (b.get("reason") for b in blocks)))[:300],
        }
    confidences = [b.get("confidence") for b in blocks if isinstance(b.get("confidence"), (int, float))]
    if confidences:
        base["confidence"] = round(min(confidences), 2)
    return base


def build_report_input(
    dataset: dict[str, Any],
    issues: list[dict[str, Any]],
    coverage: dict[str, Any],
    semantic_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge rule hits into report rows using the shared report_input contract."""
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    order_by_code = {
        _text(o.get("working_order_code")): o for o in dataset.get("orders", [])
    }

    for issue in issues:
        key = (
            _text(issue.get("working_order_code")),
            _text(issue.get("rule_item_tag")),
            _text(issue.get("field_label")),
        )
        row = merged.get(key)
        if row is None:
            order = order_by_code.get(key[0], {})
            row = {
                "issue_id": issue.get("issue_id"),
                "source_issue_ids": [issue.get("issue_id")],
                "working_order_code": issue.get("working_order_code", ""),
                "station_name": issue.get("station_name", ""),
                "city": issue.get("city", ""),
                "operation_unit_name": issue.get("operation_unit_name", ""),
                "order_type_str": issue.get("order_type_str", ""),
                "rf_form_name": issue.get("rule_item_name") or issue.get("rule_item_tag", ""),
                "rule_item_tag": issue.get("rule_item_tag", ""),
                "field_label": issue.get("field_label", ""),
                "message": issue.get("message", ""),
                "display_evidence": issue.get("display_evidence") or issue.get("message", ""),
                "remark_entries": list(issue.get("remark_entries") or []),
                "rule_ids": [issue.get("rule_id")],
                "severity": issue.get("severity", "低"),
                "create_time": order.get("create_time"),
                "semantic": issue.get("semantic"),
            }
            merged[key] = row
            continue
        row["source_issue_ids"].append(issue.get("issue_id"))
        if issue.get("rule_id") not in row["rule_ids"]:
            row["rule_ids"].append(issue.get("rule_id"))
        if issue.get("message") and issue["message"] not in row["message"]:
            row["message"] = f"{row['message']}；{issue['message']}"
        row["display_evidence"] = f"{row['display_evidence']}；{issue.get('display_evidence') or issue.get('message', '')}"
        for entry in issue.get("remark_entries") or []:
            if entry not in row["remark_entries"]:
                row["remark_entries"].append(entry)
        if _SEVERITY_RANK.get(issue.get("severity", "低"), 3) < _SEVERITY_RANK.get(row["severity"], 3):
            row["severity"] = issue.get("severity", "低")
        if _SEVERITY_RANK.get(issue.get("severity", "低"), 3) == _SEVERITY_RANK.get(row["severity"], 3):
            row["issue_id"] = issue.get("issue_id") or row["issue_id"]
        if issue.get("semantic") and not row.get("semantic"):
            row["semantic"] = issue.get("semantic")

    rows = []
    for row in merged.values():
        entries = row.pop("remark_entries", [])
        row["remark_context"] = {
            "entries": entries,
            "text": "<br>".join(
                f"{e.get('field_label')}：{e.get('text') or '未填写'}" for e in entries
            ),
            "status_label": _merged_remark_status(entries),
        }
        if len(row["rule_ids"]) == 1:
            row["rule_ids"] = row["rule_ids"]
        semantic = row.get("semantic")
        if isinstance(semantic, dict) and semantic.get("reviewed") and semantic.get("reason"):
            row["semantic_note"] = f"语义复核：{semantic['reason']}"
        rows.append(row)

    severity_order = {"高": 0, "中": 1, "低": 2}
    rows.sort(key=lambda r: (severity_order.get(r["severity"], 3), r["working_order_code"]))

    pending_semantic = sum(
        1 for issue in issues
        if issue.get("rule_id") in SEMANTIC_REVIEWABLE_RULES
        and not (issue.get("semantic") or {}).get("reviewed", False)
    )
    summary = {
        "report_issue_count": len(rows),
        "retained_count": len(issues),
        "affected_order_count": len({r["working_order_code"] for r in rows}),
        "rule_counts": dict(Counter(i["rule_id"] for i in issues)),
        "severity_counts": dict(Counter(r["severity"] for r in rows)),
        "pending_review_items": 0,
        "pending_semantic_reviews": pending_semantic,
        "report_ready": pending_semantic == 0,
        "coverage": coverage,
        "semantic": semantic_stats or {},
        "query_info": dataset.get("query_info", {}),
    }
    return {
        "schema_version": "jiangsu_ops_audit_report_input.v2",
        "summary": summary,
        "items": rows,
    }


# ---------------------------------------------------------------------------
# 语义审核（LLM 语义复核，无视觉识别）
# ---------------------------------------------------------------------------

SEMANTIC_REVIEWABLE_RULES = {
    "TASK_FIELD_MISSING",
    "TASK_VALUE_OUT_OF_RANGE",
    "TASK_ABNORMAL_NO_REMARK",
    "TASK_DEVICE_INCOMPLETE",
}
SEMANTIC_BATCH_ITEMS = 6
SEMANTIC_MAX_BATCHES = 8
SEMANTIC_LLM_TIMEOUT_SECONDS = 120.0

_SEMANTIC_SYSTEM_PROMPT = (
    "你是江苏运维平台例行工单审核的语义复核员。你必须只输出一个JSON对象，"
    '格式为 {"results": [{"review_item_id": "...", "judgment": "...", '
    '"confidence": 0.0到1.0, "reason": "不超过80字的中文理由"}]}，'
    "不要输出解释文字或Markdown代码块。每个输入项独立判断，不得用同一工单其他表单或字段的情况替代当前项。"
    "judgment 只能取以下值："
    "unresolved（规则命中成立，问题确实存在）；"
    "not_applicable（该规则对本表单/本字段不适用，属于误报）；"
    "valid_explanation（异常或缺失已有合理业务解释）；"
    "needs_verification（证据不足无法判断）。"
    "拿不准时给 needs_verification，不要放大化判定。"
)

_SEMANTIC_RULE_GUIDES: dict[str, str] = {
    "TASK_FIELD_MISSING": (
        "背景：检查项 status=已完成，但表单中某个时间类字段为空。"
        "请判断：结合检查项名称与字段含义，该时间字段在此类表单中是否为业务上必须填写的信息。"
        "若该字段在此类表单中通常不填、由其他字段承载时间、或属于可选附录信息，判 not_applicable；"
        "若确属应填而未填，判 unresolved；证据不足判 needs_verification。"
    ),
    "TASK_VALUE_OUT_OF_RANGE": (
        "背景：行式检查项的实际值疑似超出表单内置参考范围。"
        "请结合同行的异常处理记录/备注/上下文，判断该数值偏离是否已有基本合理的业务解释"
        "（如已处置复测、仪器无该功能、厂家备案参数与通用范围不同、单位或量程差异）。"
        "已有合理解释判 valid_explanation；无解释或解释与证据矛盾判 unresolved；无法判断判 needs_verification。"
        "简短但相关且不矛盾的说明（如“已处理”“已复测正常”“按厂家参数”）原则上判 valid_explanation。"
    ),
    "TASK_ABNORMAL_NO_REMARK": (
        "背景：行式检查项结论为异常，但当前异常处理记录字段为空。"
        "请结合该检查项其他字段与上下文，判断异常说明是否由其他字段承载（如处置记录、复测结果、处理记录）。"
        "已由其他字段合理解释判 valid_explanation；确无任何说明判 unresolved；无法判断判 needs_verification。"
    ),
    "TASK_DEVICE_INCOMPLETE": (
        "背景：检查项已完成，但设备品牌/型号/编号存在缺失。"
        "请结合检查项名称判断：此类表单/检查项是否本就不要求完整设备信息"
        "（如站房环境类检查不针对特定设备、设备字段由其他表单承载）。"
        "本就不要求判 not_applicable；确属应填而未填判 unresolved；无法判断判 needs_verification。"
    ),
}


def _dataset_index(dataset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for order in dataset.get("orders", []):
        code = _text(order.get("working_order_code"))
        if not code:
            continue
        tasks_by_tag: dict[str, dict[str, Any]] = {}
        for task in order.get("tasks", []):
            tag = _text(task.get("rule_item_tag"))
            if tag:
                tasks_by_tag.setdefault(tag, task)
        index[code] = {"order": order, "tasks_by_tag": tasks_by_tag}
    return index


def _issue_semantic_context(issue: dict[str, Any], index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    entry = index.get(issue.get("working_order_code", "")) or {}
    order = entry.get("order") or {}
    task = (entry.get("tasks_by_tag") or {}).get(_text(issue.get("rule_item_tag"))) or {}
    context: dict[str, Any] = {
        "rule_id": issue.get("rule_id"),
        "order_type": issue.get("order_type_str"),
        "station_name": issue.get("station_name"),
        "order_status": order.get("order_status_str"),
        "current_point": order.get("current_point_name"),
        "rule_item_name": task.get("rule_item_name"),
        "rule_item_tag": task.get("rule_item_tag"),
        "field_label": issue.get("field_label"),
    }
    guide_key = issue.get("rule_id")
    if guide_key == "TASK_VALUE_OUT_OF_RANGE":
        label = _text(issue.get("field_label"))
        row = next((r for r in task.get("rows", []) if _text(r.get("label")) == label), None)
        if row:
            context["row"] = {
                "status_value": row.get("status_value"),
                "actual_value": row.get("actual_value"),
                "remark_value": row.get("remark_value"),
                "reference_limit": row.get("reference_limit"),
            }
        siblings = [
            {"label": r.get("label"), "actual": r.get("actual_value"), "remark": r.get("remark_value")}
            for r in (task.get("rows") or [])[:30]
            if _text(r.get("remark_value"))
        ]
        if siblings:
            context["related_remarks"] = siblings
    elif guide_key == "TASK_ABNORMAL_NO_REMARK":
        label = _text(issue.get("field_label"))
        row = next((r for r in task.get("rows", []) if _text(r.get("label")) == label), None)
        if row:
            context["row"] = {
                "status_value": row.get("status_value"),
                "actual_value": row.get("actual_value"),
                "remark_value": row.get("remark_value"),
            }
        context["task_remarks"] = [
            {"label": f.get("label"), "value": f.get("value")}
            for f in (task.get("fields") or [])
            if _text(f.get("value"))
        ][:20]
    elif guide_key == "TASK_DEVICE_INCOMPLETE":
        context["device"] = task.get("device") or {}
        context["form_component"] = task.get("form_component")
    elif guide_key == "TASK_FIELD_MISSING":
        context["fields_preview"] = [
            {"label": f.get("label"), "type": f.get("type"), "filled": _text(f.get("value")) != ""}
            for f in (task.get("fields") or [])[:30]
        ]
    return context


async def apply_semantic_review(
    dataset: dict[str, Any],
    outcome: dict[str, Any],
    *,
    timeout: float = SEMANTIC_LLM_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Attach LLM semantic-review results to reviewable issues; return stats."""
    issues = outcome.get("issues", [])
    candidates = [i for i in issues if i.get("rule_id") in SEMANTIC_REVIEWABLE_RULES]
    stats = {"eligible": len(candidates), "reviewed": 0, "unreviewed": 0, "downgraded": 0}
    if not candidates:
        outcome["summary"]["semantic"] = stats
        return stats

    from app.services.llm_service import llm_service

    if not getattr(llm_service, "base_url", "") or not getattr(llm_service, "model", ""):
        for issue in candidates:
            issue["semantic"] = {"reviewed": False, "judgment": "unreviewed", "reason": "语义复核模型未配置。"}
        stats["unreviewed"] = len(candidates)
        outcome["summary"]["semantic"] = stats
        return stats

    index = _dataset_index(dataset)
    results: dict[str, dict[str, Any]] = {}
    batches: list[list[dict[str, Any]]] = []
    batch: list[dict[str, Any]] = []
    for position, issue in enumerate(candidates):
        item = {
            "review_item_id": f"item-{position}",
            "rule_id": issue.get("rule_id"),
            "message": issue.get("message"),
            "criteria": _SEMANTIC_RULE_GUIDES.get(issue.get("rule_id", ""), ""),
            "context": _issue_semantic_context(issue, index),
        }
        batch.append(item)
        if len(batch) >= SEMANTIC_BATCH_ITEMS:
            batches.append(batch)
            batch = []
    if batch:
        batches.append(batch)
    batches = batches[:SEMANTIC_MAX_BATCHES]

    for batch_index, batch_items in enumerate(batches):
        payload = json.dumps({"items": batch_items}, ensure_ascii=False, default=str)
        messages = [
            {"role": "system", "content": _SEMANTIC_SYSTEM_PROMPT},
            {"role": "user", "content": payload},
        ]
        try:
            reply = await llm_service.chat(messages, temperature=0.0, timeout=timeout, max_tokens=2000)
            parsed = json.loads(re.sub(r"^```(?:json)?|```$", "", reply.strip(), flags=re.M).strip())
            for result in parsed.get("results", []):
                item_id = _text(result.get("review_item_id"))
                judgment = _text(result.get("judgment"))
                if item_id and judgment:
                    results[item_id] = result
        except Exception as exc:  # noqa: BLE001
            logger.warning("jiangsu_ops_audit_semantic_batch_failed", batch=batch_index, error=str(exc))

    for position, issue in enumerate(candidates):
        key = f"item-{position}"
        result = results.get(key)
        if not isinstance(result, dict):
            issue["semantic"] = {"reviewed": False, "judgment": "unreviewed", "reason": "本批语义复核未覆盖。"}
            stats["unreviewed"] += 1
            continue
        judgment = _text(result.get("judgment")) or "needs_verification"
        reason = _text(result.get("reason"))[:160]
        try:
            confidence = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        issue["semantic"] = {
            "reviewed": True,
            "judgment": judgment,
            "confidence": confidence,
            "reason": reason,
        }
        stats["reviewed"] += 1
        if judgment in {"not_applicable", "valid_explanation"} and issue.get("severity") != "低":
            issue["severity"] = "低"
            issue["message"] = f"{issue.get('message', '')}（语义复核：{reason or judgment}）"
            stats["downgraded"] += 1

    # 语义复核可能改变严重度，重排并重算统计。
    severity_order = {"高": 0, "中": 1, "低": 2}
    issues.sort(key=lambda i: (severity_order.get(i["severity"], 3), i["working_order_code"]))
    summary = outcome["summary"]
    summary["semantic"] = stats
    return stats


def _standard_result(tool_name: str, summary: str, data: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    refs = merge_refs(
        {"files": [build_file_ref(path, role="output", label=path.split("/")[-1]) for path in paths]},
        {"data": []},
    )
    return {
        "status": "success",
        "success": True,
        "summary": summary,
        "data": data,
        "metadata": {"tool_name": tool_name, "generator": tool_name},
        "refs": refs,
    }


class JiangsuOpsAuditFetchTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_ops_audit_fetch_dataset",
            description="Fetch Jiangsu routine (non-fault) work orders with translated form fields for audit.",
            category=ToolCategory.QUERY,
            function_schema={
                "name": "jiangsu_ops_audit_fetch_dataset",
                "description": (
                    "从本地 ODS 数据库（江苏同步管线，5分钟增量）抽取非故障工单"
                    "（巡检/现场检查/校准/质控/质量保证/数据录入）及表单字段，"
                    "翻译 rFCommon 泛化列为具名字段后落盘数据集，不执行审核规则。"
                    "仅覆盖 2026-07-01 之后、同步水位之前的工单；无匹配数据时直接报错。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_types": {
                            "type": "array",
                            "items": {"type": "string", "enum": AUDITABLE_ORDER_TYPES},
                            "description": "工单类型；默认全部非故障类型。禁止传 Fault。",
                        },
                        "create_time_start": {"type": "string", "description": "创建时间起，YYYY-MM-DD HH:mm:ss。"},
                        "create_time_end": {"type": "string", "description": "创建时间止，YYYY-MM-DD HH:mm:ss。"},
                        "workflow_statuses": {
                            "type": "array", "items": {"type": "string"},
                            "description": "节点状态：ToAssign/ToAccept/Doing/Finish/Reject，也接受中文。",
                        },
                        "order_statuses": {
                            "type": "array", "items": {"type": "string"},
                            "description": "工单状态：Wait/Doing/Finish/Invalid，也接受中文。",
                        },
                        "working_order_codes": {
                            "type": "array", "items": {"type": "string"},
                            "description": "工单号（模糊匹配）列表。",
                        },
                        "station_codes": {
                            "type": "array", "items": {"type": "string"},
                            "description": "平台站点编码列表，如 [\"3104A\"]。",
                        },
                        "limit": {"type": "integer", "description": "最多抽取工单数，默认 50，最大 300。"},
                        "output_dir": {"type": "string", "description": "输出目录；不填按数据目录自动隔离。"},
                    },
                    "required": [],
                },
            },
            version="0.1.0",
            requires_context=True,
        )

    async def execute(
        self,
        context=None,
        order_types: Optional[list[str]] = None,
        create_time_start: Optional[str] = None,
        create_time_end: Optional[str] = None,
        workflow_statuses: Optional[list[str]] = None,
        order_statuses: Optional[list[str]] = None,
        working_order_codes: Optional[list[str]] = None,
        station_codes: Optional[list[str]] = None,
        limit: int = 50,
        output_dir: Optional[str] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        try:
            result = await fetch_dataset(
                context,
                order_types=order_types,
                create_time_start=create_time_start,
                create_time_end=create_time_end,
                workflow_statuses=workflow_statuses,
                order_statuses=order_statuses,
                working_order_codes=working_order_codes,
                station_codes=station_codes,
                limit=limit,
                output_dir=output_dir,
            )
            summary = result["summary"]
            watermark = result["query_info"].get("rf_common_watermark") or ""
            watermark_text = f"表单同步截至 {watermark[:19]}。" if watermark else ""
            text = (
                f"已抽取工单 {summary['order_count']} 条，检查项 {summary['task_count']} 个，"
                f"附件 {summary['attachment_count']} 个，未匹配字段字典检查项 {summary['unmapped_task_count']} 个。"
                f"{watermark_text}数据集：{result['dataset_path']}"
            )
            return _standard_result(self.name, text, result, [result["dataset_path"]])
        except Exception as exc:  # noqa: BLE001
            logger.error("jiangsu_ops_audit_fetch_failed", error=str(exc), exc_info=True)
            return {
                "status": "failed", "success": False,
                "summary": f"江苏工单审核取数失败：{exc}",
                "data": {"error": str(exc)},
                "metadata": {"tool_name": self.name, "error": str(exc)},
            }


class JiangsuOpsAuditRunRulesTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_ops_audit_run_rules",
            description="Run deterministic audit rules on a fetched Jiangsu routine work-order dataset.",
            category=ToolCategory.ANALYSIS,
            function_schema={
                "name": "jiangsu_ops_audit_run_rules",
                "description": "对江苏非故障工单数据集执行确定性审核规则，生成问题清单与报告输入文件。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dataset_path": {
                            "type": "string",
                            "description": "jiangsu_ops_audit_fetch_dataset 返回的 dataset_path 原值。",
                        },
                        "output_dir": {"type": "string", "description": "结果输出目录；不填与数据集同目录。"},
                        "enable_semantic": {
                            "type": "boolean",
                            "default": True,
                            "description": (
                                "是否对候选问题执行 LLM 语义复核（判断规则是否误报、异常是否已有合理解释）。"
                                "语义结果只作降级建议，不删除问题。传 false 跳过。"
                            ),
                        },
                    },
                    "required": ["dataset_path"],
                },
            },
            version="0.1.0",
            requires_context=True,
        )

    async def execute(
        self,
        context=None,
        dataset_path: str = "",
        output_dir: Optional[str] = None,
        enable_semantic: bool = True,
        **_: Any,
    ) -> Dict[str, Any]:
        if not dataset_path:
            return {
                "status": "failed", "success": False,
                "summary": "缺少 dataset_path。",
                "data": {"error": "missing_dataset_path"},
                "metadata": {"tool_name": self.name},
            }
        try:
            resolved = resolve_agent_path(dataset_path)
            if not resolved.exists():
                return {
                    "status": "failed", "success": False,
                    "summary": f"数据集文件不存在：{dataset_path}",
                    "data": {"error": "dataset_not_found", "dataset_path": dataset_path},
                    "metadata": {"tool_name": self.name},
                }
            dataset = json.loads(resolved.read_text(encoding="utf-8"))
            outcome = run_rules(dataset)
            semantic_stats: dict[str, Any] | None = None
            if enable_semantic:
                try:
                    semantic_stats = await apply_semantic_review(dataset, outcome)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("jiangsu_ops_audit_semantic_failed", error=str(exc))
                    semantic_stats = {"eligible": 0, "reviewed": 0, "unreviewed": 0, "downgraded": 0, "error": str(exc)[:160]}
            else:
                # 关闭语义复核时，候选问题视为未复核，报告门禁会置为未就绪。
                semantic_stats = {"eligible": 0, "reviewed": 0, "unreviewed": 0, "downgraded": 0, "skipped": True}
                for issue in outcome["issues"]:
                    if issue.get("rule_id") in SEMANTIC_REVIEWABLE_RULES:
                        issue["semantic"] = {"reviewed": False, "judgment": "unreviewed", "reason": "本次未启用语义复核。"}

            report_input = build_report_input(dataset, outcome["issues"], outcome["coverage"], semantic_stats)
            outcome["summary"]["report_ready"] = report_input["summary"]["report_ready"]
            outcome["summary"]["report_issue_count"] = report_input["summary"]["report_issue_count"]

            target_dir = resolve_agent_path(output_dir) if output_dir else resolved.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            issues_path = target_dir / "jiangsu_ops_audit_issues.json"
            report_input_path = target_dir / "jiangsu_ops_audit_report_input.json"
            issues_path.write_text(json.dumps(outcome["issues"], ensure_ascii=False, indent=2), encoding="utf-8")
            report_input_path.write_text(
                json.dumps(report_input, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            summary = outcome["summary"]
            report_summary = report_input["summary"]
            top_rules = "，".join(f"{k}({v})" for k, v in list(summary["rule_counts"].items())[:5])
            semantic_text = ""
            if semantic_stats is not None:
                semantic_text = (
                    f"语义复核：候选 {semantic_stats.get('eligible', 0)} 条，"
                    f"已复核 {semantic_stats.get('reviewed', 0)} 条，"
                    f"降级 {semantic_stats.get('downgraded', 0)} 条"
                    + (f"，未复核 {semantic_stats.get('unreviewed', 0)} 条" if semantic_stats.get("unreviewed") else "")
                    + "。"
                )
            readiness_text = (
                "报告就绪。"
                if report_summary["report_ready"]
                else (
                    f"报告未就绪（待语义复核 {report_summary['pending_semantic_reviews']} 条、"
                    f"待人工核验 {report_summary['pending_review_items']} 条），"
                    "先交付待核验清单，不得生成正式报告。"
                )
            )
            text = (
                f"审核完成：规则命中 {summary['issue_count']} 条，报告问题 {report_summary['report_issue_count']} 条，"
                f"涉及工单 {report_summary['affected_order_count']} 条；"
                f"覆盖工单 {outcome['coverage']['orders']} 条、检查项 {outcome['coverage']['tasks']} 个、"
                f"行式检查项 {outcome['coverage']['row_tasks']} 个。高频规则：{top_rules}。{semantic_text}"
                f"{readiness_text}"
                f"问题清单：{format_agent_path(issues_path)}；报告输入：{format_agent_path(report_input_path)}"
            )
            data = {
                "issues_path": format_agent_path(issues_path),
                "report_input_path": format_agent_path(report_input_path),
                "summary": {**summary, **{k: report_summary[k] for k in (
                    "report_issue_count", "retained_count", "report_ready",
                    "pending_review_items", "pending_semantic_reviews")}},
                "coverage": outcome["coverage"],
                "semantic": semantic_stats,
                "report_items": report_input["items"][:30],
                "issues": outcome["issues"][:30],
            }
            return _standard_result(
                self.name, text, data,
                [format_agent_path(issues_path), format_agent_path(report_input_path)],
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("jiangsu_ops_audit_run_rules_failed", error=str(exc), exc_info=True)
            return {
                "status": "failed", "success": False,
                "summary": f"江苏工单审核规则执行失败：{exc}",
                "data": {"error": str(exc)},
                "metadata": {"tool_name": self.name},
            }


async def jiangsu_ops_audit_fetch_dataset(context=None, **kwargs: Any) -> Dict[str, Any]:
    return await JiangsuOpsAuditFetchTool().execute(context=context, **kwargs)


async def jiangsu_ops_audit_run_rules(context=None, **kwargs: Any) -> Dict[str, Any]:
    return await JiangsuOpsAuditRunRulesTool().execute(context=context, **kwargs)


__all__ = [
    "JiangsuOpsAuditFetchTool",
    "JiangsuOpsAuditRunRulesTool",
    "jiangsu_ops_audit_fetch_dataset",
    "jiangsu_ops_audit_run_rules",
    "fetch_dataset",
    "run_rules",
    "apply_semantic_review",
    "build_report_input",
]
