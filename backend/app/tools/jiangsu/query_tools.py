"""Read-only Jiangsu provincial city, district and statistics query tools."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.jiangsu.result_filter import compact_air_quality_records, externalize_compact_records

logger = structlog.get_logger(__name__)


class _JiangsuApiTool(LLMTool):
    """Shared authenticated, read-only client for Jiangsu provincial APIs."""

    _DATA_TYPES = {0: "原始工况", 1: "审核工况", 2: "原始标况", 3: "审核标况"}

    def __init__(self, **kwargs: Any) -> None:
        from config.settings import settings

        self.base_url = settings.jiangsu_air_api_base_url.rstrip("/")
        self.username = settings.jiangsu_air_api_username
        self.password = settings.jiangsu_air_api_password
        self.timeout_seconds = settings.jiangsu_air_api_timeout_seconds
        self._token: str | None = None
        self._token_lock = asyncio.Lock()
        self._region_rows: list[dict[str, Any]] | None = None
        self._region_lock = asyncio.Lock()
        super().__init__(**kwargs)

    def _validate_config(self) -> None:
        if not self.base_url or not self.username or not self.password:
            raise ValueError("未配置江苏省数据接口地址、账号或密码")

    @staticmethod
    def _parse_range(start_time: str | None, end_time: str | None, max_days: int = 366) -> None:
        try:
            start = datetime.fromisoformat((start_time or "").replace("Z", "+00:00"))
            end = datetime.fromisoformat((end_time or "").replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("时间必须为 YYYY-MM-DD HH:mm:ss 格式") from exc
        if start > end:
            raise ValueError("start_time 不能晚于 end_time")
        if (end - start).days > max_days:
            raise ValueError(f"单次统计查询时间范围不能超过 {max_days} 天")

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

    async def _get(self, endpoint: str, params: list[tuple[str, Any]]) -> dict[str, Any]:
        self._validate_config()
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}", "SysCode": "SunAirProvince"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(f"{self.base_url}/{endpoint}", params=params, headers=headers)
            if response.status_code == 401:
                self._token = None
                headers["Authorization"] = f"Bearer {await self._get_token()}"
                response = await client.get(f"{self.base_url}/{endpoint}", params=params, headers=headers)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success") or int(payload.get("state", 500)) != 200:
            raise ValueError(str(payload.get("msg") or "江苏接口返回失败"))
        return payload

    async def _resolve_area_codes(
        self, codes: list[str] | None, area_names: list[str] | None, scope: str
    ) -> list[str]:
        """Resolve human place names with the platform's live region directory."""
        direct_codes = [str(code).strip() for code in codes or [] if str(code).strip()]
        names = [str(name).strip() for name in area_names or [] if str(name).strip()]
        if not names:
            return direct_codes

        async with self._region_lock:
            if self._region_rows is None:
                payload = await self._get("AirCityProductBase/GetBSDRegionAsync", [])
                rows = payload.get("result") or []
                if not isinstance(rows, list):
                    raise ValueError("江苏行政区划目录返回格式异常")
                self._region_rows = [row for row in rows if isinstance(row, dict) and row.get("areaCode")]
        rows = self._region_rows
        assert rows is not None

        target_level = {"city": 2, "district": 3}[scope]
        normalise = lambda value: str(value or "").strip().replace(" ", "").rstrip("省市区县")
        selected = set(direct_codes)
        for name in names:
            raw_matches = [
                str(row["areaCode"]) for row in rows
                if name == str(row["areaCode"]) or normalise(name) == normalise(row.get("areaName"))
            ]
            if not raw_matches:
                raise ValueError(f"未在江苏行政区划目录中找到“{name}”")
            descendants = set(raw_matches)
            frontier = list(raw_matches)
            while frontier:
                parent = frontier.pop()
                for row in rows:
                    code = str(row["areaCode"])
                    if str(row.get("parentID") or "") == parent and code not in descendants:
                        descendants.add(code)
                        frontier.append(code)
            resolved = [
                str(row["areaCode"]) for row in rows
                if str(row["areaCode"]) in descendants and row.get("level") == target_level
            ]
            # A name at the requested level must also be retained.
            selected.update(resolved)
        # Preserve the platform directory order (and therefore the province's
        # normal city order) instead of returning arbitrary set iteration.
        return [
            str(row["areaCode"]) for row in rows
            if str(row["areaCode"]) in selected
        ]


