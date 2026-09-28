"""剑鱼标讯 (jianyu360.com) tender source.

The site is a qiankun SPA whose search API returns AES-encrypted payloads
(``antiEncrypt``).  Decryption happens inside a dedicated helper iframe
(``/page_decrypt/index.html``) over ``postMessage``.  We therefore drive a real
Chromium page, call the same-origin search API from the page context, and hand
the ciphertext to the site's own decrypt iframe -- no need to replicate the
obfuscated crypto.

Search API::

    POST /jyapi/jybx/core/fType/searchList
    body: {keyWords, publishTime: "<startUnix>-<endUnix>", pageNum, pageSize, ...}

``publishTime`` is an exact unix-second window, so a single publish date maps to
``[dayStart, dayEnd]`` for both the daily run and historical backfill.

Detail content is fetched through ``/jyapi/jybx/core/participate/content`` and
falls back to the (partly masked) ``detail`` snippet returned by search.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import date, datetime, time as dtime
from typing import Any, Optional

import structlog

from config.settings import settings

from ..models import NoticeType, TenderCandidate

logger = structlog.get_logger()

START_URL = "https://www.jianyu360.cn/jylab/supsearch/index.html"
SITE_BASE = "https://www.jianyu360.cn"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)

_SEARCH_BODY_BASE: dict[str, Any] = {
    "searchGroup": 1,
    "reqType": "lastNews",
    "pageNum": 1,
    "pageSize": 50,
    "keyWords": "",
    "searchMode": 0,
    "bidField": "",
    "publishTime": "",
    "selectType": "title,content",
    "subtype": "",
    "exclusionWords": "",
    "buyer": "",
    "winner": "",
    "agency": "",
    "industry": "",
    "province": "",
    "city": "",
    "district": "",
    "buyerClass": "",
    "fileExists": "",
    "price": "",
    "buyerTel": "",
    "winnerTel": "",
    "basicClass": "",
    "deadlineType": "",
}

# Runs inside the page: POST a same-origin API, then decrypt via the site iframe.
_DECRYPT_FETCH_JS = r"""
async ({url, body, timeoutMs}) => {
  const iframe = document.querySelector('iframe[name^="jianyu_"]');
  if (!iframe) return {error: "decrypt iframe not ready"};
  const target = location.origin;
  const resp = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
    credentials: "include",
  });
  const raw = await resp.json();
  if (raw.antiEncrypt === undefined && raw.error_code !== undefined) {
    return {plain: raw};
  }
  if (!raw.antiEncrypt && raw.data !== undefined && typeof raw.data === "object") {
    return {plain: raw};
  }
  const plain = await new Promise((resolve, reject) => {
    const id = "jy_" + Date.now() + "_" + Math.random().toString(36).slice(2);
    const handler = (ev) => {
      if (ev.data && ev.data.id === id) {
        window.removeEventListener("message", handler);
        resolve(ev.data);
      }
    };
    window.addEventListener("message", handler);
    iframe.contentWindow.postMessage(
      {id, base64Key: raw.secretKey, cipherText: raw.data, fromOrigin: location.origin, type: "decrypt"},
      target
    );
    setTimeout(() => {
      window.removeEventListener("message", handler);
      reject(new Error("decrypt timeout"));
    }, timeoutMs);
  });
  return {plainText: plain.plainText};
}
"""


def _day_window(publish_date: date) -> str:
    start = datetime.combine(publish_date, dtime.min)
    end = datetime.combine(publish_date, dtime.max)
    return f"{int(start.timestamp())}-{int(end.timestamp())}"


def _parse_day(ts: Any) -> Optional[date]:
    try:
        value = int(str(ts).strip())
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(value).date()


def _notice_type(subtype: str, has_winner: bool) -> NoticeType:
    text = subtype or ""
    if any(word in text for word in ("中标", "成交", "结果", "验收", "合同")):
        return NoticeType.WINNING_BID
    if any(word in text for word in ("变更", "澄清", "答疑", "更正")):
        return NoticeType.CHANGE
    if any(word in text for word in ("招标", "采购", "竞争性", "比选", "询价", "单一来源")):
        return NoticeType.TENDER
    return NoticeType.WINNING_BID if has_winner else NoticeType.OTHER


class JianyuClient:
    name = "jianyu360"

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        cookie: str | None = None,
        headless: bool = True,
        timeout_ms: int = 30000,
    ):
        self.username = username or os.getenv("JIANYU_USERNAME")
        self.password = password or os.getenv("JIANYU_PASSWORD")
        self.cookie = cookie or os.getenv("JIANYU_COOKIE")
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._lock = asyncio.Lock()
        self._login_attempted = False

    async def _ensure_page(self):
        if self._page is not None and not self._page.is_closed():
            return self._page
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        context_kwargs: dict[str, Any] = {"user_agent": os.getenv("JIANYU_USER_AGENT", DEFAULT_UA)}
        if self.cookie:
            # cookie string "a=1; b=2" -> storage via headers is handled by route below
            context_kwargs["extra_http_headers"] = {"Cookie": self.cookie}
        self._context = await self._browser.new_context(**context_kwargs)
        self._page = await self._context.new_page()
        await self._page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
        await self._page.wait_for_timeout(6000)
        return self._page

    async def _login_if_configured(self) -> None:
        if self._login_attempted or not (self.username and self.password):
            return
        self._login_attempted = True
        try:
            page = await self._ensure_page()
            await page.click("text=登录", timeout=5000)
            await page.wait_for_timeout(1500)
            await page.fill('input[name="pass_phone"]', self.username)
            await page.fill('input[name="pass_pass"]', self.password)
            await page.click("text=登录", timeout=5000)
            await page.wait_for_timeout(4000)
            logger.info("jianyu_login_attempted", username=self.username)
        except Exception:  # noqa: BLE001
            logger.exception("jianyu_login_failed")

    async def _call(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        page = await self._ensure_page()
        result = await page.evaluate(
            _DECRYPT_FETCH_JS,
            {"url": url, "body": body, "timeoutMs": self.timeout_ms},
        )
        if result.get("plainText"):
            return json.loads(result["plainText"])
        if result.get("plain") is not None:
            return result["plain"]
        raise RuntimeError(f"jianyu decrypt failed: {result.get('error')}")

    async def search(
        self,
        keyword: str,
        notice_type: NoticeType,
        publish_date: Optional[date] = None,
        max_pages: int = 1,
    ) -> list[TenderCandidate]:
        async with self._lock:
            await self._login_if_configured()
            if publish_date is not None:
                window = _day_window(publish_date)
            else:
                today = date.today()
                window = _day_window(today)
            if max_pages and max_pages > 0:
                page_limit = max_pages
            else:
                page_limit = 5
            candidates: list[TenderCandidate] = []
            for page_num in range(1, page_limit + 1):
                body = dict(_SEARCH_BODY_BASE)
                body.update(
                    {
                        "keyWords": keyword,
                        "publishTime": window,
                        "pageNum": page_num,
                        "pageSize": 50,
                    }
                )
                try:
                    payload = await self._call(
                        f"{SITE_BASE}/jyapi/jybx/core/fType/searchList", body
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("jianyu_search_failed", keyword=keyword, page=page_num)
                    break
                records = ((payload.get("data") or {}).get("list")) or []
                if not records:
                    break
                for record in records:
                    candidate = self._to_candidate(record, keyword)
                    if publish_date is not None and candidate.publish_date != publish_date:
                        continue
                    candidates.append(candidate)
                if len(records) < 50:
                    break
                await asyncio.sleep(1.0)
            return candidates

    def _to_candidate(self, record: dict[str, Any], keyword: str) -> TenderCandidate:
        bid_id = record.get("id")
        title = str(record.get("title") or "").strip()
        buyer = record.get("buyer")
        winner = record.get("winner")
        snippet = str(record.get("detail") or "")
        raw_list_text = " ".join(
            str(item)
            for item in [
                title,
                buyer,
                winner,
                record.get("area"),
                record.get("industry"),
                snippet[:200],
            ]
            if item
        )
        return TenderCandidate(
            title=title,
            url=f"{SITE_BASE}/detail/{bid_id}.html",
            notice_type=_notice_type(record.get("subtype") or "", bool(winner)),
            keyword=keyword,
            source=self.name,
            publish_date=_parse_day(record.get("publishTime")),
            raw_list_text=raw_list_text,
            metadata={
                "jianyu_id": bid_id,
                "buyer": buyer,
                "winner": winner,
                "area": record.get("area"),
                "city": record.get("city"),
                "industry": record.get("industry"),
                "site": record.get("site"),
                "subtype": record.get("subtype"),
                "detail_snippet": snippet,
            },
        )

    async def fetch_detail(self, candidate: TenderCandidate) -> str:
        if candidate.source != self.name:
            candidate.source = self.name
        metadata = candidate.metadata or {}
        snippet = metadata.get("detail_snippet") or ""
        bid_id = metadata.get("jianyu_id")
        if bid_id:
            async with self._lock:
                try:
                    payload = await self._call(
                        f"{SITE_BASE}/jyapi/jybx/core/participate/content",
                        {"id": bid_id},
                    )
                    content = (
                        payload.get("data")
                        if isinstance(payload, dict)
                        else payload
                    )
                    if isinstance(content, (dict, list)):
                        text = json.dumps(content, ensure_ascii=False)
                    else:
                        text = str(content or "")
                    if len(text) > len(snippet):
                        return text
                except Exception:  # noqa: BLE001
                    logger.exception("jianyu_detail_failed", id=bid_id)
        return f"<html><body>{snippet}</body></html>"

    async def close(self) -> None:
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:  # noqa: BLE001
                pass
            self._context = None
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:  # noqa: BLE001
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
            self._playwright = None
        self._page = None


def build_jianyu_source(config) -> JianyuClient:
    return JianyuClient(
        username=getattr(settings, "jianyu_username", None),
        password=getattr(settings, "jianyu_password", None),
        cookie=getattr(settings, "jianyu_cookie", None),
    )
