"""中大平台登录锁定治理回归测试。

背景：2026-11-15 起平台验证码 OCR 失效，登录反复失败触发平台
"连续登录失败3次锁10分钟"（code=2141）；worker 单进程内的锁定水位
拦不住多 fetcher 轮番重试的互相续锁，国控站数据断供超 24 小时。

修复面：
- Redis 共享锁定水位（跨进程/跨重启）+ 连续锁定退避；
- 登录互斥锁（同一时刻只允许一个进程实际发起登录）；
- 验证码识别 OCR 失败后自动切换视觉模型候选链；
- 登录成功清除锁定水位与连续锁定计数。
"""

import time
from types import SimpleNamespace

import pytest
from Crypto.PublicKey import RSA

import app.fetchers.xuchang_zhongda_station as zhongda_mod
from app.fetchers.xuchang_zhongda_station import (
    LOCKOUT_SECONDS,
    ZhongdaSession,
)


class StubRedis:
    """最小 Redis stub：get/set(nx)/incr/expire/delete。"""

    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return False
        self.store[key] = str(value)
        return True

    def incr(self, key):
        value = int(self.store.get(key, "0")) + 1
        self.store[key] = str(value)
        return value

    def expire(self, key, ttl):
        return True

    def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)


def make_session(redis_client) -> ZhongdaSession:
    return ZhongdaSession(
        base_url="http://zhongda.test",
        username="u",
        password="p",
        timeout=5,
        retries=3,
        redis_client=redis_client,
    )


PEM = RSA.generate(1024).publickey().export_key().decode()
LOGIN_HTML = f'<input data-val="{PEM}" />'


class FakeResponse:
    def __init__(self, text="", json_data=None):
        self.text = text
        self._json = json_data or {}
        self.status_code = 200
        self.content = b"fake-captcha-image"

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


class FakeSession:
    headers: dict = {}

    def __init__(self, login_results):
        self.login_results = list(login_results)
        self.login_calls = 0

    def get(self, url, timeout=None):
        return FakeResponse(text=LOGIN_HTML)

    def post(self, url, data=None, timeout=None):
        self.login_calls += 1
        return FakeResponse(json_data=self.login_results.pop(0))


# ---- 共享锁定水位 -----------------------------------------------------------


def test_lock_shared_across_sessions():
    redis = StubRedis()
    first = make_session(redis)
    until = first._set_shared_lock()
    assert until == pytest.approx(time.time() + LOCKOUT_SECONDS, abs=5)
    assert float(redis.store["suyuan:fetcher:zhongda_login_locked_until"]) == pytest.approx(until, abs=0.1)

    second = make_session(redis)
    assert second._locked_until_shared() == pytest.approx(until, abs=0.1)
    with pytest.raises(RuntimeError, match="锁定中"):
        second.login()


def test_lock_backoff_grows_with_repeat_locks():
    redis = StubRedis()
    session = make_session(redis)
    first_until = session._set_shared_lock()
    second_until = session._set_shared_lock()
    third_until = session._set_shared_lock()
    assert second_until - first_until == pytest.approx(120, abs=2)
    assert third_until - second_until == pytest.approx(120, abs=2)


def test_lock_count_expires_to_reset_backoff():
    redis = StubRedis()
    session = make_session(redis)
    session._set_shared_lock()
    redis.store.pop("suyuan:fetcher:zhongda_login_lock_count")
    again = session._set_shared_lock()
    assert again - time.time() == pytest.approx(LOCKOUT_SECONDS, abs=5)


def test_redis_down_falls_back_to_process_local():
    class BrokenRedis:
        def get(self, key):
            raise ConnectionError("down")

        def set(self, *args, **kwargs):
            raise ConnectionError("down")

        def incr(self, key):
            raise ConnectionError("down")

    session = ZhongdaSession(
        base_url="http://zhongda.test", username="u", password="p",
        timeout=5, retries=3, redis_client=BrokenRedis(),
    )
    until = session._set_shared_lock()
    assert session._locked_until_shared() == pytest.approx(until, abs=0.1)
    with pytest.raises(RuntimeError, match="锁定中"):
        session.login()


