import asyncio
import json
import sys
import types

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


def test_json_chat_passes_configured_timeout_to_openai_client(monkeypatch):
    captured_kwargs = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            return types.SimpleNamespace(
                choices=[
                    types.SimpleNamespace(
                        message=types.SimpleNamespace(content='{"ok": true}')
                    )
                ]
            )

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)
            self.chat = types.SimpleNamespace(
                completions=FakeCompletions()
            )

    fake_openai = types.SimpleNamespace(
        APIConnectionError=Exception,
        APITimeoutError=TimeoutError,
        AsyncOpenAI=FakeAsyncOpenAI,
        InternalServerError=RuntimeError,
        RateLimitError=RuntimeError,
    )
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setenv("TENDER_LLM_TIMEOUT_SECONDS", "12.5")

    client = OpenAICompatibleTenderLLMClient.__new__(
        OpenAICompatibleTenderLLMClient
    )
    client.api_key = "test-key"
    client.base_url = "https://example.test/v1"
    client.model = "test-model"
    client.temperature = 0.0

    data = asyncio.run(client._json_chat("test"))

    assert data == {"ok": True}
    assert captured_kwargs["timeout"] == 12.5
    assert captured_kwargs["max_retries"] == 0


def test_extract_notice_uses_llm_notice_type_field():
    class NoticeTypeClient(OpenAICompatibleTenderLLMClient):
        async def _json_chat(self, prompt):
            return {
                "notice_type": "winning_bid",
                "project_name": "生态环境监测服务项目",
                "purchaser": "某生态环境局",
                "winning_bidder": "某环保科技有限公司",
                "winning_amount": "100万元",
                "province": "广东",
                "city": "广州",
                "publish_date": "2026-06-30",
                "summary": "项目已完成成交结果公告。",
                "key_requirements": ["环境监测服务"],
            }

    client = NoticeTypeClient.__new__(NoticeTypeClient)
    candidate = TenderCandidate(
        title="生态环境监测服务项目成交结果公告",
        url="https://example.test/winning",
        notice_type=NoticeType.TENDER,
    )

    notice = asyncio.run(
        client.extract_notice(
            candidate,
            "成交供应商：某环保科技有限公司；成交金额：100万元",
            TenderFilterDecision(
                is_relevant=True,
                reason="LLM初筛命中环境业务公告",
                confidence=0.8,
            ),
        )
    )

    assert notice.notice_type == NoticeType.WINNING_BID


def test_extract_notice_clears_winning_fields_when_notice_type_is_not_winning():
    class TenderTypeClient(OpenAICompatibleTenderLLMClient):
        async def _json_chat(self, prompt):
            return {
                "notice_type": "tender",
                "project_name": "生态环境监测服务项目",
                "purchaser": "某生态环境局",
                "winning_bidder": "某环保科技有限公司",
                "winning_amount": "100万元",
                "budget_amount": "120万元",
                "province": "广东",
                "city": "广州",
                "publish_date": "2026-06-30",
                "summary": "项目正在采购阶段。",
                "key_requirements": ["环境监测服务"],
            }

    client = TenderTypeClient.__new__(TenderTypeClient)
    candidate = TenderCandidate(
        title="生态环境监测服务项目采购公告",
        url="https://example.test/tender",
        notice_type=NoticeType.TENDER,
    )

    notice = asyncio.run(
        client.extract_notice(
            candidate,
            "本项目预算金额120万元，采购环境监测服务。",
            TenderFilterDecision(
                is_relevant=True,
                reason="LLM初筛命中环境业务公告",
                confidence=0.8,
            ),
        )
    )

    assert notice.notice_type == NoticeType.TENDER
    assert notice.winning_bidder is None
    assert notice.winning_amount is None
    assert notice.winning_amount_wan_yuan is None


def test_combined_detail_prompt_requires_procurement_behavior_before_extraction():
    client = OpenAICompatibleTenderLLMClient.__new__(
        OpenAICompatibleTenderLLMClient
    )
    candidate = TenderCandidate(
        title="某项目环境影响报告书审批公示",
        url="https://example.test/eia",
        notice_type=NoticeType.TENDER,
    )

    prompt = client._combined_notice_prompt(
        candidate,
        "建设项目环境影响报告书受理公示，没有采购人、预算、投标或成交信息。",
        TenderFilterDecision(
            is_relevant=True,
            reason="初筛命中环境词",
            confidence=0.8,
        ),
    )
    payload = json.loads(prompt)

    joined_rules = json.dumps(payload, ensure_ascii=False)
    assert "先判断采购内容是否属于环境业务" in payload["task"]
    assert "如果不是环境业务，直接返回is_relevant=false" in joined_rules
    assert "环境影响报告书" in joined_rules
    assert "行政审批" in joined_rules
    assert "采购要素" in joined_rules


