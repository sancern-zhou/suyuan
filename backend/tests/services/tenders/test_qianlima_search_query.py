from datetime import date

import pytest
import requests

from app.services.tenders import qianlima_client as qianlima_client_module
from app.services.tenders.models import NoticeType
from app.services.tenders.qianlima_client import QianlimaClient


@pytest.fixture(autouse=True)
def clear_qianlima_account_pool(monkeypatch):
    monkeypatch.delenv("QIANLIMA_ACCOUNTS", raising=False)
    monkeypatch.delenv("QIANLIMA_SEARCH_API_URL", raising=False)
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


def test_public_search_is_default_and_does_not_send_member_session(
    monkeypatch, tmp_path
):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"member-token"}],"origins":[]}',
        encoding="utf-8",
    )
    client = QianlimaClient(storage_state_path=str(storage_state))
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"data": []}}

    def fake_post(*args, **kwargs):
        captured["url"] = args[0]
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("app.services.tenders.qianlima_client.requests.post", fake_post)

    client._request_search_api("生态环境局", 2, date(2026, 8, 4))

    assert captured["url"] == "https://search.qianlima.com/api/v1/website/search"
    assert captured["params"] == {
        "keywords": "生态环境局",
        "filtermode": 1,
        "timeType": 4,
        "areas": "",
        "types": -1,
        "searchMode": "0",
        "beginTime": "2026-08-04",
        "endTime": "2026-08-04",
        "isfirst": False,
        "currentPage": 2,
        "numPerPage": 20,
    }
    assert "cookies" not in captured
    assert "x-auth-token" not in captured["headers"]


@pytest.mark.asyncio
async def test_vip_search_query_uses_business_keyword_only():
    client = QianlimaClient(use_search_api=True)
    captured_queries = []

    async def fake_request(query, page_number, publish_date):
        captured_queries.append(query)
        return {"data": {"data": []}}

    client._request_search_api_with_retries = fake_request

    await client._search_via_api(
        "生态环境局",
        NoticeType.TENDER,
        publish_date=date(2026, 6, 30),
        max_pages=1,
    )

    assert captured_queries == ["生态环境局"]


def test_vip_search_refreshes_member_session_on_unauthorized(monkeypatch, tmp_path):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"expired"}],"origins":[]}',
        encoding="utf-8",
    )
    client = QianlimaClient(
        username="user",
        password="password",
        storage_state_path=str(storage_state),
    )
    login_calls = []
    post_calls = []

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def raise_for_status(self):
            if self.status_code >= 400:
                error = requests.HTTPError(f"{self.status_code} error")
                error.response = self
                raise error

        def json(self):
            return self._payload

    def fake_login():
        login_calls.append(True)
        storage_state.write_text(
            '{"cookies":[{"name":"xAuthToken","value":"fresh"}],"origins":[]}',
            encoding="utf-8",
        )

    def fake_post(*args, **kwargs):
        post_calls.append(kwargs["headers"].get("x-auth-token"))
        if len(post_calls) == 1:
            return FakeResponse(401, {})
        return FakeResponse(200, {"data": {"data": []}})

    monkeypatch.setattr(client, "_login_via_api", fake_login)
    monkeypatch.setattr("app.services.tenders.qianlima_client.requests.post", fake_post)

    payload = client._request_vip_search_api(
        "生态环境局 招标公告", 1, date(2026, 6, 29)
    )

    assert payload == {"data": {"data": []}}
    assert login_calls == [True]
    assert post_calls == ["expired", "fresh"]


