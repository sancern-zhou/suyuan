from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import date, datetime
from typing import Any, List, Optional
from urllib.parse import quote_plus, urljoin

import requests
import urllib3

from .models import NoticeType, TenderCandidate

NOTICE_TYPE_QUERY = {
    NoticeType.TENDER: "招标公告",
    NoticeType.WINNING_BID: "中标公告",
    NoticeType.CHANGE: "变更公告",
    NoticeType.OTHER: "招标采购",
}


def parse_qianlima_list_html(
    html: str,
    base_url: str,
    keyword: str,
    notice_type: NoticeType,
) -> List[TenderCandidate]:
    candidates: List[TenderCandidate] = []
    seen = set()
    link_pattern = re.compile(
        r"<a\b[^>]*href=[\'\"]([^\'\"]+)[\'\"][^>]*>(.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    for href, label_html in link_pattern.findall(html or ""):
        title = _clean_link_label(label_html)
        if not _looks_like_notice(title):
            continue
        url = urljoin(base_url, href)
        key = url.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            TenderCandidate(
                title=title,
                url=url,
                notice_type=notice_type,
                keyword=keyword,
                source="qianlima",
                raw_list_text=title,
            )
        )
    return candidates


def parse_qianlima_search_api_response(
    payload: dict[str, Any],
    keyword: str,
    notice_type: NoticeType,
) -> List[TenderCandidate]:
    candidates: List[TenderCandidate] = []
    rows = _extract_api_rows(payload)
    for row in rows:
        title = _clean_link_label(
            str(row.get("popTitle") or row.get("showTitle") or row.get("title") or "")
        )
        show_title = _clean_link_label(str(row.get("showTitle") or ""))
        raw_list_text = " ".join(
            item for item in [title, show_title, str(row.get("areaName") or "")] if item
        )
        url = str(row.get("url") or row.get("originUrl") or "").strip()
        if not title or not url or not _looks_like_notice(title):
            continue
        publish_date = _parse_date(
            row.get("updateTime") or row.get("publishTime") or row.get("date")
        )
        candidates.append(
            TenderCandidate(
                title=title,
                url=url,
                notice_type=notice_type,
                keyword=keyword,
                source="qianlima",
                publish_date=publish_date,
                raw_list_text=raw_list_text,
                metadata={
                    "contentid": row.get("contentid"),
                    "prog_name": row.get("progName"),
                    "area_name": row.get("areaName"),
                    "catid": row.get("catid"),
                    "update_time_str": row.get("updateTimeStr"),
                    "origin_url": row.get("originUrl"),
                },
            )
        )
    return _dedupe_candidates(candidates)


def _extract_api_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data", payload)
    if isinstance(data, dict):
        rows = data.get("data") or data.get("list") or data.get("records") or []
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    return None


def _clean_link_label(label_html: str) -> str:
    label = re.sub(r"<[^>]+>", " ", label_html or "")
    label = re.sub(r"\s+", " ", label)
    return label.strip(" -_\t\r\n")


def _looks_like_notice(title: str) -> bool:
    if not title or len(title) < 8:
        return False
    include_words = [
        "招标",
        "采购",
        "中标",
        "成交",
        "变更",
        "结果",
        "公告",
        "项目",
        "选取",
    ]
    exclude_words = ["关于我们", "联系我们", "会员", "登录", "注册", "帮助", "首页"]
    return any(word in title for word in include_words) and not any(
        word in title for word in exclude_words
    )


