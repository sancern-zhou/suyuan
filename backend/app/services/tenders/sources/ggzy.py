"""Concurrent scraper for provincial/municipal public-resource trading platforms.

Many provincial platforms run the same "智能搜索" (Elasticsearch) component, so a
single templated request works across them::

    POST {base}/inteligentsearch/rest/esinteligentsearch/getFullTextDataNew
    body: {wd: <keyword>, time: [{fieldName: <webdate|infodate>, startTime, endTime}], ...}

The response records already contain the full announcement ``content`` plus a
relative ``linkurl``, so no separate detail request is needed.  Platforms are
queried concurrently to spread load and avoid per-site rate limits.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
import structlog

from config.settings import settings

from ..models import NoticeType, TenderCandidate

logger = structlog.get_logger()

SEARCH_PATH = "/inteligentsearch/rest/esinteligentsearch/getFullTextDataNew"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)


@dataclass(frozen=True)
class Platform:
    province: str
    base_url: str
    time_field: str = "webdate"
    referer: str = ""
    # "es" = shares the 智能搜索 endpoint (usable); "todo" = needs a bespoke adapter.
    adapter: str = "es"


# Full roster extracted from bulletin.cebpubservice.com/media.html (34 platforms).
# Only the "es" ones answer the shared 智能搜索 endpoint so far.
PLATFORM_REGISTRY: tuple[Platform, ...] = (
    Platform("浙江", "https://ggzy.zj.gov.cn", "webdate", "https://ggzy.zj.gov.cn/jyxxgk/list.html"),
    Platform("四川", "http://ggzyjy.sc.gov.cn", "webdate", "http://ggzyjy.sc.gov.cn/"),
    Platform("海南", "https://ggzy.hainan.gov.cn", "webdate", "https://ggzy.hainan.gov.cn/ggzy/"),
    Platform("北京", "https://ggzyfw.beijing.gov.cn", adapter="todo"),
    Platform("天津", "http://60.28.163.169", adapter="todo"),
    Platform("河北-招标投标", "http://www.hebeieb.com.cn", adapter="todo"),
    Platform("河北-公共资源", "http://www.hbggzyfwpt.cn", adapter="todo"),
    Platform("山西", "http://www.sxbid.com.cn", adapter="todo"),
    Platform("内蒙古", "http://www.nmgztb.com.cn", adapter="todo"),
    Platform("内蒙古-公共资源", "https://ggzyjy.nmg.gov.cn", adapter="todo"),
    Platform("辽宁", "http://www.lntb.gov.cn", adapter="todo"),
    Platform("吉林", "http://www.jl.gov.cn/ggzy", adapter="todo"),
    Platform("黑龙江", "https://ggzyjyw.hlj.gov.cn", adapter="todo"),
    Platform("上海", "https://www.shggzy.com", adapter="todo"),
    Platform("江苏", "http://www.jszbtb.com", adapter="todo"),
    Platform("安徽", "https://ggzy.ah.gov.cn", adapter="todo"),
    Platform("福建", "https://ggzyfw.fujian.gov.cn", adapter="todo"),
    Platform("江西", "http://www.jxsggzy.cn", adapter="todo"),
    Platform("山东", "http://ggzyjy.shandong.gov.cn", adapter="todo"),
    Platform("河南", "http://hndzzbtb.fgw.henan.gov.cn", adapter="todo"),
    Platform("湖南", "http://bidding.fgw.hunan.gov.cn", adapter="todo"),
    Platform("广东", "http://zbtb.gd.gov.cn", adapter="todo"),
    Platform("广西", "http://zbtb.gxi.gov.cn:9000", adapter="todo"),
    Platform("重庆", "https://www.cqggzy.com", adapter="todo"),
    Platform("贵州", "http://ztb.guizhou.gov.cn", adapter="todo"),
    Platform("云南", "https://ggzy.yn.gov.cn", adapter="todo"),
    Platform("西藏", "http://ggzy.xizang.gov.cn", adapter="todo"),
    Platform("陕西", "http://www.sntba.com", adapter="todo"),
    Platform("甘肃", "http://ggzyjy.gansu.gov.cn", adapter="todo"),
    Platform("秦皇岛", "https://www.qhdzzbfw.gov.cn", adapter="todo"),
    Platform("宁夏", "https://ggzyjy.fzggw.nx.gov.cn", adapter="todo"),
    Platform("新疆", "https://ggzy.xinjiang.gov.cn", adapter="todo"),
    Platform("新疆兵团", "http://ggzy.xjbt.gov.cn", adapter="todo"),
)

# Only platforms sharing the 智能搜索 endpoint are queried today.
PLATFORMS: tuple[Platform, ...] = tuple(
    p for p in PLATFORM_REGISTRY if p.adapter == "es"
)

_PLATFORM_BY_PROVINCE = {p.province: p for p in PLATFORM_REGISTRY}


def _notice_type(category: str) -> NoticeType:
    text = category or ""
    if any(word in text for word in ("中标", "成交", "结果", "验收", "合同")):
        return NoticeType.WINNING_BID
    if any(word in text for word in ("变更", "澄清", "答疑", "更正", "废标", "流标")):
        return NoticeType.CHANGE
    if any(word in text for word in ("招标", "采购", "磋商", "询价", "比选", "竞价", "单一来源")):
        return NoticeType.TENDER
    return NoticeType.OTHER


def _parse_dt(value: Any) -> Optional[date]:
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _title_key(value: str) -> str:
    import re

    text = re.sub(r"<[^>]+>", "", str(value or ""))
    return re.sub(r"[\s\-—_（）()【】\[\]：:，,。.、/]+", "", text).lower()


class GgzyEsSource:
    """Fan out a keyword query to several provincial public-resource platforms."""

    name = "ggzy"

    def __init__(
        self,
        platforms: Optional[list[Platform]] = None,
        timeout: float = 20.0,
        page_size: int = 50,
        concurrency: int = 8,
    ):
        self.platforms = platforms if platforms is not None else list(PLATFORMS)
        self.timeout = timeout
        self.page_size = page_size
        self._semaphore = asyncio.Semaphore(max(1, concurrency))
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"},
        )

    def platforms_for_province(self, province: str | None) -> list[Platform]:
        if not province:
            return list(self.platforms)
        text = province.strip()
        return [
            p
            for p in self.platforms
            if p.province in text or text in p.province
            or text.rstrip("省市自治区") in p.province
        ]

    def _body(
        self,
        platform: Platform,
        keyword: str,
        publish_date: Optional[date],
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        if start is None or end is None:
            if publish_date is not None:
                start = datetime.combine(publish_date, dtime.min).strftime("%Y-%m-%d %H:%M:%S")
                end = datetime.combine(publish_date, dtime.max).strftime("%Y-%m-%d %H:%M:%S")
            else:
                start = end = ""
        return {
            "token": "", "pn": 0, "rn": self.page_size, "sdt": "", "edt": "",
            "wd": keyword, "inc_wd": "", "exc_wd": "", "fields": "title", "cnum": "001",
            "sort": '{"webdate":"0"}', "ssort": "title", "cl": 200, "terminal": "",
            "condition": [],
            "time": [{"fieldName": platform.time_field, "startTime": start, "endTime": end}],
            "highlights": "", "statistics": None, "unionCondition": None, "accuracy": "",
            "noParticiple": "1", "searchRange": None, "isBusiness": "1",
        }

    async def search(
        self,
        keyword: str,
        notice_type: NoticeType,
        publish_date: Optional[date] = None,
        max_pages: int = 1,
    ) -> list[TenderCandidate]:
        results = await asyncio.gather(
            *(self._search_platform(p, keyword, publish_date) for p in self.platforms)
        )
        return [candidate for items in results for candidate in items]

    async def _search_platform(
        self,
        platform: Platform,
        keyword: str,
        publish_date: Optional[date],
        start: str | None = None,
        end: str | None = None,
    ) -> list[TenderCandidate]:
        async with self._semaphore:
            try:
                response = await self._client.post(
                    urljoin(platform.base_url, SEARCH_PATH),
                    json=self._body(platform, keyword, publish_date, start, end),
                    headers={
                        "Referer": platform.referer or platform.base_url + "/",
                        "Origin": platform.base_url,
                        "Content-Type": "application/json;charset=utf-8",
                    },
                )
                response.raise_for_status()
                payload = response.json()
            except Exception:  # noqa: BLE001
                logger.exception("ggzy_platform_search_failed", platform=platform.province, keyword=keyword)
                return []
        records = ((payload.get("result") or {}).get("records")) or []
        candidates: list[TenderCandidate] = []
        for record in records:
            candidate = self._to_candidate(platform, record, keyword)
            if publish_date is not None and candidate.publish_date != publish_date:
                continue
            candidates.append(candidate)
        return candidates

    async def search_by_title(
        self,
        title: str,
        province: str | None = None,
        publish_date: Optional[date] = None,
        tolerance_days: int = 3,
    ) -> Optional[TenderCandidate]:
        """Find a notice on a matching provincial platform by its title."""
        if not title:
            return None
        targets = self.platforms_for_province(province)
        if not targets:
            return None
        if publish_date is not None:
            start = datetime.combine(
                publish_date - timedelta(days=tolerance_days), dtime.min
            ).strftime("%Y-%m-%d %H:%M:%S")
            end = datetime.combine(
                publish_date + timedelta(days=tolerance_days), dtime.max
            ).strftime("%Y-%m-%d %H:%M:%S")
        else:
            start = end = None
        results = await asyncio.gather(
            *(
                self._search_platform(p, title, None, start, end)
                for p in targets
            )
        )
        key = _title_key(title)
        if not key:
            return None
        for items in results:
            for candidate in items:
                if _title_key(candidate.title) == key:
                    return candidate
        return None

    async def enrich_detail(self, candidate: TenderCandidate) -> str:
        """Try to obtain the full detail for a candidate from the ggzy platforms."""
        metadata = candidate.metadata or {}
        province = (
            metadata.get("province")
            or metadata.get("ggzy_province")
            or metadata.get("city")
        )
        found = await self.search_by_title(
            candidate.title, province, candidate.publish_date
        )
        if found is None:
            return ""
        return await self.fetch_detail(found)

    def _to_candidate(
        self, platform: Platform, record: dict[str, Any], keyword: str
    ) -> TenderCandidate:
        title = str(record.get("title") or record.get("titlenew") or "").strip()
        link = str(record.get("linkurl") or "").strip()
        url = urljoin(platform.base_url + "/", link) if link else f"{platform.base_url}/#{record.get('id')}"
        content = str(record.get("content") or "")
        city = record.get("infod") or record.get("xiaquname") or ""
        category = record.get("categoryname") or ""
        raw_list_text = " ".join(
            item for item in [title, str(city), category, content[:200]] if item
        )
        return TenderCandidate(
            title=title,
            url=url,
            notice_type=_notice_type(category),
            keyword=keyword,
            source=self.name,
            publish_date=_parse_dt(record.get("webdate") or record.get("infodate")),
            raw_list_text=raw_list_text,
            metadata={
                "ggzy_province": platform.province,
                "ggzy_category": category,
                "ggzy_city": city,
                "ggzy_infoid": record.get("infoid"),
                "ggzy_content": content,
            },
        )

    async def fetch_detail(self, candidate: TenderCandidate) -> str:
        metadata = candidate.metadata or {}
        snippet = str(metadata.get("ggzy_content") or "")
        url = candidate.url or ""
        if url.startswith("http"):
            platform = _PLATFORM_BY_PROVINCE.get(metadata.get("ggzy_province"))
            async with self._semaphore:
                try:
                    response = await self._client.get(
                        url,
                        headers={
                            "User-Agent": USER_AGENT,
                            "Referer": platform.referer if platform else url,
                        },
                    )
                    if response.status_code == 200 and len(response.text) > len(snippet):
                        return response.text
                except Exception:  # noqa: BLE001
                    logger.exception("ggzy_detail_fetch_failed", url=url)
        return snippet

    async def close(self) -> None:
        await self._client.aclose()


def build_ggzy_source(config) -> GgzyEsSource:
    raw = getattr(settings, "ggzy_platforms", None) or "浙江,四川,海南"
    provinces = [item.strip() for item in raw.split(",") if item.strip()]
    platforms = [_PLATFORM_BY_PROVINCE[p] for p in provinces if p in _PLATFORM_BY_PROVINCE]
    if not platforms:
        platforms = list(PLATFORMS)
    return GgzyEsSource(platforms=platforms)
