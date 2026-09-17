"""Constrained, auditable Jiangsu station device-control tools.

The upstream QC service is a legacy form API.  This adapter deliberately does
not expose its URL, signing algorithm, raw command codes, or arbitrary payloads
to the Agent.  It only maps a reviewed command vocabulary to that service.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import structlog
from Crypto.Cipher import DES3
from Crypto.Util.Padding import pad

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.jiangsu import device_control_simulation as simulation
from app.tools.resource_declarations import resources_for_visuals
from app.utils.path_config import format_agent_path, resolve_agent_path

logger = structlog.get_logger(__name__)


_STATION_DIRECTORY_PATH = "AirCityProductBase/GetAllEnabledBSDStationAsync"

_VALVE_CODES = {
    "so2_valve": ("SO2质控阀", "0_1", "0_24"),
    "no_valve": ("NO质控阀", "0_2", "0_25"),
    "co_valve": ("CO质控阀", "0_3", "0_26"),
    "o3_valve": ("O3质控阀", "0_4", "0_27"),
}
_POWER_CODES = {
    "zero_air_generator": ("质控电源", "0_7", "0_28", "零气机电源"),
    "dynamic_calibrator": ("质控电源", "0_8", "0_29", "校准仪电源"),
}
_AIR_CONDITIONER_MODES = {"on": 0, "cool": 1, "heat": 16, "dry": 31, "fan": 46, "off": 63}

# GetQCStateInfo returns a flat dict keyed by the platform's Chinese device
# names; the reviewed platform page maps them exactly this way.
_DEVICE_STATE_KEYS = {
    "so2_valve": "SO2质控阀",
    "no_valve": "NO质控阀",
    "co_valve": "CO质控阀",
    "o3_valve": "O3质控阀",
    "zero_air_generator": "零气机电源",
    "dynamic_calibrator": "校准仪电源",
}
# Asset basenames under frontend/src/assets/devicecontrol, copied from the
# platform station-house control page.
_DEVICE_ICONS = {
    "so2_valve": "so2",
    "no_valve": "no",
    "co_valve": "co",
    "o3_valve": "o3",
    "zero_air_generator": "air-generator",
    "dynamic_calibrator": "dynamic-calibrator",
    "air_conditioner": "air-conditioner",
}

_AC_MODE_TEXT = {0: "自动", 1: "制冷", 16: "制热", 31: "除湿", 46: "送风", 63: "关机"}


def _build_sim_rtype_map() -> dict[str, tuple[str, str]]:
    """Map legacy rType codes to the simulated state change they represent."""
    mapping: dict[str, tuple[str, str]] = {}
    for _name, on_code, off_code in _VALVE_CODES.values():
        mapping[on_code] = (_name, "开启")
        mapping[off_code] = (_name, "关闭")
    for _name, on_code, off_code, display in _POWER_CODES.values():
        mapping[on_code] = (display, "开启")
        mapping[off_code] = (display, "关闭")
    return mapping


_SIM_RTYPE_STATE = _build_sim_rtype_map()


def _simulation_changes(payload: dict[str, Any]) -> dict[str, str]:
    """Translate one CtlDevState payload into the simulated state it changes."""
    r_type = str(payload.get("rType") or "")
    if r_type in _SIM_RTYPE_STATE:
        key, value = _SIM_RTYPE_STATE[r_type]
        return {key: value}
    if str(payload.get("devName") or "") == "空调控制":
        try:
            mode = _AC_MODE_TEXT.get(int(payload.get("cmdIndex") or 0), "自动")
        except (TypeError, ValueError):
            mode = "自动"
        if mode == "关机":
            return {"空调": "关闭"}
        index = payload.get("selectIndex")
        if isinstance(index, int) and mode != "自动":
            return {"空调": f"{mode} {index + 15}℃"}
        return {"空调": mode}
    return {}


def _normalise_switch_state(value: Any) -> str | None:
    """Normalise the platform's 开启/关闭 style switch values."""
    if isinstance(value, bool):
        return "开启" if value else "关闭"
    text = str(value or "").strip()
    if not text:
        return None
    if "开" in text:
        return "开启"
    if "关" in text:
        return "关闭"
    return None


