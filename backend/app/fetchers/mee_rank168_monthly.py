"""抓取生态环境部 168 重点城市月度排名（官网附表长图 + 多模态识别入库）。

数据源：https://www.mee.gov.cn/hjzl/dqhj/qgkqzlzk/ 「全国空气质量状况」栏目，
每月 21~31 日发布《生态环境部公布<year>年<month>月[和1—N月]全国环境空气质量
状况》新闻稿。正文末尾"附表"是一张长条 JPG（约 1100×7000，168 行），无任何
xls/pdf 电子附件（2026-05~09 各期实测均如此），因此唯一自动化路径是下载该
图后用多模态大模型识别。

附表列结构（2026 年各期一致）：
  序号 | 城市 | 当月综合指数 | 当月PM2.5 | 1-N月综合指数 | 1-N月PM2.5
按当月综合指数降序排列（序号即排名，1=最差）。PM2.5 排名表不发布，按同口径
降序推导（并列取相同名次，与既有人工导入 1-7 月表的处理一致）。

流程：列表页发现新一期 → 下载正文定位附表图 → 多模态识别为 JSON 行 →
强校验（168 城名单/序号连续/数值范围）→ 幂等 upsert DataCrawler.Rank168CityMonthly
（UK: City+PeriodType+DataMonth，month/cum 双口径）。

- 多模态：复用乡镇/中大抓取器同款视觉候选链（CAPTCHA_VISION_CANDIDATES：
  SCNET Qwen3.8-Flash → SCNET GLM-5.3-Flash → GLM glm-4.6v，OpenAI 兼容
  chat/completions），某候选未配置/报错/输出非法自动切下一个；长图按行
  切片分段识别降低出错率。
- 校验不过整期放弃入库并抛错（宁缺勿错，下轮定时重试），不部分写入。
- 调度：每月 22/25/28 日 09:23（发布约 21 日起，三次容错重试；与 ssfb 三波
  :14-:24/:55-:59、transport :26-:50、乡镇 :11 等错峰；月频任务数据库仅在
  末尾短连接写入）。
- 历史回补：2026-08/09/10 期由本抓取器首轮自动补抓（列表页仍保留链接），
  2026-01~07 为人工导入（源 06_rank168_monthly.xlsx），不被覆盖——同 UK
  upsert 仅在识别成功时同值重写。
"""

from __future__ import annotations

import asyncio
import base64
import calendar
import io
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import aiomysql
import httpx
import structlog
from PIL import Image

from app.fetchers.base.fetcher_interface import DataFetcher
from app.integrations.xuchang.town_cloud_client import (
    CAPTCHA_VISION_CANDIDATES,
    _vision_endpoint,
)
from config.settings import settings

logger = structlog.get_logger()

LIST_URL = "https://www.mee.gov.cn/hjzl/dqhj/qgkqzlzk/"
TABLE = "Rank168CityMonthly"
EXPECTED_ROWS = 168
# 仅抓取该年份起的附表新版式（6 列：序号/城市/当月CI/当月PM2.5/累计CI/累计PM2.5）。
# 2025 年及更早各期附表版式不同（列结构/行数不一致），不在自动抓取范围。
MIN_YEAR = 2026
# 每期识别切片数（长图 168 行，每片约 28 行；切片过多调用慢、过少单图行数多易错）
SLICE_COUNT = 6

_TITLE_RE = re.compile(
    r"生态环境部公布(?P<year>20\d{2})年(?P<month>\d{1,2})月"
    r"(?:和1[—–-](?P<cum>\d{1,2})月)?全国环境空气质量状况"
)
_IMAGE_SRC_RE = re.compile(r"""src=["'](?:\./)?(?P<src>W020[^"']+\.(?:jpg|png))["']""", re.I)


@dataclass(frozen=True)
class Article:
    year: int
    month: int
    has_cum: bool
    url: str

    @property
    def data_month(self) -> date:
        return date(self.year, self.month, 1)


def parse_list_articles(html: str) -> list[Article]:
    """从栏目列表页 HTML 提取发布文章（仅 168 城排名相关新闻稿）。"""
    articles: list[Article] = []
    for match in re.finditer(r"href=[\"'](?P<href>[^\"']+\.shtml)[\"'][^>]*>(?P<title>[^<]+)<", html):
        title = match.group("title").strip()
        m = _TITLE_RE.search(title)
        if not m:
            continue
        href = match.group("href")
        url = httpx.URL(LIST_URL).join(href)
        articles.append(Article(
            year=int(m.group("year")),
            month=int(m.group("month")),
            has_cum=m.group("cum") is not None,
            url=str(url),
        ))
    return articles


