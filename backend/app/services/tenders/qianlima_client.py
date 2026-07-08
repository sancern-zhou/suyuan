from __future__ import annotations

import asyncio
import json
import os
import random
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, List, Optional
from urllib.parse import quote, quote_plus, urljoin, urlsplit, urlunsplit

import requests
import structlog
import urllib3

from config.settings import settings
from .models import NoticeType, TenderCandidate

logger = structlog.get_logger()

NOTICE_TYPE_QUERY = {
    NoticeType.TENDER: "招标公告",
    NoticeType.WINNING_BID: "中标公告",
    NoticeType.CHANGE: "变更公告",
    NoticeType.OTHER: "招标采购",
}


@dataclass(frozen=True)
class _QianlimaAccount:
    username: str
    password: str
    storage_state_path: str


class _QianlimaDailyLimitError(RuntimeError):
    pass


class QianlimaDetailAccessExhaustedError(RuntimeError):
    stop_tender_detail_processing = True


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
    search_ignores_notice_type = True

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
        accounts: Optional[str] = None,
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
        self._accounts = _parse_qianlima_accounts(
            username or os.getenv("QIANLIMA_USERNAME"),
            password or os.getenv("QIANLIMA_PASSWORD"),
            storage_state_path,
            accounts,
        )
        self._active_account_index = 0
        self._daily_limited_accounts: dict[date, set[int]] = {}
        self._detail_access_exhausted = False
        self._account_switch_lock = asyncio.Lock()
        self.username = self._accounts[0].username if self._accounts else None
        self.password = self._accounts[0].password if self._accounts else None
        self.storage_state_path = (
            self._accounts[0].storage_state_path if self._accounts else storage_state_path
        )
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
        self._start_lock = asyncio.Lock()
        self._browser_detail_semaphore = asyncio.Semaphore(
            max(1, int(os.getenv("QIANLIMA_BROWSER_DETAIL_CONCURRENCY", "3")))
        )
        logger.info(
            "qianlima_account_pool_loaded",
            account_count=len(self._accounts),
            active_username=self.username,
        )

    async def __aenter__(self) -> "QianlimaClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self) -> None:
        if self._context is not None:
            return
        async with self._start_lock:
            if self._context is not None:
                return
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            launch_kwargs = {"headless": self.headless}
            proxy_config = _qianlima_playwright_proxy()
            if proxy_config:
                launch_kwargs["proxy"] = proxy_config
            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            context_kwargs = {}
            if os.path.exists(self.storage_state_path):
                context_kwargs["storage_state"] = self.storage_state_path
            self._context = await self._browser.new_context(
                ignore_https_errors=not self.verify_tls, **context_kwargs
            )
            if _env_bool("QIANLIMA_BLOCK_HEAVY_RESOURCES", True):
                await self._context.route("**/*", self._route_lightweight_detail_resources)

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
        auth_token = str(data.get("token") or "").strip()
        os.makedirs(os.path.dirname(self.storage_state_path), exist_ok=True)
        cookies = self._cookies_to_storage_state(session.cookies)
        if auth_token:
            cookies.extend(
                [
                    {
                        "name": "xAuthToken",
                        "value": auth_token,
                        "domain": ".qianlima.com",
                        "path": "/",
                        "expires": -1,
                        "httpOnly": False,
                        "secure": True,
                        "sameSite": "Lax",
                    },
                    {
                        "name": "xAuthToken",
                        "value": auth_token,
                        "domain": ".vip.qianlima.com",
                        "path": "/",
                        "expires": -1,
                        "httpOnly": False,
                        "secure": True,
                        "sameSite": "Lax",
                    },
                ]
            )
        state = {
            "cookies": cookies,
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
            except Exception as exc:
                if os.getenv("QIANLIMA_STRICT_SEARCH_API", "").lower() in {
                    "1",
                    "true",
                    "yes",
                }:
                    raise
                if publish_date is not None and max_pages <= 0:
                    raise RuntimeError(
                        "千里马完整日期抓取依赖搜索API；API失败时不能降级为空浏览器抓取"
                    ) from exc
        return await self._search_via_browser(
            keyword, notice_type, publish_date, max_pages
        )

    async def fetch_detail(self, candidate: TenderCandidate) -> str:
        if self._detail_access_exhausted:
            raise QianlimaDetailAccessExhaustedError(
                "千里马详情账号池浏览上限已耗尽，停止后续详情页访问"
            )
        async with self._browser_detail_semaphore:
            if self._detail_access_exhausted:
                raise QianlimaDetailAccessExhaustedError(
                    "千里马详情账号池浏览上限已耗尽，停止后续详情页访问"
                )
            last_error: Exception | None = None
            max_retries = int(os.getenv("QIANLIMA_DETAIL_MAX_RETRIES", "3"))
            max_attempts = max_retries * max(1, len(self._accounts))
            for _ in range(max_attempts):
                account_index = self._active_account_index
                await self._ensure_member_detail_session()
                await self.start()
                await _sleep_before_detail_request()
                page = await self._context.new_page()
                daily_limit_error: _QianlimaDailyLimitError | None = None
                try:
                    await page.goto(candidate.url, wait_until="domcontentloaded")
                    networkidle_timeout_ms = int(
                        os.getenv("QIANLIMA_DETAIL_NETWORKIDLE_TIMEOUT_MS", "1500")
                    )
                    if networkidle_timeout_ms > 0:
                        try:
                            await page.wait_for_load_state(
                                "networkidle", timeout=networkidle_timeout_ms
                            )
                        except Exception:
                            pass
                    await page.wait_for_timeout(self.request_delay_ms)
                    content = await page.content()
                    if _is_detail_unavailable_page(content):
                        raise _QianlimaDailyLimitError(
                            "千里马详情页返回浏览上限或壳页面，拒绝入库"
                        )
                    if _is_member_limited_page(content):
                        raise RuntimeError("千里马详情页返回会员受限内容，拒绝使用非会员脱敏详情")
                    if _is_access_verification_page(content):
                        raise RuntimeError("千里马详情页触发访问验证，无法确认会员详情内容")
                    return content
                except _QianlimaDailyLimitError as exc:
                    last_error = exc
                    daily_limit_error = exc
                except Exception as exc:
                    last_error = exc
                    await page.wait_for_timeout(self.request_delay_ms)
                finally:
                    await page.close()
                if daily_limit_error is not None:
                    if await self._switch_to_next_detail_account(account_index):
                        continue
                    self._detail_access_exhausted = True
                    raise QianlimaDetailAccessExhaustedError(
                        "千里马详情账号池浏览上限已耗尽，停止后续详情页访问"
                    ) from daily_limit_error
            if last_error:
                raise last_error
            return ""

    async def _ensure_member_detail_session(self) -> None:
        if not _env_bool("QIANLIMA_REQUIRE_MEMBER_DETAIL", True):
            return
        if self._storage_state_cookie_value("xAuthToken"):
            return
        if not self.username or not self.password:
            raise RuntimeError("千里马详情页抓取要求会员登录态，但缺少账号密码配置")
        await self._login_via_browser()
        if not self._storage_state_cookie_value("xAuthToken"):
            raise RuntimeError("千里马会员登录态刷新失败，缺少xAuthToken")

    async def _switch_to_next_detail_account(self, limited_account_index: int) -> bool:
        if len(self._accounts) <= 1:
            logger.warning(
                "qianlima_account_switch_unavailable",
                reason="single_account",
                limited_account_index=limited_account_index,
            )
            return False
        today = date.today()
        async with self._account_switch_lock:
            limited = self._daily_limited_accounts.setdefault(today, set())
            limited.add(limited_account_index)
            if self._active_account_index not in limited:
                logger.info(
                    "qianlima_account_switch_skipped",
                    active_account_index=self._active_account_index,
                    limited_account_index=limited_account_index,
                )
                return True
            for offset in range(1, len(self._accounts) + 1):
                next_index = (self._active_account_index + offset) % len(self._accounts)
                if next_index in limited:
                    continue
                self._active_account_index = next_index
                account = self._accounts[next_index]
                self.username = account.username
                self.password = account.password
                self.storage_state_path = account.storage_state_path
                await self.close()
                logger.warning(
                    "qianlima_account_switched_after_daily_limit",
                    from_account_index=limited_account_index,
                    to_account_index=next_index,
                    to_username=account.username,
                )
                return True
        logger.warning(
            "qianlima_account_switch_unavailable",
            reason="all_accounts_limited",
            limited_account_index=limited_account_index,
            account_count=len(self._accounts),
        )
        return False

    async def _route_lightweight_detail_resources(self, route) -> None:
        request = route.request
        resource_type = getattr(request, "resource_type", "")
        url = getattr(request, "url", "")
        blocked_types = {"image", "font", "media"}
        blocked_hosts = (
            "hm.baidu.com",
            "analytics",
            "doubleclick",
            "googletagmanager",
            "cnzz.com",
        )
        if resource_type in blocked_types or any(host in url for host in blocked_hosts):
            await route.abort()
            return
        await route.continue_()

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
        refreshed_member_session = False
        for attempt in range(1, max_retries + 1):
            try:
                return await asyncio.to_thread(
                    self._request_search_api, query, page_number, publish_date
                )
            except requests.RequestException as exc:
                last_error = exc
                if (
                    self._is_unauthorized_error(exc)
                    and not refreshed_member_session
                    and self.username
                    and self.password
                ):
                    refreshed_member_session = True
                    await self._login_via_browser()
                    try:
                        return await asyncio.to_thread(
                            self._request_search_api,
                            query,
                            page_number,
                            publish_date,
                        )
                    except requests.RequestException as retry_exc:
                        last_error = retry_exc
                if attempt >= max_retries:
                    break
                await asyncio.sleep(min(3 * attempt, 12))
        if last_error:
            raise last_error
        return {}

    def _is_unauthorized_error(self, exc: requests.RequestException) -> bool:
        response = getattr(exc, "response", None)
        return getattr(response, "status_code", None) == 401

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
            proxies=_qianlima_search_proxies(),
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
        response = self._post_vip_search_api(payload, headers)
        if response.status_code == 401 and self.username and self.password:
            self._login_via_api()
            headers = self._http_headers("https://search.vip.qianlima.com/index.html")
            headers["Origin"] = "https://search.vip.qianlima.com"
            headers["Content-Type"] = "application/json"
            auth_token = self._storage_state_cookie_value("xAuthToken")
            if auth_token:
                headers["x-auth-token"] = auth_token
            response = self._post_vip_search_api(payload, headers)
        response.raise_for_status()
        return response.json()

    def _post_vip_search_api(
        self, payload: dict[str, Any], headers: dict[str, str]
    ) -> requests.Response:
        return requests.post(
            self.search_api_url,
            json=payload,
            timeout=int(os.getenv("QIANLIMA_REQUEST_TIMEOUT", "30")),
            verify=self.verify_tls,
            headers=headers,
            cookies=self._storage_state_cookies(),
            proxies=_qianlima_search_proxies(),
        )

    async def _search_via_browser(
        self,
        keyword: str,
        notice_type: NoticeType,
        publish_date: Optional[date],
        max_pages: int,
    ) -> List[TenderCandidate]:
        await self.start()
        candidates: List[TenderCandidate] = []
        query = keyword.strip()
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
            proxies=_qianlima_requests_proxies(),
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


def _is_member_limited_page(html: str) -> bool:
    value = _clean_link_label(html or "")
    patterns = [
        r"会员专享",
        r"会员可见",
        r"开通会员",
        r"升级会员",
        r"VIP会员",
        r"登录后查看",
        r"请登录后查看",
        r"查看完整信息",
        r"查看完整内容",
        r"下文中\*+为隐藏内容",
        r"\*+为隐藏内容",
        r"尚未开通.*权限",
        r"未开通.*权限",
        r"联系信息.*隐藏",
        r"联系方式.*隐藏",
    ]
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in patterns)