class _JiangsuAreaDataTool(_JiangsuApiTool):
    _SCOPE = ""
    _CODE_PARAM = "codes"
    _ENDPOINTS: dict[str, str] = {}

    def __init__(self) -> None:
        scope_cn = "城市" if self._SCOPE == "city" else "区县"
        super().__init__(
            name=f"jiangsu_fetch_{self._SCOPE}_data",
            description=f"查询江苏省{scope_cn}小时或日均空气质量明细数据。",
            category=ToolCategory.QUERY,
            version="1.0.0",
            function_schema={
                "name": f"jiangsu_fetch_{self._SCOPE}_data",
                "description": f"只读查询江苏省{scope_cn}小时或日均空气质量数据，返回 AQI、质量等级和主要污染物。超过24条过滤后结果将外部化保存，data仅返回首尾样本，file_path可供按需读取。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "data_kind": {"type": "string", "enum": [f"{self._SCOPE}_hour", f"{self._SCOPE}_day"]},
                        "codes": {"type": "array", "items": {"type": "string"}, "description": f"{scope_cn}行政区划编码；已知编码时使用。"},
                        "area_names": {"type": "array", "items": {"type": "string"}, "description": f"{scope_cn}、区县或江苏省名称；工具内部自动解析编码并展开下级区域。"},
                        "start_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss"},
                        "end_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss"},
                        "data_type": {"type": "integer", "enum": [0, 1, 2, 3], "default": 1, "description": "0原始工况、1审核工况、2原始标况、3审核标况；默认1（审核工况）。"},
                        "max_results": {"type": "integer", "minimum": 1, "maximum": 1000, "description": "返回上限，默认200。"},
                    },
                    "required": ["data_kind", "start_time", "end_time"],
                },
            },
        )

    async def execute(self, context=None, data_kind: str | None = None, codes: list[str] | None = None, area_names: list[str] | None = None,
                      start_time: str | None = None, end_time: str | None = None, data_type: int = 1,
                      max_results: int = 200, **_: Any) -> dict[str, Any]:
        try:
            if data_kind not in self._ENDPOINTS:
                raise ValueError(f"data_kind 必须为 {'、'.join(self._ENDPOINTS)}")
            codes = await self._resolve_area_codes(codes, area_names, self._SCOPE)
            if not codes or len(codes) > 100 or not all(isinstance(code, str) and code.strip() for code in codes):
                raise ValueError("codes 需要 1 至 100 个有效行政区划编码")
            if data_type not in self._DATA_TYPES:
                raise ValueError("data_type 必须为 0、1、2 或 3")
            if not isinstance(max_results, int) or not 1 <= max_results <= 1000:
                raise ValueError("max_results 必须在 1 至 1000 之间")
            self._parse_range(start_time, end_time, max_days=31)
            params: list[tuple[str, Any]] = [("skipCount", 0), ("maxResultCount", max_results)]
            params.extend((f"{self._CODE_PARAM}[{index}]", code.strip()) for index, code in enumerate(codes))
            params.extend([("timePoint[0]", start_time), ("timePoint[1]", end_time), ("dataType", data_type)])
            payload = await self._get(self._ENDPOINTS[data_kind], params)
            result = payload.get("result") or {}
            items = result.get("items", []) if isinstance(result, dict) else []
            compact_items, filter_metadata = compact_air_quality_records(items)
            raw_file_path = None
            if context is not None and len(items) > 24:
                raw_file_path = context.save_data(
                    data=items,
                    schema=f"jiangsu_{self._SCOPE}_{data_kind}_raw",
                    metadata={"source_tool": self.name, "record_count": len(items), "filtered": False},
                )
            inline_items, filtered_file_path, externalization = externalize_compact_records(
                compact_items,
                context=context,
                schema=f"jiangsu_{self._SCOPE}_{data_kind}_filtered",
                metadata={"source_tool": self.name, "source_record_count": len(items)},
            )
            metadata = {"source": "jiangsu_air_province_api", "endpoint": self._ENDPOINTS[data_kind],
                        "scope": self._SCOPE, "codes": codes, "area_names": area_names or [], "time_range": [start_time, end_time],
                        "data_type": data_type, "data_type_label": self._DATA_TYPES[data_type],
                        "total_count": result.get("totalCount", len(items)), "record_count": len(compact_items),
                        "queried_at": datetime.now().astimezone().isoformat(), **filter_metadata}
            if raw_file_path:
                metadata["raw_data_file_path"] = raw_file_path
            metadata["context_data"] = externalization
            return {
                "status": "success" if compact_items else "empty", "success": True, "data": inline_items,
                "metadata": metadata,
                "summary": f"江苏{self._SCOPE}数据查询完成：原始 {len(items)} 条，清洗并删除完全重复记录后保留完整时间序列 {len(compact_items)} 条。",
                **{key: externalization[key] for key in ("data_complete", "record_count", "returned_records", "sample_strategy")},
                **({"file_path": filtered_file_path} if filtered_file_path else {}),
            }
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("jiangsu_area_data_failed", scope=self._SCOPE, error=str(exc))
            return {"status": "failed", "success": False, "data": [], "summary": f"江苏数据查询失败：{exc}"}


