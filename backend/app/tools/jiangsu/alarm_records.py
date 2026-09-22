"""Read-only client for Jiangsu operations alarm/call records."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx
import structlog

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger(__name__)


class JiangsuAlarmRecordsTool(LLMTool):
    """Fetch paged CallRecord alarm records from the Jiangsu operations platform."""

    _PATH = "operation/CallRecord/GetCallRecordPagedListAsync"
    _SORT_FIELDS = {"id", "timePoint", "createTime", "modifyTime"}

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        from config.settings import settings

        self.base_url = (base_url or settings.jiangsu_ops_api_base_url).rstrip("/")
        self.token_url = (token_url or settings.jiangsu_ops_token_url).rstrip("/")
        # Keep credentials independent, while allowing an existing provincial
        # credential set to be reused during a staged deployment.
        self.username = username if username is not None else (
            settings.jiangsu_ops_api_username or settings.jiangsu_air_api_username
        )
        self.password = password if password is not None else (
            settings.jiangsu_ops_api_password or settings.jiangsu_air_api_password
        )
        self.timeout_seconds = timeout_seconds or settings.jiangsu_ops_api_timeout_seconds
        self._token: str | None = None
        self._token_lock = asyncio.Lock()
        super().__init__(
            name="jiangsu_fetch_alarm_records",
            description="按单一站点查询江苏运维平台原始告警/电话记录（只读），站点名称必填且时间范围不超过 24 小时。",
            category=ToolCategory.QUERY,
            version="1.1.0",
            function_schema={
                "name": "jiangsu_fetch_alarm_records",
                "description": (
                    "按站点名称和时间范围查询江苏运维平台原始告警/电话记录，用于逐条复核。"
                    "必须提供 station_name，且时间范围不能超过 24 小时；不支持城市/区县/站点类型整批查询。"
                    "结构化的事件查询、聚合与积压统计请优先使用 execute_smart_event_sql_query，"
                    "本工具只作为按站点核对原始告警的兜底通道。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "station_name": {"type": "string", "description": "站点名称（必填），系统据此解析站点编码。"},
                        "start_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss，与 end_time 间隔不超过 24 小时。"},
                        "end_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss。"},
                        "call_type": {"type": "string", "description": "可选，例如 qb。"},
                        "alarm_state": {"type": "integer", "description": "可选告警状态，例如 1。"},
                        "call_level": {"type": "string", "description": "可选，例如 qb。"},
                        "skip_count": {"type": "integer", "minimum": 0, "default": 0},
                        "max_result_count": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
                        "sorting": {"type": "string", "enum": ["id", "timePoint", "createTime", "modifyTime"], "default": "id"},
                    },
                    "required": ["station_name", "start_time", "end_time"],
                },
            },
        )

    async def execute(
        self,
        context=None,
        station_name: str | None = None,
        station_codes: list[str] | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        call_type: str | None = None,
        alarm_state: int | None = None,
        call_level: str | None = None,
        skip_count: int = 0,
        max_result_count: int = 50,
        sorting: str = "id",
        **extra: Any,
    ) -> dict[str, Any]:
        """Agent-facing query.

        The raw platform alarm endpoint can return an unbounded dataset and is
        expensive to page.  It is therefore restricted to a directly named
        station and a window of at most 24 hours; structured event-center
        queries (``execute_smart_event_sql_query``) are the preferred path.
        """
        for banned in ("city_name", "district_name", "station_type"):
            if extra.get(banned):
                return {
                    "status": "failed",
                    "success": False,
                    "data": [],
                    "summary": (
                        f"原始告警查询必须按站点名称查询，不支持 {banned} 整批查询；"
                        "请先用 execute_smart_event_sql_query 查询事件中心结构化事件"
                    ),
                }
        name = str(station_name or "").strip()
        if not name:
            return {
                "status": "failed",
                "success": False,
                "data": [],
                "summary": (
                    "必须提供 station_name；请先用 execute_smart_event_sql_query 查询事件中心结构化事件，"
                    "必要时再按站点名称查询原始告警"
                ),
            }
        try:
            resolved_codes = await self._resolve_station_name_codes(name)
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("jiangsu_alarm_station_resolve_failed", station_name=name, error=str(exc))
            return {"status": "failed", "success": False, "data": [], "summary": f"江苏运维告警记录查询失败：{exc}"}
        return await self._query(
            station_codes=resolved_codes,
            station_name=name,
            start_time=start_time,
            end_time=end_time,
            call_type=call_type,
            alarm_state=alarm_state,
            call_level=call_level,
            skip_count=skip_count,
            max_result_count=max_result_count,
            sorting=sorting,
        )

    async def execute_pipeline(
        self,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
        station_codes: list[str] | None = None,
        city_name: str | None = None,
        district_name: str | None = None,
        station_type: str | None = None,
        call_type: str | None = None,
        alarm_state: int | None = None,
        call_level: str | None = None,
        skip_count: int = 0,
        max_result_count: int = 100,
        sorting: str = "id",
    ) -> dict[str, Any]:
        """Internal bounded sweep used by the event pipelines.

        Not exposed to the Agent: it keeps the legacy unscoped/geographic
        behaviour so the background alarm ingestion can still cover the
        province, while the Agent-facing ``execute`` stays station-scoped.
        """
        try:
            scope_codes = [str(code).strip() for code in (station_codes or []) if str(code).strip()]
            if not scope_codes and (city_name or district_name):
                from app.tools.jiangsu.fault_diagnosis import _resolve_station_rows
                rows = await _resolve_station_rows(None, city_name, district_name)
                scope_codes = [row["station_code"] for row in rows if row.get("station_code")]
                if not scope_codes:
                    raise ValueError("未解析到可查询的江苏站点")
            return await self._query(
                station_codes=scope_codes or None,
                start_time=start_time,
                end_time=end_time,
                call_type=call_type,
                alarm_state=alarm_state,
                call_level=call_level,
                skip_count=skip_count,
                max_result_count=max_result_count,
                sorting=sorting,
                station_type=station_type,
            )
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("jiangsu_alarm_records_pipeline_failed", error=str(exc))
            return {"status": "failed", "success": False, "data": [], "summary": f"江苏运维告警记录查询失败：{exc}"}
        except Exception:
            logger.exception("jiangsu_alarm_records_pipeline_unexpected_error")
            return {"status": "failed", "success": False, "data": [], "summary": "江苏运维告警记录查询发生未预期错误。"}

    async def _resolve_station_name_codes(self, station_name: str) -> list[str]:
        from app.tools.jiangsu.fault_diagnosis import _resolve_station_rows

        rows = await _resolve_station_rows(station_name, None, None)
        codes = [str(row.get("station_code") or "").strip() for row in rows if row.get("station_code")]
        codes = [code for code in codes if code]
        if not codes:
            raise ValueError(f"未解析到站点“{station_name}”")
        return codes

    async def _query(
        self,
        *,
        station_codes: list[str] | None,
        start_time: str | None,
        end_time: str | None,
        call_type: str | None,
        alarm_state: int | None,
        call_level: str | None,
        skip_count: int,
        max_result_count: int,
        sorting: str,
        station_name: str | None = None,
        station_type: str | None = None,
    ) -> dict[str, Any]:
        try:
            unscoped = not station_codes
            codes = self._validate(station_codes if not unscoped else None, start_time, end_time, alarm_state, skip_count, max_result_count, sorting)
            allowed_codes: set[str] | None = None
            station_type_filter_applied = False
            if unscoped and station_type and station_type not in {"全部", "所有", "all", "*"}:
                allowed_codes, station_type_filter_applied = await self._resolve_station_type_codes(station_type)
            records: list[dict[str, Any]] = []
            total_count = 0
            # The upstream endpoint accepts at most 100 station codes.  Keep
            # the unified tool call transparent by batching larger geographic
            # selections internally (for example, the whole province).
            batches = [codes[offset:offset + 100] for offset in range(0, len(codes), 100)] if codes else [None]
            for batch in batches:
                params: list[tuple[str, str | int]] = [
                    ("skipCount", skip_count), ("sorting", sorting),
                    ("maxResultCount", max_result_count),
                    ("timePoint[0]", start_time or ""), ("timePoint[1]", end_time or ""),
                ]
                if batch:
                    params.extend((f"code[{index}]", code) for index, code in enumerate(batch))
                if call_type: params.append(("CallType", call_type.strip()))
                if alarm_state is not None: params.append(("DDALARMSTATE", alarm_state))
                if call_level: params.append(("CallLevel", call_level.strip()))
                page_skip = skip_count
                while True:
                    if page_skip != skip_count:
                        params = [(key, value) for key, value in params if key != "skipCount"]
                        params.insert(0, ("skipCount", page_skip))
                    page_records, page_total = self._extract_page(await self._request(params))
                    records.extend(page_records)
                    total_count = total_count + page_total if batch else page_total
                    if batch or not page_records or page_skip + len(page_records) >= page_total:
                        break
                    page_skip += len(page_records)
            upstream_total_count = total_count
            if allowed_codes is not None:
                records = [item for item in records if self._record_station_code(item) in allowed_codes]
                total_count = len(records)
            metadata = {
                "source": "jiangsu_operations_alarm_api",
                "endpoint": self._PATH,
                "station_name": station_name,
                "station_codes": codes,
                "station_type": station_type,
                "station_type_filter_applied": station_type_filter_applied,
                "scope_mode": "upstream_all_stations" if unscoped else "station_codes",
                "time_range": [start_time, end_time],
                "filters": {"call_type": call_type, "alarm_state": alarm_state, "call_level": call_level},
                "pagination": {"skip_count": skip_count, "max_result_count": max_result_count, "sorting": sorting},
                "record_count": len(records),
                "total_count": total_count,
                "upstream_total_count": upstream_total_count,
                "queried_at": datetime.now().astimezone().isoformat(),
            }
            return {
                "status": "success" if records else "empty",
                "success": True,
                "data": records,
                "metadata": metadata,
                "summary": f"江苏运维告警记录查询完成：返回 {len(records)} 条记录，共 {total_count} 条。",
            }
        except (ValueError, httpx.HTTPError) as exc:
            logger.warning("jiangsu_alarm_records_failed", error=str(exc))
            return {"status": "failed", "success": False, "data": [], "summary": f"江苏运维告警记录查询失败：{exc}"}
        except Exception:
            logger.exception("jiangsu_alarm_records_unexpected_error")
            return {"status": "failed", "success": False, "data": [], "summary": "江苏运维告警记录查询发生未预期错误。"}

    def _validate(
        self, station_codes, start_time, end_time, alarm_state, skip_count, max_result_count, sorting
    ) -> list[str]:
        if station_codes is not None and not all(isinstance(code, str) and code.strip() for code in station_codes):
            raise ValueError("未解析到可查询的江苏站点，请检查站点目录或地理条件")
        codes = [code.strip() for code in station_codes or []]
        try:
            start = datetime.fromisoformat((start_time or "").replace("Z", "+00:00"))
            end = datetime.fromisoformat((end_time or "").replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("时间必须为 YYYY-MM-DD HH:mm:ss 格式") from exc
        if start > end:
            raise ValueError("start_time 不能晚于 end_time")
        if end - start > timedelta(days=1):
            raise ValueError("单次查询时间范围不能超过 24 小时")
        if alarm_state is not None and not isinstance(alarm_state, int):
            raise ValueError("alarm_state 必须为整数")
        if not isinstance(skip_count, int) or skip_count < 0:
            raise ValueError("skip_count 必须是非负整数")
        if not isinstance(max_result_count, int) or not 1 <= max_result_count <= 100:
            raise ValueError("max_result_count 必须在 1 到 100 之间")
        if sorting not in self._SORT_FIELDS:
            raise ValueError("sorting 必须为 id、timePoint、createTime 或 modifyTime")
        if not self.base_url or not self.token_url or not self.username or not self.password:
            raise ValueError("未配置江苏运维告警接口地址、Token 地址、账号或密码")
        return codes

    async def _resolve_station_type_codes(self, station_type: str) -> tuple[set[str], bool]:
        """Resolve station codes from the live provincial directory."""
        from app.tools.jiangsu.fault_diagnosis import _JiangsuAuthenticatedApi, JiangsuFaultWorkOrdersTool
        from app.tools.jiangsu.station_type import filter_station_rows

        payload = await _JiangsuAuthenticatedApi(source="air").get(
            JiangsuFaultWorkOrdersTool._STATION_DIRECTORY_PATH, []
        )
        rows = payload.get("result") or []
        if not isinstance(rows, list):
            raise ValueError("江苏站点目录返回格式异常")
        filtered, applied = filter_station_rows([row for row in rows if isinstance(row, dict)], station_type)
        codes = {
            self._record_station_code(row)
            for row in filtered
            if self._record_station_code(row)
        }
        return codes, applied

    @staticmethod
    def _record_station_code(record: dict[str, Any]) -> str:
        return str(
            record.get("stacode") or record.get("stationCode") or record.get("StationCode")
            or record.get("code") or record.get("station_code") or ""
        ).strip()

    async def _request(self, params: list[tuple[str, str | int]]) -> dict[str, Any]:
        token = await self._get_token()
        response = await self._get(params, token)
        if response.status_code == 401:
            self._token = None
            response = await self._get(params, await self._get_token())
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
                response = await client.get(
                    self.token_url,
                    params={"UserName": self.username, "Pwd": self.password},
                )
            response.raise_for_status()
            payload = response.json()
            token = payload.get("result") if isinstance(payload, dict) else None
            if not isinstance(payload, dict) or not payload.get("success") or not isinstance(token, str) or not token:
                message = payload.get("msg") if isinstance(payload, dict) else None
                raise ValueError(str(message or "江苏运维接口 Token 获取失败"))
            self._token = token
            return token

    async def _get(self, params: list[tuple[str, str | int]], token: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            return await client.get(
                f"{self.base_url}/{self._PATH}",
                params=params,
                headers={"Authorization": f"Bearer {token}", "SysCode": "SunOps", "Accept": "application/json"},
            )

    @staticmethod
    def _extract_page(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        result = payload.get("result", payload)
        if not isinstance(result, dict):
            raise ValueError("江苏运维接口返回 result 不是分页对象")
        records = result.get("items", result.get("data", []))
        if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
            raise ValueError("江苏运维接口返回记录列表无效")
        total_count = result.get("totalCount", result.get("total", len(records)))
        try:
            return records, int(total_count)
        except (TypeError, ValueError) as exc:
            raise ValueError("江苏运维接口返回 totalCount 无效") from exc
