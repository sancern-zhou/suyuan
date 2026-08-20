"""Jiangsu fault work-order dispatch: LLM drafts, a human confirms in the panel.

The Agent may only produce a pending-confirmation draft through
``jiangsu_prepare_fault_work_order``.  Station identity, the device ledger and
the platform fault-phenomenon vocabulary are resolved by the system (not by the
LLM) through the authenticated operations gateway.  The work order is created
on the Suncere operations platform only after an operator confirms the draft
from the right-side preview panel (``app/api/jiangsu_work_order_routes.py``).
"""

from __future__ import annotations

import asyncio
import json
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.jiangsu.fault_diagnosis import (
    _clean_identifier_list,
    _JiangsuAuthenticatedApi,
    _resolve_station_rows,
)
from app.tools.resource_declarations import resources_for_visuals
from app.utils.path_config import format_agent_path, get_data_registry

logger = structlog.get_logger(__name__)

VISUAL_TYPE = "fault_work_order"
ORDER_TYPE_FAULT = "Fault"
_DEVICE_LIST_PATH = "asset/DeviceManagement/GetBSDDeviceListAsync"
_FAULT_CONTENTS_PATH = "operation/FaultOrder/GetFaultContents"
_CREATE_FAULT_ORDER_PATH = "operation/FaultOrder/CreateAsync"
_RECENT_ORDERS_PATH = "operation/FaultOrder/GetWorkingOrderInfoByUniqueCode"

URGENCY_LEVELS = {"Normal": "一般", "Middle": "中等", "Urgent": "紧急"}
MAX_TITLE_LENGTH = 100
MAX_TEXT_LENGTH = 4000
MAX_VERIFICATION_ITEMS = 8
MAX_DEVICES = 20
MAX_DRAFT_DEVICES_FETCH = 20
EDITABLE_FIELDS = (
    "order_title",
    "order_content",
    "fault_description",
    "remediation_plan",
    "verification_standards",
    "urgency",
    "device_id",
    "fault_content_ids",
    "plan_finish_time",
)


# ---------------------------------------------------------------------------
# Draft persistence (file-backed so the web and worker processes share state)
# ---------------------------------------------------------------------------


def _drafts_dir() -> Path:
    directory = get_data_registry() / "work_order_drafts"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _draft_path(draft_id: str) -> Path:
    return _drafts_dir() / f"{draft_id}.json"


