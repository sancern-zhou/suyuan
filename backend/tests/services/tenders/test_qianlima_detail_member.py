import asyncio

import pytest
import requests

from app.services.tenders.models import TenderCandidate
from app.services.tenders.qianlima_client import (
    QianlimaClient,
    QianlimaDetailAccessExhaustedError,
    _sleep_before_detail_request,
)


@pytest.fixture(autouse=True)
def clear_qianlima_account_pool(monkeypatch):
    monkeypatch.delenv("QIANLIMA_ACCOUNTS", raising=False)
    monkeypatch.setenv("QIANLIMA_DETAIL_MIN_DELAY_SECONDS", "0")
    monkeypatch.setenv("QIANLIMA_DETAIL_MAX_DELAY_SECONDS", "0")
    monkeypatch.delenv("QIANLIMA_PROXY_SERVER", raising=False)
    monkeypatch.delenv("QIANLIMA_PROXY_USERNAME", raising=False)
    monkeypatch.delenv("QIANLIMA_PROXY_PASSWORD", raising=False)
    monkeypatch.setattr(
        "app.services.tenders.qianlima_client.settings.qianlima_proxy_server", None
    )
    monkeypatch.setattr(
        "app.services.tenders.qianlima_client.settings.qianlima_proxy_username", None
    )
    monkeypatch.setattr(
        "app.services.tenders.qianlima_client.settings.qianlima_proxy_password", None
    )


def test_client_uses_explicit_account_pool(tmp_path):
    storage_state = tmp_path / "qianlima_state.json"

    client = QianlimaClient(
        username="primary",
        password="primary-pass",
        storage_state_path=str(storage_state),
        accounts="account1:pass1,account2:pass2",
    )

    assert [account.username for account in client._accounts] == ["account1", "account2"]
    assert client.username == "account1"
    assert client.storage_state_path == str(
        tmp_path / "qianlima_state.account1.json"
    )


class FakeDetailPage:
    def __init__(self, content):
        self._content = content
        self.visited_url = None

    async def goto(self, url, wait_until=None):
        self.visited_url = url

    async def wait_for_load_state(self, state, timeout=None):
        return None

    async def wait_for_timeout(self, timeout):
        return None

    async def content(self):
        return self._content

    async def close(self):
        return None


class FakeBrowserContext:
    def __init__(self, page):
        self.page = page
        self.routes = []

    async def new_page(self):
        return self.page

    async def route(self, pattern, handler):
        self.routes.append((pattern, handler))


class FakeBrowserContextQueue:
    def __init__(self, pages):
        self.pages = list(pages)
        self.closed = False

    async def new_page(self):
        return self.pages.pop(0)

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_fetch_detail_prefers_http_legacy_detail_when_it_has_procurement_content(
    monkeypatch, tmp_path
):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"token"}],"origins":[]}',
        encoding="utf-8",
    )
    client = QianlimaClient(
        storage_state_path=str(storage_state),
        use_detail_http=True,
    )
    http_detail = (
        "<html><title>2026年成都市武侯生态环境局应急监测设备采购项目</title>"
        "采购内容:A02060500-环保监测设备。预算金额：30万元。"
        "下文中****为隐藏内容，仅对千里马会员用户开放。</html>"
    )
    monkeypatch.setattr(client, "_fetch_detail_http", lambda _url: http_detail)

    async def fail_start():
        raise AssertionError("HTTP 旧版详情可用时不应打开浏览器壳页")

    monkeypatch.setattr(client, "start", fail_start)

    detail = await client.fetch_detail(
        TenderCandidate(title="公告", url="https://example.test/detail")
    )

    assert "环保监测设备" in detail
    assert "预算金额" in detail


