"""Read-only Jiangsu data tools for focused station fault diagnosis."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

import httpx
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.jiangsu.device_control import _DeviceControlClient
from app.tools.jiangsu.result_filter import externalize_compact_records
from app.tools.jiangsu.station_data import JiangsuStationDataTool
from app.tools.resource_declarations import resources_for_visuals, single_file_product
from app.utils.path_config import (
    format_agent_path,
    get_data_registry,
    get_sessions_dir,
    is_path_within,
    resolve_agent_path,
)

logger = structlog.get_logger(__name__)


class _JiangsuAuthenticatedApi:
    def __init__(self, *, source: str) -> None:
        from config.settings import settings

        if source == "air":
            self.base_url = settings.jiangsu_air_api_base_url.rstrip("/")
            self.token_url = f"{self.base_url}/AirCityBaseCommon/GetExternalApiToken"
            self.username = settings.jiangsu_air_api_username
            self.password = settings.jiangsu_air_api_password
            self.sys_code = "SunAirProvince"
        else:
            self.base_url = settings.jiangsu_ops_api_base_url.rstrip("/")
            self.token_url = settings.jiangsu_ops_token_url.rstrip("/")
            self.username = settings.jiangsu_ops_api_username or settings.jiangsu_air_api_username
            self.password = settings.jiangsu_ops_api_password or settings.jiangsu_air_api_password
            self.sys_code = "SunOps"
        self.timeout_seconds = settings.jiangsu_ops_api_timeout_seconds
        self._token: str | None = None
        self._lock = asyncio.Lock()

    async def get(self, path: str, params: list[tuple[str, str]]) -> dict[str, Any]:
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
                f"{self.base_url}/{path.lstrip('/')}", params=params,
                headers={"Authorization": f"Bearer {token}", "SysCode": self.sys_code, "Accept": "application/json"},
            )
        if response.status_code == 401:
            self._token = None
            return await self.get(path, params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("江苏接口返回格式无效")
        if payload.get("success") is False:
            raise ValueError(str(payload.get("msg") or payload.get("message") or "江苏接口返回失败"))
        return payload

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST through the authenticated air/ops gateway.

        The station-house UI uses this gateway to keep the QC signing key on
        the platform server. A scalar JSON response is wrapped as ``result``
        so callers can handle it alongside normal API envelopes.
        """
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/{path.lstrip('/')}", json=payload,
                headers={"Authorization": f"Bearer {token}", "SysCode": self.sys_code, "Accept": "application/json"},
            )
        if response.status_code == 401:
            self._token = None
            return await self.post(path, payload)
        response.raise_for_status()
        body = response.json()
        if isinstance(body, dict):
            if body.get("success") is False:
                raise ValueError(str(body.get("msg") or body.get("message") or "江苏接口返回失败"))
            return body
        return {"result": body}

    async def download_file(
        self,
        path: str,
        params: list[tuple[str, str]],
        *,
        max_bytes: int,
        retry_unauthorized: bool = True,
    ) -> tuple[bytes, str]:
        """Download one authenticated platform file with a hard size limit."""
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            async with client.stream(
                "GET",
                f"{self.base_url}/{path.lstrip('/')}",
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "SysCode": self.sys_code,
                    "Accept": "*/*",
                },
            ) as response:
                if response.status_code == 401 and retry_unauthorized:
                    self._token = None
                    return await self.download_file(
                        path,
                        params,
                        max_bytes=max_bytes,
                        retry_unauthorized=False,
                    )
                response.raise_for_status()
                declared_size = response.headers.get("content-length")
                if declared_size:
                    try:
                        parsed_size = int(declared_size)
                    except ValueError:
                        parsed_size = None
                    if parsed_size is not None and parsed_size > max_bytes:
                        raise ValueError(f"附件超过单文件 {max_bytes // (1024 * 1024)}MB 限制")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > max_bytes:
                        raise ValueError(f"附件超过单文件 {max_bytes // (1024 * 1024)}MB 限制")
                return bytes(content), str(response.headers.get("content-type") or "application/octet-stream")

    async def _get_token(self) -> str:
        if self._token:
            return self._token
        if not self.base_url or not self.token_url or not self.username or not self.password:
            raise ValueError("未配置江苏接口地址或账号")
        async with self._lock:
            if self._token:
                return self._token
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.token_url, params={"UserName": self.username, "Pwd": self.password})
            response.raise_for_status()
            payload = response.json()
            token = payload.get("result") if isinstance(payload, dict) else None
            if not isinstance(token, str) or not token:
                raise ValueError("江苏接口 Token 获取失败")
            self._token = token
            return token


class JiangsuStationAlarmLogsTool(LLMTool):
    _PATH = "stationintegrate/StationIntegrate/GetAlarmLogsAsync"
    # A city-wide fan-out (Nanjing: 121 stations) still needs ~90s even at
    # high concurrency, and the upstream starts timing out beyond ~20
    # in-flight requests.  Geographic scopes are therefore rejected; only
    # directly addressed stations are queried concurrently, mirroring the
    # auto-inspection limit.
    _MAX_STATIONS = 10

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_station_alarm_logs",
            description="读取江苏站房设备告警日志、告警统计与设备告警状态；只支持直接指定站点（名称/平台编码/唯一编码，最多 10 个，并发查询）。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_station_alarm_logs", "description": "按站点名称、平台站点编码或唯一编码读取站房设备告警，最多 10 个站点并发查询；不支持城市/区县批量。",
                             "parameters": {"type": "object", "properties": {
                                 "station_names": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                                    "description": "站点名称列表，最多 10 个。"},
                                 "station_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                                    "description": "平台站点编码列表，例如 [\"5006A\"]，最多 10 个。"},
                                 "unique_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                                   "description": "平台唯一编码列表；已知时可直接使用，最多 10 个。"},
                             }, "required": []}},
        )

    async def execute(self, context=None, station_names: list[str] | None = None,
                      station_codes: list[str] | None = None, unique_codes: list[str] | None = None,
                      **_: Any) -> dict[str, Any]:
        try:
            stations = await self._resolve_stations(station_names, station_codes, unique_codes)
            api = _JiangsuAuthenticatedApi(source="air")
            data = list(await asyncio.gather(
                *(self._fetch_station(api, station) for station in stations)
            ))
            count = sum(len(item["result"].get("alarmLogs") or []) for item in data)
            failed_count = sum(1 for item in data if not item["success"])
            success = failed_count < len(stations)
            summary = f"站房告警查询完成：并发查询 {len(stations)} 个站点，返回 {count} 条告警记录"
            if failed_count:
                summary += f"，{failed_count} 个站点查询失败"
            return {"status": "success" if success else "failed", "success": success, "data": data,
                    "metadata": {"source": "jiangsu_station_integrate_api", "endpoint": self._PATH,
                                 "station_count": len(stations), "record_count": count,
                                 "failed_station_count": failed_count,
                                 "queried_at": datetime.now().astimezone().isoformat()}, "summary": summary + "。"}
        except (ValueError, httpx.HTTPError) as exc:
            return {"status": "failed", "success": False, "data": {}, "summary": f"站房告警查询失败：{exc}"}

    async def _fetch_station(self, api: _JiangsuAuthenticatedApi, station: dict[str, str]) -> dict[str, Any]:
        try:
            payload = await api.get(self._PATH, [("StationCode", station["station_code"])])
            result = payload.get("result") or {}
            if not isinstance(result, dict):
                raise ValueError("站房告警接口 result 无效")
            return {"station": station, "result": result, "success": True}
        except (ValueError, httpx.HTTPError) as exc:
            return {"station": station, "result": {}, "success": False, "error": str(exc)}

    async def _resolve_stations(
        self,
        station_names: list[str] | None,
        station_codes: list[str] | None,
        unique_codes: list[str] | None,
    ) -> list[dict[str, str]]:
        return await _resolve_direct_station_scope(
            station_names, station_codes, unique_codes,
            max_stations=self._MAX_STATIONS,
            alternative_tool="jiangsu_fetch_alarm_records",
        )


_FAULT_ORDER_LIST_FIELDS = (
    "workingOrderCode",
    "uniqueCode",
    "stationCodeStr",
    "stationName",
    "city",
    "deviceId",
    "deviceInfo",
    "deviceCode",
    "operationUnitName",
    "orderTitle",
    "orderContent",
    "orderStatus",
    "orderStatusStr",
    "urgencyType",
    "urgencyTypeStr",
    "workFlowStatus",
    "workFlowStatusStr",
    "currentPointName",
    "currentPointFormCode",
    "createTime",
    "updateTime",
    "finishTime",
    "otherContent",
    "isMakeup",
    "faultProcessType",
    "id",
)


def _compact_fault_order_list_item(item: Any) -> dict[str, Any]:
    """Keep list/review fields while dropping platform UI state and empty placeholders."""
    if not isinstance(item, dict):
        return {}
    compact = {
        field: item[field]
        for field in _FAULT_ORDER_LIST_FIELDS
        if field in item and item[field] not in (None, "", [], {})
    }
    if "stationCodeStr" not in compact:
        station_codes = item.get("stationCodes")
        if isinstance(station_codes, list) and station_codes:
            compact["stationCodeStr"] = str(station_codes[0])
    return compact


def _detail_working_order_code(entry: Any) -> str:
    if not isinstance(entry, dict):
        return ""
    work_order = entry.get("wo") if isinstance(entry.get("wo"), dict) else entry
    return str(work_order.get("workingOrderCode") or "").strip()


_FAULT_ORDER_WORKFLOW_FIELDS = ("name", "description", "type", "status", "version")
_FAULT_ORDER_WORKFLOW_STEP_FIELDS = (
    "guid", "taskName", "description", "formCode", "rank", "roleId", "status", "createTime",
)
_FAULT_ORDER_ATTACHMENT_FIELDS = (
    "id", "workingOrderCode", "functionCode", "typeCode", "fileName", "filePath",
    "remark", "createTime", "updateTime",
)
_FAULT_ORDER_ATTACHMENT_KEYS = {"commonFile", "commonFile1", "commonFile2"}
_FAULT_ORDER_DETAIL_UI_FIELDS = {
    "checkTask", "isEdit", "isFormEdit", "isShow", "isShowModifyRecord",
    "orderDetailDto", "selectDevices", "wflWorkFlowTaskList",
}
_FAULT_ORDER_ATTACHMENT_DOWNLOAD_PATH = "basicinfo/FileCommon/DownFile"
_FAULT_ORDER_ATTACHMENT_MAX_COUNT = 20
_FAULT_ORDER_ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024
_FAULT_ORDER_ATTACHMENT_TOTAL_MAX_BYTES = 100 * 1024 * 1024
_FAULT_ORDER_ATTACHMENT_CONCURRENCY = 4
_FAULT_ORDER_BLOCKED_ATTACHMENT_SUFFIXES = {
    ".asp", ".aspx", ".bat", ".cmd", ".com", ".dll", ".exe", ".msi", ".php", ".ps1", ".sh",
}


