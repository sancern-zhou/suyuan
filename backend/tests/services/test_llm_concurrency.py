"""AIMD 并发治理器测试（对齐 ZCode dynamic-workflow concurrency.ts 语义）。"""

import asyncio
import time

from app.services.llm_concurrency import (
    ConcurrencyController,
    LlmConcurrencyGovernor,
    llm_request_slot,
)


def make_controller(initial=2):
    return ConcurrencyController(initial)


def drive_successes(controller, count, *, epoch=None, waiters=True):
    for _ in range(count):
        # cap 增长会翻 epoch：不传 epoch 时每轮取当前值（模拟顺序到达的成功）
        controller.succeeded(controller.epoch if epoch is None else epoch, has_waiters=waiters)


def test_initial_cap_and_growth_limit():
    controller = make_controller(2)
    assert controller.cap == 2
    assert controller.growth_limit == 4


def test_additive_growth_after_success_streak():
    controller = make_controller(2)
    epoch = controller.epoch
    drive_successes(controller, 4, epoch=epoch)
    assert controller.cap == 3
    assert controller.last_good == 2
    drive_successes(controller, 4, epoch=controller.epoch)
    assert controller.cap == 4
    assert controller.last_good == 3


def test_growth_requires_waiters():
    controller = make_controller(2)
    drive_successes(controller, 8, epoch=controller.epoch, waiters=False)
    assert controller.cap == 2


def test_throttle_at_probe_level_falls_back_to_last_good_without_factor():
    controller = make_controller(2)
    drive_successes(controller, 4, epoch=controller.epoch)
    drive_successes(controller, 4, epoch=controller.epoch)
    assert controller.cap == 4 and controller.last_good == 3
    # 在已证明水位之上被拒：回落到 lastGood，不乘系数
    controller.throttled(time.monotonic(), controller.epoch)
    assert controller.cap == 3
    # 墙下移（cap == lastGood 被拒）：乘 0.75 并清 lastGood
    controller.throttled(time.monotonic(), controller.epoch)
    assert controller.cap == 2
    assert controller.last_good == 0


def test_epoch_damping_ignores_stale_signals():
    controller = make_controller(2)
    stale_epoch = controller.admitted(time.monotonic())
    # 另一次请求触发裁决（epoch 翻页）
    controller.throttled(time.monotonic(), controller.epoch)
    assert controller.epoch != stale_epoch
    # 旧 epoch 的迟到成功不参与裁决
    event = controller.succeeded(stale_epoch, has_waiters=True)
    assert event is None
    assert controller.cap == 1  # 0.75 收缩生效
    drive_successes(controller, 4, epoch=controller.epoch)
    assert controller.cap == 2


def test_throttle_sets_cooldown_from_retry_after():
    controller = make_controller(2)
    now = time.monotonic()
    controller.admitted(now)
    controller.throttled(now, controller.epoch, retry_after=30.0)
    assert controller.cooldown_until >= now + 30.0
    assert not controller.can_admit(now)
    assert controller.can_admit(now + 31.0)


def test_throttle_without_retry_after_does_not_set_cooldown():
    controller = make_controller(2)
    now = time.monotonic()
    controller.admitted(now)
    controller.throttled(now, controller.epoch)
    assert controller.cooldown_until == 0.0
    assert controller.can_admit(now)


def test_transient_failure_keeps_cap():
    controller = make_controller(4)
    now = time.monotonic()
    epoch = controller.admitted(now)
    controller.failed_transient(epoch)
    assert controller.cap == 4


def test_quota_stop_releases_slot_without_concurrency_signal():
    controller = make_controller(4)
    now = time.monotonic()
    controller.admitted(now)
    controller.ended()
    assert controller.in_flight == 0
    assert controller.cap == 4  # 配额不是并发信号
    assert controller.can_admit(now)  # 不进冷却


def test_idle_reset_returns_to_initial():
    controller = make_controller(2)
    drive_successes(controller, 8, waiters=True)
    grown_cap = controller.cap
    assert grown_cap > 2
    controller.last_request_at = time.monotonic() - 301.0
    controller.observe(time.monotonic())
    assert controller.cap == 2


def test_set_growth_limit_smoothly_lowers_cap():
    controller = make_controller(2)
    drive_successes(controller, 8, waiters=True)
    assert controller.cap == 4
    controller.set_growth_limit(2)
    assert controller.cap == 2
    assert controller.growth_limit == 2


def test_bucket_request_slot_bounds_concurrency():
    """桶级：并发不超过 cap；正常完成计成功。"""

    async def run():
        governor = LlmConcurrencyGovernor(default_concurrency=2)
        peak = {"value": 0}
        current = {"value": 0}

        async def one_request():
            async with governor.request_slot("glm", "glm-5.3"):
                current["value"] += 1
                peak["value"] = max(peak["value"], current["value"])
                await asyncio.sleep(0.05)
                current["value"] -= 1

        await asyncio.gather(*(one_request() for _ in range(6)))
        controller = governor.bucket_controller("glm", "glm-5.3")
        assert peak["value"] <= 2
        assert controller.in_flight == 0

    asyncio.run(run())


def test_bucket_rate_limit_error_shrinks_cap_and_sets_cooldown():
    async def run():
        governor = LlmConcurrencyGovernor(default_concurrency=2)
        async with governor.request_slot("glm", "glm-5.3") as slot:
            pass  # 正常退出
        controller = governor.bucket_controller("glm", "glm-5.3")
        assert controller.in_flight == 0

        with_cool = None
        try:
            async with governor.request_slot("glm", "glm-5.3"):
                raise RuntimeError("Error code: 429 - rate limit exceeded, retry-after: 1")
        except RuntimeError as exc:
            with_cool = exc
        assert with_cool is not None
        assert controller.cap < 2
        assert controller.cooldown_until > time.monotonic()

    asyncio.run(run())


def test_bucket_quota_error_does_not_freeze_bucket():
    """配额停止走 ended-only：不冻桶（ZCode 的关键区分）。"""

    async def run():
        governor = LlmConcurrencyGovernor(default_concurrency=2)
        try:
            async with governor.request_slot("glm", "glm-5.3"):
                raise RuntimeError("Error code: 402 - token plan 用量上限")
        except RuntimeError:
            pass
        controller = governor.bucket_controller("glm", "glm-5.3")
        assert controller.in_flight == 0
        assert controller.cap == 2  # cap 不动
        assert controller.cooldown_until == 0.0  # 不进冷却
        assert controller.can_admit(time.monotonic())

    asyncio.run(run())


def test_module_level_slot_helper_works():
    async def run():
        async with llm_request_slot(None, None):
            pass

    asyncio.run(run())