@pytest.mark.asyncio
async def test_fetch_detail_requires_member_session(monkeypatch, tmp_path):
    storage_state = tmp_path / "qianlima_state.json"
    client = QianlimaClient(
        username="user",
        password="password",
        storage_state_path=str(storage_state),
        use_detail_http=True,
    )
    login_calls = []

    async def fake_browser_login(login_url=None):
        login_calls.append(login_url)
        storage_state.write_text(
            '{"cookies":[{"name":"xAuthToken","value":"token"}],"origins":[]}',
            encoding="utf-8",
        )

    monkeypatch.setattr(client, "_login_via_browser", fake_browser_login)
    monkeypatch.setattr(
        client,
        "_fetch_detail_http",
        lambda _url: (_ for _ in ()).throw(
            AssertionError("详情页不应使用HTTP直抓")
        ),
    )
    page = FakeDetailPage("完整浏览器会员详情正文")
    client._context = FakeBrowserContext(page)

    detail = await client.fetch_detail(
        TenderCandidate(title="公告", url="https://example.test/detail")
    )

    assert login_calls == [None]
    assert detail == "完整浏览器会员详情正文"


@pytest.mark.asyncio
async def test_fetch_detail_falls_back_to_browser_member_context_when_http_fails(
    monkeypatch, tmp_path
):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"token"}],"origins":[]}',
        encoding="utf-8",
    )
    client = QianlimaClient(
        storage_state_path=str(storage_state),
        use_detail_http=True,
    )
    http_calls = []

    def fail_http(url):
        http_calls.append(url)
        raise requests.RequestException("HTTP detail unavailable")

    monkeypatch.setattr(client, "_fetch_detail_http", fail_http)
    page = FakeDetailPage("完整浏览器会员详情正文")
    client._context = FakeBrowserContext(page)

    detail = await client.fetch_detail(
        TenderCandidate(title="公告", url="https://example.test/detail")
    )

    assert detail == "完整浏览器会员详情正文"
    assert page.visited_url == "https://example.test/detail"
    assert http_calls == ["https://example.test/detail"]


@pytest.mark.asyncio
async def test_fetch_detail_rejects_member_limited_browser_content(
    monkeypatch, tmp_path
):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"token"}],"origins":[]}',
        encoding="utf-8",
    )
    client = QianlimaClient(
        storage_state_path=str(storage_state),
        use_detail_http=True,
    )
    client._context = FakeBrowserContext(
        FakeDetailPage("该信息为会员专享，请升级会员后查看完整信息")
    )


    with pytest.raises(RuntimeError, match="会员"):
        await client.fetch_detail(
            TenderCandidate(title="公告", url="https://example.test/detail")
        )


@pytest.mark.asyncio
async def test_fetch_detail_rejects_hidden_content_without_member_permission(
    monkeypatch, tmp_path
):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"token"}],"origins":[]}',
        encoding="utf-8",
    )
    client = QianlimaClient(
        storage_state_path=str(storage_state),
        use_detail_http=True,
    )
    client._context = FakeBrowserContext(
        FakeDetailPage("下文中****为隐藏内容，仅对千里马会员用户开放，您尚未开通该权限")
    )

    with pytest.raises(RuntimeError, match="会员"):
        await client.fetch_detail(
            TenderCandidate(title="公告", url="https://example.test/detail")
        )


@pytest.mark.asyncio
async def test_fetch_detail_rejects_daily_limit_shell_page(monkeypatch, tmp_path):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"token"}],"origins":[]}',
        encoding="utf-8",
    )
    client = QianlimaClient(
        storage_state_path=str(storage_state),
        use_detail_http=True,
    )
    client._context = FakeBrowserContext(
        FakeDetailPage(
            "详情 加载中... 标题 标的物 项目编号 招标单位 中标单位 "
            "防诈骗提醒 今日浏览已达到上限，请明日再试哟～ "
            "数据来自千里马招标网"
        )
    )

    with pytest.raises(RuntimeError, match="会员|浏览上限|受限"):
        await client.fetch_detail(
            TenderCandidate(title="公告", url="https://example.test/detail")
        )