def pick_attachment_image(article_html: str, article_url: str) -> str:
    """正文最后一张 W020 图即附表（图1/2/3 为统计图，附表图在最末）。"""
    candidates = _IMAGE_SRC_RE.findall(article_html)
    if not candidates:
        raise ValueError(f"正文未找到附表图: {article_url}")
    return str(httpx.URL(article_url).join(candidates[-1]))


def slice_image(image_bytes: bytes, count: int = SLICE_COUNT) -> list[bytes]:
    """把附表长图纵向切成若干段（JPEG bytes），各段带少量重叠防切断行。"""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    width, height = image.size
    overlap = 40
    slices: list[bytes] = []
    step = height // count
    for idx in range(count):
        top = max(0, idx * step - (overlap if idx else 0))
        bottom = min(height, (idx + 1) * step + (overlap if idx < count - 1 else 0))
        buf = io.BytesIO()
        image.crop((0, top, width, bottom)).save(buf, format="JPEG", quality=95)
        slices.append(buf.getvalue())
    return slices


def build_prompt(article: Article, slice_index: int, slice_count: int) -> str:
    return (
        f"这是生态环境部{article.year}年{article.month}月168个重点城市环境空气质量"
        f"综合指数、PM2.5浓度状况附表长图的第{slice_index + 1}/{slice_count}段。"
        "表格列为：序号 | 城市 | 当月综合指数 | 当月PM2.5浓度 | 1-N月综合指数 | 1-N月PM2.5浓度。"
        "请逐行识别本段内所有数据行（表头/标题不要输出），输出严格JSON数组，"
        "每个元素形如 {\"seq\": 序号整数, \"city\": \"城市名(含市字)\", "
        "\"month_ci\": 当月综合指数数值, \"month_pm25\": 当月PM2.5数值, "
        "\"cum_ci\": 1-N月综合指数数值, \"cum_pm25\": 1-N月PM2.5数值}。"
        "数值按图中原样输出（综合指数两位小数、PM2.5一位小数），不要换算、不要推测。"
        "只输出JSON数组，不要任何其他文字。若某格无法辨认，对应字段填null。"
    )


