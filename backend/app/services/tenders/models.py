from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class NoticeType(str, Enum):
    TENDER = "tender"
    WINNING_BID = "winning_bid"
    CHANGE = "change"
    OTHER = "other"


@dataclass(slots=True)
class TenderCandidate:
    title: str
    url: str
    notice_type: NoticeType = NoticeType.OTHER
    keyword: str = ""
    source: str = "qianlima"
    publish_date: Optional[date] = None
    raw_list_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def normalized_url_key(self) -> str:
        return self.url.strip().lower()


@dataclass(slots=True)
class TenderFilterDecision:
    is_relevant: bool
    reason: str
    confidence: float
    decision_source: str = "rules"
    matched_positive_keywords: List[str] = field(default_factory=list)
    matched_negative_keywords: List[str] = field(default_factory=list)
    project_category: Optional[str] = None


@dataclass(slots=True)
class TenderNotice:
    title: str
    url: str
    notice_type: NoticeType
    raw_content: str
    project_name: Optional[str] = None
    purchaser: Optional[str] = None
    agency: Optional[str] = None
    winning_bidder: Optional[str] = None
    budget_amount: Optional[str] = None
    budget_amount_wan_yuan: Optional[float] = None
    winning_amount: Optional[str] = None
    winning_amount_wan_yuan: Optional[float] = None
    province: Optional[str] = None
    city: Optional[str] = None
    publish_date: Optional[date] = None
    bid_open_date: Optional[str] = None
    deadline: Optional[str] = None
    industry_category: Optional[str] = None
    environment_relevance: bool = False
    filter_reason: str = ""
    filter_confidence: float = 0.0
    summary: str = ""
    key_requirements: List[str] = field(default_factory=list)
    attachment_urls: List[str] = field(default_factory=list)
    structured_json: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_payload(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["notice_type"] = self.notice_type.value
        for key in ("publish_date", "created_at", "updated_at"):
            value = payload.get(key)
            if value is not None:
                payload[key] = value.isoformat()
        return payload


@dataclass(slots=True)
class PipelineRunResult:
    total_candidates: int = 0
    duplicate_candidates: int = 0
    filtered_out: int = 0
    detail_fetch_failures: int = 0
    saved_notices: int = 0
    vector_indexed: int = 0
    errors: List[str] = field(default_factory=list)