@pytest.mark.asyncio
async def test_fetch_detail_switches_account_after_daily_limit_shell_page(
    monkeypatch, tmp_path
):
    storage_state = tmp_path / "qianlima_state.json"
    first_state = tmp_path / "qianlima_state.account1.json"
    second_state = tmp_path / "qianlima_state.account2.json"
    first_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"token1"}],"origins":[]}',
        encoding="utf-8",
    )
    second_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"token2"}],"origins":[]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("QIANLIMA_ACCOUNTS", "account1:pass1,account2:pass2")
    client = QianlimaClient(storage_state_path=str(storage_state))
    contexts = [
        FakeBrowserContextQueue(
            [
                FakeDetailPage(
                    "详情 加载中... 标题 标的物 项目编号 招标单位 "
                    "防诈骗提醒 今日浏览已达到上限，请明日再试哟～ "
                    "数据来自千里马招标网"
                )
            ]
        ),
        FakeBrowserContextQueue([FakeDetailPage("完整浏览器会员详情正文 采购内容：监测服务")]),
    ]
    start_storage_paths = []

    async def fake_start():
        start_storage_paths.append(client.storage_state_path)
        client._context = contexts[len(start_storage_paths) - 1]

    monkeypatch.setattr(client, "start", fake_start)

    detail = await client.fetch_detail(
        TenderCandidate(title="公告", url="https://example.test/detail")
    )

    assert detail == "完整浏览器会员详情正文 采购内容：监测服务"
    assert client.username == "account2"
    assert contexts[0].closed is True
    assert start_storage_paths == [str(first_state), str(second_state)]


@pytest.mark.asyncio
async def test_fetch_detail_stops_after_all_accounts_reach_daily_limit(
    monkeypatch, tmp_path
):
    storage_state = tmp_path / "qianlima_state.json"
    first_state = tmp_path / "qianlima_state.account1.json"
    second_state = tmp_path / "qianlima_state.account2.json"
    for state_path, token in [(first_state, "token1"), (second_state, "token2")]:
        state_path.write_text(
            f'{{"cookies":[{{"name":"xAuthToken","value":"{token}"}}],"origins":[]}}',
            encoding="utf-8",
        )
    monkeypatch.setenv("QIANLIMA_ACCOUNTS", "account1:pass1,account2:pass2")
    client = QianlimaClient(storage_state_path=str(storage_state))
    contexts = [
        FakeBrowserContextQueue(
            [
                FakeDetailPage(
                    "详情 加载中... 标题 标的物 项目编号 招标单位 "
                    "防诈骗提醒 今日浏览已达到上限，请明日再试哟～ "
                    "数据来自千里马招标网"
                )
            ]
        ),
        FakeBrowserContextQueue(
            [
                FakeDetailPage(
                    "详情 加载中... 标题 标的物 项目编号 招标单位 "
                    "防诈骗提醒 今日浏览已达到上限，请明日再试哟～ "
                    "数据来自千里马招标网"
                )
            ]
        ),
    ]
    start_calls = 0

    async def fake_start():
        nonlocal start_calls
        client._context = contexts[start_calls]
        start_calls += 1

    monkeypatch.setattr(client, "start", fake_start)

    with pytest.raises(QianlimaDetailAccessExhaustedError):
        await client.fetch_detail(
            TenderCandidate(title="公告1", url="https://example.test/detail-1")
        )
    with pytest.raises(QianlimaDetailAccessExhaustedError):
        await client.fetch_detail(
            TenderCandidate(title="公告2", url="https://example.test/detail-2")
        )

    assert start_calls == 2
    assert contexts[0].closed is True
    assert len(contexts[1].pages) == 0


@pytest.mark.asyncio
async def test_stale_daily_limit_error_does_not_mark_current_account_limited(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("QIANLIMA_ACCOUNTS", "account1:pass1,account2:pass2,account3:pass3")
    client = QianlimaClient(storage_state_path=str(tmp_path / "qianlima_state.json"))
    closed = 0

    async def fake_close():
        nonlocal closed
        closed += 1

    client.close = fake_close

    assert await client._switch_to_next_detail_account(0) is True
    assert client.username == "account2"

    assert await client._switch_to_next_detail_account(0) is True
    assert client.username == "account2"
    assert closed == 1


@pytest.mark.asyncio
async def test_fetch_detail_allows_member_detail_with_sidebar_daily_limit(
    monkeypatch, tmp_path
):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"token"}],"origins":[]}',
        encoding="utf-8",
    )
    client = QianlimaClient(storage_state_path=str(storage_state))
    content = (
        "详情 采购内容：污染源在线监控系统日常运维。预算金额：100万元。"
        "投标文件递交截止时间：2026年7月20日。"
        + "项目正文" * 600
        + "防诈骗提醒 今日浏览已达到上限，请明日再试哟～ 数据来自千里马招标网"
    )
    client._context = FakeBrowserContext(FakeDetailPage(content))

    detail = await client.fetch_detail(
        TenderCandidate(title="公告", url="https://example.test/detail")
    )

    assert "采购内容" in detail


