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


def test_bucket_works_across_multiple_event_loops():
    """worker 进程内主循环与 run_db 线程池私有循环共用 governor：
    同一桶的唤醒 Condition 不能跨循环复用，修复前第二个循环会直接抛
    "is bound to a different event loop"。"""

    governor = LlmConcurrencyGovernor(default_concurrency=2)

    async def one_call(results, errors):
        try:
            async with governor.request_slot("scnet", "DeepSeek-V4.1-Flash"):
                results.append(asyncio.get_running_loop())
                await asyncio.sleep(0.01)
        except Exception as exc:  # noqa: BLE001 - 测试断言用
            errors.append(exc)

    loop_a = asyncio.new_event_loop()
    loop_b = asyncio.new_event_loop()
    try:
        results_a: list = []
        errors_a: list = []
        loop_a.run_until_complete(one_call(results_a, errors_a))
        assert not errors_a

        results_b: list = []
        errors_b: list = []
        loop_b.run_until_complete(one_call(results_b, errors_b))
        assert not errors_b

        assert results_a and results_b
        assert results_a[0] is not results_b[0]

        controller = governor.bucket_controller("scnet", "DeepSeek-V4.1-Flash")
        assert controller.in_flight == 0
    finally:
        loop_a.close()
        loop_b.close()


def test_cross_loop_queueing_admits_after_release():
    """cap=1 时另一循环的请求在前一循环释放后能拿到槽位
    （跨循环唤醒靠 1s 兜底轮询，不能因循环不同而报错或永久排队）。"""

    import threading

    governor = LlmConcurrencyGovernor(default_concurrency=1)
    loop_a = asyncio.new_event_loop()
    loop_b = asyncio.new_event_loop()
    ready = threading.Event()
    release = threading.Event()
    holder_errors: list = []
    holder_entered = threading.Event()

    async def holder():
        try:
            async with governor.request_slot("scnet", "m"):
                holder_entered.set()
                await asyncio.get_running_loop().run_in_executor(None, release.wait, 5)
        except Exception as exc:  # noqa: BLE001 - 测试断言用
            holder_errors.append(exc)

    async def waiter(results):
        await asyncio.get_running_loop().run_in_executor(None, holder_entered.wait, 5)
        try:
            async with governor.request_slot("scnet", "m"):
                results.append(True)
        except Exception:  # noqa: BLE001 - 测试断言用
            results.append(False)

    try:
        thread_a = threading.Thread(target=lambda: loop_a.run_until_complete(holder()))
        thread_a.start()

        results: list = []
        thread_b = threading.Thread(target=lambda: loop_b.run_until_complete(waiter(results)))
        thread_b.start()

        assert holder_entered.wait(5)
        release.set()
        thread_a.join(10)
        thread_b.join(10)

        assert not holder_errors
        assert results == [True]
        controller = governor.bucket_controller("scnet", "m")
        assert controller.in_flight == 0
    finally:
        loop_a.close()
        loop_b.close()