def _qianlima_playwright_proxy() -> dict[str, str] | None:
    server = _qianlima_proxy_setting("server")
    if not server:
        return None
    proxy = {"server": server}
    username = _qianlima_proxy_setting("username")
    password = _qianlima_proxy_setting("password")
    if username:
        proxy["username"] = username
    if password:
        proxy["password"] = password
    return proxy


def _qianlima_requests_proxies() -> dict[str, str] | None:
    server = _qianlima_proxy_setting("server")
    if not server:
        return None
    proxy_url = _proxy_url_with_credentials(
        server,
        _qianlima_proxy_setting("username"),
        _qianlima_proxy_setting("password"),
    )
    return {"http": proxy_url, "https": proxy_url}


def _qianlima_search_proxies() -> dict[str, str] | None:
    return None


def _qianlima_proxy_setting(name: str) -> str:
    env_name = f"QIANLIMA_PROXY_{name.upper()}"
    value = os.getenv(env_name)
    if value is not None and value.strip():
        return value.strip()
    return str(getattr(settings, f"qianlima_proxy_{name}", "") or "").strip()


async def _sleep_before_detail_request() -> None:
    min_delay = float(os.getenv("QIANLIMA_DETAIL_MIN_DELAY_SECONDS", "0"))
    max_delay = float(os.getenv("QIANLIMA_DETAIL_MAX_DELAY_SECONDS", "0"))
    if max_delay <= 0 and min_delay <= 0:
        return
    if max_delay < min_delay:
        max_delay = min_delay
    await asyncio.sleep(random.uniform(min_delay, max_delay))


