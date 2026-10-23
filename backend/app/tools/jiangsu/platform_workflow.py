"""Write human disposal decisions back to the Suncere operations platform.

The Agent tool surface never gains a platform-write capability: this module is
only invoked from human-confirmed actions (work-order review decisions in the
task scheduler center, dispatch submissions in the smart-event center) and
from the status read-back poller.  Every attempt is audited to a JSONL file in
the data registry and returns a result descriptor instead of raising, so a
platform outage can never block the local review lifecycle.

Platform flow being mirrored (Fault workflow):
    创建工单 -> 故障处理 -> 运维单位审核 -> 省中心审核(FaultApprove)

Smart-event dispatch no longer assumes the fault flow: it creates platform
运维告警工单 with the platform's own type vocabulary (PersonIntrusion /
FogCannon / InstrumentFault, see ``alarm_order_types``), associates an existing
in-flight order first, and stores the type alongside the order code so the
status read-back can query the same type.

An order arriving at 省中心审核 is ToAssign with no assignee, so a write-back
must first claim the node (``WorkingOrder/ReceiveOrderAsync``) with an account
holding the node role, then submit the node (``FaultOrder/SaveOrderAsync``):
approve (``processStatus=true``) closes the order, reject sends it back to the
previous node with ``submitRemark`` carrying the reviewer's opinion.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import structlog

from app.tools.jiangsu.alarm_order_types import (
    normalise_platform_order_type,
    platform_order_type_label,
    platform_order_type_params,
)
from app.tools.jiangsu.fault_diagnosis import (
    _detail_working_order_code,
    _JiangsuAuthenticatedApi,
)
from app.tools.jiangsu.fault_diagnosis import JiangsuFaultWorkOrdersTool
from app.tools.jiangsu.work_order_dispatch import _parse_platform_time
from app.utils.path_config import format_agent_path, get_data_registry

logger = structlog.get_logger(__name__)

_LIST_PATH = JiangsuFaultWorkOrdersTool._LIST_PATH
_DETAIL_PATH = JiangsuFaultWorkOrdersTool._PATH
_WORKFLOW_PATH = JiangsuFaultWorkOrdersTool._WORKFLOW_PATH
_RECEIVE_PATH = "operation/WorkingOrder/ReceiveOrderAsync"
_SAVE_ORDER_PATH = "operation/FaultOrder/SaveOrderAsync"
_FAULT_ORDER_CREATE_PATH = "operation/FaultOrder/CreateAsync"
# 江苏运维新国标分支的告警工单建单入口（AlarmOrderAppService.CreateAsync）。
# 告警工单必须走该入口：它会创建 mtc_alarmorder 辅助记录并按类型选用独立流程。
_ALARM_ORDER_CREATE_PATH = "operation/AlarmOrder/CreateAsync"

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


def _alarm_order_list_params(
    order_type: str,
    *,
    station_code: str = "",
    working_order_code: str = "",
    in_flight_only: bool = False,
) -> list[tuple[str, str]]:
    """List filters shared by link-lookup and created-code re-query."""
    params = platform_order_type_params(order_type)
    if working_order_code:
        params.append(("WorkingOrderCode", working_order_code))
    if station_code:
        params.append(("StationCode", station_code))
    if in_flight_only:
        params.extend([("OrderStatus", "Wait"), ("OrderStatus", "Doing")])
        params.extend([
            ("WorkFlowStatus", "ToAssign"),
            ("WorkFlowStatus", "ToAccept"),
            ("WorkFlowStatus", "Doing"),
        ])
    params.extend([("MaxResultCount", "50"), ("SkipCount", "0")])
    return params


def _list_items(payload: Any) -> list[dict[str, Any]]:
    """Accept both paged envelopes and the legacy bare list response."""
    result = (payload or {}).get("result") if isinstance(payload, dict) else None
    if isinstance(result, dict):
        items = result.get("items") or result.get("data") or []
    elif isinstance(result, list):
        items = result
    else:
        items = []
    return [item for item in items if isinstance(item, dict)]


def _row_id(item: dict[str, Any]) -> int:
    try:
        return int(item.get("id") or 0)
    except (TypeError, ValueError):
        return 0


def _link_window_hours() -> int:
    from config.settings import settings

    try:
        return int(getattr(settings, "jiangsu_platform_alarm_order_link_window_hours", 24))
    except (TypeError, ValueError):
        return 24


def _parse_link_time(value: Any) -> datetime | None:
    """Parse event or platform timestamps into naive local time for comparison."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return _parse_platform_time(text)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


