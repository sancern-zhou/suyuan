"""Read-only client for Jiangsu operations alarm/call records."""

from __future__ import annotations

import asyncio
from datetime import datetime
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
            description="查询江苏运维平台的告警/电话记录，仅支持读取，不能处置或关闭告警。",
            category=ToolCategory.QUERY,
            version="1.0.0",
            function_schema={
                "name": "jiangsu_fetch_alarm_records",
                "description": "按站点、告警状态、级别和时间范围查询江苏运维告警/电话记录。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "station_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                        "start_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss"},
                        "end_time": {"type": "string", "description": "YYYY-MM-DD HH:mm:ss"},
                        "call_type": {"type": "string", "description": "可选，例如 qb。"},
                        "alarm_state": {"type": "integer", "description": "可选告警状态，例如 1。"},
                        "call_level": {"type": "string", "description": "可选，例如 qb。"},
                        "skip_count": {"type": "integer", "minimum": 0, "default": 0},
                        "max_result_count": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
                        "sorting": {"type": "string", "enum": ["id", "timePoint", "createTime", "modifyTime"], "default": "id"},
                    },
                    "required": ["station_codes", "start_time", "end_time"],
                },
            },
        )

    async def execute(
        self,
        context=None,
        station_codes: list[str] | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        call_type: str | None = None,
        alarm_state: int | None = None,
        call_level: str | None = None,
        skip_count: int = 0,
        max_result_count: int = 50,
        sorting: str = "id",
        **_: Any,
    ) -> dict[str, Any]:
        try:
            codes = self._validate(
                station_codes, start_time, end_time, alarm_state, skip_count, max_result_count, sorting
            )
            params: list[tuple[str, str | int]] = [
                ("skipCount", skip_count),
                ("sorting", sorting),
                ("maxResultCount", max_result_count),
                ("timePoint[0]", start_time or ""),
                ("timePoint[1]", end_time or ""),
            ]
            params.extend((f"code[{index}]", code) for index, code in enumerate(codes))
            if call_type:
                params.append(("CallType", call_type.strip()))
            if alarm_state is not None:
                params.append(("DDALARMSTATE", alarm_state))
            if call_level:
                params.append(("CallLevel", call_level.strip()))

            payload = await self._request(params)
            records, total_count = self._extract_page(payload)
            metadata = {
                "source": "jiangsu_operations_alarm_api",
                "endpoint": self._PATH,
                "station_codes": codes,
                "time_range": [start_time, end_time],
                "filters": {"call_type": call_type, "alarm_state": alarm_state, "call_level": call_level},
                "pagination": {"skip_count": skip_count, "max_result_count": max_result_count, "sorting": sorting},
                "record_count": len(records),
                "total_count": total_count,
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
        if not station_codes or not all(isinstance(code, str) and code.strip() for code in station_codes):
            raise ValueError("station_codes 至少需要一个有效站点编码")
        codes = [code.strip() for code in station_codes]
        if len(codes) > 100:
            raise ValueError("单次最多查询 100 个站点")
        try:
            start = datetime.fromisoformat((start_time or "").replace("Z", "+00:00"))
            end = datetime.fromisoformat((end_time or "").replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("时间必须为 YYYY-MM-DD HH:mm:ss 格式") from exc
        if start > end:
            raise ValueError("start_time 不能晚于 end_time")
        if (end - start).days > 31:
            raise ValueError("单次查询时间范围不能超过 31 天")
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
