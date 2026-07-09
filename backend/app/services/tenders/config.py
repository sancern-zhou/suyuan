from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Sequence

from app.services.tenders.models import NoticeType

DEFAULT_TENDER_KEYWORDS = [
    "生态环境局",
    "环境监测中心",
    "生态环境厅",
    "环境监测站",
    "生态环境分局",
    "环境监控中心",
    "污染源在线监控",
    "空气自动站",
    "水质自动站",
    "VOCs走航",
    "噪声自动监测",
]


def parse_keywords(value: str | Sequence[str]) -> list[str]:
    if isinstance(value, str):
        items = value.split(",")
    else:
        items = value
    return [item.strip() for item in items if item and item.strip()]


def parse_notice_types(value: str | Sequence[NoticeType | str]) -> list[NoticeType]:
    mapping = {
        "tender": NoticeType.TENDER,
        "winning_bid": NoticeType.WINNING_BID,
        "change": NoticeType.CHANGE,
        "other": NoticeType.OTHER,
    }
    if isinstance(value, str):
        items: Sequence[NoticeType | str] = value.split(",")
    else:
        items = value

    notice_types: list[NoticeType] = []
    for item in items:
        if isinstance(item, NoticeType):
            notice_types.append(item)
            continue
        normalized = str(item).strip()
        if not normalized:
            continue
        try:
            notice_types.append(mapping[normalized])
        except KeyError as exc:
            raise ValueError(f"unsupported tender notice type: {normalized}") from exc
    return notice_types


def default_target_date(today: date | None = None) -> date:
    return (today or date.today()) - timedelta(days=1)


@dataclass(slots=True)
class TenderFetcherConfig:
    enabled: bool = True
    schedule: str = "30 2 * * *"
    keywords: list[str] = field(default_factory=lambda: list(DEFAULT_TENDER_KEYWORDS))
    notice_types: list[NoticeType] = field(
        default_factory=lambda: [NoticeType.TENDER, NoticeType.WINNING_BID]
    )
    max_pages: int = 0
    qianlima_storage_state: str = (
        "backend_data_registry/tenders/qianlima_storage_state.json"
    )
    qianlima_base_url: str = "https://www.qianlima.com"
    qianlima_headless: bool = True
    enable_llm: bool = True