def save_draft(draft: dict[str, Any]) -> None:
    target = _draft_path(draft["draft_id"])
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(draft, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    temporary.replace(target)


def load_draft(draft_id: str) -> dict[str, Any] | None:
    try:
        raw = json.loads(_draft_path(draft_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def audit_event(event: dict[str, Any]) -> str:
    path = get_data_registry() / "work_order_dispatch_audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return format_agent_path(path)


# ---------------------------------------------------------------------------
# Deterministic composition / validation helpers
# ---------------------------------------------------------------------------


def compose_order_content(
    *,
    fault_description: str,
    remediation_plan: str,
    verification_standards: list[str],
    event_id: str = "",
    evidence_ref: str = "",
) -> str:
    """System-composed work-order body; the LLM never writes this directly."""
    lines = [f"【故障描述】{fault_description.strip()}", f"【处置方案】{remediation_plan.strip()}"]
    standards = [item.strip() for item in verification_standards if item.strip()]
    if standards:
        lines.append("【验证标准】")
        lines.extend(f"- {standard}" for standard in standards[:MAX_VERIFICATION_ITEMS])
    trace = "；".join(
        part
        for part in (
            f"事件 {event_id.strip()}" if event_id.strip() else "",
            f"证据包 {evidence_ref.strip()}" if evidence_ref.strip() else "",
        )
        if part
    )
    if trace:
        lines.append(f"【来源】江苏站点告警自动诊断（{trace}，AI 草案经人工确认后创建）")
    return "\n".join(lines)


def _normalise_text(value: str, field: str, *, maximum: int = MAX_TEXT_LENGTH) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field}不能为空")
    if len(text) > maximum:
        raise ValueError(f"{field}超出 {maximum} 字长度限制")
    return text


def select_device(devices: list[dict[str, Any]], hint: str | None) -> dict[str, Any] | None:
    """Pick the device matching the diagnostic hint; deterministic order wins."""
    keyword = str(hint or "").strip().lower()
    if not keyword:
        return devices[0] if devices else None
    for device in devices:
        haystack = " ".join(
            str(device.get(part) or "")
            for part in ("label", "device_type_name", "device_type", "device_brand", "device_model", "device_code")
        ).lower()
        if keyword in haystack:
            return device
    return devices[0] if devices else None


def _bigrams(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)} if len(text) >= 2 else {text}


def match_fault_contents(options: list[dict[str, Any]], hints: list[str] | None) -> list[str]:
    """Map free-text fault categories onto the platform's fixed vocabulary.

    Substring coverage handles exact wording; shared Chinese bigrams keep
    near-synonyms such as 数据中断 ↔ 数据异常 or 不能开机 ↔ 无法开机 mapped.
    """
    keywords = [str(hint or "").strip().lower() for hint in (hints or []) if str(hint or "").strip()]
    keyword_bigrams = {keyword: _bigrams(keyword) for keyword in keywords}
    matched: list[str] = []
    for option in options:
        name = str(option.get("name") or "").strip()
        identifier = str(option.get("fault_content_id") or "").strip()
        if not name or not identifier or identifier == "other":
            continue
        lowered = name.lower()
        if any(
            keyword in lowered or lowered in keyword or (keyword_bigrams[keyword] & _bigrams(lowered))
            for keyword in keywords
        ):
            matched.append(identifier)
    return matched


def _parse_plan_finish_time(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("建议完成时间不能为空")
    for layout in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, layout).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    raise ValueError("建议完成时间格式无效，应为 YYYY-MM-DD HH:mm")


def validate_edits(draft: dict[str, Any], edits: dict[str, Any]) -> dict[str, Any]:
    """Validate operator edits against the system-resolved draft context.

    Returns the normalized final values used for platform submission.  Fields
    the operator did not touch fall back to the draft's prepared values.
    """
    merged = {field: edits.get(field, draft.get(field)) for field in EDITABLE_FIELDS}
    if merged.get("device_id") is None:
        merged["device_id"] = draft.get("selected_device_id")
    if merged.get("fault_content_ids") is None:
        merged["fault_content_ids"] = draft.get("selected_fault_content_ids")
    final: dict[str, Any] = {}
    final["order_title"] = _normalise_text(merged["order_title"], "工单标题", maximum=MAX_TITLE_LENGTH)
    final["fault_description"] = _normalise_text(merged["fault_description"], "故障描述")
    final["remediation_plan"] = _normalise_text(merged["remediation_plan"], "处置方案")
    standards = merged["verification_standards"]
    if not isinstance(standards, list):
        standards = [standards] if standards else []
    final["verification_standards"] = [
        str(item).strip() for item in standards if str(item or "").strip()
    ][:MAX_VERIFICATION_ITEMS]
    urgency = str(merged["urgency"] or "").strip()
    if urgency not in URGENCY_LEVELS:
        raise ValueError("紧急程度必须是 Normal、Middle 或 Urgent")
    final["urgency"] = urgency
    devices = draft.get("devices") or []
    device_id = merged["device_id"]
    try:
        device_id = int(device_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("必须选择有效设备") from exc
    if not any(int(device.get("device_id") or 0) == device_id for device in devices):
        raise ValueError("所选设备不在该站点设备台账中")
    final["device_id"] = device_id
    vocabulary = (draft.get("fault_contents") or {}).get(str(device_id)) or []
    allowed = {str(option.get("fault_content_id")) for option in vocabulary} | {"other"}
    content_ids = merged["fault_content_ids"]
    if not isinstance(content_ids, list):
        content_ids = [content_ids] if content_ids else []
    content_ids = [str(item).strip() for item in content_ids if str(item or "").strip()]
    if not content_ids:
        raise ValueError("至少选择一个故障现象")
    unknown = [item for item in content_ids if item not in allowed]
    if unknown:
        raise ValueError(f"故障现象 {','.join(unknown)} 不属于所选设备的平台故障现象")
    final["fault_content_ids"] = content_ids
    final["plan_finish_time"] = _parse_plan_finish_time(merged["plan_finish_time"])
    order_content = merged["order_content"]
    if order_content is None or not str(order_content).strip():
        order_content = compose_order_content(
            fault_description=final["fault_description"],
            remediation_plan=final["remediation_plan"],
            verification_standards=final["verification_standards"],
            event_id=draft.get("event_id") or "",
            evidence_ref=draft.get("evidence_ref") or "",
        )
    final["order_content"] = _normalise_text(order_content, "工单内容")
    return final


# ---------------------------------------------------------------------------
# Platform submission (used by the confirm API route)
# ---------------------------------------------------------------------------


async def create_fault_work_order_on_platform(final: dict[str, Any], station_code: str) -> dict[str, Any]:
    api = _JiangsuAuthenticatedApi(source="ops")
    payload = {
        "orderType": ORDER_TYPE_FAULT,
        "orderTitle": final["order_title"],
        "orderContent": final["order_content"],
        "otherContent": final["fault_description"],
        "urgencyType": final["urgency"],
        "deviceId": final["device_id"],
        "stationCodes": [station_code],
        "checkTask": final["fault_content_ids"],
        "planFinishTime": final["plan_finish_time"],
        "issuedType": [],
    }
    response = await api.post(_CREATE_FAULT_ORDER_PATH, payload)
    return response if isinstance(response, dict) else {"result": response}


async def resolve_created_order_code(
    *, unique_code: str, order_title: str, created_after: datetime
) -> str | None:
    """The create endpoint returns only ``true``; re-query the newest orders."""
    api = _JiangsuAuthenticatedApi(source="ops")
    payload = await api.get(_RECENT_ORDERS_PATH, [("uniqueCode", unique_code), ("take", "8")])
    entries = payload.get("result") or []
    if not isinstance(entries, list):
        return None
    best: tuple[datetime, str] | None = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        order = entry.get("wo") or {}
        if str(order.get("orderTitle") or "").strip() != order_title.strip():
            continue
        created = _parse_platform_time(order.get("createTime"))
        if created is None or created < created_after - timedelta(minutes=10):
            continue
        code = str(order.get("workingOrderCode") or "").strip()
        if code and (best is None or created > best[0]):
            best = (created, code)
    return best[1] if best else None


def _parse_platform_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for layout in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text[: len(layout) + 2], layout)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Platform lookups used while preparing the draft
# ---------------------------------------------------------------------------


async def _fetch_station_devices(api: _JiangsuAuthenticatedApi, station_code: str) -> list[dict[str, Any]]:
    payload = await api.get(_DEVICE_LIST_PATH, [("StationCode", station_code)])
    rows = payload.get("result") or payload.get("data") or []
    if not isinstance(rows, list):
        raise ValueError("站点设备台账接口返回格式无效")
    devices: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            device_id = int(row.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if device_id <= 0:
            continue
        type_name = str(row.get("deviceTypeName") or "").strip()
        device_type = str(row.get("deviceType") or "").strip()
        brand = str(row.get("deviceBrand") or "").strip()
        model = str(row.get("deviceModel") or "").strip()
        code = str(row.get("deviceCode") or "").strip()
        label = " ".join(part for part in (type_name or device_type, f"{brand}-{model}" if brand or model else "", code) if part)
        devices.append({
            "device_id": device_id,
            "device_code": code,
            "device_type": device_type,
            "device_type_name": type_name,
            "device_brand": brand,
            "device_model": model,
            "label": label or f"设备 {device_id}",
        })
        if len(devices) >= MAX_DEVICES:
            break
    return devices


async def _fetch_fault_contents(api: _JiangsuAuthenticatedApi, device_id: int) -> list[dict[str, Any]]:
    try:
        payload = await api.get(_FAULT_CONTENTS_PATH, [("deviceId", str(device_id)), ("workingOrderCode", "")])
    except (ValueError, httpx.HTTPError) as exc:
        logger.info("jiangsu_fault_contents_unavailable", device_id=device_id, error=str(exc))
        return []
    result = payload.get("result") or {}
    contents = result.get("faultContents") if isinstance(result, dict) else None
    if not isinstance(contents, list):
        return []
    options: list[dict[str, Any]] = []
    for item in contents:
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("faultContentId") or item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if identifier and name:
            options.append({"fault_content_id": identifier, "name": name})
    return options


class JiangsuFaultWorkOrderDraftTool(LLMTool):
    """Prepare a review-ready fault work-order draft; never dispatch directly."""

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_prepare_fault_work_order",
            description=(
                "生成江苏故障工单待确认草案：站点、设备台账和故障现象由系统自动解析，"
                "标题/故障描述/处置方案由诊断结论填充；草案在右侧面板供人工修改并确认推送，"
                "确认前不会在运维平台创建任何工单。"
            ),
            category=ToolCategory.TASK_MANAGEMENT,
            function_schema={
                "name": "jiangsu_prepare_fault_work_order",
                "description": (
                    "基于已完成的故障诊断生成待确认故障工单草案。系统自动解析站点、设备与平台故障现象；"
                    "本工具只创建待确认草案，需要人工在预览面板确认后才真正推送工单。"
                ),
                "parameters": {"type": "object", "properties": {
                    "station_name": {"type": "string", "description": "站点名称（与其他参数三选一）。"},
                    "station_code": {"type": "string", "description": "平台站点编码，例如 5006A。"},
                    "unique_code": {"type": "string", "description": "平台唯一编码。"},
                    "event_id": {"type": "string", "description": "触发本次诊断的事件 ID。"},
                    "evidence_ref": {"type": "string", "description": "证据包引用（事件证据包标识）。"},
                    "order_title": {"type": "string", "description": "工单标题，不超过 100 字。"},
                    "fault_description": {"type": "string", "description": "故障描述：症状、时间范围和关键证据。"},
                    "remediation_plan": {"type": "string", "description": "处置方案：远程核查与现场处置步骤。"},
                    "verification_standards": {"type": "array", "items": {"type": "string"}, "maxItems": 8,
                                               "description": "验证标准列表，每条一句话。"},
                    "urgency": {"type": "string", "enum": ["Normal", "Middle", "Urgent"],
                                "description": "紧急程度：Normal 一般、Middle 中等、Urgent 紧急。"},
                    "device_hint": {"type": "string", "description": "疑似故障设备提示，例如 PM10 分析仪、空调。"},
                    "fault_category_hints": {"type": "array", "items": {"type": "string"},
                                             "description": "故障现象关键词，系统自动匹配平台固定现象选项。"},
                    "plan_finish_hours": {"type": "integer", "minimum": 1, "maximum": 336,
                                          "description": "建议完成时限（小时），1–336。"},
                }, "required": ["order_title", "fault_description", "remediation_plan", "urgency"]},
            },
        )

    async def execute(
        self,
        context=None,
        station_name: str | None = None,
        station_code: str | None = None,
        unique_code: str | None = None,
        event_id: str | None = None,
        evidence_ref: str | None = None,
        order_title: str | None = None,
        fault_description: str | None = None,
        remediation_plan: str | None = None,
        verification_standards: list[str] | None = None,
        urgency: str | None = None,
        device_hint: str | None = None,
        fault_category_hints: list[str] | None = None,
        plan_finish_hours: int = 48,
        **_: Any,
    ) -> dict[str, Any]:
        from config.settings import settings

        try:
            names = _clean_identifier_list([station_name] if station_name else None, "station_names")
            stations = await _resolve_station_rows(
                names[0] if names else None,
                None,
                None,
                station_code=station_code,
                unique_code=unique_code,
            )
            if not stations:
                raise ValueError("未解析到有效站点")
            station = stations[0]
            title = _normalise_text(order_title, "工单标题", maximum=MAX_TITLE_LENGTH)
            description = _normalise_text(fault_description, "故障描述")
            plan = _normalise_text(remediation_plan, "处置方案")
            if urgency not in URGENCY_LEVELS:
                raise ValueError("urgency 必须是 Normal、Middle 或 Urgent")
            if not isinstance(plan_finish_hours, int) or not 1 <= plan_finish_hours <= 336:
                raise ValueError("plan_finish_hours 必须为 1–336 的整数小时")
            standards = [
                str(item).strip() for item in (verification_standards or []) if str(item or "").strip()
            ][:MAX_VERIFICATION_ITEMS]

            api = _JiangsuAuthenticatedApi(source="ops")
            devices = await _fetch_station_devices(api, station["station_code"])
            if not devices:
                raise ValueError("该站点在运维平台无设备台账，无法创建故障工单；请改为提示人工派单")
            device = select_device(devices, device_hint)
            fetched_contents = await asyncio.gather(*(
                _fetch_fault_contents(api, int(item["device_id"]))
                for item in devices[:MAX_DRAFT_DEVICES_FETCH]
            ))
            fault_contents = {
                str(item["device_id"]): options
                for item, options in zip(devices[:MAX_DRAFT_DEVICES_FETCH], fetched_contents, strict=True)
            }
            selected_ids = match_fault_contents(fault_contents.get(str(device["device_id"])) or [], fault_category_hints)
            if not selected_ids:
                selected_ids = ["other"]

            now = datetime.now().astimezone()
            draft_id = secrets.token_urlsafe(18)
            order_content = compose_order_content(
                fault_description=description,
                remediation_plan=plan,
                verification_standards=standards,
                event_id=event_id or "",
                evidence_ref=evidence_ref or "",
            )
            draft = {
                "draft_id": draft_id,
                "status": "pending",
                "order_type": ORDER_TYPE_FAULT,
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(hours=settings.jiangsu_work_order_draft_ttl_hours)).isoformat(),
                "session_id": str(getattr(context, "session_id", "") or ""),
                "event_id": str(event_id or "").strip(),
                "evidence_ref": str(evidence_ref or "").strip(),
                "station": station,
                "devices": devices,
                "selected_device_id": device["device_id"],
                "fault_contents": fault_contents,
                "selected_fault_content_ids": selected_ids,
                "order_title": title,
                "fault_description": description,
                "remediation_plan": plan,
                "verification_standards": standards,
                "order_content": order_content,
                "urgency": urgency,
                "plan_finish_time": (now + timedelta(hours=plan_finish_hours)).strftime("%Y-%m-%d %H:%M:%S"),
            }
            save_draft(draft)
            audit_path = audit_event({
                "occurred_at": now.isoformat(),
                "action": "draft_prepared",
                "draft_id": draft_id,
                "station_code": station["station_code"],
                "event_id": draft["event_id"],
                "device_id": device["device_id"],
                "order_title": title,
                "session_id": draft["session_id"],
            })
            visual = {
                "id": f"fault_work_order_{draft_id[:12]}",
                "type": VISUAL_TYPE,
                "title": f"工单确认 · {station['station_name'] or station['station_code']}",
                "data": {"draft": draft},
                "meta": {
                    "generator": self.name,
                    "event_id": draft["event_id"],
                    "station_code": station["station_code"],
                    "audit_log": audit_path,
                },
            }
            return {
                "status": "pending_confirmation",
                "success": True,
                "data": {
                    "draft_id": draft_id,
                    "station": station,
                    "device": device,
                    "fault_content_ids": selected_ids,
                    "expires_at": draft["expires_at"],
                    "editable_fields": list(EDITABLE_FIELDS),
                },
                "confirmation_token": draft_id,
                "visuals": [visual],
                "resources": resources_for_visuals([visual], tool_name=self.name),
                "metadata": {
                    "source": "jiangsu_operations_api",
                    "audit_log": audit_path,
                    "visual_behavior": "fault_work_order_panel",
                },
                "summary": (
                    f"工单草案已生成（待人工确认）：{title}。"
                    "已在右侧面板生成工单预览，站点、设备与故障现象由系统自动解析；"
                    "请人工核对并可修改后确认推送。当前尚未在运维平台创建工单。"
                ),
            }
        except (ValueError, httpx.HTTPError) as exc:
            return {"status": "failed", "success": False, "summary": f"工单草案生成失败：{exc}"}
