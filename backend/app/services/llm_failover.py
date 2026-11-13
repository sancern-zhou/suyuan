"""
Shared LLM concurrency and failover helpers.

The policy mirrors OpenClaw's practical shape: classify provider failures,
fallback for transient capacity errors and auth rejections (relay gateways
often return 403 transiently), and keep context-overflow errors on the
compaction path instead of moving them to another model.
"""
import asyncio
import re
import time
import weakref
from dataclasses import dataclass
from typing import Iterable, Optional

import structlog

from config.settings import settings

logger = structlog.get_logger()


@dataclass(frozen=True)
class LLMCandidate:
    provider: str
    model: Optional[str] = None


@dataclass(frozen=True)
class LLMFailure:
    reason: str
    status: Optional[int] = None
    code: Optional[str] = None
    message: str = ""


class LLMFailoverError(Exception):
    """Raised when all configured LLM candidates fail."""

    def __init__(self, attempts: list[dict]):
        self.attempts = attempts
        summary = " | ".join(
            f"{a.get('provider')}/{a.get('model')}: {a.get('reason')} {a.get('error')}"
            for a in attempts
        )
        super().__init__(f"All LLM fallback candidates failed: {summary}")


class LLMResponseRejectedError(Exception):
    """Raised when a response completes but fails caller-side validation.

    Unlike transport failures this does not mark the provider as cooldown;
    only the current request moves on to the next fallback candidate.
    """

    def __init__(self, reason: str, attempts: Optional[list[dict]] = None):
        self.reason = reason
        self.attempts = attempts or []
        super().__init__(reason)


_pool_semaphores: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_pool_semaphore_limits: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_cooldowns: dict[str, tuple[float, LLMFailure]] = {}
# provider -> (连续失败次数, 最近一次失败时间戳)。用于指数退避：同一 provider 在
# 短窗口内反复失败（网关故障、key 过期、payload 持续超限）时，冷却时长按 60→120→
# 240→480→900s 翻倍，避免 60s 固定冷却过期后立刻撞回故障节点空烧一整个
# first-token 超时（2026-11-11 14:02-14:18 一次 run 因此拖长 4~5 倍）。
_failure_streaks: dict[str, tuple[int, float]] = {}


def _pool_key(provider: Optional[str] = None, model: Optional[str] = None) -> str:
    provider_key = (provider or "global").strip().lower() or "global"
    model_key = (model or "").strip().lower()
    return f"{provider_key}:{model_key}" if model_key else provider_key


def get_llm_pool_semaphore(provider: Optional[str] = None, model: Optional[str] = None) -> asyncio.Semaphore:
    """Deprecated: 固定信号量已被 AIMD 治理器取代（app.services.llm_concurrency）。

    仅为向后兼容保留；新的模型请求一律走 ``llm_request_slot``。
    """
    key = _pool_key(provider, model)
    limit = max(1, int(getattr(settings, "llm_global_max_concurrency", 2) or 2))
    loop = asyncio.get_running_loop()
    semaphores = _pool_semaphores.setdefault(loop, {})
    limits = _pool_semaphore_limits.setdefault(loop, {})
    if key not in semaphores or limits.get(key) != limit:
        semaphores[key] = asyncio.Semaphore(limit)
        limits[key] = limit
        logger.info("llm_pool_concurrency_configured", pool_key=key, limit=limit)
    return semaphores[key]


def get_global_llm_semaphore() -> asyncio.Semaphore:
    """Backward-compatible alias for the default pool."""
    return get_llm_pool_semaphore()


def parse_fallback_candidates(
    primary_provider: str,
    primary_model: str,
    raw_fallbacks: Optional[str] = None,
) -> list[LLMCandidate]:
    """Build the configured candidate chain, preserving order and removing duplicates."""
    raw = raw_fallbacks if raw_fallbacks is not None else (getattr(settings, "llm_fallbacks", "") or "")
    candidates = [LLMCandidate(primary_provider.lower(), primary_model)]
    seen = {(primary_provider.lower(), primary_model)}

    for item in re.split(r"[,;\n]+", raw):
        value = item.strip()
        if not value:
            continue
        if "/" in value:
            provider, model = value.split("/", 1)
            candidate = LLMCandidate(provider.strip().lower(), model.strip() or None)
        else:
            candidate = LLMCandidate(value.lower(), None)
        key = (candidate.provider, candidate.model or "")
        if candidate.provider and key not in seen:
            seen.add(key)
            candidates.append(candidate)

    return candidates


def get_cooldown_failure(provider: str) -> Optional[LLMFailure]:
    cooldown = _cooldowns.get(provider)
    if not cooldown:
        return None
    until, failure = cooldown
    if time.time() >= until:
        _cooldowns.pop(provider, None)
        return None
    return failure


def mark_provider_cooldown(provider: str, failure: LLMFailure) -> None:
    # format(400) 错误通常是瞬态的（网关格式兼容、模型临时不可用等），不打 cooldown，
    # 避免主 provider 被跳过导致所有请求落到 fallback 而 fallback 又因余额不足失败。
    if failure.reason == "format":
        logger.info(
            "llm_cooldown_skipped_for_format",
            provider=provider,
            status=failure.status,
        )
        return
    now = time.time()
    streak, last_marked_at = _failure_streaks.get(provider, (0, 0.0))
    decay_seconds = max(
        60.0,
        float(getattr(settings, "llm_failover_streak_decay_seconds", 1800) or 1800),
    )
    if now - last_marked_at > decay_seconds:
        streak = 0
    base_seconds = max(0, int(getattr(settings, "llm_failover_cooldown_seconds", 60) or 0))
    max_seconds = max(
        base_seconds,
        int(getattr(settings, "llm_failover_cooldown_max_seconds", 900) or 0),
    )
    seconds = min(max_seconds, base_seconds * (2 ** streak)) if base_seconds > 0 else 0
    _failure_streaks[provider] = (streak + 1, now)
    if seconds <= 0:
        return
    _cooldowns[provider] = (now + seconds, failure)
    _record_failure_counter(provider, failure)
    logger.warning(
        "llm_provider_cooldown_marked",
        provider=provider,
        reason=failure.reason,
        status=failure.status,
        cooldown_seconds=seconds,
        failure_streak=streak + 1,
    )