class QianlimaClient:
    def __init__(
        self,
        base_url: str = "https://www.qianlima.com",
        search_url_template: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        storage_state_path: str = "data/qianlima_storage_state.json",
        headless: bool = True,
        request_delay_ms: int = 800,
        use_search_api: Optional[bool] = None,
        use_detail_http: Optional[bool] = None,
        verify_tls: Optional[bool] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.search_url_template = search_url_template or os.getenv(
            "QIANLIMA_SEARCH_URL_TEMPLATE",
            "https://search.qianlima.com/?key={keyword}&page={page}",
        )
        self.search_api_url = os.getenv(
            "QIANLIMA_SEARCH_API_URL",
            "https://search.vip.qianlima.com/rest/service/website/search/solr",
        )
        self.username = username or os.getenv("QIANLIMA_USERNAME")
        self.password = password or os.getenv("QIANLIMA_PASSWORD")
        self.storage_state_path = storage_state_path
        self.headless = headless
        self.request_delay_ms = request_delay_ms
        self.use_search_api = (
            _env_bool("QIANLIMA_USE_SEARCH_API", True)
            if use_search_api is None
            else use_search_api
        )
        self.use_detail_http = (
            _env_bool("QIANLIMA_USE_DETAIL_HTTP", True)
            if use_detail_http is None
            else use_detail_http
        )
        self.verify_tls = (
            _env_bool("QIANLIMA_VERIFY_TLS", False)
            if verify_tls is None
            else verify_tls
        )
        if not self.verify_tls:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self._playwright = None
        self._browser = None
        self._context = None

    async def __aenter__(self) -> "QianlimaClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self) -> None:
        if self._context is not None:
            return
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        context_kwargs = {}
        if os.path.exists(self.storage_state_path):
            context_kwargs["storage_state"] = self.storage_state_path
        self._context = await self._browser.new_context(
            ignore_https_errors=not self.verify_tls, **context_kwargs
        )

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def login(self, login_url: Optional[str] = None) -> None:
        if not self.username or not self.password:
            raise RuntimeError(
                "QIANLIMA_USERNAME and QIANLIMA_PASSWORD must be set in the environment"
            )
        method = os.getenv("QIANLIMA_LOGIN_METHOD", "api").strip().lower()
        if method == "api":
            await asyncio.to_thread(self._login_via_api)
            return
        await self._login_via_browser(login_url)

    async def _login_via_browser(self, login_url: Optional[str] = None) -> None:
        await self.start()
        page = await self._context.new_page()
        await page.goto(
            login_url or "https://vip.qianlima.com/login/",
            wait_until="domcontentloaded",
        )
        await page.fill(
            'input[type="text"], input[name*="user"], input[name*="phone"], input[placeholder*="账号"], input[placeholder*="手机号"]',
            self.username,
        )
        await page.fill(
            'input[type="password"], input[placeholder*="密码"]', self.password
        )
        await page.click('button:has-text("登录"), input[type="submit"], .login-btn')
        await page.wait_for_load_state("networkidle")
        os.makedirs(os.path.dirname(self.storage_state_path), exist_ok=True)
        await self._context.storage_state(path=self.storage_state_path)
        await page.close()

    def _login_via_api(self) -> None:
        session = requests.Session()
        session.headers.update(self._http_headers("https://vip.qianlima.com/login/"))
        session.headers.pop("Origin", None)
        session.get(
            "https://vip.qianlima.com/login/",
            timeout=int(os.getenv("QIANLIMA_REQUEST_TIMEOUT", "30")),
            verify=self.verify_tls,
        )
        response = session.get(
            os.getenv(
                "QIANLIMA_LOGIN_API_URL",
                "https://vip.qianlima.com/rest/u/api/user/new/web/login",
            ),
            params={
                "username": self.username,
                "psw": self.password,
                "source": "",
                "remLogin": 1,
            },
            timeout=int(os.getenv("QIANLIMA_REQUEST_TIMEOUT", "30")),
            verify=self.verify_tls,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"千里马登录HTTP失败: {response.status_code}")
        payload = response.json()
        data = payload.get("data") or {}
        if data.get("loginStatus") != 200:
            message = data.get("message") or payload.get("msg") or "千里马登录失败"
            raise RuntimeError(message)
        os.makedirs(os.path.dirname(self.storage_state_path), exist_ok=True)
        state = {
            "cookies": self._cookies_to_storage_state(session.cookies),
            "origins": [],
        }
        with open(self.storage_state_path, "w", encoding="utf-8") as file_obj:
            json.dump(state, file_obj, ensure_ascii=False, indent=2)

    def _cookies_to_storage_state(self, cookie_jar) -> list[dict[str, Any]]:
        cookies: list[dict[str, Any]] = []
        seen = set()
        for cookie in cookie_jar:
            domains = [cookie.domain or ".qianlima.com", ".qianlima.com"]
            for domain in domains:
                key = (cookie.name, domain, cookie.path or "/")
                if key in seen:
                    continue
                seen.add(key)
                cookies.append(
                    {
                        "name": cookie.name,
                        "value": cookie.value,
                        "domain": domain,
                        "path": cookie.path or "/",
                        "expires": int(cookie.expires) if cookie.expires else -1,
                        "httpOnly": bool(getattr(cookie, "_rest", {}).get("HttpOnly")),
                        "secure": bool(cookie.secure),
                        "sameSite": "Lax",
                    }
                )
        return cookies

    async def search(
        self,
        keyword: str,
        notice_type: NoticeType,
        publish_date: Optional[date] = None,
        max_pages: int = 1,
    ) -> List[TenderCandidate]:
        if self.use_search_api:
            try:
                return await self._search_via_api(
                    keyword, notice_type, publish_date, max_pages
                )
            except Exception:
                if os.getenv("QIANLIMA_STRICT_SEARCH_API", "").lower() in {
                    "1",
                    "true",
                    "yes",
                }:
                    raise
        return await self._search_via_browser(
            keyword, notice_type, publish_date, max_pages
        )

    async def fetch_detail(self, candidate: TenderCandidate) -> str:
        if self.use_detail_http:
            try:
                detail = await asyncio.to_thread(self._fetch_detail_http, candidate.url)
            except Exception:
                detail = ""
            if detail and not _is_access_verification_page(detail):
                return detail
        await self.start()
        max_retries = int(os.getenv("QIANLIMA_DETAIL_MAX_RETRIES", "3"))
        last_error: Exception | None = None
        for _ in range(max_retries):
            page = await self._context.new_page()
            try:
                await page.goto(candidate.url, wait_until="domcontentloaded")
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                await page.wait_for_timeout(self.request_delay_ms)
                return await page.content()
            except Exception as exc:
                last_error = exc
                await page.wait_for_timeout(self.request_delay_ms)
            finally:
                await page.close()
        if last_error:
            raise last_error
        return ""

    async def _search_via_api(
        self,
        keyword: str,
        notice_type: NoticeType,
        publish_date: Optional[date],
        max_pages: int,
    ) -> List[TenderCandidate]:
        candidates: List[TenderCandidate] = []
        query = keyword.strip()
        complete_date_crawl = publish_date is not None and max_pages <= 0
        page_limit = (
            int(os.getenv("QIANLIMA_MAX_COMPLETE_PAGES", "50"))
            if complete_date_crawl
            else max_pages
        )
        seen_target_date = False
        page_delay_ms = int(
            os.getenv("QIANLIMA_SEARCH_PAGE_DELAY_MS", str(self.request_delay_ms))
        )
        page_number = 1
        while page_number <= page_limit:
            payload = await self._request_search_api_with_retries(
                query, page_number, publish_date
            )
            data = payload.get("data") or {}
            pages_count = data.get("pagesCount")
            if complete_date_crawl and isinstance(pages_count, int) and pages_count > 0:
                page_limit = min(page_limit, pages_count)
            page_candidates = parse_qianlima_search_api_response(
                payload, keyword, notice_type
            )
            if not page_candidates:
                break
            page_dates = [
                item.publish_date
                for item in page_candidates
                if item.publish_date is not None
            ]
            if publish_date is not None:
                if any(item.publish_date == publish_date for item in page_candidates):
                    seen_target_date = True
                page_candidates = [
                    item
                    for item in page_candidates
                    if item.publish_date == publish_date
                ]
            candidates.extend(page_candidates)
            if complete_date_crawl and self._is_past_target_date_page(
                page_dates, publish_date, seen_target_date
            ):
                break
            if page_number < page_limit and page_delay_ms > 0:
                await asyncio.sleep(page_delay_ms / 1000)
            page_number += 1
        return _dedupe_candidates(candidates)

    async def _request_search_api_with_retries(
        self,
        query: str,
        page_number: int,
        publish_date: date | None = None,
    ) -> dict[str, Any]:
        max_retries = int(os.getenv("QIANLIMA_SEARCH_MAX_RETRIES", "4"))
        last_error: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                return await asyncio.to_thread(
                    self._request_search_api, query, page_number, publish_date
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= max_retries:
                    break
                await asyncio.sleep(min(3 * attempt, 12))
        if last_error:
            raise last_error
        return {}

    def _is_past_target_date_page(
        self,
        page_dates: list[date],
        target_date: date | None,
        seen_target_date: bool,
    ) -> bool:
        if target_date is None or not page_dates:
            return False
        if all(item < target_date for item in page_dates):
            return True
        return seen_target_date and not any(item >= target_date for item in page_dates)

    def _request_search_api(
        self,
        query: str,
        page_number: int,
        publish_date: date | None = None,
    ) -> dict[str, Any]:
        if "search.vip.qianlima.com" in self.search_api_url:
            return self._request_vip_search_api(query, page_number, publish_date)

        params = {
            "keywords": query,
            "page": page_number,
            "pageSize": int(os.getenv("QIANLIMA_PAGE_SIZE", "10")),
            "searchType": int(os.getenv("QIANLIMA_SEARCH_TYPE", "1")),
        }
        response = requests.post(
            self.search_api_url,
            params=params,
            json={},
            timeout=int(os.getenv("QIANLIMA_REQUEST_TIMEOUT", "30")),
            verify=self.verify_tls,
            headers=self._http_headers("https://search.qianlima.com/"),
            cookies=self._storage_state_cookies(),
        )
        response.raise_for_status()
        return response.json()

    def _request_vip_search_api(
        self,
        query: str,
        page_number: int,
        publish_date: date | None = None,
    ) -> dict[str, Any]:
        payload = {
            "keywords": query,
            "timeType": (
                4 if publish_date else int(os.getenv("QIANLIMA_TIME_TYPE", "8"))
            ),
            "filtermode": os.getenv("QIANLIMA_FILTER_MODE", "8"),
            "searchMode": int(os.getenv("QIANLIMA_SEARCH_MODE", "1")),
            "currentPage": page_number,
            "numPerPage": int(os.getenv("QIANLIMA_PAGE_SIZE", "20")),
            "sortType": os.getenv("QIANLIMA_SORT_TYPE", "6" if publish_date else "2"),
            "allType": int(os.getenv("QIANLIMA_ALL_TYPE", "-1")),
            "noticeSegmentTypeStr": os.getenv("QIANLIMA_NOTICE_SEGMENT_TYPE", ""),
            "beginAmount": "",
            "endAmount": "",
            "purchasingUnitIdList": "",
            "threeClassifyTagStr": "",
            "fourLevelCategoryIdListStr": "",
            "threeLevelCategoryIdListStr": "",
            "levelId": "",
            "tab": int(os.getenv("QIANLIMA_SEARCH_TAB", "0")),
            "searchDataType": int(os.getenv("QIANLIMA_SEARCH_DATA_TYPE", "0")),
            "types": os.getenv("QIANLIMA_TYPES", "-1"),
            "showContent": 1,
            "hasTenderTransferProject": 1,
            "newAreas": "",
            "hasChooseSortType": 1,
            "summaryType": 0,
        }
        if publish_date:
            payload["beginTime"] = publish_date.isoformat()
            payload["endTime"] = publish_date.isoformat()
        headers = self._http_headers("https://search.vip.qianlima.com/index.html")
        headers["Origin"] = "https://search.vip.qianlima.com"
        headers["Content-Type"] = "application/json"
        auth_token = self._storage_state_cookie_value("xAuthToken")
        if auth_token:
            headers["x-auth-token"] = auth_token
        response = requests.post(
            self.search_api_url,
            json=payload,
            timeout=int(os.getenv("QIANLIMA_REQUEST_TIMEOUT", "30")),
            verify=self.verify_tls,
            headers=headers,
            cookies=self._storage_state_cookies(),
        )
        response.raise_for_status()
        return response.json()

    async def _search_via_browser(
        self,
        keyword: str,
        notice_type: NoticeType,
        publish_date: Optional[date],
        max_pages: int,
    ) -> List[TenderCandidate]:
        await self.start()
        candidates: List[TenderCandidate] = []
        query = " ".join([keyword, NOTICE_TYPE_QUERY.get(notice_type, "")]).strip()
        for page_number in range(1, max_pages + 1):
            url = self.search_url_template.format(
                keyword=quote_plus(query),
                raw_keyword=query,
                notice_type=notice_type.value,
                page=page_number,
                publish_date=publish_date.isoformat() if publish_date else "",
            )
            page = await self._context.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(self.request_delay_ms)
            html = await page.content()
            await page.close()
            candidates.extend(
                parse_qianlima_list_html(html, self.base_url, keyword, notice_type)
            )
        return _dedupe_candidates(candidates)

    def _fetch_detail_http(self, url: str) -> str:
        response = requests.get(
            url,
            timeout=int(os.getenv("QIANLIMA_REQUEST_TIMEOUT", "30")),
            verify=self.verify_tls,
            headers=self._http_headers("https://search.qianlima.com/"),
            cookies=self._storage_state_cookies(),
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        return response.text

    def _http_headers(self, referer: str) -> dict[str, str]:
        return {
            "User-Agent": os.getenv(
                "QIANLIMA_USER_AGENT",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
            ),
            "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": referer,
            "Origin": "https://search.qianlima.com",
        }

    def _storage_state_cookies(self) -> dict[str, str]:
        if not os.path.exists(self.storage_state_path):
            return {}
        try:
            with open(self.storage_state_path, "r", encoding="utf-8") as file_obj:
                state = json.load(file_obj)
        except (OSError, json.JSONDecodeError):
            return {}
        cookies = {}
        for cookie in state.get("cookies", []):
            name = cookie.get("name")
            value = cookie.get("value")
            if name and value:
                cookies[name] = value
        return cookies

    def _storage_state_cookie_value(self, cookie_name: str) -> str | None:
        return self._storage_state_cookies().get(cookie_name)


def _is_access_verification_page(html: str) -> bool:
    value = html or ""
    return (
        "Access Verification" in value
        or "showValidateCode" in value
        or "请输入验证码" in value
    )


def _dedupe_candidates(candidates: List[TenderCandidate]) -> List[TenderCandidate]:
    seen = set()
    unique: List[TenderCandidate] = []
    for candidate in candidates:
        key = candidate.normalized_url_key()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