class JiangsuGeographyResolverTool(_JiangsuApiTool):
    """Resolve Jiangsu administrative names to the platform's area codes.

    The source is the same provincial platform that serves the air-quality
    endpoints, so the mapping follows the codes actually accepted by them.
    """

    _ENDPOINT = "AirCityProductBase/GetBSDRegionAsync"
    _LEVELS = {"province": 1, "city": 2, "district": 3}

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_resolve_geography",
            description="解析江苏省、省辖市和区县名称为江苏平台行政区划编码，并可展开下级区域。",
            category=ToolCategory.QUERY,
            version="1.0.0",
            function_schema={
                "name": "jiangsu_resolve_geography",
                "description": "只读查询江苏平台行政区划目录。查询江苏省今天的城市数据时，传 area_names=['江苏省']、target_level='city'，再将返回的 area_code 用于城市数据工具。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "area_names": {
                            "type": "array", "items": {"type": "string"},
                            "description": "区域名称或行政区划编码；省级名称可展开为下级城市。",
                        },
                        "target_level": {
                            "type": "string", "enum": ["province", "city", "district"],
                            "description": "返回的区域层级；未提供时保留匹配区域本身。",
                        },
                    },
                },
            },
        )

    @staticmethod
    def _normalise_name(value: Any) -> str:
        return str(value or "").strip().replace(" ", "").rstrip("省市区县")

    async def execute(
        self,
        context=None,
        area_names: list[str] | None = None,
        target_level: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        try:
            if target_level is not None and target_level not in self._LEVELS:
                raise ValueError("target_level 必须为 province、city 或 district")
            if area_names is not None and (
                not area_names
                or len(area_names) > 50
                or not all(isinstance(name, str) and name.strip() for name in area_names)
            ):
                raise ValueError("area_names 需要 1 至 50 个有效区域名称或编码")

            payload = await self._get(self._ENDPOINT, [])
            raw_rows = payload.get("result") or []
            if not isinstance(raw_rows, list):
                raise ValueError("江苏行政区划目录返回格式异常")
            rows = [row for row in raw_rows if isinstance(row, dict) and row.get("areaCode")]
            matched_codes: set[str] = set()
            for requested in area_names or []:
                requested_text = requested.strip()
                requested_name = self._normalise_name(requested_text)
                for row in rows:
                    code = str(row["areaCode"])
                    if requested_text == code or requested_name == self._normalise_name(row.get("areaName")):
                        matched_codes.add(code)

            if target_level:
                expected_level = self._LEVELS[target_level]
                if matched_codes:
                    selected_codes = set(matched_codes)
                    frontier = list(matched_codes)
                    while frontier:
                        parent_code = frontier.pop()
                        for row in rows:
                            code = str(row["areaCode"])
                            if str(row.get("parentID") or "") == parent_code and code not in selected_codes:
                                selected_codes.add(code)
                                frontier.append(code)
                    result_rows = [row for row in rows if str(row["areaCode"]) in selected_codes and row.get("level") == expected_level]
                else:
                    result_rows = []
            elif area_names:
                result_rows = [row for row in rows if str(row["areaCode"]) in matched_codes]
            else:
                result_rows = rows

            data = [
                {
                    "area_code": str(row["areaCode"]),
                    "area_name": row.get("areaName"),
                    "parent_code": str(row.get("parentID") or ""),
                    "level": row.get("level"),
                }
                for row in result_rows
            ]
            return {
                "status": "success" if data else "empty",
                "success": True,
                "data": data,
                "metadata": {
                    "source": "jiangsu_air_province_api",
                    "endpoint": self._ENDPOINT,
                    "requested_areas": area_names or [],
                    "target_level": target_level,
                    "record_count": len(data),
                },
                "summary": f"江苏行政区划解析完成：返回 {len(data)} 个区域。",
            }
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("jiangsu_geography_resolve_failed", error=str(exc))
            return {"status": "failed", "success": False, "data": [], "summary": f"江苏行政区划解析失败：{exc}"}


class JiangsuCityDataTool(_JiangsuAreaDataTool):
    _SCOPE = "city"
    _ENDPOINTS = {
        "city_hour": "airdata/DATCityHour/GetDATCityHourDisplayPagedListAsync",
        "city_day": "airdata/DATCityDay/GetDATCityDayDisplayPagedListAsync",
    }


class JiangsuDistrictDataTool(_JiangsuAreaDataTool):
    _SCOPE = "district"
    _ENDPOINTS = {
        "district_hour": "airdata/DATDistrictHour/GetDATDistrictHourDisplayPagedListAsync",
        "district_day": "airdata/DATDistrictDay/GetDATDistrictDayDisplayPagedListAsync",
    }


class JiangsuStatisticsTool(_JiangsuApiTool):
    """Query server-calculated rankings and operation quality statistics."""

    _ENDPOINTS = {
        "city_rank": "GetCityRankStatisticsPagedAsync",
        "district_rank": "GetDistrictRankStatisticsPagedAsync",
        "station_rank": "GetStationRankStatisticsPagedAsync",
        "station_o3_rank": "GetStationO3RankStatisticsPagedAsync",
        "station_overday": "GetStationOverDayStatisticsPagedAsync",
        "station_transfer_rate": "GetStationTransferRateQueryDataPage",
        "station_effective_rate": "GetStationEffectiveRateQueryDataPage",
        "station_receive_rate": "GetStationReceiveRateQueryDataPage",
    }
    _CODE_FIELDS = {"city_rank": "CityCode", "district_rank": "DistrictCode", "station_rank": "StationCode",
                    "station_o3_rank": "StationCode", "station_overday": "StationCode",
                    "station_transfer_rate": "codes", "station_effective_rate": "codes", "station_receive_rate": "codes"}

    def __init__(self) -> None:
        super().__init__(
            name="jiangsu_query_statistics", description="查询江苏省城市、区县、站点排名及传输率、有效率等统计结果。",
            category=ToolCategory.QUERY, version="1.0.0",
            function_schema={
                "name": "jiangsu_query_statistics",
                "description": "只读查询江苏平台已计算的排名、同比、达标率、超标天、传输率、有效率和接收率统计。",
                "parameters": {"type": "object", "properties": {
                    "statistic_kind": {"type": "string", "enum": list(self._ENDPOINTS), "description": "统计类型。"},
                    "codes": {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": "城市、区县或站点编码。"},
                    "start_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss"},
                    "end_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss"},
                    "data_type": {"type": "integer", "enum": [0, 1, 2, 3], "default": 1,
                                  "description": "0原始工况、1审核工况、2原始标况、3审核标况；默认1（审核工况）。"},
                    "pollutant_code": {"type": "string", "description": "仅 station_overday 必填，如 PM2_5 或 O3_8h。"},
                    "cal_area_type": {"type": "integer", "description": "城市/区县排名的计算区域类型，可选。"},
                    "ascending": {"type": "boolean", "description": "排名升序，默认 true。"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 1000},
                }, "required": ["statistic_kind", "codes", "start_time", "end_time"]},
            },
        )

    async def execute(self, context=None, statistic_kind: str | None = None, codes: list[str] | None = None,
                      start_time: str | None = None, end_time: str | None = None, data_type: int = 1,
                      pollutant_code: str | None = None, cal_area_type: int | None = None,
                      ascending: bool = True, max_results: int = 200, **_: Any) -> dict[str, Any]:
        try:
            if statistic_kind not in self._ENDPOINTS:
                raise ValueError("不支持的 statistic_kind")
            if not codes or len(codes) > 300 or not all(isinstance(code, str) and code.strip() for code in codes):
                raise ValueError("codes 需要 1 至 300 个有效编码")
            if data_type not in self._DATA_TYPES:
                raise ValueError("data_type 必须为 0、1、2 或 3")
            if statistic_kind == "station_overday" and not pollutant_code:
                raise ValueError("station_overday 必须提供 pollutant_code")
            if not isinstance(max_results, int) or not 1 <= max_results <= 1000:
                raise ValueError("max_results 必须在 1 至 1000 之间")
            self._parse_range(start_time, end_time)
            code_field = self._CODE_FIELDS[statistic_kind]
            params: list[tuple[str, Any]] = [("skipCount", 0), ("maxResultCount", max_results)]
            params.extend((f"{code_field}[{index}]", code.strip()) for index, code in enumerate(codes))
            params.extend([("TimePoint[0]", start_time), ("TimePoint[1]", end_time), ("DataType", data_type)])
            if statistic_kind not in {"station_transfer_rate", "station_effective_rate", "station_receive_rate"}:
                params.extend([("TimeType", 100), ("IsAsc", str(bool(ascending)).lower())])
            if pollutant_code:
                params.append(("PollutantCode", pollutant_code))
            if cal_area_type is not None:
                params.append(("CalAreaType", cal_area_type))
            endpoint = f"dataanalysis/StationDataStatisticQuery/{self._ENDPOINTS[statistic_kind]}"
            payload = await self._get(endpoint, params)
            result = payload.get("result") or {}
            items = result.get("items", []) if isinstance(result, dict) else []
            return {
                "status": "success" if items else "empty", "success": True, "data": items,
                "metadata": {"source": "jiangsu_air_province_api", "endpoint": endpoint,
                             "statistic_kind": statistic_kind, "codes": codes, "time_range": [start_time, end_time],
                             "data_type": data_type, "data_type_label": self._DATA_TYPES[data_type],
                             "total_count": result.get("totalCount", len(items)), "record_count": len(items),
                             "queried_at": datetime.now().astimezone().isoformat()},
                "summary": f"江苏{statistic_kind}统计查询完成：返回 {len(items)} 条记录。",
            }
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("jiangsu_statistics_failed", statistic_kind=statistic_kind, error=str(exc))
            return {"status": "failed", "success": False, "data": [], "summary": f"江苏统计查询失败：{exc}"}