@pytest.mark.asyncio
async def test_fetch_detail_uses_dedicated_browser_detail_concurrency(
    monkeypatch, tmp_path
):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"token"}],"origins":[]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("QIANLIMA_BROWSER_DETAIL_CONCURRENCY", "2")
    active = 0
    max_active = 0

    class SlowPage(FakeDetailPage):
        async def goto(self, url, wait_until=None):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            await super().goto(url, wait_until=wait_until)

    class SlowContext:
        async def new_page(self):
            return SlowPage("完整浏览器会员详情正文")

    client = QianlimaClient(storage_state_path=str(storage_state))
    client._context = SlowContext()

    await asyncio.gather(
        *[
            client.fetch_detail(
                TenderCandidate(title=f"公告{i}", url=f"https://example.test/{i}")
            )
            for i in range(6)
        ]
    )

    assert max_active == 2


@pytest.mark.asyncio
async def test_detail_request_uses_safe_delay_defaults_without_env(monkeypatch):
    monkeypatch.delenv("QIANLIMA_DETAIL_MIN_DELAY_SECONDS")
    monkeypatch.delenv("QIANLIMA_DETAIL_MAX_DELAY_SECONDS")
    monkeypatch.setattr(
        "app.services.tenders.qianlima_client.random.uniform",
        lambda minimum, maximum: (minimum, maximum),
    )
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr("app.services.tenders.qianlima_client.asyncio.sleep", fake_sleep)

    await _sleep_before_detail_request()

    assert sleep_calls == [(8.0, 25.0)]


@pytest.mark.asyncio
async def test_fetch_detail_waits_random_delay_before_opening_page(
    monkeypatch, tmp_path
):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"token"}],"origins":[]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("QIANLIMA_DETAIL_MIN_DELAY_SECONDS", "8")
    monkeypatch.setenv("QIANLIMA_DETAIL_MAX_DELAY_SECONDS", "25")
    monkeypatch.setattr(
        "app.services.tenders.qianlima_client.random.uniform",
        lambda minimum, maximum: 13.5,
    )
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr("app.services.tenders.qianlima_client.asyncio.sleep", fake_sleep)
    page = FakeDetailPage("完整浏览器会员详情正文")
    client = QianlimaClient(storage_state_path=str(storage_state))
    client._context = FakeBrowserContext(page)

    detail = await client.fetch_detail(
        TenderCandidate(title="公告", url="https://example.test/detail")
    )

    assert detail == "完整浏览器会员详情正文"
    assert sleep_calls == [13.5]


@pytest.mark.asyncio
async def test_start_blocks_heavy_browser_detail_resources(monkeypatch, tmp_path):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")
    context = FakeBrowserContext(FakeDetailPage("正文"))

    class FakeBrowser:
        async def new_context(self, **kwargs):
            return context

    class FakeChromium:
        async def launch(self, headless=True):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    async def fake_async_playwright_start():
        return FakePlaywright()

    class FakeAsyncPlaywright:
        async def start(self):
            return await fake_async_playwright_start()

    monkeypatch.setattr(
        "playwright.async_api.async_playwright",
        lambda: FakeAsyncPlaywright(),
    )
    client = QianlimaClient(storage_state_path=str(storage_state))

    await client.start()

    assert context.routes


