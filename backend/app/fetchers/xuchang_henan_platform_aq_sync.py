"""省城市空气质量大数据综合应用系统年度对比三表每日增量同步。"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.utils.path_config import PROJECT_ROOT

logger = structlog.get_logger()


def _sync_module():
    path = PROJECT_ROOT / "projects/xuchang/data-ops/sync_henan_platform_aq/sync.py"
    spec = importlib.util.spec_from_file_location("xuchang_henan_platform_aq_sync_job", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载省平台同步脚本: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class XuchangHenanPlatformAqSyncFetcher(DataFetcher):
    def __init__(self) -> None:
        super().__init__(
            name="xuchang_henan_platform_aq_sync_fetcher",
            schedule="0 4 * * *",
            description="省平台年度/月度/MTD/YTD三表同步DataCrawler",
        )

    async def fetch_and_store(self) -> Any:
        # SQL Server 使用同步 pyodbc，整段读取移出 worker 事件循环。
        import asyncio

        result = await asyncio.to_thread(_sync_module().sync)
        logger.info("xuchang_henan_platform_aq_sync_completed", **result)
        return result
