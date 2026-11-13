"""LLM failover 加固回归：413 分类、指数退避、成功清零连续失败计数。

背景（2026-11-11 14:02-14:18 故障窗口）：
- scnet 连续 408/413，固定 60s 冷却过期后立刻撞回故障节点，一次 run 拖长 4~5 倍；
- go 的 key 过期（401 auth）每 60s 白烧一个 hop；
- 413 被归为 unknown，未触发压缩路径也未精确切换。
"""
import time

import pytest

from app.services import llm_failover
from app.services.llm_failover import (
    LLMFailure,
    classify_llm_failure,
    get_cooldown_failure,
    mark_provider_cooldown,
    reset_provider_failures,
    should_fallback,
)


class _StatusError(Exception):
    def __init__(self, status: int, message: str = ""):
        super().__init__(message or f"Client error '{status}'")
        self.status = status


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    llm_failover._cooldowns.clear()
    llm_failover._failure_streaks.clear()
    monkeypatch.setattr(llm_failover.settings, "llm_failover_cooldown_seconds", 60)
    monkeypatch.setattr(llm_failover.settings, "llm_failover_cooldown_max_seconds", 900)
    monkeypatch.setattr(llm_failover.settings, "llm_failover_streak_decay_seconds", 1800)
    yield
    llm_failover._cooldowns.clear()
    llm_failover._failure_streaks.clear()


def _remaining(provider: str) -> float:
    failure = get_cooldown_failure(provider)
    assert failure is not None, "provider should be in cooldown"
    until, _ = llm_failover._cooldowns[provider]
    return until - time.time()


def test_classify_413_status_attr():
    failure = classify_llm_failure(_StatusError(413, "Request Entity Too Large"))
    assert failure.reason == "payload_too_large"
    assert failure.status == 413
    assert should_fallback(failure) is True


def test_classify_413_message_only():
    # httpx.HTTPStatusError 风格：status 属性可能缺失，错误文本内嵌状态码
    err = RuntimeError(
        "Client error '413 Request Entity Too Large' for url 'https://api.scnet.cn/api/llm/v1/chat/completions'"
    )
    failure = classify_llm_failure(err)
    assert failure.reason == "payload_too_large"
    assert should_fallback(failure) is True


def test_classify_context_overflow_message_still_wins():
    # 带 request_too_large 关键词的模型级溢出仍归 context_overflow（压缩路径），不回归
    err = RuntimeError("request_too_large: prompt exceeds model context")
    failure = classify_llm_failure(err)
    assert failure.reason == "context_overflow"


def test_cooldown_exponential_backoff():
    failure = LLMFailure("timeout", 408, None, "Request timed out")
    mark_provider_cooldown("prov_a", failure)
    assert 55 <= _remaining("prov_a") <= 60
    mark_provider_cooldown("prov_a", failure)
    assert 115 <= _remaining("prov_a") <= 120
    mark_provider_cooldown("prov_a", failure)
    assert 235 <= _remaining("prov_a") <= 240


def test_cooldown_exponential_capped():
    failure = LLMFailure("auth", 401, None, "api key expired")
    for _ in range(10):
        mark_provider_cooldown("prov_b", failure)
    assert 895 <= _remaining("prov_b") <= 900


def test_streak_decays_after_quiet_window(monkeypatch):
    failure = LLMFailure("timeout", 408, None, "Request timed out")
    mark_provider_cooldown("prov_c", failure)
    mark_provider_cooldown("prov_c", failure)
    assert 115 <= _remaining("prov_c") <= 120
    # 冷却到期且超过衰减窗口后，下一次失败回到基础时长
    real_time = time.time
    monkeypatch.setattr(
        llm_failover.time, "time", lambda: real_time() + 3600
    )
    mark_provider_cooldown("prov_c", failure)
    assert 55 <= _remaining("prov_c") <= 60


def test_reset_on_success_clears_streak():
    failure = LLMFailure("timeout", 408, None, "Request timed out")
    mark_provider_cooldown("prov_d", failure)
    mark_provider_cooldown("prov_d", failure)
    reset_provider_failures("prov_d")
    mark_provider_cooldown("prov_d", failure)
    assert 55 <= _remaining("prov_d") <= 60


def test_reset_keeps_active_cooldown():
    failure = LLMFailure("timeout", 408, None, "Request timed out")
    mark_provider_cooldown("prov_e", failure)
    reset_provider_failures("prov_e")
    # 刚标记的冷却不被 reset 解除（防止流量立刻打回故障节点）
    assert get_cooldown_failure("prov_e") is not None


def test_format_still_skips_cooldown():
    mark_provider_cooldown("prov_f", LLMFailure("format", 400, None, "bad schema"))
    assert get_cooldown_failure("prov_f") is None


def test_zero_base_cooldown_disables_backoff(monkeypatch):
    monkeypatch.setattr(llm_failover.settings, "llm_failover_cooldown_seconds", 0)
    mark_provider_cooldown("prov_g", LLMFailure("timeout", 408, None, "timeout"))
    assert get_cooldown_failure("prov_g") is None


def test_per_provider_streaks_independent():
    failure = LLMFailure("timeout", 408, None, "timeout")
    mark_provider_cooldown("prov_h", failure)
    mark_provider_cooldown("prov_h", failure)
    mark_provider_cooldown("prov_i", failure)
    assert 115 <= _remaining("prov_h") <= 120
    assert 55 <= _remaining("prov_i") <= 60


def test_payload_too_large_falls_back_but_scnet_shrinks_traffic():
    """复现 2026-11-11 场景：413 → 切候选且冷却生效，同 run 内不再每轮撞 scnet。"""
    err = RuntimeError(
        "Client error '413 Request Entity Too Large' for url 'https://api.scnet.cn/api/llm/v1/chat/completions'"
    )
    failure = classify_llm_failure(err)
    assert should_fallback(failure)
    mark_provider_cooldown("scnet", failure)
    # 冷却期内 get_cooldown_failure 命中 → 候选循环直接跳过 scnet
    assert get_cooldown_failure("scnet") is not None