def _compact_fields(item: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    return {
        field: item[field]
        for field in fields
        if field in item and item[field] not in (None, "", [], {})
    }


def _prune_empty_detail_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: compact
            for key, item in value.items()
            if key not in _FAULT_ORDER_ATTACHMENT_KEYS
            and key not in _FAULT_ORDER_DETAIL_UI_FIELDS
            and not key.startswith("btn")
            and (compact := _prune_empty_detail_value(item)) not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [
            compact
            for item in value
            if (compact := _prune_empty_detail_value(item)) not in (None, "", [], {})
        ]
    return value


def _extract_fault_order_attachments(detail: dict[str, Any]) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def _walk(value: Any, source: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child_source = f"{source}.{key}" if source else key
                if key in _FAULT_ORDER_ATTACHMENT_KEYS:
                    candidates = item if isinstance(item, list) else [item]
                    for candidate in candidates:
                        compact = _compact_fields(candidate, _FAULT_ORDER_ATTACHMENT_FIELDS)
                        if not compact:
                            continue
                        identity = (
                            str(compact.get("id") or ""),
                            str(compact.get("filePath") or ""),
                            str(compact.get("fileName") or ""),
                        )
                        if identity in seen:
                            continue
                        seen.add(identity)
                        compact["source"] = child_source
                        attachments.append(compact)
                    continue
                if key != "selectDevices":
                    _walk(item, child_source)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                _walk(item, f"{source}[{index}]")

    _walk(detail, "")
    return attachments


def _compact_fault_order_detail(detail: Any) -> tuple[dict[str, Any], dict[str, int]]:
    if not isinstance(detail, dict):
        return {}, {"select_devices_omitted": 0, "attachment_count": 0}

    compact: dict[str, Any] = {}
    work_order = _prune_empty_detail_value(detail.get("wo") or {})
    if work_order:
        compact["wo"] = work_order

    processes = _prune_empty_detail_value(detail.get("details") or [])
    compact["details"] = processes

    for field in ("faultContentItems", "checkItemList"):
        value = _prune_empty_detail_value(detail.get(field) or [])
        if value:
            compact[field] = value
    for field in ("faultDevice", "changeDevice"):
        value = _prune_empty_detail_value(detail.get(field) or {})
        if value:
            compact[field] = value

    workflow = detail.get("workFlowInfo") or {}
    if isinstance(workflow, dict):
        compact_workflow: dict[str, Any] = {}
        workflow_header = _compact_fields(workflow.get("workFlow"), _FAULT_ORDER_WORKFLOW_FIELDS)
        if workflow_header:
            compact_workflow["workFlow"] = workflow_header
        steps = [
            step
            for item in (workflow.get("stepList") or [])
            if (step := _compact_fields(item, _FAULT_ORDER_WORKFLOW_STEP_FIELDS))
        ]
        if steps:
            compact_workflow["stepList"] = steps
        if compact_workflow:
            compact["workFlowInfo"] = compact_workflow

    attachments = _extract_fault_order_attachments(detail)
    if attachments:
        compact["attachments"] = attachments
    selected_devices = detail.get("selectDevices")
    selected_device_count = len(selected_devices) if isinstance(selected_devices, list) else 0
    return compact, {
        "select_devices_omitted": selected_device_count,
        "attachment_count": len(attachments),
    }


def _validated_fault_attachment_path(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or "\x00" in raw or "\\" in raw or "?" in raw or "#" in raw:
        raise ValueError("附件路径无效")
    path = PurePosixPath(raw)
    if not path.is_absolute() or len(path.parts) < 3 or path.parts[1] != "NewFiles":
        raise ValueError("附件不在平台 NewFiles 目录")
    if any(part in {"", ".", ".."} for part in path.parts[1:]):
        raise ValueError("附件路径包含非法目录")
    return raw


def _safe_fault_attachment_name(attachment: dict[str, Any], index: int) -> str:
    raw_name = str(attachment.get("fileName") or "").replace("\x00", "").replace("\\", "/")
    safe_name = Path(raw_name).name.strip()
    remote_suffix = PurePosixPath(str(attachment.get("filePath") or "")).suffix.lower()
    if not safe_name or safe_name in {".", ".."}:
        safe_name = f"attachment-{index + 1}{remote_suffix}"
    safe_name = re.sub(r"[^0-9A-Za-z._()\-\u4e00-\u9fff]+", "_", safe_name).strip("._")
    if not safe_name:
        safe_name = f"attachment-{index + 1}{remote_suffix}"
    suffix = Path(safe_name).suffix.lower() or remote_suffix
    if suffix in _FAULT_ORDER_BLOCKED_ATTACHMENT_SUFFIXES:
        raise ValueError(f"不允许下载可执行附件类型 {suffix}")
    if not Path(safe_name).suffix and remote_suffix:
        safe_name += remote_suffix
    if len(safe_name) <= 180:
        return safe_name
    suffix = Path(safe_name).suffix
    return f"{Path(safe_name).stem[:180 - len(suffix)]}{suffix}"


def _fault_attachment_output_dir(raw_resource_path: str | None, order_code: str) -> Path:
    safe_order_code = re.sub(r"[^0-9A-Za-z_-]+", "_", order_code).strip("_") or "fault-order"
    if raw_resource_path:
        raw_path = resolve_agent_path(raw_resource_path)
        sessions_dir = get_sessions_dir().resolve()
        if not raw_path.is_file() or not is_path_within(raw_path, [sessions_dir]):
            raise ValueError("详单审计资源不在当前会话目录")
        output_dir = (raw_path.parent / "attachments" / safe_order_code).resolve()
        if not is_path_within(output_dir, [raw_path.parent]):
            raise ValueError("附件输出目录无效")
    else:
        output_dir = (get_data_registry() / "work_order_review_attachments" / safe_order_code).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _save_fault_attachment(output_dir: Path, file_name: str, content: bytes, identity: str) -> Path:
    identity_prefix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    target = (output_dir / f"{identity_prefix}-{file_name}").resolve()
    if not is_path_within(target, [output_dir]):
        raise ValueError("附件文件名无效")
    checksum = hashlib.sha256(content).hexdigest()
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == checksum:
        return target
    temporary = target.with_name(f".{target.name}.tmp-{uuid4().hex}")
    try:
        temporary.write_bytes(content)
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


async def _download_fault_order_attachments(
    *,
    api: _JiangsuAuthenticatedApi,
    attachments: list[dict[str, Any]],
    raw_resource_path: str | None,
    order_code: str,
    tool_name: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    if not attachments:
        return attachments, [], {"downloaded": 0, "failed": 0, "skipped": 0, "bytes": 0}

    try:
        output_dir = _fault_attachment_output_dir(raw_resource_path, order_code)
    except (OSError, ValueError) as exc:
        for attachment in attachments:
            attachment["download_status"] = "failed"
            attachment["download_error"] = f"附件会话目录不可用：{str(exc)[:240]}"
        return attachments, [], {"downloaded": 0, "failed": len(attachments), "skipped": 0, "bytes": 0}
    semaphore = asyncio.Semaphore(_FAULT_ORDER_ATTACHMENT_CONCURRENCY)

    async def _fetch(index: int, attachment: dict[str, Any]) -> dict[str, Any]:
        if index >= _FAULT_ORDER_ATTACHMENT_MAX_COUNT:
            return {"status": "skipped", "error": f"附件数量超过 {_FAULT_ORDER_ATTACHMENT_MAX_COUNT} 个限制"}
        try:
            remote_path = _validated_fault_attachment_path(attachment.get("filePath"))
            file_name = _safe_fault_attachment_name(attachment, index)
            async with semaphore:
                content, content_type = await api.download_file(
                    _FAULT_ORDER_ATTACHMENT_DOWNLOAD_PATH,
                    [("filePath", remote_path)],
                    max_bytes=_FAULT_ORDER_ATTACHMENT_MAX_BYTES,
                )
            return {
                "status": "downloaded",
                "content": content,
                "content_type": content_type,
                "file_name": file_name,
                "remote_path": remote_path,
            }
        except (ValueError, httpx.HTTPError) as exc:
            return {"status": "failed", "error": str(exc)[:300]}
        except Exception as exc:
            logger.warning(
                "jiangsu_fault_attachment_download_failed",
                working_order_code=order_code,
                attachment_index=index,
                error=str(exc),
            )
            return {"status": "failed", "error": str(exc)[:300]}

    resources: list[dict[str, Any]] = []
    downloaded = failed = skipped = total_bytes = 0
    for batch_start in range(0, len(attachments), _FAULT_ORDER_ATTACHMENT_CONCURRENCY):
        batch = attachments[batch_start:batch_start + _FAULT_ORDER_ATTACHMENT_CONCURRENCY]
        if total_bytes >= _FAULT_ORDER_ATTACHMENT_TOTAL_MAX_BYTES:
            for attachment in batch:
                skipped += 1
                attachment["download_status"] = "skipped"
                attachment["download_error"] = "附件总大小超过 100MB 限制"
            continue
        fetched = await asyncio.gather(*(
            _fetch(batch_start + offset, attachment)
            for offset, attachment in enumerate(batch)
        ))
        for offset, (attachment, result) in enumerate(zip(batch, fetched, strict=True)):
            index = batch_start + offset
            status = result["status"]
            if status == "skipped":
                skipped += 1
                attachment["download_status"] = "skipped"
                attachment["download_error"] = result["error"]
                continue
            if status == "failed":
                failed += 1
                attachment["download_status"] = "failed"
                attachment["download_error"] = result["error"]
                continue

            content = result["content"]
            if total_bytes + len(content) > _FAULT_ORDER_ATTACHMENT_TOTAL_MAX_BYTES:
                skipped += 1
                attachment["download_status"] = "skipped"
                attachment["download_error"] = "附件总大小超过 100MB 限制"
                continue
            identity = str(attachment.get("id") or result["remote_path"] or index)
            try:
                saved_path = _save_fault_attachment(output_dir, result["file_name"], content, identity)
            except (OSError, ValueError) as exc:
                failed += 1
                attachment["download_status"] = "failed"
                attachment["download_error"] = f"保存附件失败：{str(exc)[:240]}"
                continue
            checksum = hashlib.sha256(content).hexdigest()
            total_bytes += len(content)
            downloaded += 1
            attachment.update({
                "download_status": "success",
                "local_path": format_agent_path(saved_path),
                "content_type": result["content_type"],
                "size_bytes": len(content),
                "sha256": checksum,
            })
            resources.append(single_file_product(
                saved_path,
                tool_name=tool_name,
                role="attachment",
                label=str(attachment.get("fileName") or result["file_name"]),
                logical_key=(
                    f"jiangsu-fault-attachment:{order_code}:"
                    f"{hashlib.sha256(identity.encode()).hexdigest()[:16]}"
                ),
                metadata={
                    "working_order_code": order_code,
                    "attachment_id": attachment.get("id"),
                    "source": attachment.get("source"),
                    "size_bytes": len(content),
                    "sha256": checksum,
                },
            ))
    return attachments, resources, {
        "downloaded": downloaded,
        "failed": failed,
        "skipped": skipped,
        "bytes": total_bytes,
    }


class JiangsuFaultWorkOrdersTool(LLMTool):
    _PATH = "operation/FaultOrder/GetWorkingOrderInfoByUniqueCode"
    # Station-free filtered listing, mirroring the platform's FaultOrder page
    # (front FaultHandling.vue): order code, creation time, workflow node,
    # node status and order status are all optional server-side filters.
    _LIST_PATH = "operation/WorkingOrder/GetMtcWorkingOrderPagedListAsync"
    _WORKFLOW_PATH = "operation/WflWorkFlow/GetWorkFlowByUser"
    _STATION_DIRECTORY_PATH = "AirCityProductBase/GetAllEnabledBSDStationAsync"
    # Per-station serial calls need ~1.3s each upstream; a city-wide sweep
    # (Nanjing: 121 stations) would take minutes.  Geographic fan-out is
    # therefore rejected in favour of directly addressed concurrent queries.
    _MAX_STATIONS = 10
    _MAX_FETCH_ALL_RECORDS = 1000
    _WORKFLOW_STATUS_LABELS = {"待分配": "ToAssign", "待领取": "ToAccept", "处理中": "Doing",
                               "已完成": "Finish", "已拒绝": "Reject"}
    _ORDER_STATUS_LABELS = {"待处理": "Wait", "处理中": "Doing", "已完成": "Finish", "已作废": "Invalid"}
    # Platform defaults for the fault-order list page: in-flight workflow
    # nodes plus all not-invalidated order states.
    _DEFAULT_WORKFLOW_STATUSES = ["ToAssign", "ToAccept", "Doing"]
    _DEFAULT_ORDER_STATUSES = ["Wait", "Doing", "Finish"]

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_fault_work_orders",
            description="查询江苏故障工单清单：按工单号、创建时间、工单节点和状态筛选时，默认在一次工具调用内取齐匹配清单；超过 24 条时完整清单外部化保存、上下文返回 24 条首尾预览。也可仅按明确站点读取最近工单与历史处置详情。具体工单复核请继续调用 jiangsu_fetch_fault_work_order_detail。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_fault_work_orders", "description": "查询故障工单清单。默认 fetch_all=true，由工具内部完成分页并一次返回完整匹配范围；超过 24 条自动保存完整数据文件并内联首尾 24 条。仅当用户明确要求浏览某一页时才设置 fetch_all=false。",
                             "parameters": {"type": "object", "properties": {
                                 "station_names": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                                    "description": "站点名称列表，最多 10 个；与其他筛选条件组合时作为站点过滤。"},
                                 "station_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                                    "description": "平台站点编码列表，例如 [\"5006A\"]，最多 10 个。"},
                                 "unique_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                                    "description": "平台唯一编码列表；已知时可直接使用，最多 10 个。"},
                                 "take": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5,
                                           "description": "仅按站点查询时每站返回的最近工单条数。"},
                                 "working_order_code": {"type": "string",
                                                         "description": "工单号，模糊匹配，如 \"GD20260801001\"。"},
                                 "start_time": {"type": "string", "description": "创建时间起，YYYY-MM-DD HH:mm:ss。"},
                                 "end_time": {"type": "string", "description": "创建时间止，YYYY-MM-DD HH:mm:ss。"},
                                 "current_points": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                                                     "description": "工单节点名称列表，如 [\"故障处理\"]；也可传节点 guid。"},
                                 "workflow_statuses": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                                                        "description": "节点状态：ToAssign 待分配、ToAccept 待领取、Doing 处理中、Finish 已完成、Reject 已拒绝；也接受中文。默认 [\"ToAssign\",\"ToAccept\",\"Doing\"]。"},
                                 "order_statuses": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                                                     "description": "工单状态：Wait 待处理、Doing 处理中、Finish 已完成、Invalid 已作废；也接受中文。默认 [\"Wait\",\"Doing\",\"Finish\"]。"},
                                 "fetch_all": {"type": "boolean", "default": True,
                                                 "description": "默认 true：工具内部取齐匹配清单，禁止 Agent 自行逐页重复调用。仅在用户明确要求某页时设为 false。"},
                                 "page": {"type": "integer", "minimum": 1, "default": 1,
                                          "description": "仅 fetch_all=false 时生效，页码从 1 开始。"},
                                 "page_size": {"type": "integer", "minimum": 1, "maximum": 50, "default": 50,
                                                "description": "内部分页或显式分页的每页条数，最大 50。"},
                             }, "required": []}},
            requires_context=True,
        )

    async def execute(self, context=None, station_names: list[str] | None = None,
                      station_codes: list[str] | None = None, unique_codes: list[str] | None = None,
                      take: int = 5, working_order_code: str | None = None,
                      start_time: str | None = None, end_time: str | None = None,
                      current_points: list[str] | None = None,
                      workflow_statuses: list[str] | None = None,
                      order_statuses: list[str] | None = None,
                      fetch_all: bool = True,
                      page: int = 1, page_size: int = 50, **_: Any) -> dict[str, Any]:
        try:
            if not isinstance(take, int) or not 1 <= take <= 20:
                raise ValueError("take 必须为 1–20 的整数")
            if _.get("city_name") or _.get("district_name"):
                raise ValueError("不支持城市/区县批量：请直接指定站点（station_names/station_codes/unique_codes），"
                                 "或改用工单号、状态、时间等条件筛选工单列表")
            def _nonempty(values: list[str] | None) -> bool:
                return any(isinstance(value, str) and value.strip() for value in (values or []))

            stations_given = _nonempty(station_names) or _nonempty(station_codes) or _nonempty(unique_codes)
            points = current_points if isinstance(current_points, list) else None
            filters_given = bool(working_order_code or start_time or end_time
                                 or (points is not None and len(points) > 0)
                                 or workflow_statuses is not None or order_statuses is not None)
            if not stations_given or filters_given:
                return await self._execute_filtered(
                    context,
                    station_names, station_codes, unique_codes,
                    working_order_code=working_order_code, start_time=start_time, end_time=end_time,
                    current_points=points, workflow_statuses=workflow_statuses,
                    order_statuses=order_statuses, fetch_all=fetch_all,
                    page=page, page_size=page_size,
                )
            stations = await _resolve_direct_station_scope(
                station_names, station_codes, unique_codes,
                max_stations=self._MAX_STATIONS, require_unique_code=True,
            )
            api = _JiangsuAuthenticatedApi(source="ops")
            results = list(await asyncio.gather(
                *(self._fetch_orders(api, station, take) for station in stations)
            ))
            orders = [order for item in results for order in item["orders"]]
            failed_count = sum(1 for item in results if not item["success"])
            success = failed_count < len(stations)
            summary = f"故障工单查询完成：并发查询 {len(stations)} 个站点，返回 {len(orders)} 条记录"
            if failed_count:
                summary += f"，{failed_count} 个站点查询失败"
            return {"status": "success" if success and orders else ("empty" if success else "failed"),
                    "success": success, "data": orders,
                    "metadata": {"source": "jiangsu_operations_api", "endpoint": self._PATH,
                                 "query_mode": "per_station",
                                 "station_count": len(stations), "failed_station_count": failed_count,
                                 "record_count": len(orders), "queried_at": datetime.now().astimezone().isoformat()},
                    "summary": summary + "。"}
        except (ValueError, httpx.HTTPError) as exc:
            return {"status": "failed", "success": False, "data": [], "summary": f"故障工单查询失败：{exc}"}

    async def _execute_filtered(
        self,
        context: Any,
        station_names: list[str] | None,
        station_codes: list[str] | None,
        unique_codes: list[str] | None,
        *,
        working_order_code: str | None,
        start_time: str | None,
        end_time: str | None,
        current_points: list[str] | None,
        workflow_statuses: list[str] | None,
        order_statuses: list[str] | None,
        fetch_all: bool,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """List fault orders through the platform's filtered paged endpoint."""
        try:
            page, page_size = int(page or 1), int(page_size or 50)
            if page < 1 or not 1 <= page_size <= 50:
                raise ValueError("page 必须从 1 开始，page_size 必须为 1–50 的整数")
            if not isinstance(fetch_all, bool):
                raise ValueError("fetch_all 必须为布尔值")
            order_code = str(working_order_code or "").strip()
            if len(order_code) > 64:
                raise ValueError("working_order_code 过长")
            filter_params: list[tuple[str, str]] = []
            if order_code:
                filter_params.append(("WorkingOrderCode", order_code))
            time_range: list[str] = []
            if start_time or end_time:
                start = _parse_iso_time(start_time, "start_time") if start_time else datetime(2000, 1, 1)
                end = _parse_iso_time(end_time, "end_time") if end_time else datetime.now()
                if start > end:
                    raise ValueError("开始时间不能晚于结束时间")
                time_range = [start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")]
                filter_params += [("CreateTime", time_range[0]), ("CreateTime", time_range[1])]
            point_guids: list[str] = []
            if current_points:
                point_guids = await self._resolve_point_guids(current_points)
                filter_params += [("CurrentPoint", guid) for guid in point_guids]
            workflow_values, workflow_default = self._normalise_status_values(
                workflow_statuses, self._WORKFLOW_STATUS_LABELS,
                self._DEFAULT_WORKFLOW_STATUSES, "workflow_statuses",
            )
            order_values, order_default = self._normalise_status_values(
                order_statuses, self._ORDER_STATUS_LABELS,
                self._DEFAULT_ORDER_STATUSES, "order_statuses",
            )
            filter_params += [("WorkFlowStatus", value) for value in workflow_values]
            filter_params += [("OrderStatus", value) for value in order_values]
            station_filter_codes: list[str] = []
            if station_names or station_codes or unique_codes:
                stations = await _resolve_direct_station_scope(
                    station_names, station_codes, unique_codes, max_stations=self._MAX_STATIONS,
                )
                station_filter_codes = [station["station_code"] for station in stations]
                filter_params += [("StationCode", code) for code in station_filter_codes]

            api = _JiangsuAuthenticatedApi(source="ops")
            request_page = 1 if fetch_all else page
            request_page_size = 50 if fetch_all else page_size
            payload = await self._fetch_filtered_page(
                api, filter_params, page=request_page, page_size=request_page_size,
            )
            result = payload.get("result") or {}
            if not isinstance(result, dict):
                raise ValueError("故障工单列表接口 result 无效")
            items = result.get("items") or []
            total_count = result.get("totalCount", len(items))
            if not isinstance(items, list):
                raise ValueError("故障工单列表接口 items 无效")
            try:
                total_count = max(int(total_count), len(items))
            except (TypeError, ValueError):
                total_count = len(items)

            source_data_complete = (
                (request_page - 1) * request_page_size + len(items) >= total_count
            )
            fetch_limit = min(total_count, self._MAX_FETCH_ALL_RECORDS)
            if fetch_all and len(items) < fetch_limit:
                page_count = (fetch_limit + request_page_size - 1) // request_page_size
                remaining = await asyncio.gather(*(
                    self._fetch_filtered_page(
                        api, filter_params, page=page_number, page_size=request_page_size,
                    )
                    for page_number in range(2, page_count + 1)
                ))
                for page_payload in remaining:
                    page_result = page_payload.get("result") or {}
                    page_items = page_result.get("items") or []
                    if not isinstance(page_items, list):
                        raise ValueError("故障工单列表接口分页 items 无效")
                    items.extend(page_items)
                items = items[:fetch_limit]
                source_data_complete = len(items) >= total_count

            compact_items = [
                compact
                for compact in (_compact_fault_order_list_item(item) for item in items)
                if compact
            ]
            inline_items, file_path, externalization = externalize_compact_records(
                compact_items,
                context=context,
                schema="jiangsu_fault_work_order_list",
                metadata={
                    "source_tool": self.name,
                    "source_endpoint": self._LIST_PATH,
                    "total_count": total_count,
                    "source_data_complete": source_data_complete,
                },
            )
            defaults_applied = workflow_default or order_default
            summary = f"故障工单查询完成：按条件筛选获取 {len(compact_items)} 条记录（共匹配 {total_count} 条）"
            if file_path:
                summary += "；完整清单已外部化保存，当前内联首尾 24 条预览"
            if fetch_all and not source_data_complete:
                summary += f"；匹配量超过单次完整抓取上限 {self._MAX_FETCH_ALL_RECORDS} 条，当前数据不完整"
            if defaults_applied:
                summary += "；默认状态筛选：节点状态 待分配/待领取/处理中，工单状态 待处理/处理中/已完成，传空数组可清除"
            metadata = {"source": "jiangsu_operations_api", "endpoint": self._LIST_PATH,
                        "query_mode": "filtered",
                        "filters": {"working_order_code": order_code or None,
                                    "create_time": time_range or None,
                                    "current_points": current_points or [],
                                    "workflow_statuses": workflow_values,
                                    "order_statuses": order_values,
                                    "station_codes": station_filter_codes},
                        "defaults_applied": defaults_applied,
                        "record_count": len(compact_items), "total_count": total_count,
                        "returned_records": len(inline_items),
                        "fetch_all": fetch_all, "source_data_complete": source_data_complete,
                        "page": request_page, "page_size": request_page_size,
                        "context_data": externalization,
                        "queried_at": datetime.now().astimezone().isoformat()}
            return {"status": "success" if compact_items else "empty", "success": True, "data": inline_items,
                    "metadata": metadata,
                    "summary": summary + ".",
                    **{key: externalization[key] for key in (
                        "data_complete", "record_count", "returned_records", "sample_strategy"
                    )},
                    **({"file_path": file_path} if file_path else {})}
        except (ValueError, httpx.HTTPError) as exc:
            return {"status": "failed", "success": False, "data": [], "summary": f"故障工单查询失败：{exc}"}

    async def _fetch_filtered_page(
        self,
        api: _JiangsuAuthenticatedApi,
        filter_params: list[tuple[str, str]],
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        params = [
            ("OrderType", "Fault"),
            ("MaxResultCount", str(page_size)),
            ("SkipCount", str((page - 1) * page_size)),
            *filter_params,
        ]
        return await api.get(self._LIST_PATH, params)

    def _normalise_status_values(
        self,
        values: list[str] | None,
        labels: dict[str, str],
        defaults: list[str],
        name: str,
    ) -> tuple[list[str], bool]:
        """Map labels to enum values; None applies the platform defaults."""
        if values is None:
            return list(defaults), True
        if not isinstance(values, list):
            raise ValueError(f"{name} 必须是字符串数组")
        allowed = set(labels.values())
        resolved: list[str] = []
        for raw in values:
            token = str(raw or "").strip()
            value = labels.get(token, token)
            if value not in allowed:
                options = "、".join(f"{v}({k})" for k, v in labels.items())
                raise ValueError(f"{name} 含无效值“{token}”；可选：{options}")
            if value not in resolved:
                resolved.append(value)
        return resolved, False

    async def _resolve_point_guids(self, names: list[str]) -> list[str]:
        """Resolve workflow node names (or guids) against the Fault workflow."""
        payload = await _JiangsuAuthenticatedApi(source="ops").get(self._WORKFLOW_PATH, [("Type", "Fault")])
        result = payload.get("result") or {}
        steps = result.get("stepList") or []
        if not isinstance(steps, list) or not steps:
            raise ValueError("未获取到故障工单流程节点")
        by_name: dict[str, str] = {}
        guids: set[str] = set()
        for step in steps:
            if not isinstance(step, dict):
                continue
            guid = str(step.get("guid") or "").strip()
            task_name = str(step.get("taskName") or "").strip()
            if not guid:
                continue
            guids.add(guid)
            if task_name:
                by_name.setdefault(task_name, guid)
        resolved: list[str] = []
        for raw in names:
            token = str(raw or "").strip()
            if not token:
                continue
            guid = token if token in guids else by_name.get(token)
            if not guid:
                available = "、".join(by_name) or "、".join(sorted(guids))
                raise ValueError(f"未知工单节点“{token}”；可用节点：{available}")
            if guid not in resolved:
                resolved.append(guid)
        return resolved

    async def _fetch_orders(self, api: _JiangsuAuthenticatedApi, station: dict[str, str], take: int) -> dict[str, Any]:
        try:
            payload = await api.get(self._PATH, [("uniqueCode", station["unique_code"]), ("take", str(take))])
            station_orders = payload.get("result") or []
            if not isinstance(station_orders, list):
                raise ValueError("故障工单接口 result 无效")
            return {"orders": station_orders, "success": True, "station": station}
        except (ValueError, httpx.HTTPError) as exc:
            return {"orders": [], "success": False, "station": station, "error": str(exc)}

    @staticmethod
    async def _resolve_stations_by_place(station_name: str | None, city_name: str | None,
                                         district_name: str | None) -> list[dict[str, str]]:
        """Resolve the platform-only uniqueCode without exposing it to the Agent."""
        payload = await _JiangsuAuthenticatedApi(source="air").get(
            JiangsuFaultWorkOrdersTool._STATION_DIRECTORY_PATH, []
        )
        rows = payload.get("result") or []
        if not isinstance(rows, list):
            raise ValueError("江苏站点目录返回格式异常")
        matches = [row for row in rows if isinstance(row, dict)
            and (not station_name or _normalise_place_name(row.get("positionName") or row.get("stationName")) == _normalise_place_name(station_name))
            # The directory is provincial: a city selector matches cityName,
            # while a province selector (for example "江苏省") is exposed as
            # provinceName on the same rows.
            and (not city_name or _normalise_place_name(row.get("cityName")) == _normalise_place_name(city_name)
                 or _normalise_place_name(row.get("provinceName")) == _normalise_place_name(city_name))
            and (not district_name or _normalise_place_name(row.get("districtName")) == _normalise_place_name(district_name))
        ]
        if not matches:
            location = "-".join(part for part in (city_name, district_name, station_name) if part)
            raise ValueError(f"未在江苏站点目录中找到“{location}”")
        resolved = []
        for row in matches:
            unique_code = row.get("uniqueCode") or row.get("UniqueCode")
            if isinstance(unique_code, str) and unique_code.strip():
                resolved.append({"unique_code": unique_code.strip(), "station_code": str(row.get("stationCode") or row.get("StationCode") or "").strip(),
                                 "station_name": row.get("positionName") or row.get("stationName"), "city_name": row.get("cityName"), "district_name": row.get("districtName")})
        if not resolved:
            raise ValueError("匹配站点缺少江苏平台唯一编码")
        return resolved


class JiangsuFaultWorkOrderDetailTool(LLMTool):
    """Resolve one exact fault-order code and return its full platform detail."""

    _LIST_PATH = JiangsuFaultWorkOrdersTool._LIST_PATH
    _DETAIL_PATH = JiangsuFaultWorkOrdersTool._PATH
    _DETAIL_TAKE = 20

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_fault_work_order_detail",
            description=(
                "按完整故障工单号查询江苏运维平台详单。先用清单接口精确定位工单所属站点，"
                "再读取该站点最近详单并按工单号精确匹配。直接返回适合审核上下文的工单、"
                "处置记录、故障/检查项、当前设备和关键流程；同步下载附件并保存为会话资源，"
                "完整接口原文另存审计资源。"
            ),
            category=ToolCategory.QUERY,
            function_schema={
                "name": "jiangsu_fetch_fault_work_order_detail",
                "description": "按一个完整 working_order_code 获取对应故障工单详单；不得用清单记录替代详单。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "working_order_code": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 64,
                            "description": "完整故障工单号，例如 FA260824178755355757547。",
                        },
                    },
                    "required": ["working_order_code"],
                },
            },
            requires_context=True,
        )

    async def execute(self, context=None, working_order_code: str | None = None, **_: Any) -> dict[str, Any]:
        try:
            order_code = str(working_order_code or "").strip()
            if not order_code:
                raise ValueError("working_order_code 不能为空")
            if len(order_code) > 64:
                raise ValueError("working_order_code 过长")

            api = _JiangsuAuthenticatedApi(source="ops")
            list_payload = await api.get(self._LIST_PATH, [
                ("OrderType", "Fault"),
                ("MaxResultCount", "50"),
                ("SkipCount", "0"),
                ("WorkingOrderCode", order_code),
            ])
            list_result = list_payload.get("result") or {}
            list_items = list_result.get("items") or []
            if not isinstance(list_items, list):
                raise ValueError("故障工单定位接口 items 无效")
            exact = [
                item for item in list_items
                if isinstance(item, dict)
                and str(item.get("workingOrderCode") or "").strip().casefold() == order_code.casefold()
            ]
            if not exact:
                return {"status": "empty", "success": True, "data": [],
                        "metadata": {"source": "jiangsu_operations_api", "query_mode": "detail_by_code",
                                     "working_order_code": order_code, "record_count": 0},
                        "summary": f"未找到与工单号 {order_code} 完全匹配的故障工单。"}

            unique_code = str(exact[0].get("uniqueCode") or "").strip()
            if not unique_code:
                raise ValueError(f"工单 {order_code} 缺少站点唯一编码，无法读取详单")
            detail_payload = await api.get(self._DETAIL_PATH, [
                ("uniqueCode", unique_code),
                ("take", str(self._DETAIL_TAKE)),
            ])
            detail_items = detail_payload.get("result") or []
            if not isinstance(detail_items, list):
                raise ValueError("故障工单详单接口 result 无效")
            matches = [
                entry for entry in detail_items
                if _detail_working_order_code(entry).casefold() == order_code.casefold()
            ]
            if not matches:
                return {"status": "failed", "success": False, "data": [],
                        "metadata": {"source": "jiangsu_operations_api", "query_mode": "detail_by_code",
                                     "working_order_code": order_code, "unique_code": unique_code,
                                     "detail_candidates": len(detail_items), "record_count": 0},
                        "summary": (
                            f"已定位工单 {order_code}，但站点最近 {self._DETAIL_TAKE} 条详单中未找到完全匹配记录；"
                            "未使用其他工单替代。"
                        )}

            detail = matches[0]
            compact_detail, projection = _compact_fault_order_detail(detail)
            if not compact_detail:
                raise ValueError("故障工单详单内容无效")
            process_count = len(compact_detail.get("details") or [])
            file_path = None
            if context is not None and hasattr(context, "save_data"):
                file_path = context.save_data(
                    data=[detail],
                    schema="jiangsu_fault_work_order_detail_raw",
                    metadata={
                        "source_tool": self.name,
                        "source_endpoint": self._DETAIL_PATH,
                        "working_order_code": order_code,
                        "unique_code": unique_code,
                        "record_count": 1,
                        "root_type": "array",
                        "payload_role": "raw_audit_copy",
                    },
                )
            attachment_resources: list[dict[str, Any]] = []
            attachment_download = {"downloaded": 0, "failed": 0, "skipped": 0, "bytes": 0}
            attachments = compact_detail.get("attachments") or []
            if isinstance(attachments, list):
                attachments, attachment_resources, attachment_download = await _download_fault_order_attachments(
                    api=api,
                    attachments=attachments,
                    raw_resource_path=file_path,
                    order_code=order_code,
                    tool_name=self.name,
                )
                if attachments:
                    compact_detail["attachments"] = attachments
            return {"status": "success", "success": True, "data": [compact_detail],
                    "metadata": {"source": "jiangsu_operations_api",
                                 "endpoints": {"locator": self._LIST_PATH, "detail": self._DETAIL_PATH},
                                 "query_mode": "detail_by_code", "working_order_code": order_code,
                                 "unique_code": unique_code, "record_count": 1,
                                 "process_record_count": process_count,
                                 "inline_projection": "fault_order_review_v1",
                                 "raw_resource_saved": bool(file_path),
                                 "attachments_downloaded": attachment_download["downloaded"],
                                 "attachments_failed": attachment_download["failed"],
                                 "attachments_skipped": attachment_download["skipped"],
                                 "attachment_bytes": attachment_download["bytes"],
                                 **projection,
                                 "queried_at": datetime.now().astimezone().isoformat()},
                    "summary": (
                        f"故障工单 {order_code} 详单查询完成，直接返回审核详单和 {process_count} 条处置/流转记录"
                        f"；已剔除 {projection['select_devices_omitted']} 条页面设备候选项"
                        f"；附件下载 {attachment_download['downloaded']} 个、失败 {attachment_download['failed']} 个"
                        f"、跳过 {attachment_download['skipped']} 个"
                        + ("，完整接口原文已保存为审计资源。" if file_path else "。")
                    ),
                    **({"resources": attachment_resources} if attachment_resources else {}),
                    **({"file_path": file_path} if file_path else {})}
        except (ValueError, httpx.HTTPError) as exc:
            return {"status": "failed", "success": False, "data": [],
                    "summary": f"故障工单详单查询失败：{exc}"}