def _decode_state_payload(result: Any) -> dict[str, Any]:
    """Decode GetQCStateInfo through the direct, gateway-string or nested envelope."""
    from app.tools.jiangsu.fault_diagnosis import _auto_inspection_data  # lazy: import cycle

    data: Any = _auto_inspection_data(result if isinstance(result, dict) else {})
    for _ in range(3):
        if not isinstance(data, dict):
            return {}
        if any(key in data for key in _DEVICE_STATE_KEYS.values()):
            return data
        nested = data.get("Data") or data.get("data") or data.get("result")
        if isinstance(nested, str):
            data = _auto_inspection_data({"result": nested})
        elif isinstance(nested, dict):
            data = nested
        else:
            return data
    return data if isinstance(data, dict) else {}


def _request_succeeded(result: Any) -> bool:
    """Handle the platform's mixed bool/string success fields."""
    from app.tools.jiangsu.fault_diagnosis import _truthy  # lazy: import cycle
    if not isinstance(result, dict):
        return False
    return _truthy(result.get("Result", result.get("success", False)))


def _normalise_station_token(value: Any) -> str:
    """Match station display names the way the platform directory spells them."""
    return str(value or "").strip().replace(" ", "").rstrip("省市区县站")


async def _resolve_station(station_id: str | None, station_name: str | None) -> dict[str, Any]:
    """Resolve the platform-only uniqueCode from an explicit id or a station name.

    Name resolution walks the provincial air station directory (the same source
    the fault-diagnosis tools use) and requires an exact normalised match so a
    conversational “鼓楼站” maps to exactly one platform station.
    """
    sid = str(station_id or "").strip()
    name = str(station_name or "").strip()
    if sid:
        _station_id(sid)
        return {"station_id": sid, "station_name": name or None, "resolved_by": "unique_code"}
    if not name:
        raise ValueError("需要提供站点唯一编号（station_id）或站点名称（station_name）")
    # Lazy import: fault_diagnosis imports this module for the QC client.
    from app.tools.jiangsu.fault_diagnosis import _JiangsuAuthenticatedApi

    payload = await _JiangsuAuthenticatedApi(source="air").get(_STATION_DIRECTORY_PATH, [])
    rows = payload.get("result") or []
    if not isinstance(rows, list):
        raise ValueError("江苏站点目录返回格式异常")
    token = _normalise_station_token(name)
    matches = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for field in ("positionName", "stationName"):
            if _normalise_station_token(row.get(field)) == token:
                matches.append(row)
                break
    if not matches:
        raise ValueError(f"未在江苏站点目录中找到“{name}”；请确认站点名称，或改用站点唯一编号")
    if len(matches) > 1:
        candidates = "、".join(
            str(row.get("positionName") or row.get("stationName") or "?") for row in matches[:5]
        )
        raise ValueError(f"站点名称“{name}”匹配到 {len(matches)} 个站点（{candidates}）；请补充站点唯一编号")
    row = matches[0]
    unique = str(row.get("uniqueCode") or row.get("UniqueCode") or "").strip()
    if not unique:
        raise ValueError(f"站点“{name}”缺少江苏平台唯一编码，无法执行反控")
    return {
        "station_id": unique,
        "station_name": str(row.get("positionName") or row.get("stationName") or name).strip(),
        "station_code": str(row.get("stationCode") or row.get("StationCode") or "").strip() or None,
        "city_name": str(row.get("cityName") or "").strip() or None,
        "district_name": str(row.get("districtName") or "").strip() or None,
        "resolved_by": "station_directory",
    }


def _workspace_command(step: str, **payload: Any) -> dict[str, Any]:
    """Right-panel navigation command transported inside result.data.ui_command."""
    return {"type": "device_control_workspace", "step": step, **payload}


def _flatten_state_entries(data: Any, *, limit: int = 24) -> list[dict[str, str]]:
    """Flatten the raw QC payload into labelled key-value rows for the panel."""
    entries: list[dict[str, str]] = []

    def walk(prefix: str, value: Any) -> None:
        if len(entries) >= limit:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                if len(entries) >= limit:
                    return
                label = str(key)
                walk(f"{prefix}.{label}" if prefix else label, child)
            return
        if isinstance(value, list):
            if value and all(isinstance(item, (str, int, float, bool)) or item is None for item in value):
                text = "、".join(str(item) for item in value[:6])
                entries.append({"label": prefix or "条目", "value": text})
                return
            for index, child in enumerate(value):
                if len(entries) >= limit:
                    return
                walk(f"{prefix}[{index}]" if prefix else f"[{index}]", child)
            return
        if value is None or (isinstance(value, str) and not value.strip()):
            return
        entries.append({"label": prefix or "值", "value": str(value)})

    walk("", data)
    return entries