def test_combined_detail_prompt_uses_expanded_project_category_enum():
    client = OpenAICompatibleTenderLLMClient.__new__(
        OpenAICompatibleTenderLLMClient
    )
    prompt = client._combined_notice_prompt(
        TenderCandidate(
            title="生态环境智慧监管平台建设项目招标公告",
            url="https://example.test/platform",
            notice_type=NoticeType.TENDER,
        ),
        "采购生态环境智慧监管平台建设服务。",
        TenderFilterDecision(
            is_relevant=True,
            reason="初筛命中环境业务",
            confidence=0.8,
        ),
    )
    payload = json.loads(prompt)
    payload_text = json.dumps(payload, ensure_ascii=False)

    assert "digital_platform" in payload_text
    assert "equipment_supplies" in payload_text
    assert "operation_maintenance" in payload_text
    assert "emergency_response" in payload_text
    assert "other_environment_procurement" in payload_text
    assert "other|null" not in payload["output_schema"]["project_category"]


def test_review_and_extract_notice_rejects_non_environment_procurement_without_notice():
    class RejectingClient(OpenAICompatibleTenderLLMClient):
        async def _json_chat(self, prompt):
            return {
                "is_relevant": False,
                "reject_reason": "详情页是环评审批公示，不是环境业务采购公告",
                "confidence": 0.94,
                "project_category": "other",
            }

    client = RejectingClient.__new__(RejectingClient)
    candidate = TenderCandidate(
        title="某项目环境影响报告书审批公示",
        url="https://example.test/eia",
        notice_type=NoticeType.TENDER,
    )

    decision = asyncio.run(
        client.review_and_extract_notice(
            candidate,
            "环境影响报告书受理公示。",
            TenderFilterDecision(
                is_relevant=True,
                reason="初筛命中环境词",
                confidence=0.8,
            ),
        )
    )

    assert isinstance(decision, TenderFilterDecision)
    assert decision.is_relevant is False
    assert decision.reason == "详情页是环评审批公示，不是环境业务采购公告"


def test_review_and_extract_notice_builds_notice_for_relevant_environment_procurement():
    class AcceptingClient(OpenAICompatibleTenderLLMClient):
        async def _json_chat(self, prompt):
            return {
                "is_relevant": True,
                "reject_reason": None,
                "confidence": 0.91,
                "project_category": "environment_monitoring",
                "notice_type": "winning_bid",
                "project_name": "生态环境监测服务项目",
                "purchaser": "某生态环境局",
                "winning_bidder": "某环保科技有限公司",
                "winning_amount": "5600000元",
                "budget_amount": "650万元",
                "province": "广东",
                "city": "广州",
                "publish_date": "2026-07-02",
                "summary": "生态环境监测服务项目成交。",
                "key_requirements": ["环境监测服务"],
            }

    client = AcceptingClient.__new__(AcceptingClient)
    candidate = TenderCandidate(
        title="生态环境监测服务项目成交公告",
        url="https://example.test/notice",
        notice_type=NoticeType.TENDER,
    )

    notice = asyncio.run(
        client.review_and_extract_notice(
            candidate,
            "成交供应商：某环保科技有限公司；成交金额：5600000元。",
            TenderFilterDecision(
                is_relevant=True,
                reason="LLM初筛命中环境业务公告",
                confidence=0.8,
            ),
        )
    )

    assert notice.notice_type == NoticeType.WINNING_BID
    assert notice.environment_relevance is True
    assert notice.filter_confidence == 0.91
    assert notice.industry_category == "environment_monitoring"
    assert notice.winning_amount_wan_yuan == 560.0


def test_review_and_extract_notice_normalizes_legacy_project_category():
    class LegacyCategoryClient(OpenAICompatibleTenderLLMClient):
        async def _json_chat(self, prompt):
            return {
                "is_relevant": True,
                "confidence": 0.9,
                "project_category": "other",
                "notice_type": "tender",
                "project_name": "环境业务采购项目",
                "summary": "环境业务采购项目。",
                "key_requirements": [],
            }

    client = LegacyCategoryClient.__new__(LegacyCategoryClient)
    notice = asyncio.run(
        client.review_and_extract_notice(
            TenderCandidate(
                title="环境业务采购项目招标公告",
                url="https://example.test/legacy-category",
                notice_type=NoticeType.TENDER,
            ),
            "采购环境业务相关服务。",
            TenderFilterDecision(
                is_relevant=True,
                reason="初筛命中环境业务公告",
                confidence=0.8,
            ),
        )
    )

    assert notice.industry_category == "other_environment_procurement"