async def _find_inflight_alarm_order(
    api: _JiangsuAuthenticatedApi,
    *,
    station_code: str,
    order_type: str,
    event_start_time: str = "",
) -> dict[str, Any] | None:
    """Find an in-flight platform alarm order for the same site and window.

    The platform creates alarm orders from alarms/video in most deployments, so
    dispatching must associate the existing order instead of creating a second
    one.  Only same-site, same-type orders created inside the configured window
    are eligible; the newest one wins.
    """
    window_hours = _link_window_hours()
    if window_hours <= 0:
        return None
    now = datetime.now()
    window_start = (_parse_link_time(event_start_time) or now) - timedelta(hours=window_hours)
    payload = await api.get(
        _LIST_PATH,
        _alarm_order_list_params(
            order_type, station_code=station_code, in_flight_only=True,
        ) + [
            ("CreateTime", window_start.strftime("%Y-%m-%d %H:%M:%S")),
            ("CreateTime", (now + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")),
        ],
    )
    best: tuple[tuple[datetime, int], dict[str, Any]] | None = None
    for item in _list_items(payload):
        row_type = str(item.get("orderType") or "").strip()
        if row_type and row_type != order_type:
            continue
        code = str(item.get("workingOrderCode") or "").strip()
        if not code:
            continue
        created = _parse_platform_time(item.get("createTime"))
        if created is None or created < window_start or created > now + timedelta(minutes=10):
            continue
        key = (created, _row_id(item))
        if best is None or key > best[0]:
            best = (key, item)
    return best[1] if best else None


async def resolve_created_alarm_order_code(
    *,
    station_code: str,
    order_type: str,
    order_title: str,
    created_after: datetime,
) -> str | None:
    """Re-query the newest created order of one type by title.

    ``FaultOrder/GetWorkingOrderInfoByUniqueCode`` is fault-only, so alarm
    orders are located through the shared list endpoint instead.
    """
    api = _JiangsuAuthenticatedApi(source="ops")
    payload = await api.get(
        _LIST_PATH,
        _alarm_order_list_params(order_type, station_code=station_code) + [
            ("CreateTime", (created_after - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")),
            ("CreateTime", (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")),
        ],
    )
    best: tuple[tuple[datetime, int], str] | None = None
    for item in _list_items(payload):
        if str(item.get("orderTitle") or "").strip().casefold() != order_title.strip().casefold():
            continue
        created = _parse_platform_time(item.get("createTime"))
        if created is None or created < created_after - timedelta(minutes=10):
            continue
        code = str(item.get("workingOrderCode") or "").strip()
        if not code:
            continue
        key = (created, _row_id(item))
        if best is None or key > best[0]:
            best = (key, code)
    return best[1] if best else None


def _alarm_order_create_path() -> str:
    from config.settings import settings

    return str(
        getattr(settings, "jiangsu_platform_alarm_order_create_path", "")
        or _ALARM_ORDER_CREATE_PATH
    ).strip() or _ALARM_ORDER_CREATE_PATH


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
    order_type: str | None = None,
    event_start_time: str = "",
    clue_json: str = "",
) -> dict[str, Any]:
    """Create or associate the platform alarm work order behind one dispatch.

    The order type must be a platform-defined alarm type
    (PersonIntrusion / FogCannon / InstrumentFault).  Before creating, the
    platform is queried for an in-flight alarm order of the same site and type
    inside the configured window; a hit is only associated, never duplicated.

    Never raises: returns a result descriptor with the resolved station,
    device and the platform ``work_order_code``.
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
        resolved_type = normalise_platform_order_type(order_type)
        type_label = platform_order_type_label(resolved_type) or resolved_type
        api = _JiangsuAuthenticatedApi(source="ops")

        # 平台通常已按告警/视频自动建单：先关联在办工单，避免同一事件两张单。
        # 关联查询失败不阻断建单，按“未命中”继续。
        try:
            existing = await _find_inflight_alarm_order(
                api,
                station_code=station["station_code"],
                order_type=resolved_type,
                event_start_time=event_start_time,
            )
        except Exception as exc:  # noqa: BLE001 - 关联是优化，不能阻断派单主流程
            logger.warning("jiangsu_smart_event_dispatch_link_lookup_failed",
                           event_id=event_id, order_type=resolved_type, error=str(exc))
            existing = None
        if existing is not None:
            existing_code = str(existing.get("workingOrderCode") or "").strip()
            logger.info("jiangsu_smart_event_dispatch_linked", event_id=event_id,
                        work_order_code=existing_code, order_type=resolved_type,
                        station_code=station["station_code"])
            return _result("linked", existing_code, action_name,
                           f"平台已有在办{type_label}告警工单（{existing_code}），仅关联未重复创建",
                           station=station, order_type=resolved_type, linked=True)

        urgency = str(urgency_type or "Middle").strip()
        if urgency not in {"Normal", "Middle", "Urgent"}:
            urgency = "Middle"
        issued = [str(item).strip() for item in (issued_types or []) if str(item).strip()]
        description_text = str(description or "").strip()
        body_lines = [f"【事件描述】{description_text or order_title}"]
        trace = "；".join(
            part for part in (
                f"智能事件 {str(event_id or '').strip()}" if str(event_id or '').strip() else "",
                f"站点 {site_name or station.get('station_name') or station['station_code']}",
            ) if part
        )
        if trace:
            body_lines.append(f"【来源】智能事件中心人工派单（{trace}）")
        order_content = "\n".join(body_lines)[:4000]

        device: dict[str, Any] | None = None
        if resolved_type == "Fault":
            devices = await _fetch_station_devices(api, station["station_code"])
            if not devices:
                raise ValueError(f"站点 {station.get('station_name') or station['station_code']} 在平台无设备台账")
            device = devices[0]
            payload = {
                "orderType": "Fault",
                "orderTitle": order_title[:100],
                "orderContent": order_content,
                "otherContent": description_text[:2000],
                "urgencyType": urgency,
                "deviceId": device["device_id"],
                "stationCodes": [station["station_code"]],
                "checkTask": ["other"],
                "planFinishTime": (
                    datetime.now().astimezone() + timedelta(hours=plan_finish_hours)
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "issuedType": issued,
            }
            create_path = _FAULT_ORDER_CREATE_PATH
        else:
            # AlarmOrderAppService.CreateAsync：设备仅在仪器故障报警时使用，
            # 站点通过 StationCode（单值）解析；标题列上限 50，线索 JSON 上限 1000。
            if resolved_type == "InstrumentFault":
                devices = await _fetch_station_devices(api, station["station_code"])
                device = devices[0] if devices else None
            payload = {
                "orderType": resolved_type,
                "stationCode": station["station_code"],
                "orderTitle": order_title[:50],
                "orderContent": order_content,
                "urgencyType": urgency,
                "issuedType": issued,
            }
            if clue_json:
                payload["clueJson"] = clue_json
            if resolved_type == "InstrumentFault":
                # 故障现象/其他现象与设备是否存在无关，先写入；设备与故障现象编码尽力补齐。
                payload["otherContent"] = description_text[:500]
                payload["faultPhenomenon"] = (description_text or order_title)[:1000]
                if device is not None:
                    payload["deviceId"] = device["device_id"]
                    payload["checkTask"] = ["other"]
            create_path = _alarm_order_create_path()
        response = await api.post(create_path, payload)
        # AlarmOrderAppService/CreateAsync 以裸 true/false 表示成败；false 必须显式失败，
        # 否则会把“未创建”记成 synced 并进入无工单号的状态。
        if isinstance(response, dict):
            result_value = response.get("result")
            if result_value is False or str(result_value).strip().lower() == "false":
                raise ValueError(
                    "平台未创建工单（CreateAsync 返回 false）：请检查告警类型工作流配置与登录账号权限"
                )
        # 回查时的 created_after 必须与平台返回的 naive createTime 同一口径，
        # 否则 aware/naive 比较抛 TypeError 且发生在建单之后。
        created_at = datetime.now()
        if resolved_type == "Fault":
            order_code = await resolve_created_order_code(
                unique_code=station.get("unique_code") or "",
                order_title=payload["orderTitle"],
                created_after=created_at,
            ) if station.get("unique_code") else None
        else:
            # 告警工单不在 FaultOrder 详单接口里，按列表接口同站点同类型回查。
            order_code = await resolve_created_alarm_order_code(
                station_code=station["station_code"],
                order_type=resolved_type,
                order_title=payload["orderTitle"],
                created_after=created_at,
            )
        logger.info("jiangsu_smart_event_dispatch_created", event_id=event_id,
                    work_order_code=order_code, order_type=resolved_type,
                    station_code=station["station_code"])
        return _result("synced", order_code or "", action_name,
                       f"平台{type_label}告警工单已创建（{order_code or '工单号回查中'}）",
                       station=station, device_id=(device or {}).get("device_id"),
                       urgency_type=urgency, issued_types=issued,
                       order_type=resolved_type)
    except Exception as exc:  # noqa: BLE001 - 契约承诺永不抛出，意外异常也落成 failed 描述符
        logger.warning("jiangsu_smart_event_dispatch_create_failed", event_id=event_id,
                       error=str(exc))
        return _result("failed", "", action_name, f"平台工单创建失败：{exc}")


def _audit_path() -> str:
    return format_agent_path(get_data_registry() / "work_order_platform_sync.jsonl")


def audit_log_path() -> str:
    return _audit_path()
