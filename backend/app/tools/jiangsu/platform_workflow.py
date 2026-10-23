"""Write human disposal decisions back to the Suncere operations platform.

The Agent tool surface never gains a platform-write capability: this module is
only invoked from human-confirmed actions (work-order review decisions in the
task scheduler center, dispatch submissions in the smart-event center) and
from the status read-back poller.  Every attempt is audited to a JSONL file in
the data registry and returns a result descriptor instead of raising, so a
platform outage can never block the local review lifecycle.

Platform flow being mirrored (Fault workflow):
    创建工单 -> 故障处理 -> 运维单位审核 -> 省中心审核(FaultApprove)

An order arriving at 省中心审核 is ToAssign with no assignee, so a write-back
must first claim the node (``WorkingOrder/ReceiveOrderAsync``) with an account
holding the node role, then submit the node (``FaultOrder/SaveOrderAsync``):
approve (``processStatus=true``) closes the order, reject sends it back to the
previous node with ``submitRemark`` carrying the reviewer's opinion.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import structlog

from app.tools.jiangsu.fault_diagnosis import (
    _detail_working_order_code,
    _JiangsuAuthenticatedApi,
)
from app.tools.jiangsu.fault_diagnosis import JiangsuFaultWorkOrdersTool
from app.utils.path_config import format_agent_path, get_data_registry

logger = structlog.get_logger(__name__)

_LIST_PATH = JiangsuFaultWorkOrdersTool._LIST_PATH
_DETAIL_PATH = JiangsuFaultWorkOrdersTool._PATH
_WORKFLOW_PATH = JiangsuFaultWorkOrdersTool._WORKFLOW_PATH
_RECEIVE_PATH = "operation/WorkingOrder/ReceiveOrderAsync"
_SAVE_ORDER_PATH = "operation/FaultOrder/SaveOrderAsync"
_CREATE_ORDER_PATH = "operation/FaultOrder/CreateAsync"

_CLOSED_ORDER_STATUSES = {"Finish", "Invalid"}
_CLAIMABLE_WORKFLOW_STATUSES = {"ToAssign", "ToAccept"}


def platform_writeback_enabled() -> bool:
    from config.settings import settings

    return bool(getattr(settings, "jiangsu_platform_writeback_enabled", False))


def _audit_event(event: dict[str, Any]) -> None:
    path = get_data_registry() / "work_order_platform_sync.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def _result(
    status: str,
    work_order_code: str,
    action: str,
    detail: str,
    **extra: Any,
) -> dict[str, Any]:
    record = {
        "status": status,
        "action": action,
        "work_order_code": work_order_code,
        "detail": detail,
        "at": datetime.now().astimezone().isoformat(),
        **extra,
    }
    _audit_event(record)
    return record


async def fetch_platform_order(work_order_code: str) -> dict[str, Any]:
    """Resolve one exact order into its full platform detail (wo/details/workFlowInfo)."""
    code = str(work_order_code or "").strip()
    if not code:
        raise ValueError("工单号不能为空")
    api = _JiangsuAuthenticatedApi(source="ops")
    list_payload = await api.get(_LIST_PATH, [
        ("OrderType", "Fault"),
        ("MaxResultCount", "50"),
        ("SkipCount", "0"),
        ("WorkingOrderCode", code),
    ])
    list_items = (list_payload.get("result") or {}).get("items") or []
    exact = [
        item for item in list_items
        if isinstance(item, dict)
        and str(item.get("workingOrderCode") or "").strip().casefold() == code.casefold()
    ]
    if not exact:
        raise ValueError(f"平台未找到工单 {code}")
    list_row = exact[0]
    unique_code = str(list_row.get("uniqueCode") or "").strip()
    if not unique_code:
        raise ValueError(f"工单 {code} 缺少站点唯一编码，无法读取详单")
    detail_payload = await api.get(_DETAIL_PATH, [("uniqueCode", unique_code), ("take", "20")])
    entries = detail_payload.get("result") or []
    for entry in entries:
        if isinstance(entry, dict) and _detail_working_order_code(entry).casefold() == code.casefold():
            entry["listRow"] = list_row
            return entry
    raise ValueError(f"工单 {code} 的站点详单中未找到匹配记录")


def _resolve_current_step(detail: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (wo, step) where step matches wo.currentPoint in workFlowInfo.stepList."""
    wo = detail.get("wo") or {}
    current_point = str(wo.get("currentPoint") or "").strip()
    workflow = detail.get("workFlowInfo") or {}
    for step in workflow.get("stepList") or []:
        if isinstance(step, dict) and str(step.get("guid") or "").strip() == current_point:
            return wo, step
    raise ValueError("未在工单流程中找到当前节点，无法提交")


