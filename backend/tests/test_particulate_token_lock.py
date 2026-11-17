"""ParticulateTokenManager token 刷新 single-flight 并发保护测试。

背景：asyncio.gather 多段查询经 to_thread 并发进入 get_token（如
query_new_standard_report 的分段并发），刷新必须收敛到一次 HTTP 请求。
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from app.utils.particulate_token_manager import ParticulateTokenManager


def _make_manager(tmp_path) -> ParticulateTokenManager:
    config_path = tmp_path / "external_api_config.yaml"
    config_path.write_text(
        "external_api:\n"
        "  base_url: http://example.local\n"
        "  username: user1\n"
        "  password: pass1\n"
        "  vocs_sys_code: SunSup\n"
        "  endpoints:\n"
        "    token: /api/token\n"
        "  token_cache_time: 1800\n"
        "  token_refresh_buffer: 300\n",
        encoding="utf-8",
    )
    return ParticulateTokenManager(config_path=str(config_path))


class _FakeResponse:
    status_code = 200

    def __init__(self, token: str):
        self._token = token

    def json(self):
        return {"success": True, "result": self._token}


def _patch_http(calls: dict, token: str):
    counter_lock = threading.Lock()

    def fake_get(url, **kwargs):
        with counter_lock:
            calls["get"] += 1
        time.sleep(0.05)  # 拉长刷新窗口放大竞态
        return _FakeResponse(token)

    def fake_post(url, **kwargs):
        with counter_lock:
            calls["post"] += 1
        return _FakeResponse(token)

    return (
        patch("app.utils.particulate_token_manager.requests.get", side_effect=fake_get),
        patch("app.utils.particulate_token_manager.requests.post", side_effect=fake_post),
    )


def test_concurrent_get_token_single_flight(tmp_path):
    manager = _make_manager(tmp_path)
    calls = {"get": 0, "post": 0}
    get_patch, post_patch = _patch_http(calls, "tok-1")

    with get_patch, post_patch:
        with ThreadPoolExecutor(max_workers=8) as pool:
            tokens = list(pool.map(lambda _: manager.get_token(), range(16)))

    assert all(token == "tok-1" for token in tokens)
    assert calls == {"get": 1, "post": 0}


def test_concurrent_refresh_after_invalidate_single_flight(tmp_path):
    manager = _make_manager(tmp_path)
    calls = {"get": 0, "post": 0}
    get_patch, post_patch = _patch_http(calls, "tok-2")

    with get_patch, post_patch:
        assert manager.get_token() == "tok-2"
        assert calls == {"get": 1, "post": 0}

        # 401 失效后并发重取：仍只允许一次真实刷新
        manager.invalidate_token()
        tokens = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            tokens = list(pool.map(lambda _: manager.get_token(), range(16)))

    assert all(token == "tok-2" for token in tokens)
    assert calls == {"get": 2, "post": 0}