async def _resolve_station_rows(
    station_name: str | None,
    city_name: str | None,
    district_name: str | None,
    *,
    station_code: str | None = None,
    station_codes: list[str] | None = None,
    unique_code: str | None = None,
    unique_codes: list[str] | None = None,
) -> list[dict[str, str]]:
    """Resolve the common station scope used by inspection tools.

    The current deployment intentionally uses the enabled station directory
    without applying role filtering.  Callers can therefore address one
    station, a city/district, or a list of platform station codes.
    """
    station_code_values = [value.strip() for value in (station_codes or []) if isinstance(value, str) and value.strip()]
    if station_code:
        station_code_values.append(_identifier(station_code, "station_code"))
    unique_code_values = [value.strip() for value in (unique_codes or []) if isinstance(value, str) and value.strip()]
    if unique_code:
        unique_code_values.append(_identifier(unique_code, "unique_code"))
    if station_code_values or unique_code_values:
        payload = await _JiangsuAuthenticatedApi(source="air").get(
            JiangsuFaultWorkOrdersTool._STATION_DIRECTORY_PATH, []
        )
        rows = payload.get("result") or []
        if not isinstance(rows, list):
            raise ValueError("江苏站点目录返回格式异常")
        station_set = set(station_code_values)
        unique_set = set(unique_code_values)
        matches = [
            row for row in rows
            if isinstance(row, dict)
            and (not station_set or str(row.get("stationCode") or row.get("StationCode") or "").strip() in station_set)
            and (not unique_set or str(row.get("uniqueCode") or row.get("UniqueCode") or "").strip() in unique_set)
        ]
        if not matches:
            requested = ",".join(station_code_values or unique_code_values)
            raise ValueError(f"未在江苏站点目录中找到“{requested}”")
        return _normalise_station_rows(matches)
    return await JiangsuFaultWorkOrdersTool._resolve_stations_by_place(
        _optional_identifier(station_name, "station_name"),
        _optional_identifier(city_name, "city_name"),
        _optional_identifier(district_name, "district_name"),
    )


