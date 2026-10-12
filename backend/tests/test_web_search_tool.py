"""web_search / web_fetch 工具单元测试

覆盖对齐 ZCode 抓取能力的改造点：
- SSRF 防护（私网/回环/链路本地拒绝、DNS 解析校验、放行开关）
- URL 级 TTL 缓存
- trafilatura 正文提取与正则回退
- 重定向策略（同主机跟随、跨主机返回、跳转目标二次校验）
- web_search 回退链与域名/时间过滤
- web_fetch prompt 按需提取与全文回退

所有 DNS 解析通过 monkeypatch fetch_core._resolve_host 完成，测试不访问网络。
"""

import asyncio
import sys
import types

import httpx
import pytest

if sys.platform == "win32":
    # app.tools 注册表依赖 fcntl（Linux-only），Windows 本机跑测试时打桩
    _fcntl = types.ModuleType("fcntl")
    _fcntl.LOCK_EX, _fcntl.LOCK_SH, _fcntl.LOCK_UN, _fcntl.LOCK_NB = 2, 1, 8, 4
    _fcntl.flock = lambda *a, **k: None
    _fcntl.lockf = lambda *a, **k: None
    sys.modules.setdefault("fcntl", _fcntl)

from app.tools.social.web_search import fetch_core
from app.tools.social.web_search.fetch_core import (
    TTLCache,
    extract_readable,
    follow_redirects_safely,
    normalize_cache_key,
    validate_url_safe,
)
from app.tools.social.web_search.tool import (
    _UNTRUSTED_BANNER,
    WebFetchTool,
    WebSearchTool,
    _normalize_domain,
)


RESOLVE_MAP = {
    "example.com": ["93.184.216.34"],
    "a.com": ["93.184.216.34"],
    "b.com": ["8.8.4.4"],
    "private.example.com": ["192.168.1.10"],
    "mixed.example.com": ["93.184.216.34", "10.0.0.1"],
    "dead.example.com": [],
}


async def fake_resolve(host: str) -> list[str]:
    if host not in RESOLVE_MAP:
        raise OSError(f"unexpected host in test: {host}")
    return RESOLVE_MAP[host]


@pytest.fixture(autouse=True)
def _no_dns_and_clean_cache(monkeypatch):
    monkeypatch.setattr(fetch_core, "_resolve_host", fake_resolve)
    fetch_core.PAGE_CACHE.clear()
    yield
    fetch_core.PAGE_CACHE.clear()


# ============================================================
# SSRF 防护
# ============================================================

class TestValidateUrlSafe:
    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:8000/admin",
        "http://192.168.1.1/router",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.1.2.3/",
        "http://172.16.0.9/",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://localhost/x",
        "http://private.example.com/",
    ])
    def test_rejects_private_targets(self, url):
        ok, err = asyncio.run(validate_url_safe(url))
        assert ok is False
        assert err

    def test_rejects_when_any_record_is_private(self):
        ok, err = asyncio.run(validate_url_safe("http://mixed.example.com/"))
        assert ok is False
        assert "内网" in err

    def test_allows_public_ip_and_host(self):
        assert asyncio.run(validate_url_safe("https://93.184.216.34/page"))[0] is True
        assert asyncio.run(validate_url_safe("https://a.com/page"))[0] is True

    @pytest.mark.parametrize("url", [
        "ftp://a.com/file",
        "javascript:alert(1)",
        "https:///no-host",
        "not a url",
    ])
    def test_rejects_bad_scheme_or_host(self, url):
        ok, _ = asyncio.run(validate_url_safe(url))
        assert ok is False

    def test_dns_failure_rejected(self):
        ok, err = asyncio.run(validate_url_safe("http://dead.example.com/"))
        assert ok is False

    def test_allow_private_env_flag(self, monkeypatch):
        monkeypatch.setenv("WEB_FETCH_ALLOW_PRIVATE", "1")
        ok, _ = asyncio.run(validate_url_safe("http://192.168.1.1/"))
        assert ok is True


# ============================================================
# TTL 缓存
# ============================================================

