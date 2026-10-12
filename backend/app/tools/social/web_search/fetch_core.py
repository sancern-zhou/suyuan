"""
web_fetch 底层能力：SSRF 防护、TTL 缓存、正文提取、重定向策略

- assert_url_safe: 解析域名并拒绝私网/回环/链路本地地址（对齐 ZCode WebFetch 拒绝私有 URL 的行为）
- TTLCache: 进程级 URL 缓存（默认 15 分钟），同一 URL 在多轮对话中不重复抓取
- extract_readable: trafilatura 主内容提取（markdown），未安装或提取失败时回退正则剥离
- follow_redirects_safely: 同主机重定向自动跟随，跨主机重定向返回给调用方决定
"""

from __future__ import annotations

import asyncio
import html as html_module
import ipaddress
import os
import re
import time
from collections import OrderedDict
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
MAX_REDIRECTS = 5

CACHE_TTL_SECONDS = 900
CACHE_MAX_ENTRIES = 64
# 超过该长度的提取结果不缓存，避免占用过多内存（maxChars 上限 50000，2 倍余量足够）
CACHE_MAX_TEXT_CHARS = 120_000


class TTLCache:
    """简单的进程级 TTL + LRU 缓存（线程安全依赖 GIL，web 工具均为单事件循环调用）"""

    def __init__(self, ttl: float = CACHE_TTL_SECONDS, maxsize: int = CACHE_MAX_ENTRIES):
        self.ttl = ttl
        self.maxsize = maxsize
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < time.monotonic():
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if self.maxsize <= 0:
            return
        self._data.pop(key, None)
        self._data[key] = (time.monotonic() + self.ttl, value)
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()


# 进程级网页缓存：key 为去掉 fragment 的 URL，value 为提取后的完整文本（未截断）
PAGE_CACHE = TTLCache()


def normalize_cache_key(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}?{parts.query}"


def _addr_is_private(addr: ipaddress._BaseAddress) -> bool:
    # ::ffff:x.y.z.w 映射地址按内嵌 IPv4 判定
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return not addr.is_global


async def _resolve_host(host: str) -> list[str]:
    """解析域名返回全部 IP（测试可 monkeypatch 此函数）"""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None)
    return [info[4][0] for info in infos]


async def validate_url_safe(url: str) -> tuple[bool, str]:
    """校验 URL 格式与目标地址安全性（SSRF 防护）

    返回 (是否安全, 错误说明)。拒绝私网/回环/链路本地等非全局地址；
    设置 WEB_FETCH_ALLOW_PRIVATE=1 可放行（内网数据源等受控场景）。
    """
    try:
        parts = urlparse(url)
    except Exception as e:
        return False, f"URL解析失败: {e}"
    if parts.scheme not in ("http", "https"):
        return False, f"仅支持 http/https，当前: '{parts.scheme or '无'}'"
    if not parts.netloc:
        return False, "缺少域名"

    if os.environ.get("WEB_FETCH_ALLOW_PRIVATE", "").strip() == "1":
        return True, ""

    host = parts.hostname
    if not host:
        return False, "缺少域名"

    # host 本身就是 IP 字面量时无需 DNS
    try:
        addr = ipaddress.ip_address(host)
        if _addr_is_private(addr):
            return False, f"拒绝访问内网/保留地址: {host}"
        return True, ""
    except ValueError:
        pass

    try:
        addrs = await _resolve_host(host)
    except Exception as e:
        return False, f"域名解析失败: {host} ({e})"
    if not addrs:
        return False, f"域名解析失败: {host}"
    for raw in addrs:
        try:
            if _addr_is_private(ipaddress.ip_address(raw)):
                return False, f"拒绝访问内网/保留地址: {host} -> {raw}"
        except ValueError:
            continue
    return True, ""


def _strip_tags(text: str) -> str:
    """移除HTML标签，解码实体"""
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html_module.unescape(text).strip()


