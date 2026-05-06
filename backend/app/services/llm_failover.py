"""
Shared LLM concurrency and failover helpers.

The policy mirrors OpenClaw's practical shape: classify provider failures,
fallback only for transient capacity errors, and keep context-overflow errors
on the compaction path instead of moving them to another model.
"""
import asyncio
import re
import time
from dataclasses import dataclass
from typing import Optional, Iterable

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


_global_semaphore: Optional[asyncio.Semaphore] = None
_global_semaphore_limit: Optional[int] = None
_cooldowns: dict[str, tuple[float, LLMFailure]] = {}


def get_global_llm_semaphore() -> asyncio.Semaphore:
    """Return a process-wide semaphore shared by all provider calls."""
    global _global_semaphore, _global_semaphore_limit
    limit = max(1, int(getattr(settings, "llm_global_max_concurrency", 2) or 2))
    if _global_semaphore is None or _global_semaphore_limit != limit:
        _global_semaphore = asyncio.Semaphore(limit)
        _global_semaphore_limit = limit
        logger.info("llm_global_concurrency_configured", limit=limit)
    return _global_semaphore


def parse_fallback_candidates(primary_provider: str, primary_model: str) -> list[LLMCandidate]:
    """Build the configured candidate chain, preserving order and removing duplicates."""
    raw = getattr(settings, "llm_fallbacks", "") or ""
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
    seconds = max(0, int(getattr(settings, "llm_failover_cooldown_seconds", 60) or 0))
    if seconds <= 0:
        return
    _cooldowns[provider] = (time.time() + seconds, failure)
    logger.warning(
        "llm_provider_cooldown_marked",
        provider=provider,
        reason=failure.reason,
        status=failure.status,
        cooldown_seconds=seconds,
    )


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


def classify_llm_failure(err: object) -> LLMFailure:
    status = _read_status(err)
    code = _read_code(err)
    message = _message(err)
    lower = message.lower()
    name = type(err).__name__

    if is_context_overflow_message(message):
        return LLMFailure("context_overflow", status, code, message)
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
    if status == 400:
        return LLMFailure("format", status, code, message)
    return LLMFailure("unknown", status, code, message)


def should_fallback(failure: LLMFailure) -> bool:
    return failure.reason in {"rate_limit", "overloaded", "timeout", "billing", "format", "unknown"}


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
