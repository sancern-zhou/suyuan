from __future__ import annotations

import asyncio
import json
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

from app.services.tenders.models import NoticeType, TenderCandidate
from app.services.tenders.qianlima_client import QianlimaClient
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.resource_declarations import resources_for_files
from config.settings import settings


class QianlimaRealtimeTenderTool(LLMTool):
    """实时检索千里马招投标信息，不读取本地 SQL 入库数据。"""

    # 类级别的信号量，确保全局并发控制
    _detail_semaphore = asyncio.Semaphore(2)

    def __init__(
        self,
        output_dir: str | Path | None = None,
        client_factory: Callable[..., Any] = QianlimaClient,
    ):
        function_schema = {
            "name": "qianlima_realtime_tender",
            "description": (
                "实时抓取千里马招投标信息。默认 search 模式返回标题和链接，并把完整结果写入本地文件；"
                "detail 模式按 URL 使用会员浏览器登录态抓取详情页并写入本地文件。"
                "不查询 tender_candidates/tender_notices，不做 LLM 环境业务筛选。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["search", "detail"],
                        "default": "search",
                        "description": "search 检索列表；detail 按 URL 抓详情页。",
                    },
                    "query": {
                        "type": "string",
                        "description": "千里马搜索关键词原文。可直接传 '景观 喷泉' 或 '景观+喷泉'。",
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "关键词数组；未传 query 时按 keyword_operator 组合。",
                    },
                    "keyword_operator": {
                        "type": "string",
                        "enum": ["space", "plus"],
                        "default": "space",
                        "description": "keywords 的组合方式：space='景观 喷泉'；plus='景观+喷泉'，更精确。",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "检索开始发布日期，YYYY-MM-DD。只传一个日期时按单日检索。",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "检索结束发布日期，YYYY-MM-DD。日期范围为闭区间。",
                    },
                    "max_pages": {
                        "type": "integer",
                        "default": 10,
                        "description": "分页上限。>0 最多抓 N 页；带日期时 0 表示完整抓取当天，日期范围内逐日应用。",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 200,
                        "description": "返回和写入的最大结果数，1-200。",
                    },
                    "url": {
                        "type": "string",
                        "description": "detail 模式要抓取的千里马详情页 URL。",
                    },
                    "title": {
                        "type": "string",
                        "description": "detail 模式可选标题，用于结果文件展示。",
                    },
                },
                "required": [],
            },
        }
        super().__init__(
            name="qianlima_realtime_tender",
            description="实时抓取千里马招投标搜索结果和会员详情页",
            category=ToolCategory.QUERY,
            function_schema=function_schema,
            version="1.0.0",
        )
        self.output_dir = Path(output_dir) if output_dir else _default_output_dir()
        self.client_factory = client_factory

        # 从 settings 读取并发数并初始化信号量
        concurrency = settings.qianlima_realtime_concurrency
        QianlimaRealtimeTenderTool._detail_semaphore = asyncio.Semaphore(concurrency)

    async def execute(
        self,
        mode: str = "search",
        query: str | None = None,
        keywords: Sequence[str] | str | None = None,
        keyword_operator: str = "space",
        start_date: str | None = None,
        end_date: str | None = None,
        max_pages: int = 10,
        max_results: int = 200,
        url: str | None = None,
        title: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        normalized_mode = (mode or "search").strip().lower()
        if normalized_mode == "detail":
            return await self._execute_detail(url=url, title=title)
        if normalized_mode != "search":
            return {"success": False, "summary": "mode 只支持 search 或 detail"}
        return await self._execute_search(
            query=query,
            keywords=keywords,
            keyword_operator=keyword_operator,
            start_date=start_date,
            end_date=end_date,
            max_pages=max_pages,
            max_results=max_results,
        )

    async def _execute_search(
        self,
        query: str | None,
        keywords: Sequence[str] | str | None,
        keyword_operator: str,
        start_date: str | None,
        end_date: str | None,
        max_pages: int,
        max_results: int,
    ) -> dict[str, Any]:
        search_query = _build_search_query(query, keywords, keyword_operator)
        if not search_query:
            return {"success": False, "summary": "search 模式需要 query 或 keywords"}

        dates = _date_range(start_date, end_date)
        result_limit = min(max(int(max_results or 50), 1), 200)

        # 添加重试机制
        max_retries = settings.qianlima_realtime_max_retries
        for attempt in range(1, max_retries + 1):
            try:
                # 请求前延迟
                await self._delay_before_request("search")

                client = self._make_client()
                try:
                    candidates: list[TenderCandidate] = []
                    if dates:
                        for publish_date in dates:
                            candidates.extend(
                                await client.search(
                                    keyword=search_query,
                                    notice_type=NoticeType.OTHER,
                                    publish_date=publish_date,
                                    max_pages=int(max_pages),
                                )
                            )
                    else:
                        candidates.extend(
                            await client.search(
                                keyword=search_query,
                                notice_type=NoticeType.OTHER,
                                publish_date=None,
                                max_pages=max(1, int(max_pages or 1)),
                            )
                        )
                finally:
                    await _close_client(client)

                records = [_candidate_to_record(item) for item in _dedupe(candidates)]
                records = records[:result_limit]
                payload = {
                    "mode": "search",
                    "query": search_query,
                    "start_date": start_date,
                    "end_date": end_date,
                    "max_pages": int(max_pages),
                    "count": len(records),
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "results": records,
                }
                output_file, markdown_file = self._write_search_files(payload)
                return {
                    "success": True,
                    "mode": "search",
                    "query": search_query,
                    "count": len(records),
                    "results": records,
                    "output_file": str(output_file),
                    "markdown_file": str(markdown_file),
                    "resources": resources_for_files(
                        [output_file, markdown_file], tool_name=self.name
                    ),
                    "summary": f"实时检索到 {len(records)} 条千里马招投标结果，已写入 {output_file}",
                }
            except Exception as exc:
                if attempt < max_retries:
                    delay = _retry_delay_seconds(attempt)
                    await asyncio.sleep(delay)
                else:
                    return {
                        "success": False,
                        "error": str(exc),
                        "summary": f"搜索失败: {str(exc)}",
                    }

    async def _execute_detail(self, url: str | None, title: str | None) -> dict[str, Any]:
        detail_url = (url or "").strip()
        if not detail_url:
            return {"success": False, "summary": "detail 模式需要 url"}

        candidate = TenderCandidate(
            title=(title or detail_url).strip(),
            url=detail_url,
            notice_type=NoticeType.OTHER,
            source="qianlima",
        )

        # 使用信号量控制并发
        async with QianlimaRealtimeTenderTool._detail_semaphore:
            # 添加重试机制
            max_retries = settings.qianlima_realtime_max_retries
            for attempt in range(1, max_retries + 1):
                try:
                    # 请求前延迟
                    await self._delay_before_request("detail")

                    client = self._make_client()
                    try:
                        html = await client.fetch_detail(candidate)
                    finally:
                        await _close_client(client)

                    text = _html_to_text(html)
                    payload = {
                        "mode": "detail",
                        "url": detail_url,
                        "generated_at": datetime.now().isoformat(timespec="seconds"),
                        "detail": {
                            "title": candidate.title,
                            "url": detail_url,
                            "text": text,
                        },
                    }
                    output_file, html_file = self._write_detail_files(payload, html)
                    return {
                        "success": True,
                        "mode": "detail",
                        "url": detail_url,
                        "title": candidate.title,
                        "text_preview": text[:1000],
                        "output_file": str(output_file),
                        "html_file": str(html_file),
                        "resources": resources_for_files(
                            [output_file, html_file], tool_name=self.name
                        ),
                        "summary": f"详情页已抓取并写入 {output_file}",
                    }
                except Exception as exc:
                    if attempt < max_retries:
                        delay = _retry_delay_seconds(attempt)
                        await asyncio.sleep(delay)
                    else:
                        return {
                            "success": False,
                            "error": str(exc),
                            "summary": f"详情页抓取失败: {str(exc)}",
                        }

    def _make_client(self):
        return self.client_factory(
            base_url=settings.qianlima_base_url,
            username=settings.qianlima_username,
            password=settings.qianlima_password,
            accounts=settings.qianlima_accounts,
            storage_state_path=settings.qianlima_storage_state,
            headless=True,
            # 传递反爬参数给客户端
            request_delay_ms=settings.qianlima_realtime_request_delay_ms,
        )

    async def _delay_before_request(self, mode: str) -> None:
        """请求前延迟"""
        if mode == "detail" and settings.qianlima_realtime_enable_detail_delay:
            min_delay = settings.qianlima_realtime_detail_min_delay_seconds
            max_delay = settings.qianlima_realtime_detail_max_delay_seconds
            await asyncio.sleep(random.uniform(min_delay, max_delay))
        elif mode == "search" and settings.qianlima_realtime_enable_search_delay:
            delay_ms = settings.qianlima_realtime_request_delay_ms
            await asyncio.sleep(delay_ms / 1000)

    def _write_search_files(self, payload: dict[str, Any]) -> tuple[Path, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stem = _file_stem("search", payload["query"])
        json_path = self.output_dir / f"{stem}.json"
        markdown_path = self.output_dir / f"{stem}.md"
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        markdown_path.write_text(_search_markdown(payload), encoding="utf-8")
        return json_path, markdown_path

    def _write_detail_files(self, payload: dict[str, Any], html: str) -> tuple[Path, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stem = _file_stem("detail", payload["url"])
        json_path = self.output_dir / f"{stem}.json"
        html_path = self.output_dir / f"{stem}.html"
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        html_path.write_text(html or "", encoding="utf-8")
        return json_path, html_path


def _retry_delay_seconds(attempt: int) -> float:
    """计算指数退避延迟时间"""
    base = settings.qianlima_realtime_base_delay_seconds
    max_delay = settings.qianlima_realtime_max_delay_seconds
    exponential = base * (2 ** max(0, attempt - 1))
    jitter = random.uniform(0, 0.5)  # 添加随机抖动
    return min(max_delay, exponential) + jitter


def _default_output_dir() -> Path:
    base_dir = Path(settings.data_registry_dir)
    if not base_dir.is_absolute():
        base_dir = Path(__file__).resolve().parents[4] / base_dir
    return base_dir / "tenders" / "realtime"


def _build_search_query(
    query: str | None,
    keywords: Sequence[str] | str | None,
    keyword_operator: str,
) -> str:
    raw_query = (query or "").strip()
    if raw_query:
        return raw_query
    if isinstance(keywords, str):
        return keywords.strip()
    parts = [str(item).strip() for item in (keywords or []) if str(item).strip()]
    separator = "+" if (keyword_operator or "").strip().lower() == "plus" else " "
    return separator.join(parts)


def _date_range(start_date: str | None, end_date: str | None) -> list[date]:
    if not start_date and not end_date:
        return []
    start = _parse_date(start_date or end_date)
    end = _parse_date(end_date or start_date)
    if start > end:
        raise ValueError("start_date 不能晚于 end_date")
    max_days = 366
    days = (end - start).days + 1
    if days > max_days:
        raise ValueError(f"日期范围最多支持 {max_days} 天")
    return [start + timedelta(days=offset) for offset in range(days)]


def _parse_date(value: str | None) -> date:
    if not value:
        raise ValueError("日期不能为空")
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def _candidate_to_record(candidate: TenderCandidate) -> dict[str, Any]:
    return {
        "title": candidate.title,
        "url": candidate.url,
        "publish_date": candidate.publish_date.isoformat()
        if candidate.publish_date
        else None,
        "notice_type": candidate.notice_type.value,
        "keyword": candidate.keyword,
        "source": candidate.source,
        "raw_list_text": candidate.raw_list_text,
        "metadata": candidate.metadata,
    }


def _dedupe(candidates: Sequence[TenderCandidate]) -> list[TenderCandidate]:
    seen: set[str] = set()
    unique: list[TenderCandidate] = []
    for candidate in candidates:
        key = candidate.normalized_url_key()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _search_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 千里马实时检索结果",
        "",
        f"- 查询词：{payload['query']}",
        f"- 结果数：{payload['count']}",
        f"- 生成时间：{payload['generated_at']}",
        "",
    ]
    for index, item in enumerate(payload["results"], start=1):
        publish_date = item.get("publish_date") or "未知日期"
        lines.append(f"{index}. [{item['title']}]({item['url']})")
        lines.append(f"   - 发布日期：{publish_date}")
        if item.get("raw_list_text"):
            lines.append(f"   - 摘要：{item['raw_list_text']}")
    return "\n".join(lines) + "\n"


def _html_to_text(html: str) -> str:
    value = re.sub(r"<script[\s\S]*?</script>", " ", html or "", flags=re.I)
    value = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _file_stem(prefix: str, value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff_.-]+", "_", value).strip("._")
    safe = safe[:60] or "qianlima"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"{prefix}_{timestamp}_{safe}"


async def _close_client(client: Any) -> None:
    close = getattr(client, "close", None)
    if close is None:
        return
    result = close()
    if hasattr(result, "__await__"):
        await result
