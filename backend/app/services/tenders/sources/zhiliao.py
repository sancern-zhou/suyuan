"""知了标讯 (zhiliaobiaoxun.com) tender source.

Auth:  POST {base}/login  {"username","smsCode":"","password":md5(raw),"rememberMe"}
       -> data.token (JWT), sent back as header ``auth-token`` (+ ``userId``).

Search:
    GET {base}/search/bid
        ?keyword=&page=&count=10&date=<preset>&timestamp=<ms>&hash=md5(kw+ts+salt)

``date`` accepts presets: today / yesterday / aWeek / aMonth / threeMonths /
sixMonths / aYear.  ``yesterday`` gives an exact previous-day result set, which
matches the daily fetcher target.  Arbitrary ranges are not exposed by the API,
so historical backfill still relies on other sources.

Detail:
    GET {base}/bid/detail/content?id=<id>&bidType=<1|2>  -> data (content text)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import date, timedelta
from typing import Any, Optional

import httpx
import structlog

from config.settings import settings

from ..models import NoticeType, TenderCandidate

logger = structlog.get_logger()

DEFAULT_BASE_URL = "https://api-service-zhiliao.bailian-ai.com"
SITE_BASE_URL = "https://www.zhiliaobiaoxun.com"
SEARCH_SALT = "zlbxdc406fce62db4066b1f586677c9"
_FONT_TAG = re.compile(r"</?font[^>]*>")
_DATE_PRESETS = (
    (0, "today"),
    (1, "yesterday"),
    (7, "aWeek"),
    (31, "aMonth"),
    (93, "threeMonths"),
    (186, "sixMonths"),
    (366, "aYear"),
)


def _clean_title(value: Any) -> str:
    return _FONT_TAG.sub("", str(value or "")).strip()


def _parse_date(value: Any) -> Optional[date]:
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _notice_type(bid_type: Any) -> NoticeType:
    try:
        value = int(bid_type)
    except (TypeError, ValueError):
        return NoticeType.OTHER
    if value == 1:
        return NoticeType.TENDER
    if value == 2:
        return NoticeType.WINNING_BID
    return NoticeType.OTHER


def _date_preset(publish_date: Optional[date]) -> str:
    if publish_date is None:
        return ""
    age = (date.today() - publish_date).days
    if age < 0:
        return ""
    for limit, preset in _DATE_PRESETS:
        if age <= limit:
            return preset
    return "aYear"


class ZhiliaoClient:
    name = "zhiliaobiaoxun"

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        cookie: str | None = None,
        timeout: float = 30.0,
        page_cap: int = 20,
    ):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.username = username or os.getenv("ZHILIAO_USERNAME")
        self.password = password or os.getenv("ZHILIAO_PASSWORD")
        self.cookie = cookie or os.getenv("ZHILIAO_COOKIE")
        self.timeout = timeout
        self.page_cap = max(1, page_cap)
        self._token: str | None = None
        self._user_id: str | None = None
        self._client = httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers=self._base_headers()
        )

    def _base_headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": os.getenv(
                "ZHILIAO_USER_AGENT",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126 Safari/537.36",
            ),
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{SITE_BASE_URL}/",
            "Origin": SITE_BASE_URL,
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    async def _ensure_login(self) -> None:
        if self._token:
            return
        if not self.username or not self.password:
            return
        body = {
            "username": self.username,
            "smsCode": "",
            "password": hashlib.md5(self.password.encode("utf-8")).hexdigest(),
            "rememberMe": False,
        }
        response = await self._client.post(f"{self.base_url}/login", json=body)
        response.raise_for_status()
        data = response.json()
        if int(data.get("code") or 0) != 1:
            raise RuntimeError(f"zhiliao login failed: {data.get('msg')}")
        payload = data.get("data") or {}
        self._token = payload.get("token")
        self._user_id = str(payload.get("userId") or "")
        logger.info("zhiliao_login_ok", is_member=payload.get("isMember"))

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._token:
            headers["auth-token"] = self._token
        if self._user_id:
            headers["userId"] = self._user_id
        return headers

    def _signed_params(
        self, keyword: str, page: int, publish_date: Optional[date]
    ) -> dict[str, Any]:
        timestamp = int(time.time() * 1000)
        digest = hashlib.md5(
            f"{keyword}{timestamp}{SEARCH_SALT}".encode("utf-8")
        ).hexdigest()
        params: dict[str, Any] = {
            "keyword": keyword,
            "page": page,
            "count": 10,
            "timestamp": timestamp,
            "hash": digest,
        }
        preset = _date_preset(publish_date)
        if preset:
            params["date"] = preset
        return params

    async def search(
        self,
        keyword: str,
        notice_type: NoticeType,
        publish_date: Optional[date] = None,
        max_pages: int = 1,
    ) -> list[TenderCandidate]:
        await self._ensure_login()
        if publish_date is not None and publish_date != date.today() - timedelta(days=1):
            # The API only exposes preset windows (today/yesterday/...), so a
            # specific historical date cannot be requested exactly. Skip it
            # rather than paging through unrelated dates.
            return []
        if max_pages and max_pages > 0:
            page_limit = max_pages
        else:
            page_limit = self.page_cap
        candidates: list[TenderCandidate] = []
        for page in range(1, page_limit + 1):
            try:
                records = await self._search_page(keyword, page, publish_date)
            except Exception:  # noqa: BLE001
                logger.exception("zhiliao_search_failed", keyword=keyword, page=page)
                break
            if not records:
                break
            page_dates: list[date] = []
            for record in records:
                candidate = self._to_candidate(record, keyword)
                if candidate.publish_date is not None:
                    page_dates.append(candidate.publish_date)
                if publish_date is not None and candidate.publish_date != publish_date:
                    continue
                candidates.append(candidate)
            if publish_date is not None and page_dates and all(
                item < publish_date for item in page_dates
            ):
                break
            if len(records) < 10:
                break
        return candidates

    async def _search_page(
        self, keyword: str, page: int, publish_date: Optional[date]
    ) -> list[dict[str, Any]]:
        response = await self._client.get(
            f"{self.base_url}/search/bid",
            params=self._signed_params(keyword, page, publish_date),
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        data = response.json()
        if int(data.get("code") or 0) != 1:
            raise RuntimeError(f"zhiliao search failed: {data.get('msg')}")
        return (data.get("data") or {}).get("records") or []

    def _to_candidate(self, record: dict[str, Any], keyword: str) -> TenderCandidate:
        bid_id = record.get("id")
        bid_type = record.get("bidType")
        title = _clean_title(record.get("titleText") or record.get("title"))
        url = f"{SITE_BASE_URL}/biddetail/noticedetail?id={bid_id}&type=b{bid_type}"
        raw_list_text = " ".join(
            str(item)
            for item in [
                title,
                record.get("caller"),
                record.get("province"),
                record.get("city"),
            ]
            if item
        )
        return TenderCandidate(
            title=title,
            url=url,
            notice_type=_notice_type(bid_type),
            keyword=keyword,
            source=self.name,
            publish_date=_parse_date(record.get("pubTime")),
            raw_list_text=raw_list_text,
            metadata={
                "zhiliao_id": bid_id,
                "zhiliao_bid_type": bid_type,
                "caller": record.get("caller"),
                "province": record.get("province"),
                "city": record.get("city"),
                "money": record.get("money"),
                "bid_method": record.get("bidMethodName"),
                "industry": record.get("bidIndustryNames"),
                "source_url": record.get("sourceUrl"),
                "uniq_key": record.get("uniqKey"),
            },
        )

    async def fetch_detail(self, candidate: TenderCandidate) -> str:
        await self._ensure_login()
        metadata = candidate.metadata or {}
        bid_id = metadata.get("zhiliao_id")
        bid_type = metadata.get("zhiliao_bid_type")
        if bid_id is None:
            match = re.search(r"id=(\d+)", candidate.url or "")
            bid_id = match.group(1) if match else None
        if bid_type is None:
            bid_type = 2 if candidate.notice_type == NoticeType.WINNING_BID else 1
        if bid_id is None:
            return ""
        response = await self._client.get(
            f"{self.base_url}/bid/detail/content",
            params={"id": bid_id, "bidType": bid_type},
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        data = response.json()
        if int(data.get("code") or 0) != 1:
            raise RuntimeError(f"zhiliao detail failed: {data.get('msg')}")
        content = data.get("data")
        if isinstance(content, (dict, list)):
            return json.dumps(content, ensure_ascii=False)
        return str(content or "")

    async def close(self) -> None:
        await self._client.aclose()


def build_zhiliao_source(config) -> ZhiliaoClient:
    return ZhiliaoClient(
        base_url=getattr(settings, "zhiliao_base_url", DEFAULT_BASE_URL),
        username=getattr(settings, "zhiliao_username", None),
        password=getattr(settings, "zhiliao_password", None),
        cookie=getattr(settings, "zhiliao_cookie", None),
    )