def _precondition_catalog(states: dict[str, str | None] | None = None) -> list[dict[str, Any]]:
    """Static review-approved command catalogue merged with live device state."""
    live = states or {}
    rows: list[dict[str, Any]] = []
    switch_note = "开关类操作等待前端人工确认交互上线，当前不可执行"
    for key, (name, _on, _off) in _VALVE_CODES.items():
        rows.append({
            "key": key, "name": name, "kind": "质控阀",
            "state_key": _DEVICE_STATE_KEYS.get(key), "icon": _DEVICE_ICONS.get(key),
            "status": live.get(key), "allowed": [], "blocked": ["开启", "关闭"], "note": switch_note,
        })
    for key, (_name, _on, _off, display) in _POWER_CODES.items():
        rows.append({
            "key": key, "name": display, "kind": "质控电源",
            "state_key": _DEVICE_STATE_KEYS.get(key), "icon": _DEVICE_ICONS.get(key),
            "status": live.get(key), "allowed": [], "blocked": ["开启", "关闭"], "note": switch_note,
        })
    rows.append({
        "key": "air_conditioner", "name": "空调", "kind": "空调",
        "state_key": "空调", "icon": _DEVICE_ICONS["air_conditioner"],
        "status": live.get("air_conditioner"),
        "allowed": ["制冷/制热/除湿/送风 16–30℃"],
        "blocked": ["开启", "关闭"],
        "note": "温度设定可经确认后执行；开关操作等待前端人工确认。开通状态不在本接口返回",
    })
    return rows


def _device_control_state_visual(station: dict[str, Any], state_data: Any, queried_at: str,
                                 *, simulated: bool = False) -> dict[str, Any]:
    station_name = str(station.get("station_name") or station["station_id"])
    states = {
        key: _normalise_switch_state(state_data.get(state_key))
        for key, state_key in _DEVICE_STATE_KEYS.items()
    } if isinstance(state_data, dict) else {}
    if isinstance(state_data, dict):
        ac_text = str(state_data.get("空调") or "").strip()
        if ac_text:
            states["air_conditioner"] = ac_text
    return {
        "id": f"device_control_{station['station_id']}",
        "type": "device_control_state",
        "title": f"{station_name}设备反控状态",
        "data": {
            "device_control": {
                "station": station,
                "snapshot": _flatten_state_entries(state_data),
                "devices": _precondition_catalog(states),
                "state_keys": list(_DEVICE_STATE_KEYS.values()),
                "simulated": simulated,
                "updated_at": queried_at,
            }
        },
        "meta": {
            "generator": "jiangsu_get_device_control_state",
            "scenario": "device_control_state",
            "station": station,
            "simulated": simulated,
        },
    }


@dataclass(frozen=True)
class _PendingCommand:
    session_id: str
    token: str
    payload: dict[str, str | int]
    summary: str
    expires_at: datetime


