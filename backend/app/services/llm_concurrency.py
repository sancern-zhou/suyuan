"""LLM 请求级 AIMD 并发治理器（对齐 ZCode dynamic-workflow 的 governor）。

对照 zai-org/ZCode `dynamic-workflow/src/engine/concurrency.ts`（纯 AIMD 状态机）
与 `bootstrap/app/workflow-concurrency-governor.ts`（进程级桶管理）移植：

- 闸门粒度是**每次模型请求尝试**（不是整个节点/子 Agent）；
- 加性增长（每 4 次连续成功 +1，且有等待者）、乘性收缩（429/过载 ×0.75）、
  空闲 5 分钟回初值；growth_limit = 2×初始并发；
- **epoch 防阻尼**：每次 cap 裁决翻 epoch，只有当前 epoch 的成功/限流参与
  裁决，防止同一批在飞请求把 cap 连续砍穿；
- **lastGood 语义**：只有完成的 streak 能抬 lastGood；在已证明水位之上探测
  被拒回落到 lastGood（不乘系数），墙下移才乘系数并清 lastGood；
- 冷却只由 Retry-After 驱动；冷却期请求排队（can_admit=False），到期由
  Condition 唤醒；
- **配额类停止（402/insufficient_quota）走 ended-only**：它的 Retry-After
  是额度窗口（可数小时），当并发信号会把桶冻住几小时。何时再试由工作流
  层的 quota_resume 按 reset_at 决定。

作用域决策：per 进程治理（与被替换的 per-process 信号量语义一致：3 个 web
worker + 1 个 worker 各自治理本进程流量）。跨进程 Redis 全局治理留待后续。
状态机保持纯函数（一律收 now 参数、不读时钟），便于确定性测试。

用法（调用方无需关心结算）::

    async with llm_request_slot(provider, model):
        result = await _do_model_request(...)
    # 正常退出 → succeeded；抛 429/过载 → throttled(Retry-After)；
    # 抛超时/网络 → failed_transient；抛配额/鉴权等 → ended（不作并发信号）
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Optional

import structlog

logger = structlog.get_logger()

# AIMD 常量（对齐 ZCode concurrency.ts L25-37）
DECREASE_FACTOR = 0.75
INCREASE_STEP = 1
INCREASE_AFTER_SUCCESSES = 4
FLOOR = 1
IDLE_RESET_SECONDS = 300.0
AUTO_GROWTH_FACTOR = 2

# 字面限流信号（决定瞬态失败里哪些算并发信号）
_RATE_SIGNAL_MARKERS = ("429", "rate limit", "too many requests", "overload")


class ConcurrencyController:
    """单模型桶的 AIMD 状态机。纯逻辑：所有时间由调用方传入（monotonic 秒）。"""

    def __init__(self, initial: int, growth_limit: Optional[int] = None) -> None:
        self.initial = max(FLOOR, int(initial))
        self.cap = self.initial
        self.growth_limit = max(self.initial, int(growth_limit or self.initial * AUTO_GROWTH_FACTOR))
        self.epoch = 0
        self.in_flight = 0
        self.waiters = 0
        self.success_streak = 0
        self.cooldown_until = 0.0
        self.last_request_at: Optional[float] = None
        self.last_throttled_at: Optional[float] = None
        self.last_good = 0
        self.last_bad = 0

    # ---- 准入 ----

    def observe(self, now: float) -> None:
        """空闲重置（惰性，无定时器）：5 分钟无请求且无在飞 → 回初值。"""
        if (
            self.in_flight == 0
            and self.waiters == 0
            and self.last_request_at is not None
            and now - self.last_request_at >= IDLE_RESET_SECONDS
        ):
            if self.cap != self.initial or self.success_streak or self.cooldown_until:
                self.epoch += 1
            self.cap = self.initial
            self.success_streak = 0
            self.cooldown_until = 0.0
            self.last_good = 0
            self.last_bad = 0

    def can_admit(self, now: float) -> bool:
        return self.in_flight < self.cap and now >= self.cooldown_until

    def admitted(self, now: float) -> int:
        """准入成功：占一个在飞名额，返回本次尝试的 epoch。"""
        self.in_flight += 1
        self.last_request_at = now
        return self.epoch

    def release(self) -> None:
        self.in_flight = max(0, self.in_flight - 1)

    # ---- 结算信号 ----

    def succeeded(self, epoch: int, has_waiters: bool) -> Optional[str]:
        """成功：streak 累积；每 K 次且需要容量时加性增长。返回事件名或 None。"""
        self.release()
        if epoch != self.epoch:
            return None
        self.success_streak += 1
        if self.success_streak >= INCREASE_AFTER_SUCCESSES:
            # 只有完成的 streak 能抬 lastGood（无等待者时照累积但不兑现增长）
            self.last_good = max(self.last_good, self.cap)
            if has_waiters and self.cap < self.growth_limit:
                self.cap = min(self.growth_limit, self.cap + INCREASE_STEP)
                self.success_streak = 0
                self.epoch += 1
                return "recovered"
        return None

    def throttled(self, now: float, epoch: int, retry_after: Optional[float] = None) -> str:
        """限流/过载：乘性收缩 + Retry-After 冷却。"""
        self.release()
        self.success_streak = 0
        self.last_throttled_at = now
        if retry_after and retry_after > 0:
            self.cooldown_until = max(self.cooldown_until, now + retry_after)
        event = "throttled"
        if epoch == self.epoch:
            if self.cap > self.last_good:
                # 在已证明水位之上探测被拒：回落，不乘系数
                self.cap = max(FLOOR, self.last_good)
                self.last_bad = self.cap
            else:
                new_cap = max(FLOOR, int(self.cap * DECREASE_FACTOR))
                self.last_bad = self.cap
                self.last_good = 0  # 墙下移，刚被证伪
                if new_cap != self.cap:
                    self.cap = new_cap
                    event = "throttled_lowered"
            self.epoch += 1
        return event

    def failed_transient(self, epoch: int) -> None:
        """超时/5xx/网络：清 streak，cap 不动（对齐 ZCode）。"""
        self.release()
        if epoch == self.epoch:
            self.success_streak = 0

    def ended(self) -> None:
        """永久失败/取消/配额停止：只在飞减一，不作并发信号。"""
        self.release()

    # ---- 治理面 ----

    def set_growth_limit(self, limit: int) -> None:
        """平滑调容：抬高不立刻动 cap；压到 cap 之下当场拉低。"""
        limit = max(self.initial, int(limit))
        self.growth_limit = limit
        if self.cap > limit:
            self.cap = limit
            self.last_good = min(self.last_good, limit)
            self.success_streak = 0
            self.epoch += 1

    def snapshot_state(self) -> Dict[str, float]:
        return {
            "cap": self.cap,
            "growth_limit": self.growth_limit,
            "in_flight": self.in_flight,
            "waiters": self.waiters,
        }


class _Bucket:
    def __init__(self, controller: ConcurrencyController) -> None:
        self.controller = controller
        self.condition = asyncio.Condition()


class _RequestSlot:
    """一次模型请求尝试的槽位；结算由 request_slot 的上下文管理器自动完成。"""

    def __init__(self, bucket: _Bucket, key: str, epoch: int) -> None:
        self.bucket = bucket
        self.key = key
        self.epoch = epoch
        self._settled = False

    async def settle(self, error: Optional[BaseException]) -> None:
        """按请求结果结算 AIMD 信号并唤醒等待者（幂等）。"""
        if self._settled:
            return
        self._settled = True
        # 懒导入：model_failure_policy 在 workflow 包内，避免拖重 llm_service 导入链
        from app.agent.workflow.model_failure_policy import (
            RETRY_TRANSIENT,
            STOP_QUOTA,
            parse_retry_after,
            resolve_model_failure_policy,
        )

        controller = self.bucket.controller
        now = time.monotonic()
        has_waiters = controller.waiters > 0
        event: Optional[str] = None
        if error is None:
            event = controller.succeeded(self.epoch, has_waiters)
        elif isinstance(error, asyncio.CancelledError):
            # 客户端断开/取消：不作任何容量信号
            controller.ended()
        else:
            policy = resolve_model_failure_policy(error)
            if policy.action == RETRY_TRANSIENT:
                message = str(error).lower()
                if any(marker in message for marker in _RATE_SIGNAL_MARKERS):
                    event = controller.throttled(now, self.epoch, parse_retry_after(str(error)))
                else:
                    controller.failed_transient(self.epoch)
            else:
                # 配额/鉴权/无效请求/模型不可用/上下文超限：ended-only，不冻桶
                controller.ended()
                if policy.action == STOP_QUOTA:
                    await self._record_quota_signal()
        async with self.bucket.condition:
            self.bucket.condition.notify_all()
        if event:
            logger.info(
                "llm_bucket_concurrency_event",
                bucket=self.key,
                aimd_event=event,
                **controller.snapshot_state(),
            )

    async def _record_quota_signal(self) -> None:
        """配额信号补账：billing 不走 provider 冷却，运行监控原来看不到它。"""
        try:
            from app.services.llm_failure_counter import record_llm_failure

            provider = self.key.split("/", 1)[0]
            await record_llm_failure(provider, "quota")
        except Exception:  # noqa: BLE001 - 旁路计数不放大故障
            pass


class LlmConcurrencyGovernor:
    """per `provider:model` 桶的进程级治理器（单例，见 get_llm_concurrency_governor）。"""

    def __init__(self, default_concurrency: int = 2) -> None:
        self.default_concurrency = max(FLOOR, int(default_concurrency))
        self._buckets: Dict[str, _Bucket] = {}

    def bucket_key(self, provider: Optional[str], model: Optional[str]) -> str:
        return f"{provider or 'default'}/{model or 'default'}"

    def bucket_controller(self, provider: Optional[str], model: Optional[str]) -> ConcurrencyController:
        key = self.bucket_key(provider, model)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(ConcurrencyController(self.default_concurrency))
            self._buckets[key] = bucket
        return bucket.controller

    def set_bucket_limit(self, provider: Optional[str], model: Optional[str], limit: int) -> None:
        """settings 热更时平滑调容（不再重建信号量）。"""
        self.bucket_controller(provider, model).set_growth_limit(max(FLOOR, int(limit)))

    @asynccontextmanager
    async def request_slot(
        self, provider: Optional[str], model: Optional[str]
    ) -> AsyncIterator[_RequestSlot]:
        key = self.bucket_key(provider, model)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(ConcurrencyController(self.default_concurrency))
            self._buckets[key] = bucket
        controller = bucket.controller
        async with bucket.condition:
            controller.waiters += 1
            try:
                epoch: Optional[int] = None
                while epoch is None:
                    now = time.monotonic()
                    controller.observe(now)
                    if controller.can_admit(now):
                        epoch = controller.admitted(now)
                        break
                    # 冷却到期或 cap 变化时被 notify；兜底 1s 轮询防漏唤醒
                    if controller.cooldown_until > now:
                        timeout = max(0.05, min(1.0, controller.cooldown_until - now))
                    else:
                        timeout = 1.0
                    try:
                        await asyncio.wait_for(bucket.condition.wait(), timeout=timeout)
                    except asyncio.TimeoutError:
                        pass
            finally:
                controller.waiters -= 1
        slot = _RequestSlot(bucket, key, epoch)
        try:
            yield slot
        except BaseException as exc:
            await slot.settle(exc)
            raise
        else:
            await slot.settle(None)


_governor: Optional[LlmConcurrencyGovernor] = None


def get_llm_concurrency_governor() -> LlmConcurrencyGovernor:
    """进程级单例（懒初始化，对齐 ZCode getWorkflowConcurrencyGovernor）。"""
    global _governor
    if _governor is None:
        from config.settings import settings

        _governor = LlmConcurrencyGovernor(default_concurrency=settings.llm_global_max_concurrency)
    return _governor


@asynccontextmanager
async def llm_request_slot(
    provider: Optional[str], model: Optional[str]
) -> AsyncIterator[_RequestSlot]:
    """模块级便捷入口：一次模型请求尝试的 AIMD 槽位。"""
    async with get_llm_concurrency_governor().request_slot(provider, model) as slot:
        yield slot
