from datetime import date

import pytest

from app.services.tenders.config import (
    DEFAULT_TENDER_KEYWORDS,
    TenderFetcherConfig,
    default_target_date,
    parse_keywords,
    parse_notice_types,
)
from app.services.tenders.models import NoticeType


def test_default_config_uses_approved_daily_scope():
    config = TenderFetcherConfig()

    assert config.schedule == "30 6 * * *"
    assert config.keywords == DEFAULT_TENDER_KEYWORDS
    assert config.notice_types == [NoticeType.TENDER, NoticeType.WINNING_BID]
    assert config.max_pages == 0


def test_parse_keywords_trims_empty_items():
    assert parse_keywords("生态环境局, 环境监测中心,,生态环境厅 ") == [
        "生态环境局",
        "环境监测中心",
        "生态环境厅",
    ]


def test_parse_notice_types_accepts_config_values():
    assert parse_notice_types("tender,winning_bid") == [
        NoticeType.TENDER,
        NoticeType.WINNING_BID,
    ]


def test_parse_notice_types_rejects_unknown_values():
    with pytest.raises(ValueError, match="unsupported tender notice type"):
        parse_notice_types("tender,unknown")


def test_default_target_date_uses_previous_day():
    assert default_target_date(today=date(2026, 7, 1)) == date(2026, 6, 30)