async def _resolve_direct_station_scope(
    station_names: list[str] | None,
    station_codes: list[str] | None,
    unique_codes: list[str] | None,
    *,
    max_stations: int,
    require_unique_code: bool = False,
    alternative_tool: str | None = None,
) -> list[dict[str, str]]:
    """Resolve a directly addressed station list for concurrent per-station APIs.

    Geographic fan-out (province/city/district) is rejected: upstream
    per-station calls need 1–2s each, a city-wide sweep takes minutes, and
    the platform starts timing out beyond ~20 concurrent requests.  Callers
    must address their stations explicitly.
    """
    names = _clean_identifier_list(station_names, "station_names")
    codes = _clean_identifier_list(station_codes, "station_codes")
    uniques = _clean_identifier_list(unique_codes, "unique_codes")
    if not names and not codes and not uniques:
        hint = f"；城市/区县整体情况请改用 {alternative_tool}" if alternative_tool else ""
        raise ValueError(f"必须直接指定站点：提供 station_names、station_codes 或 unique_codes（不支持城市/区县批量）{hint}")
    if len(names) + len(codes) + len(uniques) > max_stations:
        raise ValueError(f"一次最多并发查询 {max_stations} 个站点（不支持城市/区县批量）")
    if codes and not names and not uniques and not require_unique_code:
        # These endpoints key on the platform station code alone, so the
        # provincial directory round-trip is skipped.
        direct: dict[str, dict[str, str]] = {}
        for code in codes:
            direct.setdefault(code, {"station_code": code, "unique_code": "", "station_name": ""})
        return list(direct.values())
    resolved: list[dict[str, str]] = []
    if codes or uniques:
        resolved.extend(await _resolve_station_rows(None, None, None, station_codes=codes, unique_codes=uniques))
    for name in names:
        resolved.extend(await _resolve_station_rows(name, None, None))
    deduped: dict[str, dict[str, str]] = {}
    for station in resolved:
        deduped.setdefault(station["station_code"], station)
    stations = list(deduped.values())
    if not stations:
        raise ValueError("未解析到任何有效站点")
    if len(stations) > max_stations:
        raise ValueError(f"解析得到 {len(stations)} 个站点（可能存在重名站点），超出单次查询上限 {max_stations}；请缩小范围后重试")
    return stations