def test_vip_search_api_uses_configured_http_proxy(monkeypatch, tmp_path):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"token"}],"origins":[]}',
        encoding="utf-8",
    )
    client = QianlimaClient(storage_state_path=str(storage_state))
    monkeypatch.setenv("QIANLIMA_PROXY_SERVER", "http://proxy.example:8080")
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"data": []}}

    def fake_post(*args, **kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("app.services.tenders.qianlima_client.requests.post", fake_post)

    client._request_vip_search_api("生态环境局", 1)

    assert captured["proxies"] == {
        "http": "http://proxy.example:8080",
        "https": "http://proxy.example:8080",
    }


def test_vip_search_api_uses_configured_socks_proxy_with_httpx(
    monkeypatch, tmp_path
):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"token"}],"origins":[]}',
        encoding="utf-8",
    )
    client = QianlimaClient(storage_state_path=str(storage_state))
    monkeypatch.setenv("QIANLIMA_PROXY_SERVER", "socks5://proxy.example:1080")
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"data": []}}

    def fake_post(*args, **kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("app.services.tenders.qianlima_client.httpx.post", fake_post)

    client._request_vip_search_api("生态环境局", 1)

    assert captured["proxy"] == "socks5://proxy.example:1080"
    assert captured["follow_redirects"] is True


def test_api_login_uses_same_configured_socks_proxy(monkeypatch, tmp_path):
    storage_state = tmp_path / "qianlima_state.json"
    client = QianlimaClient(
        username="user",
        password="password",
        storage_state_path=str(storage_state),
    )
    monkeypatch.setenv("QIANLIMA_PROXY_SERVER", "socks5://proxy.example:1080")
    captured = {}

    class FakeCookies:
        jar = []

    class FakeResponse:
        status_code = 200
        headers = {"x-auth-token": "fresh"}

        def json(self):
            return {"data": {"loginStatus": 200, "token": None}}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.headers = {}
            self.cookies = FakeCookies()

        def get(self, url, **kwargs):
            return FakeResponse()

        def close(self):
            return None

    monkeypatch.setattr(
        "app.services.tenders.qianlima_client.httpx.Client", FakeClient
    )

    client._login_via_api()

    assert captured["proxy"] == "socks5://proxy.example:1080"
    assert captured["follow_redirects"] is True
    assert client._storage_state_cookie_value("xAuthToken") == "fresh"


@pytest.mark.asyncio
async def test_complete_date_crawl_does_not_fallback_to_empty_browser_search():
    client = QianlimaClient(use_search_api=True)

    async def failing_api(keyword, notice_type, publish_date, max_pages):
        raise requests.HTTPError("401 Client Error")

    async def forbidden_browser(keyword, notice_type, publish_date, max_pages):
        raise AssertionError("complete date crawl should not silently use browser fallback")

    client._search_via_api = failing_api
    client._search_via_browser = forbidden_browser

    with pytest.raises(RuntimeError, match="完整日期抓取"):
        await client.search(
            keyword="生态环境局",
            notice_type=NoticeType.TENDER,
            publish_date=date(2026, 6, 29),
            max_pages=0,
        )


@pytest.mark.asyncio
async def test_complete_date_crawl_keeps_prior_pages_when_later_page_is_blocked(
    monkeypatch,
):
    client = QianlimaClient(use_search_api=True)
    monkeypatch.setenv("QIANLIMA_SEARCH_PAGE_DELAY_MS", "0")
    calls = []

    async def fake_request(query, page_number, publish_date):
        calls.append(page_number)
        if page_number == 2:
            raise qianlima_client_module._QianlimaPublicSearchError("418 error")
        return {
            "data": {
                "pagesCount": 3,
                "data": [
                    {
                        "title": "生态环境监测设备采购公告",
                        "url": "https://www.qianlima.com/bid-1.html",
                        "updateTime": "2026-08-04",
                    }
                ],
            }
        }

    client._request_search_api_with_retries = fake_request

    rows = await client._search_via_api(
        "生态环境局", NoticeType.OTHER, date(2026, 8, 4), max_pages=0
    )

    assert calls == [1, 2]
    assert [row.url for row in rows] == ["https://www.qianlima.com/bid-1.html"]


@pytest.mark.asyncio
async def test_public_complete_date_crawl_defaults_to_five_pages(monkeypatch):
    client = QianlimaClient(use_search_api=True)
    monkeypatch.setenv("QIANLIMA_SEARCH_PAGE_DELAY_MS", "0")
    monkeypatch.delenv("QIANLIMA_MAX_COMPLETE_PAGES", raising=False)
    calls = []

    async def fake_request(query, page_number, publish_date):
        calls.append(page_number)
        return {
            "data": {
                "pagesCount": 100,
                "data": [
                    {
                        "title": f"生态环境监测设备采购公告{page_number}",
                        "url": f"https://www.qianlima.com/bid-{page_number}.html",
                        "updateTime": "2026-08-04",
                    }
                ],
            }
        }

    client._request_search_api_with_retries = fake_request

    rows = await client._search_via_api(
        "生态环境局", NoticeType.OTHER, date(2026, 8, 4), max_pages=0
    )

    assert calls == list(range(1, 6))
    assert len(rows) == 5


@pytest.mark.asyncio
async def test_public_search_does_not_login_on_unauthorized(
    monkeypatch, tmp_path
):
    storage_state = tmp_path / "qianlima_state.json"
    storage_state.write_text(
        '{"cookies":[{"name":"xAuthToken","value":"expired"}],"origins":[]}',
        encoding="utf-8",
    )
    client = QianlimaClient(
        username="user",
        password="password",
        storage_state_path=str(storage_state),
    )
    monkeypatch.setenv("QIANLIMA_SEARCH_MAX_RETRIES", "1")
    login_calls = []

    async def fake_public_request(query, page_number, publish_date):
        raise qianlima_client_module._QianlimaPublicSearchError("418 error")

    async def fake_browser_login(login_url=None):
        login_calls.append(login_url)
        storage_state.write_text(
            '{"cookies":[{"name":"xAuthToken","value":"fresh"}],"origins":[]}',
            encoding="utf-8",
        )

    monkeypatch.setattr(
        client, "_request_public_search_api_via_browser", fake_public_request
    )
    monkeypatch.setattr(client, "_login_via_browser", fake_browser_login)

    with pytest.raises(qianlima_client_module._QianlimaPublicSearchError):
        await client._request_search_api_with_retries(
            "生态环境局 招标公告", 1, date(2026, 6, 29)
        )

    assert login_calls == []
