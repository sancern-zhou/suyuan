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
from app.utils.path_config import format_agent_path, resolve_agent_path

logger = structlog.get_logger(__name__)


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
            self._pending = {key: value for key, value in self._pending.items() if value.expires_at > now}
            self._pending[pending.token] = pending
        return pending

    async def consume(self, context: Any, token: str) -> _PendingCommand:
        session_id = self._session_id(context)
        async with self._lock:
            pending = self._pending.pop(token, None)
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


class JiangsuDeviceControlStateTool(LLMTool):
    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_get_device_control_state",
            description="读取江苏站房质控阀、零气机、校准仪和空调反控相关状态；仅查询。",
            category=ToolCategory.QUERY,
            function_schema={
                "name": "jiangsu_get_device_control_state",
                "description": "按平台站点唯一编号读取可反控设备当前状态。",
                "parameters": {"type": "object", "properties": {
                    "station_id": {"type": "string", "description": "江苏平台站点 uniqueCode，不是站点名称。"},
                }, "required": ["station_id"]},
            },
        )

    async def execute(self, context=None, station_id: str | None = None, **_: Any) -> dict[str, Any]:
        try:
            station_id = _station_id(station_id)
            result = await _DeviceControlClient().post("GetQCStateInfo", {"stationId": station_id})
            success = bool(result.get("Result", result.get("success", False)))
            return {
                "status": "success" if success else "failed", "success": success,
                "data": result.get("Data", result),
                "metadata": {"source": "jiangsu_qc_api", "station_id": station_id, "method": "GetQCStateInfo"},
                "summary": "设备状态查询完成。" if success else f"设备状态查询未成功：{result.get('ErrorMessage') or result.get('message') or '服务未说明原因'}",
            }
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
                    "station_id": {"type": "string", "description": "江苏平台站点 uniqueCode。"},
                    "device": {"type": "string", "enum": [*list(_VALVE_CODES), *list(_POWER_CODES), "air_conditioner"]},
                    "action": {"type": "string", "enum": ["on", "off", "cool", "heat", "dry", "fan"]},
                    "temperature_celsius": {"type": "integer", "minimum": 16, "maximum": 30, "description": "空调 cool/heat/dry/fan 必填。"},
                }, "required": ["station_id", "device", "action"]},
            },
        )

    async def execute(self, context=None, station_id: str | None = None, device: str | None = None,
                      action: str | None = None, temperature_celsius: int | None = None, **_: Any) -> dict[str, Any]:
        try:
            payload, summary = _build_command(station_id, device, action, temperature_celsius)
            if _requires_frontend_confirmation(device, action):
                return {
                    "status": "frontend_confirmation_required", "success": False,
                    "data": {"station_id": payload["stationId"], "command": summary},
                    "summary": "该开关操作必须经前端人工确认；当前尚未提供确认交互，未生成可执行指令。",
                }
            pending = await _DeviceControlClient().prepare(context, payload, summary)
            return {
                "status": "pending_confirmation", "success": True,
                "data": {"station_id": payload["stationId"], "command": summary, "expires_at": pending.expires_at.isoformat()},
                "confirmation_token": pending.token,
                "summary": f"待确认指令：{summary}。未执行；请在下一轮获得用户明确确认后再执行。",
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
        )

    async def execute(self, context=None, confirmation_token: str | None = None, confirmed: bool = False, **_: Any) -> dict[str, Any]:
        if confirmed is not True:
            return {"status": "confirmation_required", "success": False, "summary": "未执行：必须提供 confirmed=true，且只能在用户明确确认后的下一轮调用。"}
        try:
            client = _DeviceControlClient()
            pending = await client.consume(context, str(confirmation_token or ""))
            result = await client.post("CtlDevState", pending.payload)
            accepted = bool(result.get("Result", result.get("success", False)))
            state_result: dict[str, Any] | None = None
            if accepted:
                try:
                    state_result = await client.post("GetQCStateInfo", {"stationId": pending.payload["stationId"]})
                except (ValueError, httpx.HTTPError) as exc:
                    state_result = {"recheck_error": str(exc)}
            audit_path = client.audit({
                "occurred_at": datetime.now(timezone.utc).isoformat(), "session_id": getattr(context, "session_id", None),
                "command": pending.summary, "payload": pending.payload, "accepted": accepted,
                "service_response": result, "recheck_response": state_result,
            })
            return {
                "status": "success" if accepted else "failed", "success": accepted,
                "data": {"command": pending.summary, "service_response": result, "recheck": state_result},
                "metadata": {"audit_log": audit_path, "station_id": pending.payload["stationId"]},
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
    state can be changed from Agent chat alone.
    """
    return device in {*_VALVE_CODES, *_POWER_CODES} or action in {"on", "off"}