class _DeviceControlClient:
    """Shared protocol client and in-memory, session-bound confirmations."""

    _pending: dict[str, _PendingCommand] = {}
    _lock = asyncio.Lock()

    def __init__(self) -> None:
        from config.settings import settings

        self.base_url = settings.jiangsu_qc_api_base_url.rstrip("/")
        self.api_key = settings.jiangsu_qc_api_key
        self.timeout_seconds = settings.jiangsu_qc_api_timeout_seconds
        self.confirmation_ttl_seconds = settings.jiangsu_device_control_confirmation_ttl_seconds

    def _validate_config(self) -> None:
        if not self.base_url or not self.api_key:
            raise ValueError("未配置江苏设备反控服务地址或后端签名密钥")

    @staticmethod
    def _session_id(context: Any) -> str:
        session_id = str(getattr(context, "session_id", "") or "").strip()
        if not session_id:
            raise ValueError("设备反控需要有效会话上下文")
        return session_id

    def _token(self, method: str) -> str:
        try:
            key = base64.b64decode(self.api_key, validate=True)
        except Exception as exc:
            raise ValueError("江苏设备反控签名密钥不是有效 Base64") from exc
        if len(key) not in (16, 24):
            raise ValueError("江苏设备反控签名密钥长度无效")
        try:
            cipher = DES3.new(DES3.adjust_key_parity(key), DES3.MODE_ECB)
        except ValueError:
            cipher = DES3.new(key, DES3.MODE_ECB)
        return base64.b64encode(cipher.encrypt(pad(method.encode("utf-8"), DES3.block_size))).decode("ascii")

    async def post(self, method: str, payload: dict[str, str | int]) -> dict[str, Any]:
        self._validate_config()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-5]
        form: dict[str, str | int] = {
            **payload,
            "Token": self._token(method),
            "tokenEx": hmac.new(
                self.api_key.encode("utf-8"), f"{method}_{timestamp}".encode("utf-8"), hashlib.sha1
            ).hexdigest(),
            "userName": "suyuan-agent",
            "timestamp": timestamp,
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(f"{self.base_url}/QCAPI/{method}", data=form)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("江苏设备反控服务返回格式无效")
        return result

    async def prepare(self, context: Any, payload: dict[str, str | int], summary: str) -> _PendingCommand:
        session_id = self._session_id(context)
        now = datetime.now(timezone.utc)
        pending = _PendingCommand(
            session_id=session_id,
            token=secrets.token_urlsafe(24),
            payload=payload,
            summary=summary,
            expires_at=now + timedelta(seconds=self.confirmation_ttl_seconds),
        )
        async with self._lock:
            # A new request supersedes previous unexecuted requests for the same session.
            registry = type(self)._pending
            now_utc = datetime.now(timezone.utc)
            for stale in [token for token, value in registry.items() if value.expires_at <= now_utc]:
                registry.pop(stale, None)
            registry[pending.token] = pending
        return pending

    async def consume(self, context: Any, token: str) -> _PendingCommand:
        session_id = self._session_id(context)
        async with self._lock:
            pending = type(self)._pending.pop(token, None)
        if pending is None:
            raise ValueError("确认令牌不存在、已使用或已过期；请重新生成待确认指令")
        if pending.session_id != session_id:
            raise ValueError("确认令牌不属于当前会话")
        if pending.expires_at <= datetime.now(timezone.utc):
            raise ValueError("确认令牌已过期；请重新生成待确认指令")
        return pending

    @staticmethod
    def audit(event: dict[str, Any]) -> str:
        path = resolve_agent_path("backend/backend_data_registry_jiangsu_ops/device_control_audit.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        return format_agent_path(path)


_QC_GATEWAY_PROXY_PATH = "stationintegrate/OnlineQC/QcSvcAgent"


def _gateway_form_data(payload: dict[str, str | int], *, user_name: str) -> str:
    params = "&".join(f"{key}={value}" for key, value in payload.items() if key != "userName")
    return f"{params}&userName={user_name}&timestamp={int(datetime.now().timestamp() * 1000)}"


async def _post_qc(method: str, payload: dict[str, str | int], *, gateway_data: str | None = None) -> tuple[dict[str, Any], str]:
    """Call a QC method via the air gateway first, then the direct signed endpoint.

    The gateway proxy keeps the QC signing key on the platform server, so
    deployments without jiangsu_qc_api_base_url/jiangsu_qc_api_key still work
    (this is how GetAutoInspection reaches the same service).  The direct
    3DES-signed endpoint remains as fallback for deployments that expose it.
    """
    from app.tools.jiangsu.fault_diagnosis import _JiangsuAuthenticatedApi

    if simulation.simulation_enabled() and method in {"GetQCStateInfo", "CtlDevState"}:
        station_id = str(payload.get("stationId") or "")
        if method == "GetQCStateInfo":
            return simulation.state_envelope(station_id), "simulation"
        return simulation.command_envelope(station_id, _simulation_changes(payload)), "simulation"

    data = gateway_data or _gateway_form_data(payload, user_name="suyuan-agent")
    try:
        result = await _JiangsuAuthenticatedApi(source="air").post(_QC_GATEWAY_PROXY_PATH, {
            "url": f"/QCAPI/{method}", "apiMethod": method, "data": data,
        })
        return result, "air_gateway"
    except (ValueError, httpx.HTTPError) as gateway_exc:
        client = _DeviceControlClient()
        try:
            client._validate_config()
        except ValueError:
            raise gateway_exc from None
        return await client.post(method, payload), "direct_signed"


class JiangsuDeviceControlStateTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_get_device_control_state",
            description="读取江苏站房质控阀、零气机、校准仪和空调反控相关状态；仅查询。已知站点唯一编号时传 station_id，否则传 station_name 由站点目录解析。",
            category=ToolCategory.QUERY,
            function_schema={
                "name": "jiangsu_get_device_control_state",
                "description": "按平台站点唯一编号或站点名称读取可反控设备当前状态，并在右侧面板展示设备状态与远程控制前置条件。",
                "parameters": {"type": "object", "properties": {
                    "station_id": {"type": "string", "description": "江苏平台站点 uniqueCode；已知时优先提供，不是站点名称。"},
                    "station_name": {"type": "string", "description": "站点名称，如“鼓楼站”；station_id 缺失时必填，由工具在站点目录中精确解析。"},
                }, "required": []},
            },
        )

    async def execute(self, context=None, station_id: str | None = None, station_name: str | None = None, **_: Any) -> dict[str, Any]:
        try:
            station = await _resolve_station(station_id, station_name)
            gateway_data = _gateway_form_data(
                {"StationId": station["station_id"]}, user_name="admin"
            )
            result, channel = await _post_qc(
                "GetQCStateInfo", {"stationId": station["station_id"]}, gateway_data=gateway_data,
            )
            success = _request_succeeded(result)
            state_data = _decode_state_payload(result)
            has_snapshot = bool(state_data)
            simulated = channel == "simulation"
            queried_at = datetime.now(timezone.utc).isoformat()
            visual = _device_control_state_visual(station, state_data, queried_at, simulated=simulated) if success else None
            empty_note = ("服务连通但该站点未返回设备状态数据（上游 QC 快照为空）；"
                          "可结合自动巡检或人工现场核查确认设备实际状态。")
            response: dict[str, Any] = {
                "status": "success" if success else "failed", "success": success,
                "data": {
                    "station": station,
                    "state": state_data,
                    "simulated": simulated,
                    "ui_command": _workspace_command(
                        "state", station=station, success=success, simulated=simulated,
                        message=(None if success else str(result.get("ErrorMessage") or result.get("message") or "服务未说明原因")),
                        occurred_at=queried_at,
                    ),
                },
                "metadata": {"source": "jiangsu_qc_api", "channel": channel, "station": station, "simulated": simulated,
                             "method": "GetQCStateInfo", "has_snapshot": has_snapshot, "queried_at": queried_at},
                "summary": (f"{station.get('station_name') or station['station_id']} 设备状态查询完成，已更新右侧设备状态面板。"
                            if success and has_snapshot else
                            (f"{station.get('station_name') or station['station_id']} {empty_note}" if success else
                             f"设备状态查询未成功：{result.get('ErrorMessage') or result.get('message') or '服务未说明原因'}")),
            }
            if visual is not None:
                response["visuals"] = [visual]
                response["resources"] = resources_for_visuals([visual], tool_name=self.name)
            return response
        except (ValueError, httpx.HTTPError) as exc:
            return {"status": "failed", "success": False, "data": {}, "summary": f"设备状态查询失败：{exc}"}


class JiangsuDeviceControlPrepareTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_prepare_device_control",
            description="生成江苏站房受限设备反控的待确认指令；不会执行任何设备操作。",
            category=ToolCategory.TASK_MANAGEMENT,
            function_schema={
                "name": "jiangsu_prepare_device_control",
                "description": "将固定设备动作映射为待确认指令。调用后必须等待用户下一轮明确确认，才能执行。",
                "parameters": {"type": "object", "properties": {
                    "station_id": {"type": "string", "description": "江苏平台站点 uniqueCode；已知时优先提供。"},
                    "station_name": {"type": "string", "description": "站点名称，如“鼓楼站”；station_id 缺失时必填。"},
                    "device": {"type": "string", "enum": [*list(_VALVE_CODES), *list(_POWER_CODES), "air_conditioner"]},
                    "action": {"type": "string", "enum": ["on", "off", "cool", "heat", "dry", "fan"]},
                    "temperature_celsius": {"type": "integer", "minimum": 16, "maximum": 30, "description": "空调 cool/heat/dry/fan 必填。"},
                }, "required": ["device", "action"]},
            },
            requires_context=True,
        )

    async def execute(self, context=None, station_id: str | None = None, station_name: str | None = None,
                      device: str | None = None, action: str | None = None, temperature_celsius: int | None = None,
                      **_: Any) -> dict[str, Any]:
        try:
            station = await _resolve_station(station_id, station_name)
            payload, summary = _build_command(station["station_id"], device, action, temperature_celsius)
            simulated = simulation.simulation_enabled()
            if _requires_frontend_confirmation(device, action):
                reason = "开关操作必须经前端人工确认；当前尚未提供确认交互，未生成可执行指令。"
                return {
                    "status": "frontend_confirmation_required", "success": False,
                    "data": {"station": station, "station_id": payload["stationId"], "command": summary, "simulated": simulated,
                             "ui_command": _workspace_command("blocked", station=station, command=summary, reason=reason,
                                                              simulated=simulated)},
                    "summary": reason,
                }
            pending = await _DeviceControlClient().prepare(context, payload, summary)
            note = "（演示模式：指令将在确认后作用于模拟数据）" if simulated else ""
            return {
                "status": "pending_confirmation", "success": True,
                "data": {"station": station, "station_id": payload["stationId"], "command": summary, "simulated": simulated,
                         "expires_at": pending.expires_at.isoformat(),
                         "ui_command": _workspace_command(
                             "prepare", station=station, command=summary,
                             expires_at=pending.expires_at.isoformat(),
                             confirmation_token=pending.token,
                             simulated=simulated,
                         )},
                "confirmation_token": pending.token,
                "summary": f"待确认指令：{summary}{note}。未执行；请在下一轮获得用户明确确认后再执行。",
            }
        except ValueError as exc:
            return {"status": "failed", "success": False, "summary": f"生成待确认指令失败：{exc}"}


class JiangsuDeviceControlExecuteTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_execute_device_control",
            description="执行已生成且经用户明确确认的江苏站房设备反控指令，并自动复查状态。",
            category=ToolCategory.TASK_MANAGEMENT,
            function_schema={
                "name": "jiangsu_execute_device_control",
                "description": "仅执行当前会话中有效的待确认指令；必须由用户后续消息明确确认后调用。",
                "parameters": {"type": "object", "properties": {
                    "confirmation_token": {"type": "string"},
                    "confirmed": {"type": "boolean", "const": True},
                }, "required": ["confirmation_token", "confirmed"]},
            },
            requires_context=True,
        )

    async def execute(self, context=None, confirmation_token: str | None = None, confirmed: bool = False, **_: Any) -> dict[str, Any]:
        if confirmed is not True:
            return {"status": "confirmation_required", "success": False, "summary": "未执行：必须提供 confirmed=true，且只能在用户明确确认后的下一轮调用。"}
        try:
            client = _DeviceControlClient()
            pending = await client.consume(context, str(confirmation_token or ""))
            result, channel = await _post_qc("CtlDevState", pending.payload)
            simulated = channel == "simulation"
            accepted = bool(result.get("Result", result.get("success", False)))
            state_result: dict[str, Any] | None = None
            if accepted:
                try:
                    recheck_gateway_data = _gateway_form_data(
                        {"StationId": pending.payload["stationId"]}, user_name="admin"
                    )
                    state_result, _ = await _post_qc(
                        "GetQCStateInfo", {"stationId": pending.payload["stationId"]},
                        gateway_data=recheck_gateway_data,
                    )
                except (ValueError, httpx.HTTPError) as exc:
                    state_result = {"recheck_error": str(exc)}
            audit_path = client.audit({
                "occurred_at": datetime.now(timezone.utc).isoformat(), "session_id": getattr(context, "session_id", None),
                "command": pending.summary, "payload": pending.payload, "accepted": accepted, "simulated": simulated,
                "service_response": result, "recheck_response": state_result,
            })
            readback_error = isinstance(state_result, dict) and state_result.get("recheck_error")
            return {
                "status": "success" if accepted else "failed", "success": accepted,
                "data": {
                    "station_id": pending.payload["stationId"], "command": pending.summary,
                    "service_response": result, "recheck": state_result, "simulated": simulated,
                    "ui_command": _workspace_command(
                        "execute", station={"station_id": pending.payload["stationId"]},
                        command=pending.summary, accepted=accepted, simulated=simulated,
                        message=(None if accepted else str(result.get("ErrorMessage") or result.get("message") or "服务未说明原因")),
                        readback_available=bool(accepted and state_result and not readback_error),
                        audit_log=audit_path,
                        occurred_at=datetime.now(timezone.utc).isoformat(),
                    ),
                },
                "metadata": {"audit_log": audit_path, "station_id": pending.payload["stationId"],
                             "channel": channel, "simulated": simulated},
                "summary": (f"设备反控已由平台受理：{pending.summary}。已完成状态复查。" if accepted
                            else f"设备反控未被平台受理：{result.get('ErrorMessage') or result.get('message') or '服务未说明原因'}"),
            }
        except (ValueError, httpx.HTTPError) as exc:
            return {"status": "failed", "success": False, "summary": f"设备反控执行失败：{exc}"}


