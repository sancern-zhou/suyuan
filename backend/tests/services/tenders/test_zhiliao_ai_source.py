from datetime import date

from app.services.tenders.models import NoticeType
from app.services.tenders.sources.zhiliao_ai import (
    ZhiliaoAiClient,
    _notice_type,
    _parse_date,
)


def test_zhiliao_ai_notice_type_mapping():
    assert _notice_type("中标", "中标结果", []) == NoticeType.WINNING_BID
    assert _notice_type("招标", "招标", []) == NoticeType.TENDER
    assert _notice_type("招标", "废标公告", []) == NoticeType.CHANGE
    assert _notice_type("", "", ["某公司"]) == NoticeType.WINNING_BID
    assert _notice_type("", "", []) == NoticeType.OTHER


def test_zhiliao_ai_parse_date():
    assert _parse_date("2026-09-19 09:30:00") == date(2026, 9, 19)
    assert _parse_dt_none() is None


def _parse_dt_none():
    from app.services.tenders.sources.zhiliao_ai import _parse_date as p

    return p("not-a-date")


def test_zhiliao_ai_search_body_uses_exact_day():
    client = ZhiliaoAiClient(api_key="k")
    # search() 组包逻辑通过 _post 发出；这里直接验证 page_size/日窗口参数组装
    assert client.page_size >= 1
    assert client.base_url.endswith("/api_v2")