def _proxy_url_with_credentials(
    server: str, username: str, password: str
) -> str:
    if not username:
        return server
    parts = urlsplit(server)
    if "@" in parts.netloc:
        return server
    credentials = quote(username, safe="")
    if password:
        credentials += f":{quote(password, safe='')}"
    return urlunsplit(
        (parts.scheme, f"{credentials}@{parts.netloc}", parts.path, parts.query, parts.fragment)
    )


def _parse_qianlima_accounts(
    username: str | None,
    password: str | None,
    storage_state_path: str,
    accounts_value: str | None = None,
) -> list[_QianlimaAccount]:
    account_specs: list[tuple[str, str]] = []
    raw_accounts = (
        accounts_value
        if accounts_value is not None
        else os.getenv("QIANLIMA_ACCOUNTS")
    )
    for item in (raw_accounts or "").split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        account_username, account_password = item.split(":", 1)
        account_username = account_username.strip()
        account_password = account_password.strip()
        if account_username and account_password:
            account_specs.append((account_username, account_password))
    if not account_specs and username and password:
        account_specs.append((username, password))
    accounts: list[_QianlimaAccount] = []
    for index, (account_username, account_password) in enumerate(account_specs):
        if len(account_specs) == 1:
            account_storage_path = storage_state_path
        else:
            account_storage_path = _account_storage_state_path(
                storage_state_path, account_username, index
            )
        accounts.append(
            _QianlimaAccount(
                username=account_username,
                password=account_password,
                storage_state_path=account_storage_path,
            )
        )
    return accounts


