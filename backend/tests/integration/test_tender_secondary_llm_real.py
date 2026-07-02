import os

import pytest

from app.services.tenders.llm import OpenAICompatibleTenderLLMClient
from app.services.tenders.models import NoticeType, TenderCandidate, TenderFilterDecision


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_TENDER_SECONDARY_LLM_INTEGRATION") != "1"
    or not os.getenv("TENDER_SECONDARY_LLM_API_KEY"),
    reason=(
        "set RUN_TENDER_SECONDARY_LLM_INTEGRATION=1 and "
        "TENDER_SECONDARY_LLM_API_KEY to access the real secondary tender LLM"
    ),
)


@pytest.mark.asyncio
async def test_real_secondary_tender_llm_extracts_notice():
    client = OpenAICompatibleTenderLLMClient(
        api_key=os.getenv("TENDER_SECONDARY_LLM_API_KEY"),
        base_url=os.getenv(
            "TENDER_SECONDARY_LLM_BASE_URL",
            "https://apihub.agnes-ai.com/v1/chat/completions",
        ),
        model=os.getenv("TENDER_SECONDARY_LLM_MODEL", "agnes-2.0-flash"),
    )
    candidate = TenderCandidate(
        title="生态环境局环境监测服务项目招标公告",
        url="https://example.test/tender-secondary-llm",
        notice_type=NoticeType.TENDER,
        raw_list_text="生态环境局环境监测服务项目招标公告",
    )

    notice = await client.extract_notice(
        candidate,
        (
            "项目名称：生态环境局环境监测服务项目。采购人：某市生态环境局。"
            "预算金额：120万元。采购内容：开展空气质量和水质监测服务。"
            "公告日期：2026-07-01。"
        ),
        TenderFilterDecision(
            is_relevant=True,
            reason="环境监测服务",
            confidence=0.9,
            project_category="environment_monitoring",
        ),
    )

    assert notice.project_name
    assert notice.environment_relevance is True