def _normalise_station_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    resolved: list[dict[str, str]] = []
    for row in rows:
        unique_code = row.get("uniqueCode") or row.get("UniqueCode")
        station_code = row.get("stationCode") or row.get("StationCode")
        if not str(unique_code or "").strip() or not str(station_code or "").strip():
            continue
        resolved.append({
            "unique_code": str(unique_code).strip(),
            "station_code": str(station_code).strip(),
            "station_name": str(row.get("positionName") or row.get("stationName") or "").strip(),
            "city_name": str(row.get("cityName") or "").strip(),
            "district_name": str(row.get("districtName") or "").strip(),
        })
    if not resolved:
        raise ValueError("匹配站点缺少江苏平台编码")
    return resolved


class JiangsuAutoInspectionTool(LLMTool):
    _METHOD = "GetAutoInspection"
    _PROXY_PATH = "stationintegrate/OnlineQC/QcSvcAgent"
    # Each GetAutoInspection call takes seconds upstream, so the batch is
    # queried concurrently and hard-capped.  City/district fan-out is
    # intentionally NOT supported: returning only part of a city's stations
    # invites misreading, and whole-network overviews have a dedicated
    # summary tool.
    _MAX_STATIONS = 10

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_auto_inspection",
            description="读取江苏站点自动巡检快照并按平台规则计算异常分类、状态统计和评分；只支持直接指定站点（名称/平台编码/唯一编码，最多 10 个，并发巡检）；单站成功时返回站房可视化资源。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_auto_inspection", "description": "按站点名称、平台站点编码或唯一编码查询自动巡检快照，可一次并发巡检至多 10 个指定站点。不支持城市/区县批量；需要城市级整体巡检总览时改用 jiangsu_fetch_network_inspection_summary。",
                             "parameters": {"type": "object", "properties": {
                                 "station_names": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                                    "description": "站点名称列表，最多 10 个。"},
                                 "station_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                                    "description": "平台站点编码列表，例如 [\"5006A\"]，最多 10 个。"},
                                 "unique_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                                    "description": "平台唯一编码列表；已知时可直接使用，最多 10 个。"},
                             }, "required": []}},
        )

    async def execute(self, context=None, station_names: list[str] | None = None,
                      station_codes: list[str] | None = None, unique_codes: list[str] | None = None,
                      **_: Any) -> dict[str, Any]:
        try:
            stations = await self._resolve_stations(station_names, station_codes, unique_codes)
            results = list(await asyncio.gather(
                *(self._inspect_station(station, single=(len(stations) == 1)) for station in stations)
            ))
            success = any(item["success"] for item in results)
            for item in results:
                item["issue_count"] = len(item.get("issues", []))
                item["inspection_metrics"] = _inspection_metrics(item.get("data", {}), item.get("issues", []))
            issue_count = sum(item["issue_count"] for item in results)
            visuals = []
            if len(results) == 1 and results[0].get("success"):
                visual = _stationhouse_visual(
                    results[0]["station"],
                    results[0].get("data", {}),
                    results[0].get("issues", []),
                    results[0].get("inspection_metrics", {}),
                )
                visuals.append(visual)
            return {"status": "success" if success else "empty",
                    "success": success, "data": results,
                    "metadata": {"source": "jiangsu_qc_api", "method": self._METHOD, "station_count": len(stations),
                                 "station_limit": self._MAX_STATIONS,
                                 "issue_count": issue_count, "queried_at": datetime.now().astimezone().isoformat(),
                                 "visual_behavior": "stationhouse_effect" if visuals else "none"},
                    **({"visuals": visuals, "resources": resources_for_visuals(visuals, tool_name=self.name)} if visuals else {}),
                    "summary": f"自动巡检查询完成：并发巡检 {len(stations)} 个站点，识别 {issue_count} 项异常。"}
        except (ValueError, httpx.HTTPError) as exc:
            return {"status": "failed", "success": False, "data": {}, "summary": f"自动巡检查询失败：{exc}"}

    async def _resolve_stations(
        self,
        station_names: list[str] | None,
        station_codes: list[str] | None,
        unique_codes: list[str] | None,
    ) -> list[dict[str, str]]:
        names = _clean_identifier_list(station_names, "station_names")
        codes = _clean_identifier_list(station_codes, "station_codes")
        uniques = _clean_identifier_list(unique_codes, "unique_codes")
        if not names and not codes and not uniques:
            raise ValueError(
                "必须直接指定站点：提供 station_names、station_codes 或 unique_codes（不支持城市/区县批量）；"
                "城市/区县整体巡检请改用 jiangsu_fetch_network_inspection_summary"
            )
        if len(names) + len(codes) + len(uniques) > self._MAX_STATIONS:
            raise ValueError(f"一次最多并发巡检 {self._MAX_STATIONS} 个站点；城市/区县整体情况请改用 jiangsu_fetch_network_inspection_summary")
        resolved: list[dict[str, str]] = []
        if codes or uniques:
            resolved.extend(await _resolve_station_rows(None, None, None, station_codes=codes, unique_codes=uniques))
        for name in names:
            resolved.extend(await _resolve_station_rows(name, None, None))
        deduped: dict[str, dict[str, str]] = {}
        for station in resolved:
            deduped.setdefault(station["station_code"], station)
        stations = list(deduped.values())
        if not stations:
            raise ValueError("未解析到任何有效站点")
        if len(stations) > self._MAX_STATIONS:
            raise ValueError(f"解析得到 {len(stations)} 个站点（可能存在重名站点），超出单次巡检上限 {self._MAX_STATIONS}；请缩小范围后重试")
        return stations

    async def _inspect_station(self, station: dict[str, str], *, single: bool) -> dict[str, Any]:
        try:
            payload = await _JiangsuAuthenticatedApi(source="air").post(
                self._PROXY_PATH,
                {"url": "/QCAPI/GetAutoInspection", "apiMethod": self._METHOD,
                 "data": f"StationId={station['unique_code']}&userName=admin&timestamp={int(datetime.now().timestamp() * 1000)}"},
            )
        except (ValueError, httpx.HTTPError):
            # Keep compatibility with deployments that expose the
            # signed QC endpoint directly instead of the air gateway.
            payload = await _DeviceControlClient().post(self._METHOD, {"stationId": station["unique_code"]})
        raw_data = _auto_inspection_data(payload)
        has_snapshot = isinstance(raw_data, dict) and any(
            key in raw_data for key in ("DevDtls", "devDtls", "OtherAlarmDtls", "otherAlarmDtls")
        )
        success = _truthy(payload.get("Result", payload.get("success", False))) or has_snapshot
        if not raw_data:
            raw_data = payload
        # Some enabled stations return a successful QC envelope with an
        # empty result.  The platform page still renders its room and
        # latest动环 values, so enrich the visual input from the same
        # station-history endpoint without changing the raw QC result.
        if not has_snapshot and single:
            try:
                raw_data = dict(raw_data)
                environment_snapshot = await _fetch_environment_snapshot(station["unique_code"])
                environment_snapshot.update(
                    await _fetch_station_air_snapshot(station["station_code"])
                )
                raw_data["EnvironmentSnapshot"] = environment_snapshot
            except (ValueError, httpx.HTTPError) as exc:
                logger.info("jiangsu_stationhouse_environment_fallback_unavailable",
                            station_code=station.get("station_code"), error=str(exc))
        return {
            "station": station,
            "success": success,
            "data": raw_data,
            "issues": _inspection_issues(raw_data),
            "message": payload.get("ErrorMessage") or payload.get("message"),
        }


class JiangsuNetworkInspectionSummaryTool(LLMTool):
    """Read the air-platform whole-network station-house inspection summary."""

    _PATH = "stationintegrate/StationIntegrate/GetNetworkCheckAlarms"
    _PERIODS = {"day", "week", "month"}

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_network_inspection_summary",
            description="读取江苏站房全网巡检汇总，返回城市/站点异常状态及动环、采样系统、钢瓶等分类统计；仅查询。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_network_inspection_summary",
                             "description": "查询江苏全网站房巡检汇总；支持 day、week、month。",
                             "parameters": {"type": "object", "properties": {
                                 "period": {"type": "string", "enum": ["day", "week", "month"], "default": "day",
                                            "description": "统计周期：day 昨日、week 最近一周、month 本月。"},
                             }, "required": []}},
        )

    async def execute(self, context=None, period: str = "day", **_: Any) -> dict[str, Any]:
        try:
            period = str(period or "day").strip().lower()
            if period not in self._PERIODS:
                raise ValueError("period 必须是 day、week 或 month")
            payload = await _JiangsuAuthenticatedApi(source="air").get(self._PATH, [("DataType", period)])
            result = payload.get("result") or payload.get("data") or {}
            if not isinstance(result, dict):
                raise ValueError("全网巡检接口 result 无效")
            station_list = result.get("staList") or result.get("stationList") or []
            alarm_info = result.get("alarmInfo") or []
            if not isinstance(station_list, list) or not isinstance(alarm_info, list):
                raise ValueError("全网巡检接口返回列表格式无效")
            alarm_stations = [item for item in station_list if isinstance(item, dict) and (item.get("IsAlarm") or item.get("isAlarm"))]
            return {"status": "success", "success": True, "data": result,
                    "metadata": {"source": "jiangsu_station_integrate_api", "endpoint": self._PATH,
                                 "period": period, "station_count": len(station_list),
                                 "alarm_station_count": len(alarm_stations), "queried_at": datetime.now().astimezone().isoformat()},
                    "summary": f"全网巡检汇总完成：覆盖 {len(station_list)} 个站点，{len(alarm_stations)} 个站点存在异常。"}
        except (ValueError, httpx.HTTPError) as exc:
            return {"status": "failed", "success": False, "data": {}, "summary": f"全网巡检汇总失败：{exc}"}