def _account_storage_state_path(
    storage_state_path: str, username: str, index: int
) -> str:
    directory = os.path.dirname(storage_state_path)
    filename = os.path.basename(storage_state_path)
    stem, ext = os.path.splitext(filename)
    safe_username = re.sub(r"[^A-Za-z0-9_.-]+", "_", username).strip("._")
    suffix = safe_username or f"account{index + 1}"
    return os.path.join(directory, f"{stem}.{suffix}{ext or '.json'}")


def _is_detail_unavailable_page(html: str) -> bool:
    value = _clean_link_label(html or "")
    shell_markers = [
        "加载中",
        "防诈骗提醒",
        "数据来自千里马招标网",
        "标题",
        "标的物",
        "项目编号",
        "招标单位",
    ]
    shell_score = sum(1 for marker in shell_markers if marker in value)
    procurement_content_markers = [
        "采购内容",
        "采购需求",
        "招标范围",
        "项目概况",
        "预算金额",
        "最高限价",
        "响应文件",
        "投标文件",
        "成交供应商",
        "中标供应商",
        "合同金额",
    ]
    has_procurement_content = any(marker in value for marker in procurement_content_markers)
    has_daily_limit_marker = re.search(
        r"今日浏览已达到上限|浏览已达到上限|明日再试", value, re.IGNORECASE
    )
    if has_daily_limit_marker and not has_procurement_content:
        return True
    if (
        has_daily_limit_marker
        and shell_score >= 3
        and not has_procurement_content
        and len(value) < 1500
    ):
        return True
    return shell_score >= 5 and not has_procurement_content


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
