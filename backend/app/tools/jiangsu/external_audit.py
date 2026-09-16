"""江苏省审核联网平台第三方数据审核接口封装。

对应平台 ``江苏运维新国标`` 分支新增的三个对外接口：

- ``GET  {air}/audit/AirCityDataAudit/GetExternalStationAuditStatus`` 站点审核状态
- ``GET  {air}/audit/AirCityDataAudit/GetExternalAuditLogs``          站点审核日志
- ``POST {air}/audit/ExternalEvidence/GetExternalEvidence``           AI 研判证据包

两个 GET 接口返回裸 JSON 数组（非 dict 信封），因此不能直接复用
``_JiangsuAuthenticatedApi.get``；本模块复用其 token/请求头逻辑并自带
list 兼容与限次退避重试。时间参数按平台北京时间（UTC+08:00）传不带时区
的 ISO 日期。
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any

import httpx
import structlog

from app.tools.jiangsu.fault_diagnosis import _JiangsuAuthenticatedApi

logger = structlog.get_logger(__name__)

STATION_AUDIT_STATUS_PATH = "audit/AirCityDataAudit/GetExternalStationAuditStatus"
AUDIT_LOGS_PATH = "audit/AirCityDataAudit/GetExternalAuditLogs"
EXTERNAL_EVIDENCE_PATH = "audit/ExternalEvidence/GetExternalEvidence"

TAB_TYPES: tuple[str, ...] = ("initialReview", "constant", "outlier")
TAB_TYPE_LABELS = {
    "initialReview": "初审结果",
    "constant": "恒值",
    "outlier": "离群值",
}

_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY_SECONDS = 0.5
# 平台默认 MaxResultCount=10、上限 50；文档建议按页不超过 10 条，这里取上限内
# 的 20，兼顾单站单日记录量与响应体积。
EVIDENCE_PAGE_SIZE = 20
EVIDENCE_MAX_RANGE_HOURS = 72


def _format_day(value: date | datetime | str) -> str:
    if isinstance(value, str):
        parsed = _parse_day(value)
        if parsed is None:
            raise ValueError(f"无效日期：{value}")
        value = parsed
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%Y-%m-%d")


def _parse_day(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 425, 429, 500, 502, 503, 504}
    message = str(exc).lower()
    return any(token in message for token in ("繁忙", "超时", "稍后", "频繁", "timeout", "busy"))


class JiangsuExternalAuditClient:
    """审核平台第三方接口只读客户端。"""

    def __init__(self, *, api: _JiangsuAuthenticatedApi | None = None) -> None:
        self.api = api or _JiangsuAuthenticatedApi(source="air")

    async def _request_json(
        self, *, method: str, path: str, params: list[tuple[str, str]] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        last_exc: BaseException | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                return await self._request_once(
                    method=method, path=path, params=params, json_body=json_body,
                )
            except Exception as exc:  # noqa: BLE001 - 限次退避重试瞬态错误
                last_exc = exc
                if attempt + 1 >= _MAX_ATTEMPTS or not _is_transient(exc):
                    raise
                await asyncio.sleep(_RETRY_BASE_DELAY_SECONDS * (2 ** attempt))
        raise last_exc  # pragma: no cover - 循环内必然 raise 或 return

    async def _request_once(
        self, *, method: str, path: str, params: list[tuple[str, str]] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        token = await self.api._get_token()
        url = f"{self.api.base_url}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {token}",
            "SysCode": self.api.sys_code,
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.api.timeout_seconds) as client:
            if method == "GET":
                response = await client.get(url, params=params or [], headers=headers)
            else:
                response = await client.post(url, json=json_body or {}, headers=headers)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("success") is False:
            raise ValueError(str(payload.get("msg") or payload.get("message") or "江苏审核平台接口返回失败"))
        return payload

    async def get_station_audit_status(
        self,
        start_date: date | datetime | str,
        end_date: date | datetime | str,
        station_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """查询站点逐审核日审核状态；无记录时返回空列表。"""
        params: list[tuple[str, str]] = [
            ("StartTime", _format_day(start_date)),
            ("EndTime", _format_day(end_date)),
        ]
        for code in station_codes or []:
            text = str(code or "").strip()
            if text:
                params.append(("StationCode", text))
        payload = await self._request_json(method="GET", path=STATION_AUDIT_STATUS_PATH, params=params)
        if payload is None:
            return []
        if not isinstance(payload, list):
            raise ValueError("站点审核状态接口返回格式无效")
        return [row for row in payload if isinstance(row, dict)]

    async def get_audit_logs(
        self,
        start_date: date | datetime | str,
        end_date: date | datetime | str,
        station_codes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """查询人工初审、复核审核日志；平台按业务日期换算 D日01:00→D+1日00:00。"""
        params: list[tuple[str, str]] = [
            ("StartTime", _format_day(start_date)),
            ("EndTime", _format_day(end_date)),
        ]
        for code in station_codes or []:
            text = str(code or "").strip()
            if text:
                params.append(("StationCode", text))
        payload = await self._request_json(method="GET", path=AUDIT_LOGS_PATH, params=params)
        if payload is None:
            return []
        if not isinstance(payload, list):
            raise ValueError("站点审核日志接口返回格式无效")
        return [row for row in payload if isinstance(row, dict)]

    async def get_evidence_page(
        self,
        start_date: date | datetime | str,
        end_date: date | datetime | str,
        tab_type: str,
        *,
        station_codes: list[str] | None = None,
        skip_count: int = 0,
        max_result_count: int = EVIDENCE_PAGE_SIZE,
    ) -> dict[str, Any]:
        """查询单页审核记录证据包（PagedResultDto：totalCount + items）。"""
        if tab_type not in TAB_TYPES:
            raise ValueError(f"TabType 必须是 {TAB_TYPES} 之一")
        start_text = _format_day(start_date)
        end_text = _format_day(end_date)
        start_day = _parse_day(start_text)
        end_day = _parse_day(end_text)
        if start_day is None or end_day is None:
            raise ValueError("证据包接口日期无效")
        if (end_day - start_day) > timedelta(hours=EVIDENCE_MAX_RANGE_HOURS):
            raise ValueError(f"证据包接口时间跨度超过 {EVIDENCE_MAX_RANGE_HOURS} 小时，请分段查询")
        body = {
            "startDate": f"{start_text}T00:00:00",
            "endDate": f"{end_text}T23:59:59",
            "tabType": tab_type,
            "skipCount": max(0, int(skip_count)),
            "maxResultCount": max(1, min(int(max_result_count), 50)),
        }
        codes = [str(code or "").strip() for code in (station_codes or [])]
        codes = [code for code in codes if code]
        if codes:
            body["stationCodes"] = codes
        payload = await self._request_json(method="POST", path=EXTERNAL_EVIDENCE_PATH, json_body=body)
        if not isinstance(payload, dict):
            raise ValueError("证据包接口返回格式无效")
        return payload

    async def fetch_evidence_records(
        self,
        start_date: date | datetime | str,
        end_date: date | datetime | str,
        tab_type: str,
        *,
        station_codes: list[str] | None = None,
        max_records: int | None = None,
        page_size: int = EVIDENCE_PAGE_SIZE,
    ) -> dict[str, Any]:
        """按 skipCount += 实际 items 数量 翻页，聚合当前页签全部审核记录。

        返回 ``{"total_count", "records", "truncated", "pages"}``；``max_records``
        限制落包记录数，超出部分标记 truncated。
        """
        records: list[dict[str, Any]] = []
        total_count: int | None = None
        pages = 0
        skip = 0
        truncated = False
        while True:
            page = await self.get_evidence_page(
                start_date, end_date, tab_type,
                station_codes=station_codes,
                skip_count=skip, max_result_count=page_size,
            )
            pages += 1
            try:
                total_count = int(page.get("totalCount"))
            except (TypeError, ValueError):
                total_count = None
            items = [row for row in page.get("items") or [] if isinstance(row, dict)]
            if not items:
                break
            records.extend(items)
            if max_records is not None and len(records) >= max_records:
                truncated = True
                records = records[:max_records]
                break
            skip += len(items)
            if total_count is not None and skip >= total_count:
                break
            if len(items) < page_size:
                break
        if max_records is not None and total_count is not None and len(records) < total_count and not truncated:
            truncated = True
        return {
            "total_count": total_count,
            "records": records,
            "truncated": truncated,
            "pages": pages,
        }
