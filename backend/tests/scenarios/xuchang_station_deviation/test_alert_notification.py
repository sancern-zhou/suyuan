"""站点快速污染抬升告警 LLM 通报生成测试。

重点验证：LLM 返回空正文时通过 ``validate`` 钩子触发 fallback 换模型，
而不是直接把整个告警执行置为失败。
"""
from types import SimpleNamespace

import pytest

from app.scenarios.xuchang_station_deviation import alert_notification as an
from app.services import llm_service as llm_service_module


@pytest.fixture
def task():
    return SimpleNamespace(prompt="", model_tier="flash", id="task_xuchang_station_deviation_alert")


@pytest.fixture
def package():
    return {
        "schema_version": 1,
        "station_id": "demo",
        "occurred_at": "2026-09-25T10:30:00+08:00",
        "alerts": [],
    }


async def test_generate_message_passes_validator_and_returns_text(
    monkeypatch, task, package
):
    """chat_anthropic 应收到正文非空校验器，正文存在时正常返回。"""
    captured = {}

    async def fake_chat_anthropic(self, messages, **kwargs):
        captured["validate"] = kwargs.get("validate")
        return {"content": [{"type": "text", "text": "一、告警概况……"}]}

    monkeypatch.setattr(
        llm_service_module.LLMService, "chat_anthropic", fake_chat_anthropic
    )

    message = await an._generate_station_alert_message(package, task)

    assert message == "一、告警概况……"
    validator = captured["validate"]
    assert validator is not None
    assert validator({"content": [{"type": "text", "text": "正文"}]}) is None
    assert validator({"content": [{"type": "thinking", "thinking": "思维链"}]}) == (
        "LLM 未生成告警通报正文（空响应）"
    )


async def test_generate_message_uses_evidence_when_final_text_still_empty(
    monkeypatch, task, package
):
    """所有候选都返回空正文时，仍能按真实证据生成通报。"""
    from app.services.llm_failover import LLMResponseRejectedError

    package["alerts"] = [{"alert": {
        "occurred_at": "2026-09-25T10:30:00+08:00",
        "station_name": "开发区",
        "station_id": "demo",
        "target_pollutant": "PM10",
        "measurement_granularity": "5min",
        "station_value": 108,
        "peer_mean": 60,
        "absolute_delta": 48,
        "deviation_percent": 80,
        "rule": "relative_deviation > threshold AND absolute_delta > pollutant_absolute_threshold",
    }, "evidence": {}}]

    async def fake_chat_anthropic(self, messages, **kwargs):
        raise LLMResponseRejectedError("LLM 未生成告警通报正文（空响应）")

    monkeypatch.setattr(
        llm_service_module.LLMService, "chat_anthropic", fake_chat_anthropic
    )

    message = await an._generate_station_alert_message(package, task)
    assert "一、告警概况" in message
    assert "二、气象与质控" in message
    assert "开发区" in message and "PM10" in message and "108" in message
    assert "暂无可用气象观测" in message
    assert "三、" not in message


async def test_generate_message_does_not_invent_missing_alert(monkeypatch, task, package):
    async def failed_chat(self, messages, **kwargs):
        raise ConnectionError("upstream unavailable")

    monkeypatch.setattr(llm_service_module.LLMService, "chat_anthropic", failed_chat)
    with pytest.raises(RuntimeError, match="证据包不含告警因子"):
        await an._generate_station_alert_message(package, task)
