import os

import pytest

from app.services.tenders.llm import OpenAICompatibleTenderLLMClient
from app.services.tenders.models import NoticeType, TenderCandidate, TenderFilterDecision
from app.services.tenders.pipeline import maybe_close_client
from app.services.tenders.qianlima_client import QianlimaClient


def _has_llm_key() -> bool:
    return any(
        os.getenv(name)
        for name in (
            "TENDER_LLM_API_KEY",
            "OPENAI_API_KEY",
            "DASHSCOPE_API_KEY",
            "QWEN_API_KEY",
        )
    )


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_TENDER_REAL_INTEGRATION") != "1" or not _has_llm_key(),
    reason=(
        "set RUN_TENDER_REAL_INTEGRATION=1 and configure a real tender LLM key "
        "to access Qianlima and the real LLM service"
    ),
)


@pytest.mark.asyncio
async def test_real_qianlima_search_and_real_llm_review_are_reachable():
    client = QianlimaClient(
        storage_state_path=os.getenv(
            "QIANLIMA_STORAGE_STATE",
            "backend_data_registry/tenders/qianlima_storage_state.json",
        ),
        headless=True,
    )
    try:
        candidates = await client.search(
            keyword="生态环境局",
            notice_type=NoticeType.TENDER,
            publish_date=None,
            max_pages=1,
        )
    finally:
        await maybe_close_client(client)

    assert isinstance(candidates, list)

    candidate = candidates[0] if candidates else TenderCandidate(
        title="生态环境局环境监测服务项目招标公告",
        url="https://example.com/tender-real-llm-smoke",
        notice_type=NoticeType.TENDER,
        keyword="生态环境局",
        raw_list_text="生态环境局环境监测服务项目招标公告",
    )
    llm = OpenAICompatibleTenderLLMClient()
    decision = await llm.review_candidate(
        candidate,
        TenderFilterDecision(
            is_relevant=True,
            reason="集成测试初始判断",
            confidence=0.5,
            decision_source="integration_test",
        ),
    )

    assert isinstance(decision.is_relevant, bool)
    assert decision.reason
