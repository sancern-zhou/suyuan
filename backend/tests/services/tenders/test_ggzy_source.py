from datetime import date

from app.services.tenders.models import NoticeType
from app.services.tenders.sources.ggzy import (
    PLATFORMS,
    GgzyEsSource,
    _notice_type,
    _parse_dt,
)


def test_ggzy_notice_type_mapping():
    assert _notice_type("中标公告") == NoticeType.WINNING_BID
    assert _notice_type("废标公告") == NoticeType.CHANGE
    assert _notice_type("招标公告") == NoticeType.TENDER
    assert _notice_type("") == NoticeType.OTHER


def test_ggzy_parse_dt():
    assert _parse_dt("2026-09-18 21:02:00") == date(2026, 9, 18)
    assert _parse_dt("") is None


def test_ggzy_body_uses_exact_day_window():
    source = GgzyEsSource(platforms=list(PLATFORMS[:1]))
    body = source._body(PLATFORMS[0], "生态环境", date(2026, 9, 18))
    entry = body["time"][0]
    assert entry["startTime"] == "2026-09-18 00:00:00"
    assert entry["endTime"] == "2026-09-18 23:59:59"
    assert body["wd"] == "生态环境"
    assert body["cl"] == 200


def test_ggzy_candidate_mapping_builds_absolute_url():
    source = GgzyEsSource(platforms=list(PLATFORMS[:1]))
    record = {
        "title": "某生态环境监测项目中标公告",
        "linkurl": "/jyxxgk/001/002/20260918/abc.html",
        "content": "正文摘要",
        "webdate": "2026-09-18 10:00:00",
        "categoryname": "中标公告",
        "infod": "杭州市",
    }
    candidate = source._to_candidate(PLATFORMS[0], record, "生态环境")
    assert candidate.url == "https://ggzy.zj.gov.cn/jyxxgk/001/002/20260918/abc.html"
    assert candidate.notice_type == NoticeType.WINNING_BID
    assert candidate.publish_date == date(2026, 9, 18)
    assert candidate.metadata["ggzy_province"] == "浙江"


def test_ggzy_title_key_normalizes():
    from app.services.tenders.sources.ggzy import _title_key

    assert _title_key("某局 2026 年监测项目（中标）公告") == _title_key("某局2026年监测项目中标公告")


def test_ggzy_platforms_for_province_matches_prefix():
    source = GgzyEsSource()
    names = [p.province for p in source.platforms_for_province("浙江省")]
    assert "浙江" in names
    assert "四川" not in names


def test_aggregator_enrichment_detects_masked_detail():
    from app.services.tenders.sources.aggregator import MultiSourceTenderClient

    assert MultiSourceTenderClient._needs_enrichment("短") is True
    assert MultiSourceTenderClient._needs_enrichment("登录即可免费查看" * 60) is True
    assert MultiSourceTenderClient._needs_enrichment("正文" * 400) is False