class TestTTLCache:
    def test_set_get(self):
        cache = TTLCache(ttl=10, maxsize=4)
        cache.set("k", {"v": 1})
        assert cache.get("k") == {"v": 1}

    def test_expiry(self, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(fetch_core.time, "monotonic", lambda: now[0])
        cache = TTLCache(ttl=10, maxsize=4)
        cache.set("k", "v")
        assert cache.get("k") == "v"
        now[0] += 11
        assert cache.get("k") is None

    def test_lru_eviction(self):
        cache = TTLCache(ttl=100, maxsize=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")  # a 变为最近使用
        cache.set("c", 3)  # 淘汰 b
        assert cache.get("a") == 1
        assert cache.get("b") is None
        assert cache.get("c") == 3


# ============================================================
# 正文提取
# ============================================================

ARTICLE_HTML = """<html><head><title>环境质量公报</title></head><body>
<nav><a href="/home">首页</a></nav>
<article><h1>公报正文</h1>
<p>2026年9月，全市PM2.5平均浓度为35微克/立方米。</p>
<p>详情见 <a href="https://a.com/detail">详情链接</a></p>
</article>
<script>var tracking = 'should_not_appear';</script>
</body></html>"""


class TestExtractReadable:
    def test_trafilatura_primary(self):
        text, extractor = extract_readable(ARTICLE_HTML)
        assert extractor == "trafilatura"
        assert "should_not_appear" not in text
        assert "35微克/立方米" in text
        assert text.startswith("# ")  # 标题前置

    def test_regex_fallback(self):
        text = fetch_core._extract_text_from_html(ARTICLE_HTML)
        assert "should_not_appear" not in text
        assert "# 环境质量公报" in text
        assert "[详情链接](https://a.com/detail)" in text

    def test_fallback_used_when_trafilatura_empty(self, monkeypatch):
        class FakeTrafilatura:
            @staticmethod
            def extract(*args, **kwargs):
                return None

        monkeypatch.setitem(__import__("sys").modules, "trafilatura", FakeTrafilatura)
        text, extractor = extract_readable(ARTICLE_HTML)
        assert extractor == "local_html"
        assert "35微克/立方米" in text


# ============================================================
# 重定向策略
# ============================================================

def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


class TestFollowRedirects:
    def test_same_host_followed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/":
                return httpx.Response(301, headers={"location": "https://a.com/b"})
            return httpx.Response(200, text="final-page")

        result = asyncio.run(follow_redirects_safely(_mock_client(handler), "https://a.com/"))
        assert result.kind == "ok"
        assert result.response.text == "final-page"

    def test_cross_host_returned(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(301, headers={"location": "https://b.com/new-path"})

        result = asyncio.run(follow_redirects_safely(_mock_client(handler), "https://a.com/"))
        assert result.kind == "cross_host"
        assert result.target_url == "https://b.com/new-path"

    def test_redirect_to_private_rejected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

        result = asyncio.run(follow_redirects_safely(_mock_client(handler), "https://a.com/"))
        assert result.kind == "error"
        assert "内网" in result.error

    def test_redirect_loop_bounded(self):
        def handler(request: httpx.Request) -> httpx.Response:
            next_path = "/y" if request.url.path == "/x" else "/x"
            return httpx.Response(302, headers={"location": f"https://a.com{next_path}"})

        result = asyncio.run(follow_redirects_safely(_mock_client(handler), "https://a.com/x"))
        assert result.kind == "error"
        assert "重定向" in result.error


# ============================================================
# web_search：回退链 / 域名过滤 / schema
# ============================================================

def _make_search_tool(monkeypatch, provider_env: str | None = None) -> WebSearchTool:
    for var in ("WEB_SEARCH_PROVIDER", "TENCENT_SECRET_ID", "TENCENT_SECRET_KEY",
                "FIRECRAWL_API_KEY", "BRAVE_API_KEY", "TAVILY_API_KEY",
                "BAIDU_API_KEY", "BAIDU_AK", "BAIDU_SK"):
        monkeypatch.delenv(var, raising=False)
    if provider_env:
        monkeypatch.setenv("WEB_SEARCH_PROVIDER", provider_env)
    return WebSearchTool()


class TestWebSearch:
    def test_fallback_chain_reaches_available_provider(self, monkeypatch):
        tool = _make_search_tool(monkeypatch)
        items = [
            {"title": "结果一", "url": "https://a.com/1", "content": "摘要一"},
            {"title": "结果二", "url": "https://a.com/2", "content": "摘要二"},
        ]

        async def fake_bing(query, n, allowed, blocked, time_range):
            return items

        monkeypatch.setattr(tool, "_search_bing", fake_bing)
        result = asyncio.run(tool.execute(query="测试"))
        assert result["success"] is True
        assert result["data"]["provider"] == "bing"
        assert result["data"]["count"] == 2
        assert "结果一" in result["data"]["results_text"]
        assert result["summary"].count("2 条结果") == 1

    def test_explicit_provider_first_then_fallback(self, monkeypatch):
        tool = _make_search_tool(monkeypatch, provider_env="tavily")
        monkeypatch.setenv("TAVILY_API_KEY", "fake-key")

        async def fail_tavily(query, n, allowed, blocked, time_range):
            return None

        async def fake_bing(query, n, allowed, blocked, time_range):
            return [{"title": "B", "url": "https://a.com/b", "content": "s"}]

        monkeypatch.setattr(tool, "_search_tavily", fail_tavily)
        monkeypatch.setattr(tool, "_search_bing", fake_bing)
        result = asyncio.run(tool.execute(query="测试"))
        assert result["data"]["provider"] == "bing"

    def test_all_providers_exhausted(self, monkeypatch):
        tool = _make_search_tool(monkeypatch)

        async def empty(query, n, allowed, blocked, time_range):
            return None

        monkeypatch.setattr(tool, "_search_bing", empty)
        monkeypatch.setattr(tool, "_search_duckduckgo", empty)
        result = asyncio.run(tool.execute(query="测试"))
        assert result["success"] is True
        assert result["data"]["count"] == 0
        assert "未找到结果" in result["data"]["results_text"]
        assert "已尝试" in result["data"]["results_text"]

    def test_filtered_to_empty_tries_next_provider(self, monkeypatch):
        tool = _make_search_tool(monkeypatch)

        async def blocked_bing(query, n, allowed, blocked, time_range):
            return [{"title": "广告", "url": "https://spam.example/1", "content": ""}]

        async def good_ddg(query, n, allowed, blocked, time_range):
            return [{"title": "正主", "url": "https://a.com/1", "content": ""}]

        monkeypatch.setattr(tool, "_search_bing", blocked_bing)
        monkeypatch.setattr(tool, "_search_duckduckgo", good_ddg)
        result = asyncio.run(tool.execute(query="测试", blocked_domains=["spam.example"]))
        assert result["data"]["provider"] == "duckduckgo"
        assert result["data"]["count"] == 1

    def test_apply_domain_filter(self):
        items = [
            {"title": "1", "url": "https://www.mee.gov.cn/a", "content": ""},
            {"title": "2", "url": "https://gov.mee.gov.cn/b", "content": ""},
            {"title": "3", "url": "https://example.com/c", "content": ""},
        ]
        kept = WebSearchTool._apply_domain_filter(items, ["mee.gov.cn"], None)
        assert [i["title"] for i in kept] == ["1", "2"]
        kept = WebSearchTool._apply_domain_filter(items, None, ["mee.gov.cn"])
        assert [i["title"] for i in kept] == ["3"]
        assert WebSearchTool._apply_domain_filter(items, None, None) is items

    def test_normalize_domain(self):
        assert _normalize_domain("https://www.MEE.gov.cn/x/y") == "mee.gov.cn"
        assert _normalize_domain(" example.com ") == "example.com"

    def test_site_hint(self):
        assert WebSearchTool._site_hint(["https://www.mee.gov.cn/x", "a.com"]) == \
            " site:mee.gov.cn OR site:a.com"
        assert WebSearchTool._site_hint(None) == ""

    def test_schema_has_filter_params(self):
        schema = WebSearchTool().function_schema
        props = schema["parameters"]["properties"]
        assert "allowed_domains" in props
        assert "blocked_domains" in props
        assert props["time_range"]["enum"] == ["day", "week", "month", "year"]

    def test_invalid_time_range_ignored(self, monkeypatch):
        tool = _make_search_tool(monkeypatch)
        seen = {}

        async def fake_bing(query, n, allowed, blocked, time_range):
            seen["time_range"] = time_range
            return [{"title": "T", "url": "https://a.com/1", "content": ""}]

        monkeypatch.setattr(tool, "_search_bing", fake_bing)
        asyncio.run(tool.execute(query="测试", time_range="hour"))
        assert seen["time_range"] is None

    def test_missing_query(self):
        result = asyncio.run(WebSearchTool().execute(query=""))
        assert result["success"] is False


# ============================================================
# web_fetch：安全校验 / 缓存 / 重定向 / prompt 提取
# ============================================================

def _make_fetch_tool(monkeypatch) -> WebFetchTool:
    monkeypatch.delenv("JINA_API_KEY", raising=False)
    return WebFetchTool()


class TestWebFetch:
    def test_schema_defaults_aligned(self):
        tool = WebFetchTool()
        props = tool.function_schema["parameters"]["properties"]
        assert props["maxChars"]["default"] == 20000
        assert tool.max_chars == 20000
        assert props["maxChars"]["maximum"] == 50000
        assert "prompt" in props

    def test_rejects_private_url(self):
        result = asyncio.run(WebFetchTool().execute(url="http://127.0.0.1:8000/admin"))
        assert result["success"] is False
        assert "内网" in result["summary"]

    def test_missing_url(self):
        result = asyncio.run(WebFetchTool().execute())
        assert result["success"] is False

    def _patch_fetchers(self, monkeypatch, tool, text="正文内容" * 50):
        calls = {"local": 0}

        async def fake_jina(url):
            return None

        async def fake_local(url):
            calls["local"] += 1
            return {
                "url": url,
                "final_url": url,
                "status": 200,
                "extractor": "trafilatura",
                "text": text,
            }

        monkeypatch.setattr(tool, "_fetch_jina", fake_jina)
        monkeypatch.setattr(tool, "_fetch_local", fake_local)
        return calls

    def test_cache_hit_across_calls(self, monkeypatch):
        tool = _make_fetch_tool(monkeypatch)
        calls = self._patch_fetchers(monkeypatch, tool)

        url = "https://93.184.216.34/page"
        r1 = asyncio.run(tool.execute(url=url))
        assert r1["success"] is True
        assert r1["data"]["cache"] == "miss"
        assert calls["local"] == 1

        # 同一 URL（含不同 fragment）命中缓存
        r2 = asyncio.run(tool.execute(url=url + "#section"))
        assert r2["data"]["cache"] == "hit"
        assert calls["local"] == 1
        assert r2["data"]["text"] == r1["data"]["text"]

    def test_cross_host_redirect_returned_not_followed(self, monkeypatch):
        tool = _make_fetch_tool(monkeypatch)

        async def fake_local(url):
            return {"redirect": "https://b.com/new-path"}

        monkeypatch.setattr(tool, "_fetch_jina", lambda url: asyncio.sleep(0, result=None))
        monkeypatch.setattr(tool, "_fetch_local", fake_local)

        result = asyncio.run(tool.execute(url="https://93.184.216.34/old"))
        assert result["success"] is True
        assert result["data"]["cross_host"] is True
        assert "https://b.com/new-path" in result["data"]["text"]
        # 重定向结果不写缓存
        assert fetch_core.PAGE_CACHE.get(normalize_cache_key("https://93.184.216.34/old")) is None

    def test_fetch_error_propagates(self, monkeypatch):
        tool = _make_fetch_tool(monkeypatch)

        async def fake_local(url):
            return {"error": "HTTP 404"}

        monkeypatch.setattr(tool, "_fetch_jina", lambda url: asyncio.sleep(0, result=None))
        monkeypatch.setattr(tool, "_fetch_local", fake_local)
        result = asyncio.run(tool.execute(url="https://93.184.216.34/missing"))
        assert result["success"] is False
        assert "404" in result["summary"]

    def test_prompt_extraction_and_fallback(self, monkeypatch):
        tool = _make_fetch_tool(monkeypatch)
        self._patch_fetchers(monkeypatch, tool)

        async def fake_extract(text, prompt):
            assert prompt == "提取PM2.5浓度"
            return "PM2.5：35微克/立方米"

        monkeypatch.setattr(tool, "_extract_with_prompt", fake_extract)
        result = asyncio.run(tool.execute(url="https://93.184.216.34/page", prompt="提取PM2.5浓度"))
        assert result["data"]["filtered"] is True
        assert "PM2.5：35微克/立方米" in result["data"]["text"]
        assert "按提取目标" in result["summary"]

        async def failing_extract(text, prompt):
            return None

        monkeypatch.setattr(tool, "_extract_with_prompt", failing_extract)
        result = asyncio.run(tool.execute(url="https://93.184.216.34/page", prompt="提取PM2.5浓度"))
        assert result["data"]["filtered"] is False
        assert "正文内容" in result["data"]["text"]

    def test_truncation_and_banner(self, monkeypatch):
        tool = _make_fetch_tool(monkeypatch)
        self._patch_fetchers(monkeypatch, tool, text="A" * 30000)
        result = asyncio.run(tool.execute(url="https://93.184.216.34/page", maxChars=1000))
        assert result["data"]["truncated"] is True
        assert result["data"]["text"].startswith(_UNTRUSTED_BANNER)
        assert result["data"]["length"] == len(_UNTRUSTED_BANNER) + 2 + 1000

    def test_max_chars_bounds(self, monkeypatch):
        tool = _make_fetch_tool(monkeypatch)
        self._patch_fetchers(monkeypatch, tool, text="B" * 100)
        # 低于下限 500 也至少返回全文（文本只有 100 字符）
        result = asyncio.run(tool.execute(url="https://93.184.216.34/page", maxChars=10))
        assert result["success"] is True
        assert result["data"]["truncated"] is False
