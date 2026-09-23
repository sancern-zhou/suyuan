from __future__ import annotations

from datetime import date
from typing import Optional

from config.settings import settings

from ..models import NoticeType, TenderCandidate
from ..qianlima_client import QianlimaClient


class QianlimaSource:
    name = "qianlima"

    def __init__(self, client: QianlimaClient):
        self._client = client

    async def search(
        self,
        keyword: str,
        notice_type: NoticeType,
        publish_date: Optional[date] = None,
        max_pages: int = 1,
    ) -> list[TenderCandidate]:
        return await self._client.search(
            keyword, notice_type, publish_date, max_pages
        )

    async def fetch_detail(self, candidate: TenderCandidate) -> str:
        candidate.source = self.name
        return await self._client.fetch_detail(candidate)

    async def close(self) -> None:
        await self._client.close()


def build_qianlima_source(config) -> QianlimaSource:
    client = QianlimaClient(
        base_url=settings.qianlima_base_url,
        username=settings.qianlima_username,
        password=settings.qianlima_password,
        accounts=settings.qianlima_accounts,
        storage_state_path=settings.qianlima_storage_state,
        headless=getattr(config, "qianlima_headless", True),
    )
    return QianlimaSource(client)