class JiangsuStationEnvironmentHistoryTool(LLMTool):
    """Read station-house environment/power history from the air platform."""

    _PATH = "stationintegrate/StationIntegrate/GetStationEnvPowerData"
    _DEFAULT_ITEMS = (
        "SO2GasPressAD,NOxGasPressAD,COGasPressAD,SamplePipeSPress,StationTemp,StationHum,"
        "PipeTemp,PipeHum,VA,VB,VC,IA,IB,IC,Water1,SmokeState,SampleTemp,SampleHumi,"
        "HeatPower,SampleFlow,HeatTemp,SamplePipeStay,PumpPower,SampleAirTemp,SampleAirHumi"
    )

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_station_environment_history",
            description="读取江苏站房温湿度、电流电压、钢瓶压力和采样参数历史；支持具体站点、城市/区县下辖站点。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_station_environment_history",
                             "description": "查询站房动环历史曲线和表格数据。",
                             "parameters": {"type": "object", "properties": {
                                 "station_name": {"type": "string"}, "station_code": {"type": "string"},
                                 "unique_code": {"type": "string"}, "city_name": {"type": "string"},
                                 "district_name": {"type": "string"},
                                 "start_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss。"},
                                 "end_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss。"},
                                 "time_type": {"type": "string", "enum": ["h", "30s"], "default": "h"},
                                 "pollutant_codes": {"type": "array", "items": {"type": "string"},
                                                     "description": "可选动环编码；不提供时查询全部支持项。"},
                             }, "required": ["start_time", "end_time"]}},
        )

    async def execute(self, context=None, station_name: str | None = None, city_name: str | None = None,
                      district_name: str | None = None, station_code: str | None = None,
                      unique_code: str | None = None, start_time: str | None = None,
                      end_time: str | None = None, time_type: str = "h",
                      pollutant_codes: list[str] | None = None, **_: Any) -> dict[str, Any]:
        try:
            start = _parse_iso_time(start_time, "start_time")
            end = _parse_iso_time(end_time, "end_time")
            if start > end:
                raise ValueError("开始时间不能晚于结束时间")
            time_type = str(time_type or "h").strip().lower()
            if time_type not in {"h", "30s"}:
                raise ValueError("time_type 必须是 h 或 30s")
            max_seconds = 31 * 86400 if time_type == "h" else 86400
            if (end - start).total_seconds() > max_seconds:
                raise ValueError("小时数据最多查询 31 天，30 秒数据最多查询 1 天")
            stations = await _resolve_station_rows(
                station_name, city_name, district_name,
                station_code=station_code, unique_code=unique_code,
            )
            codes = ",".join(station["unique_code"] for station in stations)
            items = [str(item).strip() for item in (pollutant_codes or []) if str(item).strip()]
            pollutant = ",".join(items) if items else self._DEFAULT_ITEMS
            payload = await _JiangsuAuthenticatedApi(source="air").get(self._PATH, [
                ("Uniquecode", codes), ("PollutantCode", pollutant), ("TimeType", time_type),
                ("StartTime", start_time or ""), ("EndTime", end_time or ""),
            ])
            result = payload.get("result") or payload.get("data") or {}
            if not isinstance(result, dict):
                raise ValueError("站房动环接口 result 无效")
            table_data = result.get("tableData") or []
            chart_data = result.get("chartData") or []
            return {"status": "success" if table_data or chart_data else "empty", "success": True,
                    "data": result, "metadata": {"source": "jiangsu_station_integrate_api", "endpoint": self._PATH,
                                 "station_count": len(stations), "time_range": [start_time, end_time],
                                 "time_type": time_type, "pollutant_codes": items or ["全部"],
                                 "record_count": len(table_data) if isinstance(table_data, list) else 0,
                                 "queried_at": datetime.now().astimezone().isoformat()},
                    "summary": f"站房动环历史查询完成：查询 {len(stations)} 个站点，返回 {len(table_data) if isinstance(table_data, list) else 0} 条表格记录。"}
        except (ValueError, httpx.HTTPError) as exc:
            return {"status": "failed", "success": False, "data": {}, "summary": f"站房动环历史查询失败：{exc}"}


class JiangsuQcTaskHistoryTool(LLMTool):
    """Read task records first; their ``rId`` and ``rStart`` drive detail tools."""

    _PATH = "operation/QualityControl/GetNewQCHisResultListAsync"
    _MAX_STATIONS = 10

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_qc_task_history",
            description="读取江苏站点历史质控任务及结果；返回的 rId、rStart 可用于继续查询状态和运行日志；最多 10 个站点并发查询。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_qc_task_history", "description": "按站点名称、平台站点编码或唯一编码查询历史质控任务，最多 10 个站点并发；不支持城市/区县批量。",
                             "parameters": {"type": "object", "properties": {
                                 "station_names": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                                    "description": "站点名称列表，最多 10 个。"},
                                 "station_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                                    "description": "平台站点编码列表，最多 10 个。"},
                                 "unique_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                                   "description": "平台唯一编码列表；已知时可直接使用，最多 10 个。"},
                                 "start_time": {"type": "string", "description": "开始时间，YYYY-MM-DD HH:mm:ss。"},
                                 "end_time": {"type": "string", "description": "结束时间，YYYY-MM-DD HH:mm:ss。"},
                                 "pollutant": {"type": "string", "description": "可选，如 SO2、NO、CO、O3。"},
                             }, "required": ["start_time", "end_time"]}},
        )

    async def execute(self, context=None, station_names: list[str] | None = None,
                      station_codes: list[str] | None = None, unique_codes: list[str] | None = None,
                      start_time: str | None = None, end_time: str | None = None,
                      pollutant: str | None = None, **_: Any) -> dict[str, Any]:
        try:
            stations = await _resolve_direct_station_scope(
                station_names, station_codes, unique_codes, max_stations=self._MAX_STATIONS,
            )
            api = _JiangsuAuthenticatedApi(source="ops")
            results = list(await asyncio.gather(
                *(self._fetch_history(api, station["station_code"], start_time, end_time, pollutant) for station in stations)
            ))
            records = [record for item in results for record in item["records"]]
            failed_count = sum(1 for item in results if not item["success"])
            success = failed_count < len(stations)
            summary = f"质控任务查询完成：并发查询 {len(stations)} 个站点，返回 {len(records)} 条记录"
            if failed_count:
                summary += f"，{failed_count} 个站点查询失败"
            metadata = {"source": "jiangsu_operations_api", "endpoint": self._PATH,
                        "station_count": len(stations), "failed_station_count": failed_count,
                        "record_count": len(records), "queried_at": datetime.now().astimezone().isoformat()}
            return {"status": "success" if records else ("empty" if success else "failed"), "success": success,
                    "data": records, "metadata": metadata, "summary": summary + "。"}
        except (ValueError, httpx.HTTPError) as exc:
            return _failed("质控任务查询", exc)

    async def _fetch_history(self, api: _JiangsuAuthenticatedApi, code: str,
                             start_time: str | None, end_time: str | None,
                             pollutant: str | None) -> dict[str, Any]:
        try:
            params = [("stationCode", code), *_time_range("sStart", start_time, end_time)]
            if pollutant:
                params.append(("poll", _identifier(pollutant, "pollutant")))
            return {"records": _list_result(await api.get(self._PATH, params), "质控任务"), "success": True}
        except (ValueError, httpx.HTTPError) as exc:
            return {"records": [], "success": False, "error": str(exc)}


class JiangsuQcTaskStatusTool(LLMTool):
    _PATH = "operation/QualityControl/GetNewQCHisTaskStatusResultAsync"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_qc_task_status",
            description="读取指定历史质控任务的执行步骤与状态快照；只读。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_qc_task_status", "description": "按质控任务 rStart 和 rId 查询执行状态。",
                             "parameters": {"type": "object", "properties": {
                                 "r_start": {"type": "string", "description": "质控任务开始时间（来自任务历史）。"},
                                 "r_id": {"type": "string", "description": "质控任务标识 rId（来自任务历史）。"},
                             }, "required": ["r_start", "r_id"]}},
        )

    async def execute(self, context=None, r_start: str | None = None, r_id: str | None = None, **_: Any) -> dict[str, Any]:
        try:
            r_start, r_id = _identifier(r_start, "r_start"), _identifier(r_id, "r_id")
            payload = await _JiangsuAuthenticatedApi(source="ops").get(self._PATH, [("rStart", r_start), ("rId", r_id)])
            result = payload.get("result") or {}
            if not isinstance(result, dict):
                raise ValueError("质控任务状态接口 result 无效")
            return {"status": "success", "success": True, "data": result,
                    "metadata": {"source": "jiangsu_operations_api", "endpoint": self._PATH, "r_start": r_start, "r_id": r_id,
                                 "queried_at": datetime.now().astimezone().isoformat()}, "summary": "质控任务状态查询完成。"}
        except (ValueError, httpx.HTTPError) as exc:
            return _failed("质控任务状态查询", exc)


class JiangsuQcRunLogTool(LLMTool):
    _PATH = "operation/QualityControl/GetNewQCHisRunLogResultListAsync"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_qc_run_logs",
            description="读取指定历史质控任务的运行日志；只读。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_qc_run_logs", "description": "按质控任务 rStart 和 rId 查询运行日志。",
                             "parameters": {"type": "object", "properties": {
                                 "r_start": {"type": "string", "description": "质控任务开始时间（来自任务历史）。"},
                                 "r_id": {"type": "string", "description": "质控任务标识 rId（来自任务历史）。"},
                             }, "required": ["r_start", "r_id"]}},
        )

    async def execute(self, context=None, r_start: str | None = None, r_id: str | None = None, **_: Any) -> dict[str, Any]:
        try:
            r_start, r_id = _identifier(r_start, "r_start"), _identifier(r_id, "r_id")
            records = _list_result(await _JiangsuAuthenticatedApi(source="ops").get(
                self._PATH, [("rStart", r_start), ("rId", r_id)]), "质控运行日志")
            return _records_response(records, self._PATH, None, "质控运行日志查询完成", {"r_start": r_start, "r_id": r_id})
        except (ValueError, httpx.HTTPError) as exc:
            return _failed("质控运行日志查询", exc)


class JiangsuQcMonitoringCurveTool(LLMTool):
    _PATH = "operation/QualityControl/GetNewQCAirDataResultListAsync"
    _MAX_STATIONS = 10

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_qc_monitoring_curve",
            description="读取质控任务前后及期间的监测项值序列，用于生成响应曲线；最多 10 个站点并发查询。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_qc_monitoring_curve", "description": "按站点名称、平台站点编码或唯一编码读取质控期间监测序列，最多 10 个站点并发；不支持城市/区县批量。",
                             "parameters": {"type": "object", "properties": {
                                 "station_names": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                                    "description": "站点名称列表，最多 10 个。"},
                                 "station_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                                    "description": "平台站点编码列表，最多 10 个。"},
                                 "unique_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10,
                                                   "description": "平台唯一编码列表；已知时可直接使用，最多 10 个。"},
                                 "pollutant": {"type": "string", "description": "污染物，如 SO2、NO、CO、O3。"},
                                 "qc_type": {"type": "string", "description": "质控类型，来自任务历史的 qcType。"},
                                 "start_time": {"type": "string", "description": "曲线开始时间，YYYY-MM-DD HH:mm:ss。"},
                                 "end_time": {"type": "string", "description": "曲线结束时间，YYYY-MM-DD HH:mm:ss。"},
                             }, "required": ["pollutant", "qc_type", "start_time", "end_time"]}},
        )

    async def execute(self, context=None, station_names: list[str] | None = None,
                      station_codes: list[str] | None = None, unique_codes: list[str] | None = None,
                      pollutant: str | None = None, qc_type: str | None = None,
                      start_time: str | None = None, end_time: str | None = None, **_: Any) -> dict[str, Any]:
        try:
            stations = await _resolve_direct_station_scope(
                station_names, station_codes, unique_codes, max_stations=self._MAX_STATIONS,
            )
            api = _JiangsuAuthenticatedApi(source="ops")
            results = list(await asyncio.gather(
                *(self._fetch_curve(api, station["station_code"], pollutant, qc_type, start_time, end_time) for station in stations)
            ))
            records = [record for item in results for record in item["records"]]
            failed_count = sum(1 for item in results if not item["success"])
            success = failed_count < len(stations)
            summary = f"质控监测曲线查询完成：并发查询 {len(stations)} 个站点，返回 {len(records)} 条记录"
            if failed_count:
                summary += f"，{failed_count} 个站点查询失败"
            metadata = {"source": "jiangsu_operations_api", "endpoint": self._PATH,
                        "station_count": len(stations), "failed_station_count": failed_count,
                        "record_count": len(records), "queried_at": datetime.now().astimezone().isoformat()}
            return {"status": "success" if records else ("empty" if success else "failed"), "success": success,
                    "data": records, "metadata": metadata, "summary": summary + "。"}
        except (ValueError, httpx.HTTPError) as exc:
            return _failed("质控监测曲线查询", exc)

    async def _fetch_curve(self, api: _JiangsuAuthenticatedApi, code: str, pollutant: str | None,
                           qc_type: str | None, start_time: str | None, end_time: str | None) -> dict[str, Any]:
        try:
            params = [("stationCode", code), ("poll", _identifier(pollutant, "pollutant")),
                      ("qcType", _identifier(qc_type, "qc_type")), *_time_range("timePoint", start_time, end_time)]
            return {"records": _list_result(await api.get(self._PATH, params), "质控监测曲线"), "success": True}
        except (ValueError, httpx.HTTPError) as exc:
            return {"records": [], "success": False, "error": str(exc)}


