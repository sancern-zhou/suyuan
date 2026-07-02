import pytest
import sqlite3
from datetime import date

from src.tenders.extractor import TenderStructuredExtractor
from src.tenders.filters import TenderRelevanceFilter
from src.tenders.models import NoticeType, TenderCandidate, TenderNotice
from src.tenders.pipeline import TenderPipeline
from src.tenders.repository import InMemoryTenderRepository, SQLiteTenderRepository
from src.tenders.qianlima_client import (
    QianlimaClient,
    parse_qianlima_list_html,
    parse_qianlima_search_api_response,
)


def make_candidate(title: str, url: str = "https://example.test/detail/1") -> TenderCandidate:
    return TenderCandidate(
        title=title,
        url=url,
        notice_type=NoticeType.TENDER,
        keyword="生态环境局",
        source="qianlima",
    )


def test_filter_excludes_ecology_department_office_procurement():
    decision = TenderRelevanceFilter().decide(
        make_candidate("某市生态环境局复印纸和打印耗材采购项目招标公告")
    )

    assert decision.is_relevant is False
    assert decision.decision_source == "rules"
    assert "办公" in decision.reason or "耗材" in decision.reason


def test_filter_excludes_ecology_department_common_service_procurement():
    decision = TenderRelevanceFilter().decide(
        make_candidate("某市生态环境局基础电信服务的网上超市采购项目合同履约验收公告")
    )

    assert decision.is_relevant is False
    assert decision.decision_source == "rules"
    assert "非环境业务" in decision.reason or "基础保障" in decision.reason


def test_filter_excludes_ecology_department_vehicle_maintenance():
    decision = TenderRelevanceFilter().decide(
        make_candidate("某州生态环境局关于车辆定点维修的服务市场采购项目成交公告")
    )

    assert decision.is_relevant is False
    assert decision.decision_source == "rules"


def test_filter_accepts_environmental_monitoring_project():
    decision = TenderRelevanceFilter().decide(
        make_candidate("某市生态环境局VOCs走航监测及污染源排查项目招标公告")
    )

    assert decision.is_relevant is True
    assert decision.decision_source == "rules"
    assert decision.confidence >= 0.75


def test_parse_qianlima_list_html_extracts_candidates():
    html = """
    <html><body>
      <a href="/zb/detail/1001.html">某市生态环境局水质自动监测站运维项目招标公告</a>
      <a href="https://www.qianlima.com/bid-1002.html">某县生态环境局复印纸采购中标公告</a>
      <a href="/about">关于我们</a>
    </body></html>
    """

    candidates = parse_qianlima_list_html(
        html=html,
        base_url="https://www.qianlima.com",
        keyword="生态环境局",
        notice_type=NoticeType.TENDER,
    )

    assert [candidate.title for candidate in candidates] == [
        "某市生态环境局水质自动监测站运维项目招标公告",
        "某县生态环境局复印纸采购中标公告",
    ]
    assert candidates[0].url == "https://www.qianlima.com/zb/detail/1001.html"


