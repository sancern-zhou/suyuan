"""Read-only client for Jiangsu provincial station air-quality data."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.jiangsu.result_filter import compact_air_quality_records, externalize_compact_records
from app.tools.jiangsu.station_type import filter_station_rows, normalize_station_type

logger = structlog.get_logger(__name__)


class JiangsuStationDataTool(LLMTool):
    """Fetch station hour, day, or five-minute observations from the Jiangsu API."""

    _BATCH_SIZE = 100
    _MAX_BATCH_ATTEMPTS = 3
    _PROVINCE_SELECTORS = {
        "江苏",
        "江苏省",
        "全省",
        "江苏全省",
        "全江苏",
        "全江苏省",
    }

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
            description="查询江苏省空气监测站的小时、日均或5分钟原始/审核、工况/标况数据，支持国控、省控、市控站点筛选。",
            category=ToolCategory.QUERY,
            version="1.0.0",
            function_schema={
                "name": "jiangsu_fetch_station_data",
                "description": (
                    "读取站点明细数据（小时、日均或5分钟原始/审核、工况/标况），用于查看原始明细、核对有效天数或自定义时间粒度的分析；"
                    "凡询问均值浓度、排名、综合指数、最高/最低站点等平台已有统计口径的问题，必须优先调用 jiangsu_query_statistics 直接查询，"
                    "不要用本工具拉取明细后自行求平均或排序。"
                    "按江苏省、市、区县、站点名称或编码读取下辖站点数据；区域和站点编码由工具内部实时目录解析，"
                    "一次调用内受控串行分批，禁止由 Agent 拆成逐站并发查询。"
                    "全省查询成本很高，仅在用户明确要求且确有必要时使用，并必须传 allow_province_query=true；"
                    "全省小时数据最多查询 6 小时、日均最多 7 天、5 分钟数据最多 1 小时。应优先缩小到市或区县。"
                    "仅用于查询，不能修改源系统。"
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
                            "minItems": 1,
                            "description": "已知的江苏平台站点编码；多个站点应在一次调用中传入，禁止拆成并发工具调用。",
                        },
                        "station_names": {
                            "type": "array", "items": {"type": "string"}, "minItems": 1,
                            "description": "站点名称；工具内部解析站点编码。",
                        },
                        "city_names": {
                            "type": "array", "items": {"type": "string"}, "minItems": 1,
                            "description": "江苏省辖市名称，例如南京市、苏州市；工具内部展开其下辖全部站点。用户明确要求全省时，也可传江苏省/全省并同时显式确认 allow_province_query。",
                        },
                        "district_names": {
                            "type": "array", "items": {"type": "string"}, "minItems": 1,
                            "description": "江苏区县名称，例如江宁区；工具内部展开其下辖全部站点。可写成“南京市江宁区”以消除同名歧义。",
                        },
                        "station_type": {
                            "type": "string",
                            "enum": ["国控", "省控", "市控", "全部"],
                            "default": "国控",
                            "description": "站点类型筛选；按城市、区县或站点名称解析时默认国控，可选省控、市控或全部。",
                        },
                        "allow_province_query": {
                            "type": "boolean", "default": False,
                            "description": "仅当用户明确要求全省站点且确有必要时设为 true。全省查询会增加接口负载并产生大量结果；默认 false。",
                        },
                        "start_time": {"type": "string", "description": "开始时间，格式 YYYY-MM-DD HH:mm:ss。"},
                        "end_time": {"type": "string", "description": "结束时间，格式 YYYY-MM-DD HH:mm:ss。"},
                        "data_type": {
                            "type": "integer",
                            "enum": [0, 1, 2, 3],
                            "default": 1,
                            "description": "0原始工况、1审核工况、2原始标况、3审核标况；默认1（审核工况）。",
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
            requires_context=True,
        )

    async def execute(
        self,
        context=None,
        data_kind: str | None = None,
        station_codes: list[str] | None = None,
        station_names: list[str] | None = None,
        city_names: list[str] | None = None,
        district_names: list[str] | None = None,
        station_type: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        data_type: int = 1,
        pollutant_codes: list[str] | None = None,
        allow_province_query: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        try:
            effective_station_type = normalize_station_type(station_type, allow_all=True) or "国控"
            self._validate_agent_scope(
                station_codes=station_codes,
                station_names=station_names,
                city_names=city_names,
                district_names=district_names,
                station_type=station_type,
                allow_province_query=allow_province_query,
            )
            records, payload = await self.fetch_raw_records(
                data_kind=data_kind,
                station_codes=station_codes,
                station_names=station_names,
                city_names=city_names,
                district_names=district_names,
                start_time=start_time,
                end_time=end_time,
                data_type=data_type,
                pollutant_codes=pollutant_codes,
                allow_province_query=allow_province_query,
                station_type=station_type,
            )
            compact_records, filter_metadata = compact_air_quality_records(records)
            raw_file_path = None
            if context is not None and len(records) > 24:
                raw_file_path = context.save_data(
                    data=records,
                    schema=f"jiangsu_{data_kind}_raw",
                    metadata={"source_tool": self.name, "record_count": len(records), "filtered": False},
                )
            inline_records, filtered_file_path, externalization = externalize_compact_records(
                compact_records,
                context=context,
                schema=f"jiangsu_{data_kind}_filtered",
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
                "station_type": effective_station_type,
                "province_query": payload.get("province_query", False),
                "batching": payload.get("batching", {}),
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
                "summary": f"江苏站点{data_kind}查询完成：原始 {len(records)} 条，清洗并删除完全重复记录后保留完整时间序列 {len(compact_records)} 条（{self._DATA_TYPES[data_type]}）。",
                **{key: externalization[key] for key in ("data_complete", "record_count", "returned_records", "sample_strategy")},
                **({"file_path": filtered_file_path} if filtered_file_path else {}),
            }
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("jiangsu_station_data_failed", error=str(exc), data_kind=data_kind)
            return {"status": "failed", "success": False, "data": [], "summary": f"江苏站点数据查询失败：{exc}"}
        except Exception:
            logger.exception("jiangsu_station_data_unexpected_error", data_kind=data_kind)
            return {"status": "failed", "success": False, "data": [], "summary": "江苏站点数据查询发生未预期错误。"}

    def _validate_agent_scope(
        self,
        *,
        station_codes: list[str] | None,
        station_names: list[str] | None,
        city_names: list[str] | None,
        district_names: list[str] | None,
        station_type: str | None,
        allow_province_query: bool,
    ) -> None:
        selectors = [station_codes, station_names, city_names, district_names]
        if not any(selectors):
            raise ValueError("请至少提供 station_codes、station_names、city_names 或 district_names 中的一项")
        for values in selectors:
            if values is not None and (
                not values or not all(isinstance(item, str) and item.strip() for item in values)
            ):
                raise ValueError("站点编码和区域/站点名称必须是非空字符串数组")
        if station_type is not None and normalize_station_type(station_type, allow_all=True) is None:
            raise ValueError("station_type 必须为 国控、省控、市控 或 全部")
        province_requested = any(
            "".join(item.split()) in self._PROVINCE_SELECTORS for item in city_names or []
        )
        if province_requested and not allow_province_query:
            raise ValueError(
                "全省站点查询数据量和接口负载较大；仅在用户明确要求且确有必要时设置 allow_province_query=true，"
                "否则请优先指定省辖市或区县"
            )

    async def fetch_raw_records(
        self,
        *,
        data_kind: str | None,
        station_codes: list[str] | None = None,
        station_names: list[str] | None = None,
        city_names: list[str] | None = None,
        district_names: list[str] | None = None,
        station_type: str | None = None,
        start_time: str | None,
        end_time: str | None,
        data_type: int = 1,
        pollutant_codes: list[str] | None = None,
        allow_province_query: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Return the unfiltered time series for deterministic background checks.

        The Agent-facing ``execute`` response intentionally compacts station
        observations.  Background anomaly detection needs the complete bounded
        series, so it uses this public read-only method instead of depending on
        private HTTP helpers.
        """
        resolved_codes = await self._resolve_station_codes(
            station_codes, station_names, city_names, district_names, station_type=station_type
        )
        self._validate(
            data_kind, resolved_codes, start_time, end_time, data_type, pollutant_codes,
            province_query=self._is_province_query(city_names),
            allow_province_query=allow_province_query,
        )
        payload: dict[str, Any] = {
            "codes": [item.strip() for item in resolved_codes],
            "timePoint": [start_time, end_time],
            "dataType": data_type,
            "province_query": self._is_province_query(city_names),
        }
        if data_kind == "station_5minute" and pollutant_codes:
            payload["pollutantCodes"] = [
                item.strip() for item in pollutant_codes if item.strip()
            ]

        records: list[dict[str, Any]] = []
        retry_count = 0
        batch_count = 0
        # Keep upstream access deliberately serial. A province/city/district
        # expansion remains one Agent tool call and never fans out into
        # concurrent per-station calls.
        for start in range(0, len(payload["codes"]), self._BATCH_SIZE):
            request_payload = {
                "codes": payload["codes"][start : start + self._BATCH_SIZE],
                "timePoint": payload["timePoint"],
                "dataType": payload["dataType"],
            }
            if "pollutantCodes" in payload:
                request_payload["pollutantCodes"] = payload["pollutantCodes"]
            response, retries = await self._request_with_retry(data_kind or "", request_payload)
            retry_count += retries
            batch_count += 1
            batch = response.get("result") or []
            if not isinstance(batch, list):
                raise ValueError("江苏接口返回 result 不是数据列表")
            records.extend(item for item in batch if isinstance(item, dict))
        payload["batching"] = {
            "strategy": "serial",
            "batch_size": self._BATCH_SIZE,
            "batch_count": batch_count,
            "retry_count": retry_count,
        }
        return records, payload

    def _validate(
        self, data_kind, station_codes, start_time, end_time, data_type, pollutant_codes,
        *, province_query: bool = False, allow_province_query: bool = False,
    ) -> None:
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
        if province_query:
            if not allow_province_query:
                raise ValueError("全省站点查询必须显式设置 allow_province_query=true")
            seconds = (end - start).total_seconds()
            province_limits = {
                "station_hour": (6 * 3600, "6 小时"),
                "station_day": (7 * 86400, "7 天"),
                "station_5minute": (3600, "1 小时"),
            }
            limit_seconds, limit_label = province_limits[data_kind]
            if seconds > limit_seconds:
                raise ValueError(
                    f"全省 {data_kind} 查询最多 {limit_label}；请缩短时间范围，或按省辖市/区县分次查询"
                )
        if data_type not in self._DATA_TYPES:
            raise ValueError("data_type 必须为 0、1、2 或 3")
        if pollutant_codes and data_kind != "station_5minute":
            raise ValueError("pollutant_codes 仅支持 station_5minute")
        if not self.base_url or not self.username or not self.password:
            raise ValueError("未配置江苏省数据接口地址、账号或密码")

    async def _request_with_retry(
        self, data_kind: str, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], int]:
        errors: list[str] = []
        for attempt in range(self._MAX_BATCH_ATTEMPTS):
            try:
                return await self._request(data_kind, payload), attempt
            except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
                errors.append(str(exc))
                if attempt + 1 >= self._MAX_BATCH_ATTEMPTS or not self._is_transient_error(exc):
                    raise
                delay = 0.5 * (2 ** attempt)
                logger.warning(
                    "jiangsu_station_batch_retry",
                    data_kind=data_kind,
                    attempt=attempt + 1,
                    station_count=len(payload.get("codes") or []),
                    delay_seconds=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)
        raise ValueError("江苏站点批次查询失败：" + "; ".join(errors))

    @staticmethod
    def _is_transient_error(exc: Exception) -> bool:
        if isinstance(exc, httpx.TransportError):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in {408, 425, 429, 500, 502, 503, 504}
        message = str(exc).lower()
        return any(token in message for token in ("繁忙", "超时", "稍后", "频繁", "timeout", "busy"))

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

    async def _resolve_station_codes(
        self,
        station_codes,
        station_names,
        city_names,
        district_names,
        *,
        station_type: str | None = None,
    ) -> list[str]:
        direct = [str(code).strip() for code in station_codes or [] if str(code).strip()]
        selectors = [*(station_names or []), *(city_names or []), *(district_names or [])]
        if not selectors:
            # Exact codes are commonly supplied by background diagnostics. Do
            # not add a directory round trip for the default case; an explicit
            # type asks us to validate them against the live directory.
            if station_type is None or normalize_station_type(station_type, allow_all=True) == "全部":
                return list(dict.fromkeys(direct))
            async with self._station_directory_lock:
                if self._station_directory is None:
                    self._station_directory = await self._get_station_directory()
            typed_rows, _ = filter_station_rows(self._station_directory or [], station_type)
            allowed = {
                str(row.get("stationCode") or row.get("StationCode"))
                for row in typed_rows
                if row.get("stationCode") or row.get("StationCode")
            }
            # Older deployments may omit the type field altogether. In that
            # case keep the exact codes and expose the limitation in metadata
            # rather than returning an unexpected empty query.
            return list(dict.fromkeys(code for code in direct if code in allowed)) or (
                list(dict.fromkeys(direct)) if not allowed else []
            )
        async with self._station_directory_lock:
            if self._station_directory is None:
                self._station_directory = await self._get_station_directory()
        rows = self._station_directory or []
        effective_type = normalize_station_type(station_type, allow_all=True) or "国控"
        rows, _ = filter_station_rows(rows, effective_type)
        normalise = lambda value: str(value or "").strip().replace(" ", "").rstrip("省市区县")
        codes = list(direct)
        for name in station_names or []:
            matches = [str(row["stationCode"]) for row in rows if normalise(row.get("positionName")) == normalise(name)]
            if not matches:
                raise ValueError(f"未在江苏站点目录中找到“{name}”")
            codes.extend(matches)
        for city in city_names or []:
            if self._is_province_name(city):
                matches = [str(row["stationCode"]) for row in rows]
            else:
                matches = [str(row["stationCode"]) for row in rows if normalise(city) == normalise(row.get("cityName"))]
            if not matches:
                raise ValueError(f"未在江苏站点目录中找到“{city}”下辖站点")
            codes.extend(matches)
        for district in district_names or []:
            requested = normalise(district)
            requested_raw = "".join(str(district).strip().split())
            matches = [
                str(row["stationCode"]) for row in rows
                if requested == normalise(row.get("districtName"))
                or requested_raw == (
                    "".join(str(row.get("cityName") or "").strip().split())
                    + "".join(str(row.get("districtName") or "").strip().split())
                )
                or requested == normalise(row.get("cityName")) + normalise(row.get("districtName"))
            ]
            if not matches:
                raise ValueError(f"未在江苏站点目录中找到“{district}”下辖站点")
            codes.extend(matches)
        return list(dict.fromkeys(codes))

    @classmethod
    def _is_province_name(cls, value: Any) -> bool:
        return "".join(str(value or "").split()) in cls._PROVINCE_SELECTORS

    @classmethod
    def _is_province_query(cls, city_names: list[str] | None) -> bool:
        return any(cls._is_province_name(item) for item in city_names or [])

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
