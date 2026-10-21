from __future__ import annotations

from datetime import date
from typing import Optional, Protocol, runtime_checkable

from ..models import NoticeType, TenderCandidate


@runtime_checkable
class TenderSource(Protocol):
    """A single tender information provider (qianlima, jianyu360, ...).

    Implementations must tag every returned candidate with ``source`` equal to
    their ``name`` so the aggregator can route detail fetching back to them.
    """

    name: str

    async def search(
        self,
        keyword: str,
        notice_type: NoticeType,
        publish_date: Optional[date] = None,
        max_pages: int = 1,
    ) -> list[TenderCandidate]: ...

    async def fetch_detail(self, candidate: TenderCandidate) -> str: ...

    async def close(self) -> None: ...