async def _claim_order(api: _JiangsuAuthenticatedApi, platform_id: Any) -> None:
    """Claim the current node so this account becomes the handler.

    ``ReceiveOrderAsync`` is a GET endpoint bound from query parameters.
    """
    try:
        platform_id_int = int(platform_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("平台工单缺少数字主键，无法领取节点") from exc
    await api.get(_RECEIVE_PATH, [("Id", str(platform_id_int))])


async def _submit_node(
    api: _JiangsuAuthenticatedApi,
    *,
    wo: dict[str, Any],
    step: dict[str, Any],
    work_order_code: str,
    approved: bool,
    remark: str,
) -> dict[str, Any]:
    payload = {
        "guid": step.get("guid"),
        "workflowId": wo.get("workFlowId") or step.get("workflowId"),
        "taskName": step.get("taskName"),
        "formCode": step.get("formCode"),
        "taskPreviousId": step.get("taskPreviousId"),
        "taskNextId": step.get("taskNextId"),
        "roleId": step.get("roleId"),
        "rank": step.get("rank"),
        "orderDetailDto": {
            "workingOrderCode": work_order_code,
            "processStep": step.get("formCode"),
            "processStatus": approved,
            "submitRemark": str(remark or "")[:2000],
            "isSubmit": True,
            "isCancel": False,
        },
    }
    status_field = step.get("status")
    if isinstance(status_field, bool):
        payload["status"] = status_field
    response = await api.post(_SAVE_ORDER_PATH, payload)
    if isinstance(response, dict) and response.get("success") is False:
        raise ValueError(str(response.get("message") or "平台节点提交失败"))
    return response if isinstance(response, dict) else {"result": response}


async def submit_review_decision(
    work_order_code: str,
    *,
    action: str,
    approved: bool,
    comment: str = "",
) -> dict[str, Any]:
    """Write one human review decision back to the platform; never raises.

    ``approved=True`` submits the current (approve) node so the order closes;
    ``approved=False`` sends the order back to the previous node carrying the
    reviewer opinion.  Returns a result descriptor: ``disabled`` when the
    write-back switch is off, ``synced`` / ``skipped`` / ``failed`` otherwise.
    """
    code = str(work_order_code or "").strip()
    action_name = str(action or "").strip() or ("approve" if approved else "reject")
    if not platform_writeback_enabled():
        return _result("disabled", code, action_name, "平台写回开关未开启")
    try:
        detail = await fetch_platform_order(code)
        wo, step = _resolve_current_step(detail)
        order_status = str(wo.get("orderStatus") or "").strip()
        if order_status in _CLOSED_ORDER_STATUSES:
            return _result("skipped", code, action_name,
                           f"平台工单已处于终态（{order_status}），无需写回")
        api = _JiangsuAuthenticatedApi(source="ops")
        workflow_status = str(wo.get("workFlowStatus") or "").strip()
        if workflow_status in _CLAIMABLE_WORKFLOW_STATUSES:
            await _claim_order(api, wo.get("id"))
        await _submit_node(
            api, wo=wo, step=step, work_order_code=code,
            approved=approved, remark=comment,
        )
        outcome = "节点通过，工单闭环" if approved else "已打回上一节点"
        logger.info("jiangsu_platform_writeback_synced", work_order_code=code,
                    action=action_name, node=step.get("taskName"))
        return _result("synced", code, action_name,
                       f"{step.get('taskName') or '审核节点'}{outcome}")
    except Exception as exc:  # noqa: BLE001 - 契约承诺永不抛出，意外异常也落成 failed 描述符
        logger.warning("jiangsu_platform_writeback_failed", work_order_code=code,
                       action=action_name, error=str(exc))
        return _result("failed", code, action_name, f"平台写回失败：{exc}")


def platform_sync_result_operation(result: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a write-back result into a review-package operation entry."""
    if not isinstance(result, dict) or result.get("status") == "disabled":
        return None
    label = {"synced": "平台同步成功", "skipped": "平台同步跳过", "failed": "平台同步失败"}.get(
        str(result.get("status")), "平台同步")
    return {
        "action": "platform_sync",
        "label": label,
        "comment": str(result.get("detail") or ""),
        "at": str(result.get("at") or datetime.now().astimezone().isoformat()),
        "source": "task_review_decision",
        "platform": {
            "work_order_code": result.get("work_order_code"),
            "decision_action": result.get("action"),
            "sync_status": result.get("status"),
        },
    }


async def create_smart_event_dispatch_order(
    *,
    event_id: str,
    site_id: str,
    site_name: str = "",
    title: str,
    description: str = "",
    urgency_type: str = "Middle",
    issued_types: list[str] | None = None,
    plan_finish_hours: int = 48,
) -> dict[str, Any]:
    """Create the real platform work order behind one smart-event dispatch.

    Never raises: returns a result descriptor with the resolved station,
    device and the platform ``work_order_code`` (re-queried after creation).
    """
    action_name = "dispatch_order"
    if not platform_writeback_enabled():
        return _result("disabled", "", action_name, "平台写回开关未开启")
    order_title = str(title or "").strip()
    if not order_title:
        return _result("failed", "", action_name, "派单标题为空，未创建平台工单")
    try:
        from app.tools.jiangsu.fault_diagnosis import _resolve_station_rows
        from app.tools.jiangsu.work_order_dispatch import (
            _fetch_station_devices,
            resolve_created_order_code,
        )

        station = None
        lookup_error: str | None = None
        for lookup in ({"station_code": site_id}, {"unique_code": site_id}):
            try:
                rows = await _resolve_station_rows(None, None, None, **lookup)
            except ValueError as exc:
                lookup_error = str(exc)
                continue
            if rows:
                station = rows[0]
                break
        if station is None:
            raise ValueError(f"未在平台站点目录解析到站点（site_id={site_id}）：{lookup_error}")
        api = _JiangsuAuthenticatedApi(source="ops")
        devices = await _fetch_station_devices(api, station["station_code"])
        if not devices:
            raise ValueError(f"站点 {station.get('station_name') or station['station_code']} 在平台无设备台账")
        device = devices[0]
        urgency = str(urgency_type or "Middle").strip()
        if urgency not in {"Normal", "Middle", "Urgent"}:
            urgency = "Middle"
        issued = [str(item).strip() for item in (issued_types or []) if str(item).strip()]
        from datetime import timedelta

        plan_finish = (datetime.now().astimezone() + timedelta(hours=plan_finish_hours))
        body_lines = [f"【事件描述】{str(description or '').strip() or order_title}"]
        trace = "；".join(
            part for part in (
                f"智能事件 {str(event_id or '').strip()}" if str(event_id or '').strip() else "",
                f"站点 {site_name or station.get('station_name') or station['station_code']}",
            ) if part
        )
        if trace:
            body_lines.append(f"【来源】智能事件中心人工派单（{trace}）")
        payload = {
            "orderType": "Fault",
            "orderTitle": order_title[:100],
            "orderContent": "\n".join(body_lines)[:4000],
            "otherContent": str(description or "").strip()[:2000],
            "urgencyType": urgency,
            "deviceId": device["device_id"],
            "stationCodes": [station["station_code"]],
            "checkTask": ["other"],
            "planFinishTime": plan_finish.strftime("%Y-%m-%d %H:%M:%S"),
            "issuedType": issued,
        }
        await api.post(_CREATE_ORDER_PATH, payload)
        # resolve_created_order_code 内部与平台返回的 naive createTime 比较，
        # created_after 必须同为 naive 本地时间（与既有派单路由/rehearsal 一致），
        # 否则 aware/naive 比较抛 TypeError 且发生在建单之后。
        created_at = datetime.now()
        order_code = await resolve_created_order_code(
            unique_code=station.get("unique_code") or "",
            order_title=payload["orderTitle"],
            created_after=created_at,
        ) if station.get("unique_code") else None
        logger.info("jiangsu_smart_event_dispatch_created", event_id=event_id,
                    work_order_code=order_code, station_code=station["station_code"])
        return _result("synced", order_code or "", action_name,
                       f"平台工单已创建（{order_code or '工单号回查中'}）",
                       station=station, device_id=device["device_id"],
                       urgency_type=urgency, issued_types=issued)
    except Exception as exc:  # noqa: BLE001 - 契约承诺永不抛出，意外异常也落成 failed 描述符
        logger.warning("jiangsu_smart_event_dispatch_create_failed", event_id=event_id,
                       error=str(exc))
        return _result("failed", "", action_name, f"平台工单创建失败：{exc}")


def _audit_path() -> str:
    return format_agent_path(get_data_registry() / "work_order_platform_sync.jsonl")


def audit_log_path() -> str:
    return _audit_path()
