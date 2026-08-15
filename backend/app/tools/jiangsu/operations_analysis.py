"""Read-only Jiangsu operations data tools for personnel activity analysis."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class _JiangsuOperationsTool(LLMTool):
    """Shared authenticated read-only client for the Jiangsu operations API."""

    def __init__(self, *, name: str, description: str, function_schema: dict[str, Any]) -> None:
        from config.settings import settings

        self.base_url = settings.jiangsu_ops_api_base_url.rstrip("/")
        self.token_url = settings.jiangsu_ops_token_url.rstrip("/")
        self.username = settings.jiangsu_ops_api_username or settings.jiangsu_air_api_username
        self.password = settings.jiangsu_ops_api_password or settings.jiangsu_air_api_password
        self.timeout_seconds = settings.jiangsu_ops_api_timeout_seconds
        self._token: str | None = None
        self._token_lock = asyncio.Lock()
        super().__init__(
            name=name,
            description=description,
            category=ToolCategory.QUERY,
            version="1.0.0",
            function_schema=function_schema,
        )

    def _validate_config(self) -> None:
        if not self.base_url or not self.token_url or not self.username or not self.password:
            raise ValueError("未配置江苏运维接口地址、Token 地址、账号或密码")

    async def _request(self, path: str, params: list[tuple[str, Any]]) -> dict[str, Any]:
        self._validate_config()
        response = await self._get(path, params, await self._get_token())
        if response.status_code == 401:
            self._token = None
            response = await self._get(path, params, await self._get_token())
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("江苏运维接口返回格式无效")
        if payload.get("success") is False:
            raise ValueError(str(payload.get("msg") or payload.get("message") or "江苏运维接口返回失败"))
        return payload

    async def _get_token(self) -> str:
        if self._token:
            return self._token
        async with self._token_lock:
            if self._token:
                return self._token
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.token_url, params={"UserName": self.username, "Pwd": self.password})
            response.raise_for_status()
            payload = response.json()
            token = payload.get("result") if isinstance(payload, dict) else None
            if not isinstance(payload, dict) or not payload.get("success") or not isinstance(token, str) or not token:
                raise ValueError(str(payload.get("msg") if isinstance(payload, dict) else "江苏运维接口 Token 获取失败"))
            self._token = token
            return token

    async def _get(self, path: str, params: list[tuple[str, Any]], token: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            return await client.get(
                f"{self.base_url}/{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}", "SysCode": "SunOps", "Accept": "application/json"},
            )

    @staticmethod
    def _page(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        result = payload.get("result", payload)
        if isinstance(result, list):
            return result, len(result)
        if not isinstance(result, dict):
            raise ValueError("江苏运维接口返回 result 无效")
        records = result.get("items", result.get("data", result.get("records", [])))
        if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
            raise ValueError("江苏运维接口返回记录列表无效")
        return records, int(result.get("totalCount", result.get("total", len(records))))


class JiangsuAttendanceRecordsTool(_JiangsuOperationsTool):
    """Fetch personnel station sign-in records, not continuous location tracking."""

    _PATH = "operation/AirCityAPPAttendance/GetAttendanceManagement"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_attendance_records",
            description="查询江苏运维人员到站签到记录（含站点、时间、定位、距站距离）；仅用于分析，不代表连续轨迹或签退记录。",
            function_schema={
                "name": "jiangsu_fetch_attendance_records",
                "description": "按人员、单位、站点和时间范围读取运维人员到站签到记录。仅只读查询。",
                "parameters": {"type": "object", "properties": {
                    "start_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss"},
                    "end_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss"},
                    "user_name": {"type": "string", "description": "可选人员姓名。"},
                    "unit_id": {"type": "string", "description": "可选运维单位编码。"},
                    "station_code": {"type": "string", "description": "可选站点编码。"},
                    "skip_count": {"type": "integer", "minimum": 0, "default": 0},
                    "max_result_count": {"type": "integer", "minimum": 1, "maximum": 500, "default": 200},
                }, "required": ["start_time", "end_time"]},
            },
        )

    async def execute(self, context=None, start_time: str | None = None, end_time: str | None = None,
                      user_name: str | None = None, unit_id: str | None = None, station_code: str | None = None,
                      skip_count: int = 0, max_result_count: int = 200, **_: Any) -> dict[str, Any]:
        try:
            self._validate(start_time, end_time, skip_count, max_result_count)
            params: list[tuple[str, Any]] = [
                ("warrantytime[0]", start_time or ""), ("warrantytime[1]", end_time or ""),
                ("skipCount", skip_count), ("maxResultCount", max_result_count),
            ]
            for key, value in (("UserName", user_name), ("UnitID", unit_id), ("StationCode", station_code)):
                if value and value.strip():
                    params.append((key, value.strip()))
            records, total_count = self._page(await self._request(self._PATH, params))
            return {
                "status": "success" if records else "empty", "success": True, "data": records,
                "metadata": {"source": "jiangsu_operations_attendance_api", "endpoint": self._PATH,
                             "time_range": [start_time, end_time], "filters": {"user_name": user_name, "unit_id": unit_id, "station_code": station_code},
                             "pagination": {"skip_count": skip_count, "max_result_count": max_result_count},
                             "record_count": len(records), "total_count": total_count, "queried_at": datetime.now().astimezone().isoformat()},
                "summary": f"江苏运维人员到站签到记录查询完成：返回 {len(records)} 条，共 {total_count} 条。",
            }
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("jiangsu_attendance_records_failed", error=str(exc))
            return {"status": "failed", "success": False, "data": [], "summary": f"江苏运维人员签到记录查询失败：{exc}"}

    @staticmethod
    def _validate(start_time: str | None, end_time: str | None, skip_count: int, max_result_count: int) -> None:
        try:
            start, end = (datetime.fromisoformat((value or "").replace("Z", "+00:00")) for value in (start_time, end_time))
        except ValueError as exc:
            raise ValueError("时间必须为 YYYY-MM-DD HH:mm:ss 格式") from exc
        if start > end or (end - start).days > 93:
            raise ValueError("时间范围必须有效且单次不超过 93 天")
        if not isinstance(skip_count, int) or skip_count < 0:
            raise ValueError("skip_count 必须是非负整数")
        if not isinstance(max_result_count, int) or not 1 <= max_result_count <= 500:
            raise ValueError("max_result_count 必须在 1 到 500 之间")


class JiangsuStationDirectoryTool(_JiangsuOperationsTool):
    """Fetch enabled station directory used to interpret sign-in locations."""

    _PATH = "operation/AirOperaBase/GetOpaEnabledStationAsync"

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_fetch_station_directory",
            description="查询江苏运维可用站点台账，用于获取站点城市、运维单位和空间位置等分析上下文。",
            function_schema={
                "name": "jiangsu_fetch_station_directory",
                "description": "只读获取江苏运维站点台账；可用站点编码筛选，避免将台账用于修改站点。",
                "parameters": {"type": "object", "properties": {
                    "station_codes": {"type": "array", "items": {"type": "string"}, "maxItems": 100, "description": "可选站点编码筛选。"},
                }},
            },
        )

    async def execute(self, context=None, station_codes: list[str] | None = None, **_: Any) -> dict[str, Any]:
        try:
            if station_codes is not None and (len(station_codes) > 100 or not all(isinstance(item, str) and item.strip() for item in station_codes)):
                raise ValueError("station_codes 最多 100 个，且必须均为有效站点编码")
            records, total_count = self._page(await self._request(self._PATH, []))
            requested = {item.strip() for item in station_codes or []}
            if requested:
                records = [item for item in records if str(item.get("stationCode") or item.get("StationCode") or "").strip() in requested]
            return {
                "status": "success" if records else "empty", "success": True, "data": records,
                "metadata": {"source": "jiangsu_operations_station_directory_api", "endpoint": self._PATH,
                             "station_codes": sorted(requested), "record_count": len(records), "total_count": total_count,
                             "queried_at": datetime.now().astimezone().isoformat()},
                "summary": f"江苏运维站点台账查询完成：返回 {len(records)} 条记录。",
            }
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("jiangsu_station_directory_failed", error=str(exc))
            return {"status": "failed", "success": False, "data": [], "summary": f"江苏运维站点台账查询失败：{exc}"}
