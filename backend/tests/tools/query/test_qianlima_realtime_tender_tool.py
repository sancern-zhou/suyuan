from __future__ import annotations

import json
from datetime import date

import pytest

from app.services.tenders.models import NoticeType, TenderCandidate
from app.tools.query.qianlima_realtime_tender.tool import QianlimaRealtimeTenderTool


class FakeQianlimaClient:
    search_calls: list[dict] = []
    detail_calls: list[TenderCandidate] = []

    def __init__(self, *args, **kwargs):
        self.closed = False

    async def search(self, keyword, notice_type, publish_date=None, max_pages=1):
        self.search_calls.append(
            {
                "keyword": keyword,
                "notice_type": notice_type,
                "publish_date": publish_date,
                "max_pages": max_pages,
            }
        )
        return [
            TenderCandidate(
                title=f"{keyword}-{publish_date.isoformat()}",
                url=f"https://www.qianlima.com/bid/{publish_date.isoformat()}",
                notice_type=NoticeType.OTHER,
                keyword=keyword,
                publish_date=publish_date,
                raw_list_text="列表摘要",
                metadata={"area_name": "广东省"},
            )
        ]

    async def fetch_detail(self, candidate):
        self.detail_calls.append(candidate)
        return "<html><body><h1>会员详情标题</h1><p>完整招标正文</p></body></html>"

    async def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def reset_fake_client():
    FakeQianlimaClient.search_calls = []
    FakeQianlimaClient.detail_calls = []


@pytest.mark.asyncio
async def test_search_mode_supports_plus_keyword_range_and_writes_files(tmp_path):
    tool = QianlimaRealtimeTenderTool(
        output_dir=tmp_path,
        client_factory=FakeQianlimaClient,
    )

    result = await tool.execute(
        mode="search",
        keywords=["景观", "喷泉"],
        keyword_operator="plus",
        start_date="2026-07-01",
        end_date="2026-07-02",
        max_pages=0,
        max_results=10,
    )

    assert result["success"] is True
    assert result["mode"] == "search"
    assert result["count"] == 2
    assert [call["keyword"] for call in FakeQianlimaClient.search_calls] == [
        "景观+喷泉",
        "景观+喷泉",
    ]
    assert [call["publish_date"] for call in FakeQianlimaClient.search_calls] == [
        date(2026, 7, 1),
        date(2026, 7, 2),
    ]
    assert all(call["max_pages"] == 0 for call in FakeQianlimaClient.search_calls)

    output_path = tmp_path / result["output_file"]
    markdown_path = tmp_path / result["markdown_file"]
    assert output_path.exists()
    assert markdown_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["query"] == "景观+喷泉"
    assert payload["mode"] == "search"
    assert payload["results"][0]["title"] == "景观+喷泉-2026-07-01"
    assert payload["results"][0]["url"] == "https://www.qianlima.com/bid/2026-07-01"
    assert "景观+喷泉-2026-07-02" in markdown_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_detail_mode_fetches_member_page_by_url_and_writes_file(tmp_path):
    tool = QianlimaRealtimeTenderTool(
        output_dir=tmp_path,
        client_factory=FakeQianlimaClient,
    )

    result = await tool.execute(
        mode="detail",
        url="https://www.qianlima.com/bid/detail-1",
        title="详情页标题",
    )

    assert result["success"] is True
    assert result["mode"] == "detail"
    assert result["url"] == "https://www.qianlima.com/bid/detail-1"
    assert FakeQianlimaClient.detail_calls[0].url == "https://www.qianlima.com/bid/detail-1"

    output_path = tmp_path / result["output_file"]
    html_path = tmp_path / result["html_file"]
    assert output_path.exists()
    assert html_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["detail"]["title"] == "详情页标题"
    assert "完整招标正文" in payload["detail"]["text"]
    assert "会员详情标题" in html_path.read_text(encoding="utf-8")


def test_qianlima_daily_limit_shell_is_detail_unavailable():
    from app.services.tenders.qianlima_client import _is_detail_unavailable_page

    html = """
    <div id="loadingAll">加载中...</div>
    <div class="topAlert">防诈骗提醒</div>
    <div id="detailContent"></div>
    <div class="data-bag-title" style="display: none;">
      今日浏览已达到上限，请明日再试哟～
    </div>
    <h3>数据来自千里马招标网</h3>
    <h4>千里马招标网是招标信息最全、覆盖地区及招标行业最广的招标网</h4>
    """ + ("广告内容" * 2000)

    assert _is_detail_unavailable_page(html) is True


def test_date_range_allows_up_to_one_year():
    from app.tools.query.qianlima_realtime_tender.tool import _date_range

    dates = _date_range("2026-01-01", "2026-12-31")

    assert len(dates) == 365
    assert dates[0].isoformat() == "2026-01-01"
    assert dates[-1].isoformat() == "2026-12-31"


def test_date_range_rejects_more_than_one_year():
    from app.tools.query.qianlima_realtime_tender.tool import _date_range

    with pytest.raises(ValueError, match="日期范围最多支持 366 天"):
        _date_range("2026-01-01", "2027-01-02")