def _station_id(value: str | None) -> str:
    station_id = str(value or "").strip()
    if not station_id or len(station_id) > 64:
        raise ValueError("station_id 必须是有效的江苏平台站点 uniqueCode")
    return station_id


def _build_command(station_id: str | None, device: str | None, action: str | None,
                   temperature_celsius: int | None) -> tuple[dict[str, str | int], str]:
    station = _station_id(station_id)
    if device in _VALVE_CODES:
        if action not in {"on", "off"}:
            raise ValueError("质控阀仅支持 on 或 off")
        name, on_code, off_code = _VALVE_CODES[device]
        return {"stationId": station, "devName": "质控阀", "rType": on_code if action == "on" else off_code}, f"站点 {station}：{name}{'开启' if action == 'on' else '关闭'}"
    if device in _POWER_CODES:
        if action not in {"on", "off"}:
            raise ValueError("质控电源仅支持 on 或 off")
        name, on_code, off_code, display = _POWER_CODES[device]
        return {"stationId": station, "devName": name, "rType": on_code if action == "on" else off_code}, f"站点 {station}：{display}{'开启' if action == 'on' else '关闭'}"
    if device == "air_conditioner":
        if action not in _AIR_CONDITIONER_MODES:
            raise ValueError("空调仅支持 on、off、cool、heat、dry 或 fan")
        if action in {"cool", "heat", "dry", "fan"}:
            if not isinstance(temperature_celsius, int) or not 16 <= temperature_celsius <= 30:
                raise ValueError("空调制冷、制热、除湿或送风必须设置 16–30℃整数温度")
            select_index = temperature_celsius - 15
            action_text = {"cool": "制冷", "heat": "制热", "dry": "除湿", "fan": "送风"}[action]
            summary = f"站点 {station}：空调设为{action_text} {temperature_celsius}℃"
        else:
            select_index = 1
            summary = f"站点 {station}：空调{'开启' if action == 'on' else '关闭'}"
        return {
            "stationId": station, "userName": "suyuan-agent", "devName": "空调控制", "rType": 23,
            "cmdIndex": _AIR_CONDITIONER_MODES[action], "passageway": 1, "operationType": 0,
            "selectIndex": select_index,
        }, summary
    raise ValueError("device 必须为受支持的质控阀、质控电源或 air_conditioner")


def _requires_frontend_confirmation(device: str | None, action: str | None) -> bool:
    """Keep all on/off actions unavailable until the UI confirmation flow exists.

    This preserves the requested initial integration scope: state reads and
    air-conditioner temperature-setting can be tested, but no equipment switch
    state can be changed from Agent chat alone.  The simulated demo mode
    (JIANGSU_DEVICE_CONTROL_SIMULATION) relaxes this so the full 质控 process can
    be demonstrated against the simulated backend.
    """
    if simulation.simulation_enabled():
        return False
    return device in {*_VALVE_CODES, *_POWER_CODES} or action in {"on", "off"}