def _inspection_metrics(data: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, Any]:
    """Mirror the platform's client-side counters without hiding raw issues."""
    categories = {"仪器状态": 0, "监测数据": 0, "站房动环": 0, "采样系统": 0, "质控与标气": 0,
                  "网络与采集": 0, "视频安防": 0, "系统安全": 0, "其他异常": 0}
    statuses = {"offline": 0, "out_of_range": 0, "other_alarm": 0}
    for issue in issues:
        category = str(issue.get("category") or "其他异常")
        if category not in categories:
            category = "其他异常"
        categories[category] += 1
        source = issue.get("source")
        if source == "OtherAlarmDtls":
            statuses["other_alarm"] += 1
        elif issue.get("severity") == "high" and "离线" in str(issue.get("description") or ""):
            statuses["offline"] += 1
        else:
            statuses["out_of_range"] += 1

    # The old page deducts for instrument state, monitoring data, dynamic
    # environment and other alarms. Keep the breakdown explicit so the Agent
    # can explain it, while preserving the unmodified issue list for auditing.
    instrument = categories["仪器状态"]
    monitoring = categories["监测数据"]
    environment = categories["站房动环"] + categories["采样系统"] + categories["质控与标气"]
    other = categories["其他异常"] + categories["网络与采集"] + categories["视频安防"] + categories["系统安全"]
    deductions = {
        "instrument_state": 30 if instrument > 1 else (15 if instrument else 0),
        "monitoring_data": min(20, monitoring * 2),
        "environment": 10 if environment else 0,
        "other_alarm": 10 if other > 1 else (5 if other else 0),
    }
    return {
        "category_counts": {key: value for key, value in categories.items() if value},
        "status_counts": {key: value for key, value in statuses.items() if value},
        "issue_count": len(issues),
        "score": max(0, 100 - sum(deductions.values())),
        "score_breakdown": deductions,
        "score_basis": "platform_frontend_compatible_v1",
    }


def _stationhouse_visual(
    station: dict[str, Any],
    data: dict[str, Any],
    issues: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """Build an ECharts graphic used by the right-side visualization panel."""
    issue_by_code: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        issue_by_code.setdefault(str(issue.get("code") or ""), []).append(issue)
    devices = data.get("DevDtls") or data.get("devDtls") or []
    latest: dict[str, dict[str, Any]] = {}
    if isinstance(devices, list):
        for device in devices:
            if not isinstance(device, dict):
                continue
            code = str(device.get("DevPollCode") or device.get("devPollCode") or "").strip()
            rows = device.get("HourDataDtsls") or device.get("hourDataDtsls") or []
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                latest[code] = rows[0]
            else:
                latest[code] = {"DataAlarm": device.get("DevAlarm", device.get("devAlarm"))}
    environment_snapshot = data.get("EnvironmentSnapshot")
    if isinstance(environment_snapshot, dict):
        for code, value in environment_snapshot.items():
            if isinstance(value, dict):
                latest[str(code)] = value

    modules = [
        ("监测仪器", [("PM10", "PM₁₀", "μg/m³"), ("PM2.5", "PM₂.₅", "μg/m³"),
                     ("SO2", "SO₂", "μg/m³"), ("NO", "NO", "μg/m³"),
                     ("CO", "CO", "μg/m³"), ("O3", "O₃", "μg/m³")]),
        ("站房动环", [("StationTemp", "站房温度", "℃"), ("StationHum", "站房湿度", "%"),
                     ("IA", "IA", "A"), ("IB", "IB", "A"), ("VA", "VA", "V"), ("VB", "VB", "V")]),
        ("采样系统", [("PipeTemp", "总管温度", "℃"), ("PipeHum", "总管湿度", "%"),
                     ("SamplePipeSPress", "总管静压", "Pa"), ("SampleFlow", "采样流量", "L/min"),
                     ("SamplePipeStay", "滞留时间", "s")]),
        ("质控与标气", [("SO2GasPressAD", "SO₂钢瓶", "MPa"), ("NOxGasPressAD", "NOx钢瓶", "MPa"),
                       ("COGasPressAD", "CO钢瓶", "MPa"), ("ZeroGasFlow", "零气流量", "SCCM"),
                       ("SpanGasFlow", "标气流量", "SCCM")]),
    ]
    def visual_value(code: str) -> str:
        value = latest.get(code)
        if not value:
            return "—"
        raw = value.get("Value", value.get("value"))
        if raw is None or str(raw).strip() == "":
            return "—"
        try:
            return f"{float(raw):.3f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return str(raw)[:10]

    scene_values = {
        code: {
            "value": visual_value(code),
            "alarm": int(_numeric(value.get("DataAlarm", value.get("dataAlarm"))) or 0),
            "time": value.get("timePoint") or value.get("TimePoint") or value.get("time") or "",
        }
        for code, value in latest.items()
        if isinstance(value, dict)
    }

    canvas_w, canvas_h = 960, 520
    graphic: list[dict[str, Any]] = [
        {"type": "rect", "left": 0, "top": 0, "shape": {"width": canvas_w, "height": canvas_h, "r": 12},
         "style": {"fill": "#07111f", "stroke": "#263a56", "lineWidth": 1}},
        {"type": "rect", "left": 0, "top": 0, "shape": {"width": canvas_w, "height": 64, "r": 12},
         "style": {"fill": "#10233b"}},
        {"type": "text", "left": 22, "top": 13, "style": {"text": f"{station.get('station_name') or '站点'} 站房巡检",
         "fill": "#f8fafc", "font": "bold 20px sans-serif"}},
        {"type": "text", "left": 22, "top": 41, "style": {"text": f"{station.get('station_code', '')} / {station.get('unique_code', '')} · {station.get('city_name', '')}{station.get('district_name', '')}",
         "fill": "#93c5fd", "font": "12px sans-serif"}},
    ]
    score = int(metrics.get("score", 100) or 0)
    score_color = "#22c55e" if score >= 90 else ("#f59e0b" if score >= 60 else "#ef4444")
    graphic.extend([
        {"type": "circle", "left": 866, "top": 8, "shape": {"cx": 32, "cy": 24, "r": 23},
         "style": {"fill": "#0b1728", "stroke": score_color, "lineWidth": 3}},
        {"type": "text", "left": 878, "top": 8, "style": {"text": str(score), "fill": score_color,
         "font": "bold 20px sans-serif", "textAlign": "center", "width": 40}},
        {"type": "text", "left": 878, "top": 36, "style": {"text": "评分", "fill": "#94a3b8",
         "font": "11px sans-serif", "textAlign": "center", "width": 40}},
    ])

    # 横向站房拓扑充分利用右侧面板宽度，避免固定窄画布造成大面积留白。
    graphic.extend([
        {"type": "rect", "left": 16, "top": 78, "shape": {"width": 600, "height": 274, "r": 8},
         "style": {"fill": "#0d1b2e", "stroke": "#52749a", "lineWidth": 2}},
        {"type": "rect", "left": 30, "top": 106, "shape": {"width": 572, "height": 218, "r": 4},
         "style": {"fill": "#132943", "stroke": "#315375", "lineWidth": 1}},
        {"type": "line", "shape": {"x1": 316, "y1": 106, "x2": 316, "y2": 324},
         "style": {"stroke": "#315375", "lineWidth": 1}},
        {"type": "line", "shape": {"x1": 30, "y1": 215, "x2": 602, "y2": 215},
         "style": {"stroke": "#315375", "lineWidth": 1}},
        {"type": "text", "left": 31, "top": 84, "style": {"text": "站房设备拓扑", "fill": "#bfdbfe", "font": "bold 13px sans-serif"}},
        {"type": "circle", "left": 280, "top": 111, "shape": {"cx": 23, "cy": 16, "r": 16},
         "style": {"fill": "#1e4b72", "stroke": "#7dd3fc", "lineWidth": 2}},
        {"type": "text", "left": 306, "top": 121, "style": {"text": "风扇 / 空调", "fill": "#dbeafe", "font": "11px sans-serif"}},
    ])
    room_nodes = [
        ("监测仪器", 44, 145, ["PM10", "PM2.5", "SO2"]),
        ("采样总管", 330, 145, ["PipeTemp", "SampleFlow", "SamplePipeSPress"]),
        ("站房动环", 44, 249, ["StationTemp", "StationHum", "IA"]),
        ("钢瓶质控", 330, 249, ["SO2GasPressAD", "NOxGasPressAD", "COGasPressAD"]),
    ]
    for title, left, top, codes in room_nodes:
        node_issues = [item for code in codes for item in issue_by_code.get(code, [])]
        node_color = "#ef4444" if node_issues else "#22c55e"
        graphic.extend([
            {"type": "rect", "left": left, "top": top, "shape": {"width": 258, "height": 58, "r": 5},
             "style": {"fill": "#182f4a", "stroke": node_color, "lineWidth": 1.5}},
            {"type": "circle", "left": left + 10, "top": top + 11, "shape": {"cx": 5, "cy": 5, "r": 5},
             "style": {"fill": node_color}},
            {"type": "text", "left": left + 24, "top": top + 8, "style": {"text": title, "fill": "#e0f2fe", "font": "bold 11px sans-serif"}},
            {"type": "text", "left": left + 11, "top": top + 32, "style": {"text": "    ".join(f"{code} {visual_value(code)}" for code in codes),
             "fill": "#9fb8d1", "font": "10px monospace"}},
        ])
    graphic.extend([
        {"type": "text", "left": 44, "top": 332, "style": {"text": "● 正常", "fill": "#22c55e", "font": "11px sans-serif"}},
        {"type": "text", "left": 116, "top": 332, "style": {"text": "● 异常", "fill": "#ef4444", "font": "11px sans-serif"}},
        {"type": "text", "left": 188, "top": 332, "style": {"text": "● 离线", "fill": "#f59e0b", "font": "11px sans-serif"}},
    ])

    # 右侧摘要采用两列指标，与平台的评分和检测统计区域一致。
    summary_left, summary_top, summary_w = 632, 78, 312
    graphic.extend([
        {"type": "rect", "left": summary_left, "top": summary_top, "shape": {"width": summary_w, "height": 274, "r": 8},
         "style": {"fill": "#0d1b2e", "stroke": "#263a56", "lineWidth": 1}},
        {"type": "text", "left": summary_left + 16, "top": summary_top + 14,
         "style": {"text": "巡检概览", "fill": "#bfdbfe", "font": "bold 13px sans-serif"}},
    ])
    available_metric_count = sum(1 for _, fields in modules for code, _, _ in fields if code in latest)
    summary_lines = [
        ("检测项", str(available_metric_count), "#60a5fa"), ("异常项", str(len(issues)), "#ef4444"),
        ("离线设备", str((metrics.get("status_counts") or {}).get("offline", 0)), "#f59e0b"),
        ("数据状态", "已返回" if environment_snapshot else "QC快照为空", "#22c55e" if environment_snapshot else "#94a3b8"),
    ]
    for idx, (label, value, color) in enumerate(summary_lines):
        col, row = idx % 2, idx // 2
        left = summary_left + 16 + col * 148
        top = summary_top + 54 + row * 92
        graphic.extend([
            {"type": "rect", "left": left, "top": top, "shape": {"width": 132, "height": 72, "r": 5},
             "style": {"fill": "#10243b", "stroke": "#1e3a5a", "lineWidth": 1}},
            {"type": "text", "left": left + 12, "top": top + 10,
             "style": {"text": label, "fill": "#94a3b8", "font": "11px sans-serif"}},
            {"type": "text", "left": left + 12, "top": top + 34,
             "style": {"text": value, "fill": color, "font": "bold 18px sans-serif"}},
        ])

    # 底部四组参数横向铺开，最多呈现每组前三项实时值。
    card_w, card_h, gap = 222, 126, 12
    for index, (name, fields) in enumerate(modules):
        left, top = 16 + index * (card_w + gap), 368
        module_issues = [item for code, _, _ in fields for item in issue_by_code.get(code, [])]
        has_module_data = any(code in latest for code, _, _ in fields)
        color = "#ef4444" if module_issues else ("#22c55e" if has_module_data else "#64748b")
        graphic.extend([
            {"type": "rect", "left": left, "top": top, "shape": {"width": card_w, "height": card_h, "r": 7},
             "style": {"fill": "#10243b", "stroke": color, "lineWidth": 1}},
            {"type": "text", "left": left + 12, "top": top + 10,
             "style": {"text": name, "fill": "#dbeafe", "font": "bold 12px sans-serif"}},
            {"type": "text", "left": left + card_w - 58, "top": top + 11,
             "style": {"text": "异常" if module_issues else ("在线" if has_module_data else "无数据"),
             "fill": color, "font": "11px sans-serif"}},
        ])
        for row, (code, label, unit) in enumerate(fields[:3]):
            row_top = top + 37 + row * 25
            graphic.extend([
                {"type": "text", "left": left + 12, "top": row_top,
                 "style": {"text": label, "fill": "#8fa8c0", "font": "10px sans-serif"}},
                {"type": "text", "left": left + 105, "top": row_top,
                 "style": {"text": f"{visual_value(code)} {unit}", "fill": "#e0f2fe", "font": "bold 11px monospace"}},
            ])
    graphic.append({"type": "text", "left": 18, "top": 502,
                    "style": {"text": "数据来源：自动巡检 QC、空气监测和站房动环接口 · 仅展示接口返回数据",
                              "fill": "#64748b", "font": "10px sans-serif"}})
    return {
        "id": f"stationhouse_{station.get('unique_code') or station.get('station_code')}",
        "type": "stationhouse",
        "title": f"{station.get('station_name') or '站点'}站房巡检",
        "data": {"animation": False, "graphic": graphic,
                 "xAxis": {"show": False, "min": 0, "max": canvas_w},
                 "yAxis": {"show": False, "min": 0, "max": canvas_h},
                 "series": [{"type": "scatter", "data": [], "silent": True}],
                 "stationhouse": {
                     "station": station,
                     "score": score,
                     "issue_count": len(issues),
                     "offline_count": int((metrics.get("status_counts") or {}).get("offline", 0)),
                     "available_count": len(scene_values),
                     "values": scene_values,
                     "issues": issues[:20],
                     "qc_snapshot_available": any(key in data for key in ("DevDtls", "devDtls")),
                     "environment_fallback": bool(environment_snapshot),
                     "updated_at": datetime.now().astimezone().isoformat(),
                 }},
        "meta": {"generator": "jiangsu_fetch_auto_inspection", "scenario": "stationhouse_inspection",
                 "station": station, "issue_count": len(issues), "metrics": metrics,
                 "environment_fallback": bool(environment_snapshot)},
    }


async def _fetch_environment_snapshot(unique_code: str) -> dict[str, dict[str, Any]]:
    """Return latest hourly values keyed by platform pollutant code."""
    end = datetime.now()
    start = end - timedelta(hours=24)
    payload = await _JiangsuAuthenticatedApi(source="air").get(
        JiangsuStationEnvironmentHistoryTool._PATH,
        [("Uniquecode", unique_code), ("PollutantCode", JiangsuStationEnvironmentHistoryTool._DEFAULT_ITEMS),
         ("TimeType", "h"), ("StartTime", start.strftime("%Y-%m-%d %H:%M:%S")),
         ("EndTime", end.strftime("%Y-%m-%d %H:%M:%S"))],
    )
    result = payload.get("result") or payload.get("data") or {}
    rows = result.get("tableData") if isinstance(result, dict) else []
    snapshot: dict[str, dict[str, Any]] = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get("itemCode") or row.get("ItemCode") or "").strip()
            if code:
                snapshot[code] = {"Value": row.get("value", row.get("Value")), "DataAlarm": 0,
                                  "timePoint": row.get("timePoint") or row.get("TimePoint")}
    return snapshot