def _normalize_ws(text: str) -> str:
    """规范化空白字符"""
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _extract_text_from_html(html_content: str) -> str:
    """从HTML中提取可读文本（正则回退方案：无 trafilatura 或提取失败时使用）"""
    text = re.sub(r"<script[\s\S]*?</script>", "", html_content, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)

    title_match = re.search(r"<title[^>]*>([\s\S]*?)</title>", text, flags=re.I)
    title = _strip_tags(title_match.group(1)).strip() if title_match else ""

    text = re.sub(
        r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>([\s\S]*?)</a>",
        lambda m: f"[{_strip_tags(m[2]).strip()}]({m[1]})",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"<h([1-6])[^>]*>([\s\S]*?)</\1>",
        lambda m: "\n" + "#" * int(m[1]) + " " + _strip_tags(m[2]).strip() + "\n",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"<li[^>]*>([\s\S]*?)</li>",
        lambda m: "\n- " + _strip_tags(m[1]).strip(),
        text,
        flags=re.I,
    )
    text = re.sub(r"</(p|div|section|article)>", "\n\n", text, flags=re.I)
    text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.I)
    text = _strip_tags(text)
    text = _normalize_ws(text)

    if title:
        text = f"# {title}\n\n{text}"
    return text


def _html_title(html_content: str) -> str:
    match = re.search(r"<title[^>]*>([\s\S]*?)</title>", html_content, flags=re.I)
    return _strip_tags(match.group(1)).strip() if match else ""


def extract_readable(html_content: str) -> tuple[str, str]:
    """提取网页主内容，返回 (文本, 提取器标识)

    优先 trafilatura（主内容提取、保留表格/链接、输出 markdown），
    未安装或提取为空时回退正则剥离方案。
    """
    try:
        import trafilatura
    except ImportError:
        trafilatura = None

    if trafilatura is not None:
        try:
            markdown = trafilatura.extract(
                html_content,
                output_format="markdown",
                include_tables=True,
                include_links=True,
                include_formatting=True,
            )
            if markdown and markdown.strip():
                title = ""
                try:
                    meta = trafilatura.extract_metadata(html_content)
                    title = (getattr(meta, "title", "") or "").strip() if meta else ""
                except Exception:
                    title = _html_title(html_content)
                if not title:
                    title = _html_title(html_content)
                text = f"# {title}\n\n{markdown.strip()}" if title else markdown.strip()
                return text, "trafilatura"
        except Exception as e:
            logger.debug("trafilatura_extract_failed", error=str(e))

    return _extract_text_from_html(html_content), "local_html"


class RedirectResult:
    """重定向策略结果：ok（拿到响应）/ cross_host（跨主机重定向，交回调用方）/ error"""

    __slots__ = ("kind", "response", "target_url", "error")

    def __init__(self, kind: str, response: Optional[httpx.Response] = None,
                 target_url: str = "", error: str = ""):
        self.kind = kind
        self.response = response
        self.target_url = target_url
        self.error = error


async def follow_redirects_safely(client: httpx.AsyncClient, url: str) -> RedirectResult:
    """逐跳跟随重定向：同主机自动跟随，跨主机停止并返回目标 URL

    每一跳都重新做 SSRF 校验，防止重定向到内网地址。
    """
    current = url
    for _ in range(MAX_REDIRECTS):
        safe, err = await validate_url_safe(current)
        if not safe:
            return RedirectResult("error", error=err)
        try:
            resp = await client.get(current, follow_redirects=False)
        except httpx.HTTPError as e:
            return RedirectResult("error", error=str(e))

        if resp.is_redirect:
            location = resp.headers.get("location")
            if not location:
                return RedirectResult("ok", response=resp)
            next_url = str(httpx.URL(current).join(location))
            # 先校验目标安全性，再判断是否跨主机：防止跳转到内网地址
            safe, err = await validate_url_safe(next_url)
            if not safe:
                return RedirectResult("error", error=err)
            if urlparse(next_url).netloc != urlparse(current).netloc:
                return RedirectResult("cross_host", target_url=next_url)
            current = next_url
            continue
        return RedirectResult("ok", response=resp)

    return RedirectResult("error", error=f"重定向次数超过 {MAX_REDIRECTS}")