@pytest.mark.asyncio
async def test_search_browser_start_passes_configured_proxy(monkeypatch, tmp_path):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")
    context = FakeBrowserContext(FakeDetailPage("正文"))
    launch_kwargs = {}

    class FakeBrowser:
        async def new_context(self, **kwargs):
            return context

    class FakeChromium:
        async def launch(self, **kwargs):
            launch_kwargs.update(kwargs)
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeAsyncPlaywright:
        async def start(self):
            return FakePlaywright()

    monkeypatch.setenv("QIANLIMA_PROXY_SERVER", "http://proxy.example:8080")
    monkeypatch.setenv("QIANLIMA_PROXY_USERNAME", "proxy-user")
    monkeypatch.setenv("QIANLIMA_PROXY_PASSWORD", "proxy-pass")
    monkeypatch.setattr(
        "playwright.async_api.async_playwright",
        lambda: FakeAsyncPlaywright(),
    )
    client = QianlimaClient(storage_state_path=str(storage_state))

    await client.start(use_proxy=True)

    assert launch_kwargs["proxy"] == {
        "server": "http://proxy.example:8080",
        "username": "proxy-user",
        "password": "proxy-pass",
    }


@pytest.mark.asyncio
async def test_detail_browser_start_is_direct_by_default(monkeypatch, tmp_path):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")
    launch_kwargs = {}

    class FakeBrowser:
        async def new_context(self, **kwargs):
            return FakeBrowserContext(FakeDetailPage("完整详情"))

    class FakeChromium:
        async def launch(self, **kwargs):
            launch_kwargs.update(kwargs)
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakePlaywrightStarter:
        async def start(self):
            return FakePlaywright()

    monkeypatch.setenv("QIANLIMA_PROXY_SERVER", "socks5://proxy.example:1080")
    monkeypatch.setattr(
        "playwright.async_api.async_playwright", lambda: FakePlaywrightStarter()
    )
    client = QianlimaClient(storage_state_path=str(storage_state))

    await client.start()

    assert "proxy" not in launch_kwargs


def test_fetch_detail_http_uses_configured_detail_proxy(monkeypatch, tmp_path):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"token"}],"origins":[]}',
        encoding="utf-8",
    )
    client = QianlimaClient(storage_state_path=str(storage_state))
    monkeypatch.setenv("QIANLIMA_PROXY_SERVER", "http://proxy.example:8080")
    captured = {}

    class FakeResponse:
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        text = "完整详情"

        def raise_for_status(self):
            return None

    def fake_get(*args, **kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(requests, "get", fake_get)

    assert client._fetch_detail_http("https://example.test/detail") == "完整详情"
    assert captured["proxies"] == {
        "http": "http://proxy.example:8080",
        "https": "http://proxy.example:8080",
    }


def test_fetch_detail_http_skips_socks_proxy_without_requests_socks(monkeypatch, tmp_path):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"token"}],"origins":[]}',
        encoding="utf-8",
    )
    client = QianlimaClient(storage_state_path=str(storage_state))
    monkeypatch.setenv("QIANLIMA_PROXY_SERVER", "socks5://127.0.0.1:1080")
    captured = {}

    class FakeResponse:
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        text = "完整详情"

        def raise_for_status(self):
            return None

    def fake_get(*args, **kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(requests, "get", fake_get)

    assert client._fetch_detail_http("https://example.test/detail") == "完整详情"
    assert captured["proxies"] is None


@pytest.mark.asyncio
async def test_start_is_serialized_when_called_concurrently(monkeypatch, tmp_path):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")
    context = FakeBrowserContext(FakeDetailPage("正文"))
    launch_calls = 0
    new_context_calls = 0

    class FakeBrowser:
        async def new_context(self, **kwargs):
            nonlocal new_context_calls
            new_context_calls += 1
            await asyncio.sleep(0.01)
            return context

    class FakeChromium:
        async def launch(self, headless=True):
            nonlocal launch_calls
            launch_calls += 1
            await asyncio.sleep(0.01)
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakeAsyncPlaywright:
        async def start(self):
            return FakePlaywright()

    monkeypatch.setattr(
        "playwright.async_api.async_playwright",
        lambda: FakeAsyncPlaywright(),
    )
    client = QianlimaClient(storage_state_path=str(storage_state))

    await asyncio.gather(*[client.start() for _ in range(5)])

    assert launch_calls == 1
    assert new_context_calls == 1
