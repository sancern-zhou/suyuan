"""Read-only client for Jiangsu provincial station air-quality data."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.jiangsu.result_filter import compact_air_quality_records, externalize_compact_records

logger = structlog.get_logger(__name__)


class JiangsuStationDataTool(LLMTool):
    """Fetch station hour, day, or five-minute observations from the Jiangsu API."""

    _ENDPOINTS = {
        "station_hour": "airdata/DATStationHour/GetStationHourDataListAsync",
        "station_day": "airdata/DATStationDay/GetStationDayDataListAsync",
        "station_5minute": "airdata/DATStation5Minute/GetStation5MinuteDataListAsync",
    }
    _DATA_TYPES = {
        0: "原始实况（工况）",
        1: "审核实况（工况）",
        2: "原始标况",
        3: "审核标况",
    }

    def __init__(
        self,
        *,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        from config.settings import settings

        self.base_url = (base_url or settings.jiangsu_air_api_base_url).rstrip("/")
        self.username = username if username is not None else settings.jiangsu_air_api_username
        self.password = password if password is not None else settings.jiangsu_air_api_password
        self.timeout_seconds = timeout_seconds or settings.jiangsu_air_api_timeout_seconds
        self._token: str | None = None
        self._token_lock = asyncio.Lock()
        self._station_directory: list[dict[str, Any]] | None = None
        self._station_directory_lock = asyncio.Lock()
        super().__init__(
            name="jiangsu_fetch_station_data",
            description="查询江苏省空气监测站的小时、日均或5分钟原始/审核、工况/标况数据。",
            category=ToolCategory.QUERY,
            version="1.0.0",
            function_schema={
                "name": "jiangsu_fetch_station_data",
                "description": (
                    "从江苏省站点数据接口读取数据。仅用于查询，不能修改源系统。"
                    "返回数据来源、查询条件、数据类型和记录数，结论必须引用这些信息。超过24条过滤后结果将外部化保存，data仅返回首尾样本，file_path可供按需读取。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "data_kind": {
                            "type": "string",
                            "enum": ["station_hour", "station_day", "station_5minute"],
                            "description": "站点小时、日均或5分钟数据。",
                        },
                        "station_codes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "江苏平台站点编码，例如 1002A；已知编码时使用。",
                        },
                        "station_names": {"type": "array", "items": {"type": "string"}, "description": "站点名称；工具内部解析站点编码。"},
                        "city_names": {"type": "array", "items": {"type": "string"}, "description": "城市或“江苏省”；工具内部展开其下辖全部站点。"},
                        "district_names": {"type": "array", "items": {"type": "string"}, "description": "区县名称；工具内部展开其下辖全部站点。"},
                        "start_time": {"type": "string", "description": "开始时间，格式 YYYY-MM-DD HH:mm:ss。"},
                        "end_time": {"type": "string", "description": "结束时间，格式 YYYY-MM-DD HH:mm:ss。"},
                        "data_type": {
                            "type": "integer",
                            "enum": [0, 1, 2, 3],
                            "description": "0原始工况、1审核工况、2原始标况、3审核标况；默认0。",
                        },
                        "pollutant_codes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "仅5分钟数据可选，例如 PM2_5、O3、SO2。",
                        },
                    },
                    "required": ["data_kind", "start_time", "end_time"],
                },
            },
        )

    async def execute(
        self,
        context=None,
        data_kind: str | None = None,
        station_codes: list[str] | None = None,
        station_names: list[str] | None = None,
        city_names: list[str] | None = None,
        district_names: list[str] | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        data_type: int = 0,
        pollutant_codes: list[str] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        try:
            station_codes = await self._resolve_station_codes(station_codes, station_names, city_names, district_names)
            self._validate(data_kind, station_codes, start_time, end_time, data_type, pollutant_codes)
            payload: dict[str, Any] = {
                "codes": [item.strip() for item in station_codes or []],
                "timePoint": [start_time, end_time],
                "dataType": data_type,
            }
            if data_kind == "station_5minute" and pollutant_codes:
                payload["pollutantCodes"] = [item.strip() for item in pollutant_codes if item.strip()]

            records: list[Any] = []
            # The upstream endpoint accepts at most 100 codes, while a city can
            # own more.  It remains one Agent tool call and batches internally.
            for start in range(0, len(payload["codes"]), 100):
                request_payload = {**payload, "codes": payload["codes"][start:start + 100]}
                response = await self._request(data_kind or "", request_payload)
                batch = response.get("result") or []
                if not isinstance(batch, list):
                    raise ValueError("江苏接口返回 result 不是数据列表")
                records.extend(batch)
            compact_records, filter_metadata = compact_air_quality_records(records)
            raw_file_path = None
            if context is not None and len(records) > 24:
                raw_file_path = context.save_data(
                    data=records,
                    schema=f"jiangsu_{data_kind}_raw",
                    metadata={"source_tool": self.name, "record_count": len(records), "filtered": True},
                )
            inline_records, filtered_file_path, externalization = externalize_compact_records(
                compact_records,
                context=context,
                schema=f"jiangsu_{data_kind}_latest",
                metadata={"source_tool": self.name, "source_record_count": len(records)},
            )
            metadata = {
                "source": "jiangsu_air_province_api",
                "endpoint": self._ENDPOINTS[data_kind or ""],
                "data_kind": data_kind,
                "data_type": data_type,
                "data_type_label": self._DATA_TYPES[data_type],
                "station_codes": payload["codes"],
                "station_names": station_names or [], "city_names": city_names or [], "district_names": district_names or [],
                "time_range": [start_time, end_time],
                "record_count": len(compact_records),
                "queried_at": datetime.now().astimezone().isoformat(),
                **filter_metadata,
            }
            if raw_file_path:
                metadata["raw_data_file_path"] = raw_file_path
            metadata["context_data"] = externalization
            return {
                "status": "success" if compact_records else "empty",
                "success": True,
                "data": inline_records,
                "metadata": metadata,
                "summary": f"江苏站点{data_kind}查询完成：原始 {len(records)} 条，去重并保留各站最新 {len(compact_records)} 条（{self._DATA_TYPES[data_type]}）。",
                **{key: externalization[key] for key in ("data_complete", "record_count", "returned_records", "sample_strategy")},
                **({"file_path": filtered_file_path} if filtered_file_path else {}),
            }
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("jiangsu_station_data_failed", error=str(exc), data_kind=data_kind)
            return {"status": "failed", "success": False, "data": [], "summary": f"江苏站点数据查询失败：{exc}"}
        except Exception:
            logger.exception("jiangsu_station_data_unexpected_error", data_kind=data_kind)
            return {"status": "failed", "success": False, "data": [], "summary": "江苏站点数据查询发生未预期错误。"}

    def _validate(self, data_kind, station_codes, start_time, end_time, data_type, pollutant_codes) -> None:
        if data_kind not in self._ENDPOINTS:
            raise ValueError("data_kind 必须为 station_hour、station_day 或 station_5minute")
        if not station_codes or not all(isinstance(item, str) and item.strip() for item in station_codes):
            raise ValueError("station_codes 至少需要一个有效站点编码")
        if len(station_codes) > 2000:
            raise ValueError("单次最多查询 2000 个站点")
        try:
            start = datetime.fromisoformat((start_time or "").replace("Z", "+00:00"))
            end = datetime.fromisoformat((end_time or "").replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("时间必须为 YYYY-MM-DD HH:mm:ss 格式") from exc
        if start > end:
            raise ValueError("start_time 不能晚于 end_time")
        max_days = 7 if data_kind == "station_5minute" else 31
        if (end - start).days > max_days:
            raise ValueError(f"{data_kind} 单次查询时间范围不能超过 {max_days} 天")
        if data_type not in self._DATA_TYPES:
            raise ValueError("data_type 必须为 0、1、2 或 3")
        if pollutant_codes and data_kind != "station_5minute":
            raise ValueError("pollutant_codes 仅支持 station_5minute")
        if not self.base_url or not self.username or not self.password:
            raise ValueError("未配置江苏省数据接口地址、账号或密码")

    async def _request(self, data_kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        token = await self._get_token()
        response = await self._post(data_kind, payload, token)
        if response.status_code == 401:
            self._token = None
            response = await self._post(data_kind, payload, await self._get_token())
        response.raise_for_status()
        result = response.json()
        if not result.get("success") or int(result.get("state", 500)) != 200:
            raise ValueError(str(result.get("msg") or "江苏接口返回失败"))
        return result

    async def _resolve_station_codes(self, station_codes, station_names, city_names, district_names) -> list[str]:
        direct = [str(code).strip() for code in station_codes or [] if str(code).strip()]
        selectors = [*(station_names or []), *(city_names or []), *(district_names or [])]
        if not selectors:
            return list(dict.fromkeys(direct))
        async with self._station_directory_lock:
            if self._station_directory is None:
                self._station_directory = await self._get_station_directory()
        rows = self._station_directory or []
        normalise = lambda value: str(value or "").strip().replace(" ", "").rstrip("省市区县")
        codes = list(direct)
        for name in station_names or []:
            matches = [str(row["stationCode"]) for row in rows if normalise(row.get("positionName")) == normalise(name)]
            if not matches:
                raise ValueError(f"未在江苏站点目录中找到“{name}”")
            codes.extend(matches)
        for city in city_names or []:
            matches = [str(row["stationCode"]) for row in rows if normalise(city) == normalise(row.get("provinceName")) or normalise(city) == normalise(row.get("cityName"))]
            if not matches:
                raise ValueError(f"未在江苏站点目录中找到“{city}”下辖站点")
            codes.extend(matches)
        for district in district_names or []:
            matches = [str(row["stationCode"]) for row in rows if normalise(district) == normalise(row.get("districtName"))]
            if not matches:
                raise ValueError(f"未在江苏站点目录中找到“{district}”下辖站点")
            codes.extend(matches)
        return list(dict.fromkeys(codes))

    async def _get_station_directory(self) -> list[dict[str, Any]]:
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
                f"{self.base_url}/AirCityProductBase/GetAllEnabledBSDStationAsync",
                headers={"Authorization": f"Bearer {token}", "SysCode": "SunAirProvince"},
            )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success") or int(payload.get("state", 500)) != 200:
            raise ValueError(str(payload.get("msg") or "江苏站点目录查询失败"))
        return [item for item in payload.get("result") or [] if isinstance(item, dict) and item.get("stationCode")]

    async def _get_token(self) -> str:
        if self._token:
            return self._token
        async with self._token_lock:
            if self._token:
                return self._token
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(
                    f"{self.base_url}/AirCityBaseCommon/GetExternalApiToken",
                    params={"UserName": self.username, "Pwd": self.password},
                )
            response.raise_for_status()
            payload = response.json()
            token = payload.get("result")
            if not payload.get("success") or not isinstance(token, str) or not token:
                raise ValueError(str(payload.get("msg") or "江苏接口 Token 获取失败"))
            self._token = token
            return token

    async def _post(self, data_kind: str, payload: dict[str, Any], token: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            return await client.post(
                f"{self.base_url}/{self._ENDPOINTS[data_kind]}",
                json=payload,
                headers={"Authorization": f"Bearer {token}", "SysCode": "SunAirProvince"},
            )
