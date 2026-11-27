"""共享的 DataCrawler MySQL 只读查询辅助（供推送场景抓取器使用）。

Crawler MySQL 与抓取器共用一个实例（13307），连接串来自 settings.crawler_mysql_url。
只做短连接查询，不复用连接池，避免与既有抓取器并发互相影响。
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger()


def _parse_crawler_mysql_url() -> dict[str, Any]:
    from config.settings import settings

    url = settings.crawler_mysql_url.split("://", 1)[1]
    auth_host, database = url.split("/", 1)
    credentials, host_port = auth_host.rsplit("@", 1)
    user, password = credentials.split(":", 1)
    host, port = host_port.split(":")
    return {
        "host": host,
        "port": int(port),
        "user": user,
        "password": password,
        "db": database.split("?", 1)[0],
    }


async def query_crawler_mysql(sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[dict[str, Any]]:
    """执行一条只读查询，返回 DictCursor 行列表；连接失败向上抛出。"""
    import aiomysql

    config = _parse_crawler_mysql_url()
    conn = await aiomysql.connect(
        host=config["host"], port=config["port"], user=config["user"],
        password=config["password"], db=config["db"],
    )
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(sql, params)
            return list(await cursor.fetchall())
    finally:
        conn.close()


def run_query_sync(sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[dict[str, Any]]:
    """在异步 fetcher 的执行线程里跑一次同步风格的查询。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(query_crawler_mysql(sql, params))
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(query_crawler_mysql(sql, params))).result()