def reset_provider_failures(provider: str) -> None:
    """候选成功后清零连续失败计数，避免历史故障让指数退避无限增长。

    只清 streak 不清 cooldown：正在生效的冷却说明该 provider 刚失败过，
    成功的是另一个候选，提前解除会立刻把流量打回故障节点。
    """
    if _failure_streaks.pop(provider, None) is not None:
        logger.info("llm_provider_failure_streak_reset", provider=provider)


def _record_failure_counter(provider: str, failure: LLMFailure) -> None:
    """旁路计数：供运行监控查询上一时段 LLM 限流/失败情况。失败静默。"""
    try:
        import asyncio

        from app.services.llm_failure_counter import record_llm_failure

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(record_llm_failure(provider, failure.reason))
    except Exception:  # noqa: BLE001 - 计数绝不影响主链路
        pass


def _read_status(err: object) -> Optional[int]:
    for name in ("status", "status_code"):
        value = getattr(err, name, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    response = getattr(err, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def _read_code(err: object) -> Optional[str]:
    code = getattr(err, "code", None)
    return code.strip() if isinstance(code, str) and code.strip() else None


def _message(err: object) -> str:
    return str(err) if str(err) else type(err).__name__


def is_context_overflow_message(message: str) -> bool:
    lower = message.lower()
    return any(
        marker in lower
        for marker in (
            "context length",
            "context window",
            "context_window_exceeded",
            "prompt is too long",
            "prompt too long",
            "request_too_large",
            "maximum context",
            "input token count exceeds",
            "上下文过长",
            "上下文超出",
            "超出最大上下文",
        )
    )


def is_media_fetch_failure_message(message: str) -> bool:
    lower = message.lower()
    return any(
        marker in lower
        for marker in (
            "fetch url failed",
            "fetch_url_failed",
            "failed to download url data",
            "download multimodal file timed out",
        )
    )


def classify_llm_failure(err: object) -> LLMFailure:
    status = _read_status(err)
    code = _read_code(err)
    message = _message(err)
    lower = message.lower()
    name = type(err).__name__

    if isinstance(err, LLMResponseRejectedError):
        return LLMFailure("invalid_response", None, None, err.reason)
    if is_context_overflow_message(message):
        return LLMFailure("context_overflow", status, code, message)
    if is_media_fetch_failure_message(message):
        return LLMFailure("media_fetch", status, code, message)
    if status == 429 or "rate limit" in lower or "too many requests" in lower or "throttl" in lower:
        return LLMFailure("rate_limit", status or 429, code, message)
    if status in {500, 502, 503, 504, 521, 522, 523, 524, 529} or "overloaded" in lower:
        return LLMFailure("overloaded", status, code, message)
    if "timeout" in lower or "ReadTimeout" in name or "APITimeout" in name or name == "TimeoutError":
        return LLMFailure("timeout", status or 408, code, message)
    if status in {401, 403} or "unauthorized" in lower or "invalid api key" in lower:
        return LLMFailure("auth", status, code, message)
    if status == 402 or "billing" in lower or "insufficient" in lower:
        return LLMFailure("billing", status, code, message)
    if status == 404 or "model not found" in lower or "not found" in lower:
        return LLMFailure("model_not_found", status, code, message)
    # 413 / "Request Entity Too Large"：单个网关对请求体积的拒绝（同一 payload 换
    # provider 常可通过，2026-11-11 实测 scnet 413 后 go2 成功）。与模型级上下文
    # 溢出（is_context_overflow_message）区分开：后者走压缩路径，前者直接切换候选。
    if status == 413 or "request entity too large" in lower or "payload too large" in lower:
        return LLMFailure("payload_too_large", status or 413, code, message)
    if status == 400:
        return LLMFailure("format", status, code, message)
    return LLMFailure("unknown", status, code, message)


def should_fallback(failure: LLMFailure) -> bool:
    # auth(401/403) 也纳入切换：中转网关（如 doubao.best）的 403 常为临时封禁/IP 风控，
    # 切到备用 provider 可用性更高；密钥真正配错时备用链会全部失败并抛 LLMFailoverError。
    # billing(402) 不切换：账户余额不足是账号级别问题，换 provider 无法解决，
    # 直接抛出错误让调用方感知，避免无意义重试消耗时间。
    # payload_too_large(413)：网关级体积拒绝，换 provider（不同的 body 限制）即可恢复。
    return failure.reason in {
        "rate_limit",
        "overloaded",
        "timeout",
        "format",
        "auth",
        "invalid_response",
        "payload_too_large",
        "unknown",
    }


def summarize_attempts(attempts: Iterable[dict]) -> list[dict]:
    return [
        {
            "provider": item.get("provider"),
            "model": item.get("model"),
            "reason": item.get("reason"),
            "status": item.get("status"),
            "code": item.get("code"),
            "error": (item.get("error") or "")[:300],
        }
        for item in attempts
    ]
