"""Read-only Jiangsu data tools for focused station fault diagnosis."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.jiangsu.device_control import _DeviceControlClient

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

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_station_alarm_logs",
            description="读取江苏站房设备告警日志、告警统计与设备告警状态；仅用于故障诊断。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_station_alarm_logs", "description": "按城市、区县或站点名称读取站房设备告警。",
                             "parameters": {"type": "object", "properties": {
                                 "station_name": {"type": "string"}, "city_name": {"type": "string"}, "district_name": {"type": "string"},
                             }, "required": []}},
        )

    async def execute(self, context=None, station_name: str | None = None, city_name: str | None = None,
                      district_name: str | None = None, station_code: str | None = None, **_: Any) -> dict[str, Any]:
        try:
            stations = ([{"station_code": _identifier(station_code, "station_code"), "unique_code": ""}]
                        if station_code else await _resolve_station_rows(station_name, city_name, district_name))
            if not stations: raise ValueError("station_name、city_name、district_name 至少提供一个")
            api = _JiangsuAuthenticatedApi(source="air"); data = []
            for station in stations:
                payload = await api.get(self._PATH, [("StationCode", station["station_code"])])
                result = payload.get("result") or {}
                if not isinstance(result, dict): raise ValueError("站房告警接口 result 无效")
                data.append({"station": station, "result": result})
            count = sum(len((x["result"].get("alarmLogs") or [])) for x in data)
            return {"status": "success", "success": True, "data": data,
                    "metadata": {"source": "jiangsu_station_integrate_api", "endpoint": self._PATH, "station_count": len(stations), "record_count": count,
                                 "queried_at": datetime.now().astimezone().isoformat()}, "summary": f"站房告警查询完成：返回 {count} 条告警记录。"}
        except (ValueError, httpx.HTTPError) as exc:
            return {"status": "failed", "success": False, "data": {}, "summary": f"站房告警查询失败：{exc}"}


class JiangsuFaultWorkOrdersTool(LLMTool):
    _PATH = "operation/FaultOrder/GetWorkingOrderInfoByUniqueCode"
    _STATION_DIRECTORY_PATH = "AirCityProductBase/GetAllEnabledBSDStationAsync"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_fault_work_orders",
            description="按城市、区县或站点名称读取故障工单与历史处置记录；仅用于故障诊断。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_fault_work_orders", "description": "按城市、区县和站点名称查询最近故障工单；工具内部解析江苏平台站点编码。",
                             "parameters": {"type": "object", "properties": {
                                 "station_name": {"type": "string", "description": "可选站点名称；不提供时查询区域下辖全部站点。"},
                                 "city_name": {"type": "string", "description": "可选城市名称；可单独查询该城市下辖站点。"},
                                 "district_name": {"type": "string", "description": "可选区县名称；可单独查询该区县下辖站点。"},
                                 "take": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                             }, "required": []}},
        )

    async def execute(self, context=None, station_name: str | None = None, city_name: str | None = None,
                      district_name: str | None = None, take: int = 5, **_: Any) -> dict[str, Any]:
        try:
            station_name = _optional_identifier(station_name, "station_name")
            city_name = _optional_identifier(city_name, "city_name")
            district_name = _optional_identifier(district_name, "district_name")
            if not any((station_name, city_name, district_name)):
                raise ValueError("station_name、city_name、district_name 至少提供一个")
            if not isinstance(take, int) or not 1 <= take <= 20:
                raise ValueError("take 必须为 1–20 的整数")
            stations = await self._resolve_stations(station_name, city_name, district_name)
            api = _JiangsuAuthenticatedApi(source="ops")
            orders: list[Any] = []
            for station in stations:
                payload = await api.get(self._PATH, [("uniqueCode", station["unique_code"]), ("take", str(take))])
                station_orders = payload.get("result") or []
                if not isinstance(station_orders, list):
                    raise ValueError("故障工单接口 result 无效")
                orders.extend(station_orders)
            return {"status": "success" if orders else "empty", "success": True, "data": orders,
                    "metadata": {"source": "jiangsu_operations_api", "endpoint": self._PATH,
                                 "station": {"station_name": station_name, "city_name": city_name, "district_name": district_name},
                                 "station_count": len(stations),
                                 "record_count": len(orders), "queried_at": datetime.now().astimezone().isoformat()},
                    "summary": f"故障工单查询完成：返回 {len(orders)} 条记录。"}
        except (ValueError, httpx.HTTPError) as exc:
            return {"status": "failed", "success": False, "data": [], "summary": f"故障工单查询失败：{exc}"}

    async def _resolve_stations(self, station_name: str | None, city_name: str | None,
                                district_name: str | None) -> list[dict[str, str]]:
        """Resolve the platform-only uniqueCode without exposing it to the Agent."""
        payload = await _JiangsuAuthenticatedApi(source="air").get(self._STATION_DIRECTORY_PATH, [])
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


async def _resolve_station_rows(station_name: str | None, city_name: str | None, district_name: str | None) -> list[dict[str, str]]:
    return await JiangsuFaultWorkOrdersTool()._resolve_stations(_optional_identifier(station_name, "station_name"), _optional_identifier(city_name, "city_name"), _optional_identifier(district_name, "district_name"))


class JiangsuAutoInspectionTool(LLMTool):
    _METHOD = "GetAutoInspection"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_auto_inspection",
            description="读取江苏站点自动巡检的设备与小时值快照；站点未接入时返回明确状态。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_auto_inspection", "description": "按城市、区县或站点名称查询自动巡检快照。",
                             "parameters": {"type": "object", "properties": {
                                 "station_name": {"type": "string"}, "city_name": {"type": "string"}, "district_name": {"type": "string"},
                             }, "required": []}},
        )

    async def execute(self, context=None, station_name: str | None = None, city_name: str | None = None,
                      district_name: str | None = None, **_: Any) -> dict[str, Any]:
        try:
            stations = await _resolve_station_rows(station_name, city_name, district_name)
            if not stations: raise ValueError("station_name、city_name、district_name 至少提供一个")
            results = []
            for station in stations:
                payload = await _DeviceControlClient().post(self._METHOD, {"stationId": station["unique_code"]})
                results.append({"station": station, "success": bool(payload.get("Result", payload.get("success", False))),
                                "data": payload.get("Data", payload.get("data", {})), "message": payload.get("ErrorMessage") or payload.get("message")})
            success = any(item["success"] for item in results)
            return {"status": "success" if success else "empty", "success": success, "data": results,
                    "metadata": {"source": "jiangsu_qc_api", "method": self._METHOD, "station_count": len(stations), "queried_at": datetime.now().astimezone().isoformat()},
                    "summary": f"自动巡检查询完成：查询 {len(stations)} 个站点。"}
        except (ValueError, httpx.HTTPError) as exc:
            return {"status": "failed", "success": False, "data": {}, "summary": f"自动巡检查询失败：{exc}"}


class JiangsuQcTaskHistoryTool(LLMTool):
    """Read task records first; their ``rId`` and ``rStart`` drive detail tools."""

    _PATH = "operation/QualityControl/GetNewQCHisResultListAsync"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_qc_task_history",
            description="读取江苏站点历史质控任务及结果；返回的 rId、rStart 可用于继续查询状态和运行日志。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_qc_task_history", "description": "按站点、时间范围和污染物查询历史质控任务。",
                             "parameters": {"type": "object", "properties": {
                                 "station_code": {"type": "string", "description": "兼容旧调用；优先使用 station_name/city_name/district_name。"},
                                 "station_name": {"type": "string"}, "city_name": {"type": "string"}, "district_name": {"type": "string"},
                                 "start_time": {"type": "string", "description": "开始时间，YYYY-MM-DD HH:mm:ss。"},
                                 "end_time": {"type": "string", "description": "结束时间，YYYY-MM-DD HH:mm:ss。"},
                                 "pollutant": {"type": "string", "description": "可选，如 SO2、NO、CO、O3。"},
                             }, "required": ["start_time", "end_time"]}},
        )

    async def execute(self, context=None, station_code: str | None = None, station_name: str | None = None,
                      city_name: str | None = None, district_name: str | None = None, start_time: str | None = None,
                      end_time: str | None = None, pollutant: str | None = None, **_: Any) -> dict[str, Any]:
        try:
            if station_code:
                codes = [_identifier(station_code, "station_code")]
            else:
                rows = await _resolve_station_rows(station_name, city_name, district_name)
                codes = [row["station_code"] for row in rows if row.get("station_code")]
            if not codes: raise ValueError("需要提供站点或地理条件")
            records = []
            for code in codes:
                params = [("stationCode", code), *_time_range("sStart", start_time, end_time)]
                if pollutant: params.append(("poll", _identifier(pollutant, "pollutant")))
                records.extend(_list_result(await _JiangsuAuthenticatedApi(source="ops").get(self._PATH, params), "质控任务"))
            return _records_response(records, self._PATH, None, "质控任务查询完成", {"station_count": len(codes)})
        except (ValueError, httpx.HTTPError) as exc:
            return _failed("质控任务查询", exc)


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

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_qc_monitoring_curve",
            description="读取质控任务前后及期间的监测项值序列，用于生成响应曲线；只读。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_qc_monitoring_curve", "description": "按站点、污染物、质控类型和时间范围读取质控期间监测序列。",
                             "parameters": {"type": "object", "properties": {
                                 "station_code": {"type": "string", "description": "兼容旧调用；优先使用 station_name/city_name/district_name。"},
                                 "station_name": {"type": "string"}, "city_name": {"type": "string"}, "district_name": {"type": "string"},
                                 "pollutant": {"type": "string", "description": "污染物，如 SO2、NO、CO、O3。"},
                                 "qc_type": {"type": "string", "description": "质控类型，来自任务历史的 qcType。"},
                                 "start_time": {"type": "string", "description": "曲线开始时间，YYYY-MM-DD HH:mm:ss。"},
                                 "end_time": {"type": "string", "description": "曲线结束时间，YYYY-MM-DD HH:mm:ss。"},
                             }, "required": ["pollutant", "qc_type", "start_time", "end_time"]}},
        )

    async def execute(self, context=None, station_code: str | None = None, station_name: str | None = None,
                      city_name: str | None = None, district_name: str | None = None, pollutant: str | None = None,
                      qc_type: str | None = None, start_time: str | None = None, end_time: str | None = None, **_: Any) -> dict[str, Any]:
        try:
            if station_code: codes = [_identifier(station_code, "station_code")]
            else:
                rows = await _resolve_station_rows(station_name, city_name, district_name)
                codes = [row["station_code"] for row in rows if row.get("station_code")]
            if not codes: raise ValueError("需要提供站点或地理条件")
            records = []
            for code in codes:
                params = [("stationCode", code), ("poll", _identifier(pollutant, "pollutant")), ("qcType", _identifier(qc_type, "qc_type")), *_time_range("timePoint", start_time, end_time)]
                records.extend(_list_result(await _JiangsuAuthenticatedApi(source="ops").get(self._PATH, params), "质控监测曲线"))
            return _records_response(records, self._PATH, None, "质控监测曲线查询完成", {"station_count": len(codes)})
        except (ValueError, httpx.HTTPError) as exc:
            return _failed("质控监测曲线查询", exc)


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


def _normalise_place_name(value: Any) -> str:
    return str(value or "").strip().replace(" ", "").rstrip("省市区县")
