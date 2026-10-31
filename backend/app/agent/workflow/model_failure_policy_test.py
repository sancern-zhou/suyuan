import time
from datetime import datetime, timedelta, timezone

import pytest

from app.agent.workflow.model_failure_policy import (
    CONTEXT_EXCEEDED,
    RETRY_TRANSIENT,
    STOP_AUTH,
    STOP_INVALID_REQUEST,
    STOP_MODEL_UNAVAILABLE,
    STOP_QUOTA,
    parse_retry_after,
    resolve_model_failure_policy,
    transient_backoff_seconds,
)


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Error code: 402 - token plan 用量上限", STOP_QUOTA),
        ("insufficient_quota: billing limit reached", STOP_QUOTA),
        ("Error code: 401 - invalid api key", STOP_AUTH),
        ("HTTP 403 Forbidden", STOP_AUTH),
        ("model not found: glm-nonexistent", STOP_MODEL_UNAVAILABLE),
        ("prompt is too long: 210000 tokens > 128000 maximum context length", CONTEXT_EXCEEDED),
        ("Error code: 400 - invalid request: request format error", STOP_INVALID_REQUEST),
        ("Error code: 429 - rate limit exceeded", RETRY_TRANSIENT),
        ("provider overloaded, please retry later", RETRY_TRANSIENT),
        ("connection reset by peer", RETRY_TRANSIENT),
        ("request timed out after 30s", RETRY_TRANSIENT),
        # 表外一切 = retry：未知错误不立即停，由预算与停摆观测兜底
        ("something utterly unexpected happened", RETRY_TRANSIENT),
    ],
)
def test_resolve_model_failure_policy_classification(message, expected):
    policy = resolve_model_failure_policy(RuntimeError(message))
    assert policy.action == expected
    assert policy.retryable == (expected == RETRY_TRANSIENT)


def test_transient_error_with_retry_after_header_is_honored():
    policy = resolve_model_failure_policy(RuntimeError('Error code: 429 - {"error":{"retry-after":37}}'))
    assert policy.retryable
    assert policy.retry_after == 37.0
    delay = transient_backoff_seconds(1, policy)
    assert delay == 37.0


def test_transient_error_without_retry_after_uses_exponential_backoff():
    policy = resolve_model_failure_policy(RuntimeError("connection reset"))
    assert policy.retry_after is None
    first = transient_backoff_seconds(1, policy)
    # 2s * 2^(n-1)，封顶 60s + 10% 抖动
    assert 2.0 <= first <= 2.5
    capped = transient_backoff_seconds(10, policy)
    assert 60.0 <= capped <= 66.5


def test_parse_retry_after_seconds_and_http_date():
    assert parse_retry_after('retry-after: 42') == 42.0
    assert parse_retry_after("no header here") is None
    # HTTP 日期形式：过去/无法解析的日期返回 None
    assert parse_retry_after('retry-after: Wed, 21 Oct 2015 07:28:00 GMT') is None


def test_quota_error_with_retry_after_carries_reset_at():
    policy = resolve_model_failure_policy(RuntimeError('Error code: 402 - {"error":{"retry-after":3600}}'))
    assert policy.action == STOP_QUOTA
    assert policy.retry_after == 3600.0
    assert policy.reset_at is not None
    assert policy.reset_at == pytest.approx(time.time() + 3600, abs=5)


def _future_reset_text(*, hours_ahead: int) -> str:
    """生成窗口内（<35 天）的重置时刻文本（北京时间口径由解析器固定）。"""
    target = datetime.now() + timedelta(hours=hours_ahead)
    return target.strftime("%Y-%m-%d %H:%M")


def test_quota_error_with_absolute_reset_time_beijing():
    text = _future_reset_text(hours_ahead=30)
    message = f"Error code: 402 - token plan 用量上限，将于 {text} 重置"
    policy = resolve_model_failure_policy(RuntimeError(message))
    assert policy.action == STOP_QUOTA
    parsed = datetime.strptime(text, "%Y-%m-%d %H:%M")
    expected = parsed.replace(tzinfo=timezone(timedelta(hours=8))).timestamp()
    assert policy.reset_at == pytest.approx(expected, abs=1)


def test_quota_error_reset_time_after_reset_word():
    # 语序二：时间在前、"重置"在后
    text = _future_reset_text(hours_ahead=40)
    message = f"Error code: 402 - 额度将于 {text} 后重置，请稍后再试"
    policy = resolve_model_failure_policy(RuntimeError(message))
    parsed = datetime.strptime(text, "%Y-%m-%d %H:%M")
    expected = parsed.replace(tzinfo=timezone(timedelta(hours=8))).timestamp()
    assert policy.reset_at == pytest.approx(expected, abs=1)


def test_quota_error_without_parseable_reset_time_is_none():
    policy = resolve_model_failure_policy(RuntimeError("Error code: 402 - insufficient_quota"))
    assert policy.action == STOP_QUOTA
    assert policy.reset_at is None


def test_quota_reset_time_outside_window_is_rejected():
    # 35 天窗口之外（2099 年远超）本应有效——换一个"过去太久"的场景验证窗口
    policy = resolve_model_failure_policy(RuntimeError("Error code: 402 - 额度已于 1999-01-01 00:00 重置"))
    assert policy.reset_at is None
    # 无"重置/reset"字样的时间戳不当作重置时刻
    policy = resolve_model_failure_policy(RuntimeError("Error code: 402 - 账单周期 2099-01-01 00:00 开始"))
    assert policy.reset_at is None


def test_transient_error_has_no_reset_at():
    policy = resolve_model_failure_policy(RuntimeError("Error code: 429 - rate limit exceeded"))
    assert policy.action == RETRY_TRANSIENT
    assert policy.reset_at is None
