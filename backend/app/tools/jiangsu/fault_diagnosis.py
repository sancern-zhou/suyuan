"""Read-only Jiangsu data tools for focused station fault diagnosis."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

import httpx
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.jiangsu.device_control import _DeviceControlClient
from app.tools.jiangsu.station_data import JiangsuStationDataTool
from app.tools.resource_declarations import resources_for_visuals

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
            description="读取江苏站房设备告警日志、告警统计与设备告警状态；仅用于巡检和故障诊断。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_station_alarm_logs", "description": "按站点名称、平台编码、唯一编码、城市或区县读取站房设备告警。",
                             "parameters": {"type": "object", "properties": {
                                 "station_name": {"type": "string"}, "station_code": {"type": "string", "description": "平台站点编码，例如 5006A。"},
                                 "unique_code": {"type": "string", "description": "站点唯一编码。"},
                                 "city_name": {"type": "string"}, "district_name": {"type": "string"},
                             }, "required": []}},
        )

    async def execute(self, context=None, station_name: str | None = None, city_name: str | None = None,
                      district_name: str | None = None, station_code: str | None = None,
                      unique_code: str | None = None, **_: Any) -> dict[str, Any]:
        try:
            # A platform station code is already sufficient for this endpoint;
            # keep the legacy direct path and avoid an unnecessary directory call.
            # A unique code still needs directory resolution to obtain its station code.
            stations = ([{"station_code": _identifier(station_code, "station_code"), "unique_code": ""}]
                        if station_code and not unique_code else await _resolve_station_rows(
                            station_name, city_name, district_name,
                            station_code=station_code, unique_code=unique_code,
                        ))
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
    return await JiangsuFaultWorkOrdersTool()._resolve_stations(
        _optional_identifier(station_name, "station_name"),
        _optional_identifier(city_name, "city_name"),
        _optional_identifier(district_name, "district_name"),
    )


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

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_auto_inspection",
            description="读取江苏站点自动巡检快照并按平台规则计算异常分类、状态统计和评分；单站成功时返回站房可视化资源；支持具体站点、城市/区县下辖站点。",
            category=ToolCategory.QUERY,
            function_schema={"name": "jiangsu_fetch_auto_inspection", "description": "按城市、区县或站点名称查询自动巡检快照。",
                             "parameters": {"type": "object", "properties": {
                                 "station_name": {"type": "string", "description": "站点名称。"},
                                 "station_code": {"type": "string", "description": "平台站点编码，例如 5006A。"},
                                 "unique_code": {"type": "string", "description": "平台唯一编码；已知时可直接使用。"},
                                 "city_name": {"type": "string", "description": "城市名称，查询该城市下辖站点。"},
                                 "district_name": {"type": "string", "description": "区县名称，查询该区县下辖站点。"},
                             }, "required": []}},
        )

    async def execute(self, context=None, station_name: str | None = None, city_name: str | None = None,
                      district_name: str | None = None, station_code: str | None = None,
                      unique_code: str | None = None, **_: Any) -> dict[str, Any]:
        try:
            stations = await _resolve_station_rows(
                station_name, city_name, district_name,
                station_code=station_code, unique_code=unique_code,
            )
            if not stations: raise ValueError("station_name、city_name、district_name 至少提供一个")
            results = []
            for station in stations:
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
                if not has_snapshot and len(stations) == 1:
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
                issues = _inspection_issues(raw_data)
                results.append({
                    "station": station,
                    "success": success,
                    "data": raw_data,
                    "issues": issues,
                    "issue_count": len(issues),
                    "message": payload.get("ErrorMessage") or payload.get("message"),
                })
            success = any(item["success"] for item in results)
            issue_count = sum(item["issue_count"] for item in results)
            for item in results:
                item["inspection_metrics"] = _inspection_metrics(item.get("data", {}), item.get("issues", []))
            visuals = []
            if len(results) == 1 and results[0].get("success"):
                station = results[0]["station"]
                visual = _stationhouse_visual(
                    station,
                    results[0].get("data", {}),
                    results[0].get("issues", []),
                    results[0].get("inspection_metrics", {}),
                )
                visuals.append(visual)
            return {"status": "success" if success else "empty", "success": success, "data": results,
                    "metadata": {"source": "jiangsu_qc_api", "method": self._METHOD, "station_count": len(stations),
                                 "issue_count": issue_count, "queried_at": datetime.now().astimezone().isoformat(),
                                 "visual_behavior": "stationhouse_effect" if visuals else "none"},
                    **({"visuals": visuals, "resources": resources_for_visuals(visuals, tool_name=self.name)} if visuals else {}),
                    "summary": f"自动巡检查询完成：查询 {len(stations)} 个站点，识别 {issue_count} 项异常。"}
        except (ValueError, httpx.HTTPError) as exc:
            return {"status": "failed", "success": False, "data": {}, "summary": f"自动巡检查询失败：{exc}"}


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


def _normalise_place_name(value: Any) -> str:
    return str(value or "").strip().replace(" ", "").rstrip("省市区县")