async def _fetch_station_air_snapshot(station_code: str) -> dict[str, dict[str, Any]]:
    """Add the latest pollutant readings when QC returns an empty envelope."""
    end = datetime.now()
    start = end - timedelta(minutes=15)
    records, _ = await JiangsuStationDataTool().fetch_raw_records(
        data_kind="station_5minute",
        station_codes=[station_code],
        start_time=start.strftime("%Y-%m-%d %H:%M:%S"),
        end_time=end.strftime("%Y-%m-%d %H:%M:%S"),
        pollutant_codes=["PM2_5", "PM10", "SO2", "NO", "CO", "O3"],
    )
    if not records:
        return {}
    latest = max(records, key=lambda row: str(row.get("timePoint") or row.get("TimePoint") or ""))
    aliases = {
        "pM10": "PM10", "pm10": "PM10", "pM2_5": "PM2.5", "pm2_5": "PM2.5", "pM25": "PM2.5",
        "sO2": "SO2", "so2": "SO2", "no": "NO", "nO": "NO", "co": "CO", "o3": "O3",
    }
    snapshot: dict[str, dict[str, Any]] = {}
    for source, code in aliases.items():
        value = latest.get(source)
        if value is not None and str(value).strip() not in {"", "-99", "—"}:
            snapshot[code] = {"Value": value, "DataAlarm": 0,
                              "timePoint": latest.get("timePoint") or latest.get("TimePoint")}
    return snapshot


def _inspection_issues(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract compact, model-friendly issues from the legacy QC snapshot."""
    issues: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return issues
    other_alarms = data.get("OtherAlarmDtls") or data.get("otherAlarmDtls") or []
    if isinstance(other_alarms, list):
        for alarm in other_alarms:
            if not isinstance(alarm, dict):
                continue
            code = str(alarm.get("SubCatalog") or alarm.get("subCatalog") or "").strip()
            description = str(alarm.get("Csuse") or alarm.get("DescriptionDE") or alarm.get("SubCatalog") or "").strip()
            issues.append({
                "category": _inspection_category(code, description),
                "code": code,
                "description": description,
                "suggestion": str(alarm.get("Deal") or "").strip(),
                "severity": _inspection_severity(alarm),
                "source": "OtherAlarmDtls",
            })
    devices = data.get("DevDtls") or data.get("devDtls") or []
    if isinstance(devices, list):
        for device in devices:
            if not isinstance(device, dict):
                continue
            device_name = str(device.get("DeviceName") or device.get("deviceName") or "未知设备").strip()
            if _numeric(device.get("DevAlarm", device.get("devAlarm"))) == 1:
                issues.append({
                    "category": _inspection_category(str(device.get("DevPollCode") or ""), device_name),
                    "code": str(device.get("DevPollCode") or "").strip(),
                    "description": f"{device_name}离线",
                    "suggestion": f"检查{device_name}及其通信链路。",
                    "severity": "high",
                    "source": "DevDtls",
                })
            status_rows = device.get("HourStatusDtls") or device.get("hourStatusDtls") or []
            if isinstance(status_rows, list):
                for status in status_rows:
                    if not isinstance(status, dict):
                        continue
                    value = _numeric(status.get("Value", status.get("value")))
                    lower = _numeric(status.get("AlarmL", status.get("alarmL")))
                    upper = _numeric(status.get("AlarmH", status.get("alarmH")))
                    if value is None or (lower is None and upper is None):
                        continue
                    outside = (lower is not None and value < lower) or (upper is not None and value > upper)
                    if outside:
                        status_name = str(status.get("StatusName") or status.get("statusName") or "状态").strip()
                        issues.append({
                            "category": _inspection_category(str(device.get("DevPollCode") or ""), device_name),
                            "code": str(device.get("DevPollCode") or "").strip(),
                            "description": f"{device_name}{status_name}超限",
                            "value": value,
                            "alarm_range": {"lower": lower, "upper": upper},
                            "suggestion": f"检查{device_name}{status_name}及相关设备。",
                            "severity": "medium",
                            "source": "HourStatusDtls",
                        })
    return issues


def _auto_inspection_data(payload: dict[str, Any]) -> dict[str, Any]:
    """Decode the QC gateway's JSON-string ``result`` envelope."""
    if not isinstance(payload, dict):
        return {}
    direct = payload.get("Data") or payload.get("data")
    if isinstance(direct, dict):
        return direct
    result = payload.get("result")
    if isinstance(result, dict):
        return result
    if not isinstance(result, str):
        return {}
    # The legacy gateway prefixes the upstream URL with ``+++``.
    text = result.split("+++", 1)[-1]
    brace = text.find("{")
    if brace >= 0:
        text = text[brace:]
    try:
        decoded = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _truthy(value: Any) -> bool:
    """Handle the platform's mixed bool/string success fields."""
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "成功"}
    return bool(value)


def _inspection_category(code: str, description: str = "") -> str:
    text = f"{code} {description}"
    pollutant_code = str(code or "").strip().upper().replace("_", "")
    if pollutant_code in {"SO2", "NO", "NO2", "NOX", "CO", "O3", "PM2.5", "PM10"} \
            or any(token in text for token in ("监测浓度", "监测数据", "污染物")):
        return "监测数据"
    if any(token in text for token in ("采样", "总管", "Sample", "Pipe")):
        return "采样系统"
    if any(token in text for token in ("质控", "零点", "跨度", "钢瓶", "GasPress")):
        return "质控与标气"
    if any(token in text for token in ("站房", "温度", "湿度", "电压", "电流", "烟感", "水浸", "动环")):
        return "站房动环"
    if any(token in text for token in ("网络", "VPN", "站点离线", "上报")):
        return "网络与采集"
    if any(token in text for token in ("摄像", "硬盘录像", "安防")):
        return "视频安防"
    if any(token in text for token in ("数据库", "工控机", "软件", "远程", "USB")):
        return "系统安全"
    return "仪器状态"


def _inspection_severity(alarm: dict[str, Any]) -> str:
    level = alarm.get("CriticalLevel", alarm.get("criticalLevel"))
    text = str(alarm.get("DescriptionDE") or alarm.get("SubCatalog") or "")
    if str(level) in {"2", "3", "4"} or any(token in text for token in ("严重", "离线", "失败")):
        return "high"
    return "medium"


def _numeric(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_iso_time(value: str | None, name: str) -> datetime:
    try:
        result = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} 必须为 YYYY-MM-DD HH:mm:ss 格式") from exc
    # The upstream service uses local server time.  Keep comparisons naive even
    # when the caller supplies an explicit UTC offset.
    return result.replace(tzinfo=None)


def _list_result(payload: dict[str, Any], label: str) -> list[Any]:
    result = payload.get("result") or []
    if not isinstance(result, list):
        raise ValueError(f"{label}接口 result 无效")
    return result


def _records_response(records: list[Any], endpoint: str, station_code: str | None, summary: str,
                      extra_metadata: dict[str, str] | None = None) -> dict[str, Any]:
    metadata: dict[str, Any] = {"source": "jiangsu_operations_api", "endpoint": endpoint,
                                "record_count": len(records), "queried_at": datetime.now().astimezone().isoformat()}
    if station_code:
        metadata["station_code"] = station_code
    if extra_metadata:
        metadata.update(extra_metadata)
    return {"status": "success" if records else "empty", "success": True, "data": records, "metadata": metadata,
            "summary": f"{summary}：返回 {len(records)} 条记录。"}


def _failed(label: str, exc: Exception) -> dict[str, Any]:
    return {"status": "failed", "success": False, "data": [], "summary": f"{label}失败：{exc}"}


def _time_range(key: str, start_time: str | None, end_time: str | None) -> list[tuple[str, str]]:
    start, end = _identifier(start_time, "start_time"), _identifier(end_time, "end_time")
    if start > end:
        raise ValueError("开始时间不能晚于结束时间")
    return [(key, start), (key, end)]


def _identifier(value: str | None, name: str) -> str:
    result = str(value or "").strip()
    if not result or len(result) > 64:
        raise ValueError(f"{name} 必须为有效站点标识")
    return result


def _optional_identifier(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, name)


def _clean_identifier_list(values: list[str] | None, name: str) -> list[str]:
    """Validate an explicit station identifier list without silent drops."""
    if values is None:
        return []
    if not isinstance(values, list) or not values:
        raise ValueError(f"{name} 必须是非空字符串数组")
    cleaned: list[str] = []
    for value in values:
        cleaned.append(_identifier(value if isinstance(value, str) else None, name))
    return cleaned


def _normalise_place_name(value: Any) -> str:
    return str(value or "").strip().replace(" ", "").rstrip("省市区县")