def parse_vision_rows(text: str) -> list[dict[str, Any]]:
    """从模型输出提取 JSON 数组（容忍 ```json 代码块）。"""
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(?P<body>\[.*?\])\s*```", cleaned, re.S)
    if fenced:
        cleaned = fenced.group("body")
    else:
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start >= 0 and end > start:
            cleaned = cleaned[start:end + 1]
    data = json.loads(cleaned)
    if not isinstance(data, list):
        raise ValueError("视觉识别结果不是 JSON 数组")
    return [row for row in data if isinstance(row, dict)]


def merge_slices(slice_rows: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """按 seq 去重合并各段（重叠区可能重复识别同一行）。"""
    merged: dict[int, dict[str, Any]] = {}
    for rows in slice_rows:
        for row in rows:
            seq = row.get("seq")
            if isinstance(seq, int):
                merged[seq] = row
    return [merged[seq] for seq in sorted(merged)]


def validate_rows(rows: list[dict[str, Any]]) -> None:
    """整期强校验：168 行、序号 1-168 连续、城市名合法、数值范围合理。"""
    if len(rows) != EXPECTED_ROWS:
        raise ValueError(f"识别行数 {len(rows)} != {EXPECTED_ROWS}")
    seqs = [row.get("seq") for row in rows]
    if seqs != list(range(1, EXPECTED_ROWS + 1)):
        raise ValueError("序号不是 1-168 连续")
    cities = [str(row.get("city") or "").strip() for row in rows]
    if any(not c or len(c) > 12 for c in cities):
        raise ValueError("存在缺失/异常城市名")
    if len(set(cities)) != EXPECTED_ROWS:
        raise ValueError("城市名有重复")
    for row in rows:
        for key, low, high in (
            ("month_ci", 1.0, 12.0), ("cum_ci", 1.0, 12.0),
            ("month_pm25", 1.0, 500.0), ("cum_pm25", 1.0, 300.0),
        ):
            value = row.get(key)
            if not isinstance(value, (int, float)) or not (low <= float(value) <= high):
                raise ValueError(f"{row.get('city')} 的 {key}={value!r} 超出合理范围")


def _rank_desc(values: list[float]) -> list[int]:
    """降序排名，并列同名次跳号（1=最差，与表内序号口径一致）。"""
    ranks: list[int] = []
    for value in values:
        ranks.append(1 + sum(1 for other in values if other > value))
    return ranks


def build_db_rows(article: Article, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    month = article.month
    last_day = calendar.monthrange(article.year, month)[1]
    month_pm25 = [float(row["month_pm25"]) for row in rows]
    cum_pm25 = [float(row["cum_pm25"]) for row in rows]
    month_pm25_ranks = _rank_desc(month_pm25)
    cum_pm25_ranks = _rank_desc(cum_pm25)
    # 附表按当月综合指数降序，序号即当月排名；累计综合指数排名未发布，同口径推导
    cum_ci_ranks = _rank_desc([float(row["cum_ci"]) for row in rows])
    source = f"mee.gov.cn:{article.url}"
    db_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        city = str(row["city"]).strip()
        for period_type, ci, ci_rank, pm25, pm25_rank in (
            ("month", row["month_ci"], idx + 1, month_pm25[idx], month_pm25_ranks[idx]),
            ("cum", row["cum_ci"], cum_ci_ranks[idx], cum_pm25[idx], cum_pm25_ranks[idx]),
        ):
            db_rows.append({
                "City": city,
                "PeriodType": period_type,
                "DataMonth": article.data_month,
                "PeriodEnd": date(article.year, month, last_day) if period_type == "cum" else None,
                "PeriodLabel": f"{month}月" if period_type == "month" else f"1-{month}月",
                "CompositeIndex": float(ci),
                "CompositeIndexRankDesc": ci_rank,
                "Pm25": pm25,
                "Pm25RankDesc": pm25_rank,
                "SourceFile": source,
            })
    return db_rows


UPSERT_SQL = f"""
INSERT INTO {TABLE} (
    City, PeriodType, DataMonth, PeriodEnd, PeriodLabel,
    CompositeIndex, CompositeIndexRankDesc, Pm25, Pm25RankDesc, SourceFile
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    PeriodEnd = VALUES(PeriodEnd),
    PeriodLabel = VALUES(PeriodLabel),
    CompositeIndex = VALUES(CompositeIndex),
    CompositeIndexRankDesc = VALUES(CompositeIndexRankDesc),
    Pm25 = VALUES(Pm25),
    Pm25RankDesc = VALUES(Pm25RankDesc),
    SourceFile = VALUES(SourceFile)
"""


class Rank168MySqlStorage:
    def __init__(self, url: str | None = None) -> None:
        self._url = url or settings.crawler_mysql_url

    def _connection_kwargs(self) -> dict[str, Any]:
        from urllib.parse import urlparse
        parsed = urlparse(self._url)
        return {
            "host": parsed.hostname,
            "port": parsed.port or 3306,
            "user": parsed.username,
            "password": parsed.password,
            "db": parsed.path.lstrip("/"),
            "charset": "utf8mb4",
        }

    async def existing_months(self) -> set[str]:
        conn = await aiomysql.connect(**self._connection_kwargs())
        try:
            async with conn.cursor() as cur:
                await cur.execute(f"SELECT DISTINCT DataMonth FROM {TABLE}")
                return {str(row[0])[:7] for row in await cur.fetchall()}
        finally:
            conn.close()

    async def save(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        cols = ["City", "PeriodType", "DataMonth", "PeriodEnd", "PeriodLabel",
                "CompositeIndex", "CompositeIndexRankDesc", "Pm25", "Pm25RankDesc", "SourceFile"]
        values = [tuple(row[c] for c in cols) for row in rows]
        conn = await aiomysql.connect(**self._connection_kwargs())
        try:
            async with conn.cursor() as cur:
                for start in range(0, len(values), 200):
                    await cur.executemany(UPSERT_SQL, values[start:start + 200])
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        finally:
            conn.close()
        return len(values)


async def call_vision(*, image_url: str, prompt: str, timeout: float = 180.0,
                      max_tokens: int = 8192) -> str:
    """按视觉候选链识别图片（OpenAI 兼容 chat/completions），返回文本。

    候选未配置、网络/协议失败、空输出自动切下一个；全部失败抛错。
    """
    image_b64 = image_url.split(",", 1)[1] if "," in image_url else image_url
    errors: list[str] = []
    for provider, model in CAPTCHA_VISION_CANDIDATES:
        endpoint = _vision_endpoint(provider)
        if endpoint is None:
            continue
        base_url, api_key = endpoint
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "image_url",
                                 "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                                {"type": "text", "text": prompt},
                            ],
                        }],
                        "max_tokens": max_tokens,
                        "temperature": 0,
                        "thinking": {"type": "disabled"},
                    },
                )
            resp.raise_for_status()
            choice = (resp.json().get("choices") or [{}])[0]
            text = (choice.get("message") or {}).get("content") or ""
            if text.strip():
                return text.strip()
            errors.append(f"{model}: 空输出")
        except Exception as exc:  # noqa: BLE001 - 候选失败记录后切下一个
            errors.append(f"{model}: {exc}")
            logger.warning("mee_rank168_vision_candidate_failed", model=model,
                           error=str(exc)[:300])
    raise RuntimeError(f"视觉候选链全部失败: {'; '.join(errors)}")


class MeeRank168MonthlyFetcher(DataFetcher):
    def __init__(
        self,
        *,
        archive_dir: Path | None = None,
        storage: Rank168MySqlStorage | None = None,
        vision_func: Any = None,
    ) -> None:
        super().__init__(
            name="mee_rank168_monthly_fetcher",
            description="生态环境部168重点城市月度排名（官网附表长图多模态识别入库 Rank168CityMonthly）",
            schedule="23 9 22,25,28 * *",
            version="1.0.0",
        )
        self.archive_dir = archive_dir or (Path(settings.data_registry_dir) / "mee_rank168")
        self.storage = storage or Rank168MySqlStorage()
        self._vision = vision_func or call_vision

    async def _fetch_bytes(self, client: httpx.AsyncClient, url: str) -> bytes:
        resp = await client.get(url, timeout=60)
        resp.raise_for_status()
        return resp.content

    async def _recognize_article(self, article: Article, image_bytes: bytes) -> list[dict[str, Any]]:
        slices = await asyncio.to_thread(slice_image, image_bytes)
        results: list[list[dict[str, Any]]] = []
        for idx, chunk in enumerate(slices):
            b64 = base64.b64encode(chunk).decode()
            last_error: Exception | None = None
            for attempt in range(1, 4):
                try:
                    text = await self._vision(
                        image_url=f"data:image/jpeg;base64,{b64}",
                        prompt=build_prompt(article, idx, len(slices)),
                        timeout=300.0,
                        max_tokens=8192,
                    )
                    parsed = parse_vision_rows(text)
                    if not parsed:
                        raise ValueError("视觉识别结果为空数组")
                    results.append(parsed)
                    logger.info("mee_rank168_slice_recognized", month=str(article.data_month),
                                slice=idx + 1, attempt=attempt, rows=len(parsed))
                    break
                except (ValueError, json.JSONDecodeError) as exc:
                    last_error = exc
                    logger.warning("mee_rank168_slice_recognition_retry",
                                   month=str(article.data_month), slice=idx + 1,
                                   attempt=attempt, error=str(exc)[:300])
            else:
                raise ValueError(f"第 {idx + 1} 段连续 3 次识别失败: {last_error}")
        merged = merge_slices(results)
        validate_rows(merged)
        return merged

    async def fetch_and_store(self) -> dict[str, Any]:
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        existing = await self.storage.existing_months()
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (compatible; suyuan-mee-rank168/1.0)"},
            follow_redirects=True,
        ) as client:
            list_html = (await self._fetch_bytes(client, LIST_URL)).decode("utf-8", "ignore")
            articles = [a for a in parse_list_articles(list_html) if a.year >= MIN_YEAR]
            pending = [a for a in articles if str(a.data_month)[:7] not in existing]
            logger.info("mee_rank168_scan", articles=len(articles), pending=len(pending))
            processed: list[str] = []
            failed: dict[str, str] = {}
            for article in sorted(pending, key=lambda a: a.data_month):
                try:
                    article_html = (await self._fetch_bytes(client, article.url)).decode("utf-8", "ignore")
                    image_url = pick_attachment_image(article_html, article.url)
                    image_bytes = await self._fetch_bytes(client, image_url)
                    (self.archive_dir / f"{article.data_month:%Y-%m}.jpg").write_bytes(image_bytes)
                    rows = await self._recognize_article(article, image_bytes)
                    db_rows = build_db_rows(article, rows)
                    saved = await self.storage.save(db_rows)
                    processed.append(str(article.data_month)[:7])
                    logger.info("mee_rank168_saved", month=str(article.data_month),
                                cities=len(rows), rows=saved)
                except Exception as exc:  # noqa: BLE001 - 单期失败不阻断其他期，下轮重试
                    failed[str(article.data_month)[:7]] = str(exc)[:300]
                    logger.error("mee_rank168_article_failed", month=str(article.data_month),
                                 error=str(exc)[:300])
            if failed and not processed:
                raise RuntimeError(f"全部待抓取期失败: {failed}")
            return {"pending": len(pending), "processed": processed, "failed": failed}