def test_login_success_clears_lock():
    redis = StubRedis()
    session = make_session(redis)
    session._set_shared_lock()
    session._clear_shared_lock()
    assert "suyuan:fetcher:zhongda_login_locked_until" not in redis.store
    assert "suyuan:fetcher:zhongda_login_lock_count" not in redis.store
    assert session._locked_until_shared() == 0.0


# ---- 登录互斥 ---------------------------------------------------------------


def test_attempt_lock_blocks_second_session():
    redis = StubRedis()
    redis.set("suyuan:fetcher:zhongda_login_attempt", "other")
    session = make_session(redis)
    with pytest.raises(RuntimeError, match="其他进程正在登录"):
        session.login()


def test_attempt_lock_released_after_failure():
    redis = StubRedis()
    session = make_session(redis)
    fake = FakeSession([{"isSucceed": False, "msg": "连续登录失败3次，请10分钟后再登录！"}])
    monkey = pytest.MonkeyPatch()
    monkey.setattr(zhongda_mod.requests, "Session", lambda: fake)
    # 锁定分支 break 后 raise
    with pytest.raises(RuntimeError, match="登录失败"):
        session.login()
    monkey.undo()
    assert "suyuan:fetcher:zhongda_login_attempt" not in redis.store


# ---- 视觉候选链切换 ---------------------------------------------------------


def test_switch_to_vision_after_captcha_failure():
    redis = StubRedis()
    session = make_session(redis)
    fake = FakeSession([
        {"isSucceed": False, "msg": "您输入的验证码不正确"},
        {"isSucceed": True},
    ])
    ocr = SimpleNamespace(classification=lambda data: "ab12")  # 形态合法的假 OCR
    vision_calls = []

    def fake_vision(image_bytes):
        vision_calls.append(1)
        return "cd34"

    monkey = pytest.MonkeyPatch()
    monkey.setattr(zhongda_mod.requests, "Session", lambda: fake)
    monkey.setattr(session, "_get_ocr", lambda: ocr)
    monkey.setattr(session, "_read_captcha_with_vision", fake_vision)
    result = session.login()
    monkey.undo()

    assert result is fake
    assert fake.login_calls == 2
    assert vision_calls == [1]  # 第一次 OCR 答错后，第二次尝试走视觉链
    assert session._prefer_vision is False  # 登录成功后恢复 OCR 优先


def test_vision_preference_persists_across_login_calls():
    redis = StubRedis()
    session = make_session(redis)
    # 第一次 login()：撞上锁定（答案大概率也错）
    fake = FakeSession([{"isSucceed": False, "msg": "连续登录失败3次，请10分钟后再登录！"}])
    ocr = SimpleNamespace(classification=lambda data: "ab12")
    monkey = pytest.MonkeyPatch()
    monkey.setattr(zhongda_mod.requests, "Session", lambda: fake)
    monkey.setattr(session, "_get_ocr", lambda: ocr)
    monkey.setattr(session, "_read_captcha_with_vision", lambda data: "cd34")
    with pytest.raises(RuntimeError, match="登录失败"):
        session.login()
    assert session._prefer_vision is True

    # 第二次 login()（锁定解除后的下一轮）：直接走视觉链，不再用 OCR 试错
    redis.store["suyuan:fetcher:zhongda_login_locked_until"] = str(time.time() - 10)
    fake2 = FakeSession([{"isSucceed": True}])
    monkey.setattr(zhongda_mod.requests, "Session", lambda: fake2)
    result = session.login()
    monkey.undo()

    assert result is fake2
    assert fake2.login_calls == 1


def test_unsolvable_captcha_not_submitted():
    redis = StubRedis()
    session = make_session(redis)
    fake = FakeSession([{"isSucceed": True}])
    ocr = SimpleNamespace(classification=lambda data: "]185")  # 形态非法

    monkey = pytest.MonkeyPatch()
    monkey.setattr(zhongda_mod.requests, "Session", lambda: fake)
    monkey.setattr(session, "_get_ocr", lambda: ocr)
    monkey.setattr(session, "_read_captcha_with_vision", lambda data: None)
    with pytest.raises(RuntimeError, match="尝试 3 次"):
        session.login()
    monkey.undo()

    # 识别失败不提交登录：平台失败计数不被消耗
    assert fake.login_calls == 0
