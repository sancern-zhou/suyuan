import asyncio

import pytest

from app.fetchers.base.fetcher_interface import DataFetcher, FetcherStatus


class BlockingFetcher(DataFetcher):
    def __init__(self):
        super().__init__("blocking", "blocking", "* * * * *")
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def fetch_and_store(self):
        self.calls += 1
        self.started.set()
        await self.release.wait()


@pytest.mark.asyncio
async def test_overlapping_fetcher_run_is_skipped_instead_of_queued():
    fetcher = BlockingFetcher()
    first = asyncio.create_task(fetcher.run())
    await fetcher.started.wait()

    await fetcher.run()

    assert fetcher.calls == 1
    assert fetcher.status == FetcherStatus.RUNNING
    fetcher.release.set()
    await first
    assert fetcher.status == FetcherStatus.IDLE
