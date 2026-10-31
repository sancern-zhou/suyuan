"""统一模型错误策略表（单一判定源）。

对照 ZCode dynamic-workflow 的 `workflow-model-failure-policy.ts`：模型请求失败
只有一个分类函数，runner 闸门、driver 收容、并发信号读同一份判定，杜绝多层
判断分叉。表内错误立即停止（配额/鉴权/无效请求/模型不可用），上下文超限单独
归类（节点失败但不换会话盲目重试）；表外一切（限流、过载、5xx、网络、超时）
一律 `retry_transient`，由节点 max_attempts 与超时预算封顶，等待时长尊重
Retry-After。
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional, Union

# 动作常量（journal / 快照 / 测试都引用稳定字符串）
RETRY_TRANSIENT = "retry_transient"
STOP_QUOTA = "stop_quota"
STOP_AUTH = "stop_auth"
STOP_INVALID_REQUEST = "stop_invalid_request"
STOP_MODEL_UNAVAILABLE = "stop_model_unavailable"
CONTEXT_EXCEEDED = "context_exceeded"


@dataclass(frozen=True)
class FailurePolicy:
    """一次模型请求失败的处置策略。"""

    action: str
    reason: str
    retryable: bool
    retry_after: Optional[float] = None  # 秒；来自 Retry-After 头或限流原文


_QUOTA_MARKERS = (
    "token plan 用量上限",
    "insufficient_quota",
    "billing limit",
    "payment required",
    "http 402",
    "error code: 402",
    "status code: 402",
    "quota exceeded",
    "余额不足",
)

_AUTH_MARKERS = (
    "http 401",
    "http 403",
    "error code: 401",
    "error code: 403",
    "status code: 401",
    "status code: 403",
    "unauthorized",
    "forbidden",
    "invalid api key",
    "authentication",
    "鉴权失败",
)

_MODEL_UNAVAILABLE_MARKERS = (
    "model not found",
    "model_not_found",
    "no available model",
    "model does not exist",
    "无可用模型",
)

_CONTEXT_MARKERS = (
    "context length exceeded",
    "maximum context length",
    "context_window_exceeded",
    "prompt is too long",
    "request too large",
    "context length limit",
    "上下文超限",
    "超出上下文长度",
)

_INVALID_REQUEST_MARKERS = (
    "http 400",
    "status code: 400",
    "status_code=400",
    "error code: 400",
    "400 client error",
    "bad request",
    "http 422",
    "error code: 422",
    "invalid request",
    "request format",
    "invalid_parameter",
)

_TRANSIENT_MARKERS = (
    "429",
    "rate limit",
    "too many requests",
    "overloaded",
    "overloaded_error",
    "服务器过载",
    "http 500",
    "http 502",
    "http 503",
    "http 529",
    "bad gateway",
    "service unavailable",
    "internal server error",
    "timeout",
    "timed out",
    "connection",
    "network",
    "ssl",
    "eof occurred",
    "temporarily unavailable",
)

_RETRY_AFTER_PATTERN = re.compile(r"retry[-_ ]after[\"':\s=]+([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)


def _error_text(error: Union[BaseException, str]) -> str:
    if isinstance(error, BaseException):
        return f"{error} {type(error).__name__}".lower()
    return str(error).lower()


def parse_retry_after(text: str) -> Optional[float]:
    """从错误文本中提取 Retry-After 秒数；支持纯秒数与 HTTP 日期两种形式。"""
    match = _RETRY_AFTER_PATTERN.search(text)
    if match:
        try:
            value = float(match.group(1))
            if value > 0:
                return value
        except ValueError:
            pass
    date_match = re.search(
        r"retry[-_ ]after[\"':\s=]+([A-Za-z]{3},\s*\d{1,2}\s+[A-Za-z]{3}\s+\d{4}[^,\"']*)",
        text,
        re.IGNORECASE,
    )
    if date_match:
        try:
            target = parsedate_to_datetime(date_match.group(1).strip())
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            delta = (target - datetime.now(timezone.utc)).total_seconds()
            if delta > 0:
                return delta
        except (TypeError, ValueError):
            pass
    return None


def resolve_model_failure_policy(error: Union[BaseException, str]) -> FailurePolicy:
    """把一次模型请求失败映射为处置策略（全引擎唯一判定源）。"""
    message = _error_text(error)
    retry_after = parse_retry_after(str(error) if isinstance(error, BaseException) else str(error))

    def policy(action: str, reason: str, retryable: bool) -> FailurePolicy:
        return FailurePolicy(action=action, reason=reason, retryable=retryable, retry_after=retry_after)

    if any(marker in message for marker in _QUOTA_MARKERS):
        return policy(STOP_QUOTA, "model quota exhausted", False)
    if any(marker in message for marker in _AUTH_MARKERS):
        return policy(STOP_AUTH, "model auth failed", False)
    if any(marker in message for marker in _MODEL_UNAVAILABLE_MARKERS):
        return policy(STOP_MODEL_UNAVAILABLE, "model unavailable", False)
    if any(marker in message for marker in _CONTEXT_MARKERS):
        return policy(CONTEXT_EXCEEDED, "context limit exceeded", False)
    if any(marker in message for marker in _INVALID_REQUEST_MARKERS):
        # 请求体本身有问题，重试同一负载没有意义
        return policy(STOP_INVALID_REQUEST, "invalid model request", False)
    if any(marker in message for marker in _TRANSIENT_MARKERS):
        return policy(RETRY_TRANSIENT, "transient model failure", True)
    # 表外一切 = retry（对齐 ZCode：未知错误码不立即停，由预算与停摆观测兜底）
    return policy(RETRY_TRANSIENT, "unclassified model failure", True)


def transient_backoff_seconds(attempt: int, policy: Optional[FailurePolicy] = None) -> float:
    """瞬态重试的等待秒数：Retry-After 优先，否则指数退避 2s→60s + 抖动。"""
    if policy is not None and policy.retry_after:
        return min(600.0, max(1.0, policy.retry_after))
    base = min(60.0, 2.0 * (2 ** max(0, attempt - 1)))
    return base + random.uniform(0, base * 0.1)
