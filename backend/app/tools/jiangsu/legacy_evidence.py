"""Adapters for evidence sources used by the legacy AI review workbench.

The legacy workbench read some sources through application services that are
not represented by the current smart-event tools.  This module keeps those
endpoints behind a small, auditable adapter contract.  A missing platform
endpoint is returned as an explicit ``unavailable`` result instead of being
silently treated as an empty query.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any

from app.tools.jiangsu.fault_diagnosis import _JiangsuAuthenticatedApi


def _payload_data(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    return payload.get("result") if payload.get("result") is not None else payload.get("data", payload)


def _records(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "list", "rows", "records", "data", "result"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def _result(*, endpoint: str, data: Any, query: dict[str, Any], success: bool = True, status: str | None = None, summary: str | None = None) -> dict[str, Any]:
    rows = _records(data)
    final_status = status or ("success" if rows else "empty")
    return {
        "success": success,
        "status": final_status,
        "summary": summary or f"{endpoint} 查询完成：返回 {len(rows)} 条记录。",
        "metadata": {
            "source": "jiangsu_legacy_review_api",
            "endpoint": endpoint,
            "query": query,
            "record_count": len(rows),
            "queried_at": datetime.now().astimezone().isoformat(),
        },
        "record_count": len(rows),
        "data": data if data is not None else [],
    }


class JiangsuLegacyEvidenceAdapter:
    """Read legacy review evidence through the current authenticated gateway."""

    _INSTRUMENT_5MIN_PATH = "airdata/Moniter5MinData/GetMoniter5MinStationDataListAsync"
    _INSTRUMENT_HOUR_PATH = "airdata/MoniterHData/GetMoniterStationDataListAsync"
    _ACQUISITION_ALARM_PATH = "stationintegrate/StationIntegrate/GetAlarmLogListAsync"
    _DOOR_PATH = "stationintegrate/HK/GetACSDoorRecordsAsync"

    def __init__(self, *, retries: int = 2) -> None:
        self.retries = max(1, int(retries))

    async def _post_retry(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                return await _JiangsuAuthenticatedApi(source="air").post(path, payload)
            except Exception as exc:  # noqa: BLE001 - preserve source failure in package
                last_error = exc
                if attempt + 1 < self.retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
        raise last_error or RuntimeError("江苏旧审核接口请求失败")

    async def _get_retry(self, path: str, params: list[tuple[str, str]]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                return await _JiangsuAuthenticatedApi(source="air").get(path, params)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt + 1 < self.retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
        raise last_error or RuntimeError("江苏旧审核接口请求失败")

    async def instrument_status(self, *, station_code: str, start_time: str, end_time: str, pollutant_codes: list[str] | None = None) -> dict[str, Any]:
        query = {"station_code": station_code, "start_time": start_time, "end_time": end_time, "pollutant_codes": pollutant_codes or []}
        payload_base = {"Codes": [station_code], "PollutantCodes": pollutant_codes or [], "StartTime": start_time, "EndTime": end_time}
        try:
            minute_payload, hour_payload = await asyncio.gather(
                self._post_retry(self._INSTRUMENT_5MIN_PATH, payload_base),
                self._post_retry(self._INSTRUMENT_HOUR_PATH, payload_base),
            )
            minute_data, hour_data = _payload_data(minute_payload), _payload_data(hour_payload)
            minute_rows, hour_rows = _records(minute_data), _records(hour_data)
            return {
                "success": True,
                "status": "success" if minute_rows or hour_rows else "empty",
                "summary": f"仪器状态查询完成：五分钟 {len(minute_rows)} 条，小时 {len(hour_rows)} 条。",
                "metadata": {"source": "jiangsu_legacy_review_api", "endpoints": [self._INSTRUMENT_5MIN_PATH, self._INSTRUMENT_HOUR_PATH], "query": query, "record_count": len(minute_rows) + len(hour_rows), "queried_at": datetime.now().astimezone().isoformat()},
                "record_count": len(minute_rows) + len(hour_rows),
                "data": {"five_minute": minute_data, "hour": hour_data},
            }
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "status": "failed", "summary": f"仪器状态查询失败：{exc}", "metadata": {"query": query}, "record_count": 0, "data": []}

    async def acquisition_alarms(self, *, station_code: str, start_time: str, end_time: str) -> dict[str, Any]:
        query = {"station_code": station_code, "start_time": start_time, "end_time": end_time}
        params = [("StationCode", station_code), ("TimePoint", start_time), ("TimePoint", end_time)]
        try:
            payload = await self._get_retry(self._ACQUISITION_ALARM_PATH, params)
            return _result(endpoint=self._ACQUISITION_ALARM_PATH, data=_payload_data(payload), query=query, summary="数采报警查询完成。")
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "status": "failed", "summary": f"数采报警查询失败：{exc}", "metadata": {"endpoint": self._ACQUISITION_ALARM_PATH, "query": query}, "record_count": 0, "data": []}

    async def platform_alarms(self, *, station_code: str, start_time: str, end_time: str) -> dict[str, Any]:
        endpoint = os.getenv("JIANGSU_PLATFORM_ALARM_ENDPOINT", "").strip()
        query = {"station_code": station_code, "start_time": start_time, "end_time": end_time}
        if not endpoint:
            return {"success": False, "status": "unavailable", "summary": "旧工作台平台报警来自 ALMsummary 数据库仓储，当前平台未提供可查询 API。", "metadata": {"source": "legacy_alm_summary", "query": query, "configuration": "JIANGSU_PLATFORM_ALARM_ENDPOINT 未配置"}, "record_count": 0, "data": []}
        try:
            params = [("StationCode", station_code), ("StartTime", start_time), ("EndTime", end_time)]
            payload = await self._get_retry(endpoint, params)
            return _result(endpoint=endpoint, data=_payload_data(payload), query=query, summary="平台报警查询完成。")
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "status": "failed", "summary": f"平台报警查询失败：{exc}", "metadata": {"endpoint": endpoint, "query": query}, "record_count": 0, "data": []}

    async def door_records(self, *, station_code: str, start_time: str, end_time: str, max_result_count: int = 1000) -> dict[str, Any]:
        query = {"station_code": station_code, "start_time": start_time, "end_time": end_time, "max_result_count": max_result_count}
        params = [("StationCode", station_code), ("EventTime", start_time), ("EventTime", end_time), ("MaxResultCount", str(max_result_count))]
        try:
            payload = await self._get_retry(self._DOOR_PATH, params)
            data = _payload_data(payload)
            rows = _records(data)
            return _result(endpoint=self._DOOR_PATH, data=data, query=query, summary=f"门禁记录查询完成：返回 {len(rows)} 条记录。")
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "status": "failed", "summary": f"门禁记录查询失败：{exc}", "metadata": {"endpoint": self._DOOR_PATH, "query": query}, "record_count": 0, "data": []}
