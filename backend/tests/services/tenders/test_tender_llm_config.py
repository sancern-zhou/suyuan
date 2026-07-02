import asyncio
import json

from app.services.tenders.llm import OpenAICompatibleTenderLLMClient
from app.services.tenders.models import (
    NoticeType,
    TenderCandidate,
    TenderFilterDecision,
)


def test_tender_llm_uses_configured_glm_provider_when_selected(monkeypatch):
    for name in [
        "TENDER_LLM_API_KEY",
        "TENDER_LLM_BASE_URL",
        "TENDER_LLM_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_MODEL",
        "QWEN_API_KEY",
        "QWEN_MODEL",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "glm")
    monkeypatch.setenv("GLM_API_KEY", "glm-valid-key")
    monkeypatch.setenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4")
    monkeypatch.setenv("GLM_MODEL", "glm-4.7")

    client = OpenAICompatibleTenderLLMClient()

    assert client.api_key == "glm-valid-key"
    assert client.base_url == "https://open.bigmodel.cn/api/coding/paas/v4"
    assert client.model == "glm-4.7"


def test_candidate_batch_prompt_uses_compact_keep_indexes():
    client = OpenAICompatibleTenderLLMClient.__new__(
        OpenAICompatibleTenderLLMClient
    )
    long_list_text = "列表摘要" * 120

    prompt = client._candidate_batch_prompt(
        [
            TenderCandidate(
                title="环境监测设备采购公告",
                url="https://example.test/1",
                notice_type=NoticeType.TENDER,
                raw_list_text=long_list_text,
            )
        ],
        TenderFilterDecision(
            is_relevant=True,
            reason="等待 LLM 基于招投标语义判断",
            confidence=0.0,
        ),
    )

    payload = json.loads(prompt)

    assert payload["output_schema"] == {"keep": ["number"]}
    assert "decisions" not in json.dumps(payload, ensure_ascii=False)
    assert payload["candidates"] == [
        {
            "i": 1,
            "t": "环境监测设备采购公告",
            "n": "tender",
            "x": long_list_text[:200],
        }
    ]
    exclude_text = " ".join(payload["exclude_when"])
    assert "采购意向" in exclude_text
    assert "履约验收" in exclude_text
    assert "网上超市" in exclude_text
    assert "招标代理" in exclude_text


def test_review_candidates_accepts_keep_index_array():
    class KeepOnlyClient(OpenAICompatibleTenderLLMClient):
        async def _json_chat(self, prompt):
            return {"keep": [2]}

    client = KeepOnlyClient.__new__(KeepOnlyClient)
    candidates = [
        TenderCandidate(title="办公用品采购", url="https://example.test/1"),
        TenderCandidate(title="环境监测服务采购", url="https://example.test/2"),
    ]

    decisions = asyncio.run(
        client.review_candidates(
            candidates,
            TenderFilterDecision(
                is_relevant=True,
                reason="等待 LLM 基于招投标语义判断",
                confidence=0.0,
            ),
        )
    )

    assert list(decisions) == ["https://example.test/2"]
    assert decisions["https://example.test/2"].is_relevant is True
    assert decisions["https://example.test/2"].reason == "LLM初筛命中环境业务公告"
