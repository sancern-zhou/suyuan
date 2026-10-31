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