def test_parse_qianlima_search_api_response_extracts_candidates():
    payload = {
        "code": 200,
        "data": {
            "data": [
                {
                    "contentid": 609894407,
                    "progName": "公告",
                    "updateTime": "2026-06-30",
                    "updateTimeStr": "2026-06-30 17:05:14",
                    "url": "https://www.qianlima.com/bid-609894407.html",
                    "originUrl": "http://www.qianlima.com/zb/detail/20260630_609894407.html",
                    "areaName": "广东-东莞",
                    "popTitle": "关于为【东莞市生态环境局石碣分局2026年-2027年石碣镇环境监测项目A】公开选取【检验检测服务】机构的公告",
                    "showTitle": "关于为【东莞市<font color ='red'>生态环境</font><font color ='red'>局</font>石碣分<font color ='red'>局</font>】公开选取",
                }
            ]
        },
    }

    candidates = parse_qianlima_search_api_response(
        payload=payload,
        keyword="生态环境局",
        notice_type=NoticeType.TENDER,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.title == "关于为【东莞市生态环境局石碣分局2026年-2027年石碣镇环境监测项目A】公开选取【检验检测服务】机构的公告"
    assert candidate.url == "https://www.qianlima.com/bid-609894407.html"
    assert candidate.publish_date.isoformat() == "2026-06-30"
    assert candidate.metadata["area_name"] == "广东-东莞"


def test_qianlima_complete_date_crawl_stops_after_target_date():
    client = QianlimaClient()
    target_date = date(2026, 6, 30)

    assert client._is_past_target_date_page([date(2026, 6, 29)], target_date, True)
    assert not client._is_past_target_date_page([date(2026, 7, 1)], target_date, False)
    assert not client._is_past_target_date_page([target_date], target_date, True)


def test_extractor_prefers_api_region_and_main_content_fields():
    candidate = make_candidate(
        "乐山市县级生态环境监测能力提升和县级生态环境监测机构标准化建设项目（二期）"
    )
    candidate.metadata["area_name"] = "四川-乐山"
    decision = TenderRelevanceFilter().decide(candidate)
    detail_text = """
    华北 北京 天津 河北 山西
    招标单位:
    立即查看
    咨询:400-688-2000查看全部商机
    采购单位：****
    采购项目名称：**市县级生态环境监测能力提升**级生态环境监测机构标准化建设项目（二期）
    预算金额：265.000000万元(人民币)
    采购需求概况：采购环保监测设备，满足环境监测站能力提升和标准化建设。
    相关公告
    注册会员享贴心服务
    """

    notice = TenderStructuredExtractor().extract(candidate, detail_text, decision)

    assert notice.province == "四川"
    assert notice.city == "乐山"
    assert notice.project_name == candidate.title
    assert notice.purchaser is None
    assert notice.budget_amount_wan_yuan == 265
    assert "raw_content" not in notice.structured_json


def test_extractor_converts_currency_amount_with_comma_to_wan_yuan():
    candidate = make_candidate("南京市生态环境分区管控方案五年定期调整技术评估服务项目")
    candidate.metadata["area_name"] = "江苏-南京"
    decision = TenderRelevanceFilter().decide(candidate)
    detail_text = """
    咨询:400-688-2000查看全部商机
    项目名称： **市生态环境分区管控方案五年定期调整技术评估服务项目
    项目预算： ￥243,500
    中选金额 ￥183300.0元
    """

    notice = TenderStructuredExtractor().extract(candidate, detail_text, decision)

    assert notice.project_name == candidate.title
    assert notice.budget_amount == "￥243,500"
    assert notice.budget_amount_wan_yuan == 24.35
    assert notice.winning_amount_wan_yuan == 18.33


class FakeQianlimaClient:
    async def search(self, keyword, notice_type, publish_date=None, max_pages=1):
        return [
            make_candidate(
                "某市生态环境局VOCs走航监测及污染源排查项目招标公告",
                "https://example.test/detail/env",
            ),
            make_candidate(
                "某市生态环境局办公桌椅采购项目招标公告",
                "https://example.test/detail/office",
            ),
        ]

    async def fetch_detail(self, candidate):
        if "office" in candidate.url:
            return "<html><body>办公桌椅采购，预算金额3万元。</body></html>"
        return """
        <html><body>
        项目名称：某市生态环境局VOCs走航监测及污染源排查项目
        采购人：某市生态环境局
        代理机构：某招标代理有限公司
        预算金额：120万元
        开标时间：2026年7月15日
        项目内容：开展VOCs走航监测、污染源排查和数据分析服务。
        </body></html>
        """


class FakeSemanticQianlimaClient:
    async def search(self, keyword, notice_type, publish_date=None, max_pages=1):
        return [
            make_candidate(
                "某市重点流域综合能力建设项目招标公告",
                "https://example.test/detail/semantic",
            )
        ]

    async def fetch_detail(self, candidate):
        return """
        <html><body>
        项目名称：某市重点流域综合能力建设项目
        采购人：某市公共事业管理中心
        预算金额：90万元
        项目内容：建设水环境数据采集、在线监控和污染溯源分析能力。
        </body></html>
        """


class FakeTenderLLMClient:
    def __init__(self):
        self.review_detail_texts = []
        self.extraction_detail_texts = []

    async def review_candidate(self, candidate, rule_decision, detail_text=""):
        self.review_detail_texts.append(detail_text)
        return rule_decision.__class__(
            is_relevant=True,
            reason="LLM 判断为环境业务项目",
            confidence=0.91,
            decision_source="llm",
            project_category="environment_monitoring",
        )

    async def refine_notice(self, notice):
        return notice

    async def extract_notice(self, candidate, detail_text, decision):
        self.extraction_detail_texts.append(detail_text)
        notice = TenderNotice(
            title=candidate.title,
            url=candidate.url,
            notice_type=candidate.notice_type,
            raw_content=detail_text,
            project_name="LLM抽取的重点流域综合能力建设项目",
            purchaser="某市公共事业管理中心",
            budget_amount="90万元",
            budget_amount_wan_yuan=90,
            publish_date=candidate.publish_date,
            industry_category=decision.project_category,
            environment_relevance=decision.is_relevant,
            filter_reason=decision.reason,
            filter_confidence=decision.confidence,
            summary="建设水环境数据采集、在线监控和污染溯源分析能力。",
            key_requirements=["水环境数据采集", "在线监控", "污染溯源分析"],
        )
        notice.structured_json = {
            "project_name": notice.project_name,
            "purchaser": notice.purchaser,
            "budget_amount": notice.budget_amount,
            "budget_amount_wan_yuan": notice.budget_amount_wan_yuan,
        }
        return notice


@pytest.mark.asyncio
async def test_pipeline_filters_fetches_extracts_and_stores_target_notice():
    repository = InMemoryTenderRepository()
    pipeline = TenderPipeline(
        client=FakeQianlimaClient(),
        repository=repository,
        relevance_filter=TenderRelevanceFilter(),
        enable_vector_index=False,
    )

    result = await pipeline.run_daily(
        keywords=["生态环境局"],
        notice_types=[NoticeType.TENDER],
        max_pages=1,
    )

    assert result.total_candidates == 2
    assert result.saved_notices == 1
    assert result.filtered_out == 1
    assert len(repository.notices) == 1
    notice = repository.notices[0]
    assert notice.project_name == "某市生态环境局VOCs走航监测及污染源排查项目"
    assert notice.purchaser == "某市生态环境局"
    assert notice.budget_amount_wan_yuan == 120
    assert notice.environment_relevance is True


@pytest.mark.asyncio
async def test_pipeline_uses_llm_without_keyword_prefilter():
    repository = InMemoryTenderRepository()
    llm_client = FakeTenderLLMClient()
    pipeline = TenderPipeline(
        client=FakeSemanticQianlimaClient(),
        repository=repository,
        llm_client=llm_client,
        enable_vector_index=False,
    )

    result = await pipeline.run_daily(
        keywords=["生态环境局"],
        notice_types=[NoticeType.TENDER],
        max_pages=1,
    )

    assert result.total_candidates == 1
    assert result.saved_notices == 1
    assert result.filtered_out == 0
    assert len(llm_client.review_detail_texts) == 2
    assert "水环境数据采集" in llm_client.review_detail_texts[1]
    assert len(llm_client.extraction_detail_texts) == 1
    assert "水环境数据采集" in llm_client.extraction_detail_texts[0]
    assert repository.notices[0].project_name == "LLM抽取的重点流域综合能力建设项目"
    assert repository.notices[0].filter_reason == "LLM 判断为环境业务项目"


@pytest.mark.asyncio
async def test_sqlite_repository_persists_candidate_and_notice(tmp_path):
    repository = SQLiteTenderRepository(str(tmp_path / "tenders.db"))
    candidate = make_candidate("某市生态环境局水质自动监测站运维项目招标公告")
    decision = TenderRelevanceFilter().decide(candidate)
    notice = TenderStructuredExtractor().extract(
        candidate,
        "项目名称：某市生态环境局水质自动监测站运维项目\n采购人：某市生态环境局\n预算金额：80万元",
        decision,
    )

    assert await repository.save_candidate(candidate, decision) is True
    assert await repository.save_candidate(candidate, decision) is False
    await repository.save_notice(notice)

    with sqlite3.connect(tmp_path / "tenders.db") as conn:
        candidate_count = conn.execute("SELECT COUNT(*) FROM tender_candidates").fetchone()[0]
        notice_row = conn.execute(
            "SELECT project_name, purchaser, budget_amount_wan_yuan FROM tender_notices"
        ).fetchone()

    assert candidate_count == 1
    assert notice_row == ("某市生态环境局水质自动监测站运维项目", "某市生态环境局", 80)
