"""④污染原因分析触发抓取器（日度，微信群+APP 推送链路的判定源）。

业务规则（2026-11 定版）：昨日许昌市 PM2.5 日均浓度高于相邻五市（郑州、
开封、平顶山、漯河、周口）均值 20% 以上时，触发污染原因分析通报推送
（微信群【污染原因分析】+ APP 广播科长/局长）。

数据口径：河南实时发布平台采集的 SsfbCityDay（18 城含济源，PM2.5 为
发布口径日值）；昨日日值尚未入库时回退 SsfbCityHour 逐小时算术平均
（与场景2回顾的补齐口径一致），并在证据包标注 data_source。

幂等：每个评估日只落一个 trigger-evidence.json；文件已存在直接跳过，
调度重试不会重复发事件。无论是否触发都落证据（含未触发的对比结果），
供回看与连续触发天数计算。
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.scenarios.xuchang_pollution_cause.constants import (
    EVIDENCE_SCHEMA_VERSION,
    EVENT_TYPE,
    NEIGHBOR_CITIES,
    STREAK_LOOKBACK_DAYS,
    TRIGGER_RATIO_THRESHOLD,
    XUCHANG_CITY,
)
from app.scheduled_tasks.models import TaskEvent
from app.utils.path_config import format_agent_path, get_data_registry

logger = structlog.get_logger()

TZ = datetime.now().astimezone().tzinfo


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _run_sync(coro: Any) -> Any:
    """在异步 fetcher 中执行一次同步风格的 async 调用（采集在执行线程内完成）。"""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


def load_city_daily_rows(target_date: date) -> tuple[list[dict[str, Any]], str]:
    """18 市 PM2.5 日均：SsfbCityDay 优先，缺数回退 SsfbCityHour 小时平均。"""
    from app.scenarios.xuchang_push_common.crawler_mysql import query_crawler_mysql

    day_start = datetime.combine(target_date, time.min)
    day_end = day_start + timedelta(days=1)

    async def _run():
        rows = await query_crawler_mysql(
            """
            SELECT City, PM25
            FROM SsfbCityDay
            WHERE DataTime >= %s AND DataTime < %s AND PM25 IS NOT NULL
            """,
            (day_start, day_end),
        )
        if rows:
            return rows, "ssfb_city_day"
        derived = await query_crawler_mysql(
            """
            SELECT City, AVG(PM25) AS PM25
            FROM SsfbCityHour
            WHERE DataTime >= %s AND DataTime < %s AND PM25 IS NOT NULL
            GROUP BY City
            """,
            (day_start, day_end),
        )
        return derived, "ssfb_city_hour_derived"

    rows, source = _run_sync(_run())
    return (
        [
            {"city": str(row.get("City") or "").strip(), "pm25": _number(row.get("PM25"))}
            for row in rows
        ],
        source,
    )


def _city_matches(name: str, canonical: str) -> bool:
    return name == canonical or name.rstrip("市") == canonical.rstrip("市")


def read_streak_days(evidence_dir: Path, target_date: date) -> int:
    """回看昨日往前的连续触发天数（不含当日；缺文件/未触发即停）。"""
    streak = 0
    for offset in range(1, STREAK_LOOKBACK_DAYS + 1):
        day = target_date - timedelta(days=offset)
        path = evidence_dir / f"{day:%Y%m%d}" / "trigger-evidence.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            break
        if not isinstance(record, dict) or not record.get("triggered"):
            break
        streak += 1
    return streak


def evaluate_trigger(
    target_date: date,
    rows: list[dict[str, Any]],
    *,
    threshold: float = TRIGGER_RATIO_THRESHOLD,
    streak_days: int | None = None,
    data_source: str = "ssfb_city_day",
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    """纯函数：按相邻五市规则评估，输出触发证据包（触发与否都返回）。"""
    by_city: dict[str, float] = {}
    for row in rows:
        city = str(row.get("city") or "").strip()
        value = _number(row.get("pm25"))
        if city and value is not None and city not in by_city:
            by_city[city] = value

    xuchang = next(
        (value for city, value in by_city.items() if _city_matches(city, XUCHANG_CITY)),
        None,
    )
    neighbor_values = [
        value
        for canonical in NEIGHBOR_CITIES
        for city, value in by_city.items()
        if _city_matches(city, canonical)
    ]
    neighbor_mean = (
        round(sum(neighbor_values) / len(neighbor_values), 1)
        if neighbor_values
        else None
    )

    deviation_ratio = None
    triggered = False
    if xuchang is not None and neighbor_mean:
        deviation_ratio = round((xuchang - neighbor_mean) / neighbor_mean, 3)
        triggered = deviation_ratio >= threshold

    ranked = sorted(by_city.items(), key=lambda item: item[1], reverse=True)
    city_rank = next(
        (index + 1 for index, (city, _) in enumerate(ranked) if _city_matches(city, XUCHANG_CITY)),
        None,
    )
    city_rows = [
        {
            "city": city,
            "pm25": value,
            "is_xuchang": _city_matches(city, XUCHANG_CITY),
            "is_neighbor": any(_city_matches(city, canonical) for canonical in NEIGHBOR_CITIES),
        }
        for city, value in ranked
    ]
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "city": XUCHANG_CITY,
        "target_date": target_date.isoformat(),
        "rule": "pm25_daily_above_neighbor_mean",
        "rule_description": "许昌市PM2.5日均浓度高于相邻五市均值20%以上",
        "ratio_threshold": threshold,
        "neighbor_cities": list(NEIGHBOR_CITIES),
        "xuchang_pm25": xuchang,
        "neighbor_mean_pm25": neighbor_mean,
        "neighbor_valid_city_count": len(neighbor_values),
        "deviation_ratio": deviation_ratio,
        "deviation_percent": round(deviation_ratio * 100, 1) if deviation_ratio is not None else None,
        "triggered": triggered,
        "streak_days": (streak_days or 0) + (1 if triggered else 0),
        "city_rank": city_rank,
        "city_count": len(city_rows),
        "city_rows": city_rows,
        "data_source": data_source,
        "evaluated_at": (evaluated_at or datetime.now()).isoformat(timespec="seconds"),
    }


class XuchangPollutionCauseTriggerFetcher(DataFetcher):
    def __init__(self, now_factory=None) -> None:
        super().__init__(
            name="xuchang_pollution_cause_trigger_fetcher",
            description="许昌市PM2.5日均高于相邻五市均值20%时触发污染原因分析推送（微信群+APP）",
            schedule="30 7 * * *",
            version="1.0.0",
        )
        self.now_factory = now_factory or (lambda: datetime.now(TZ))

    def _evidence_dir(self, target_date: date) -> Path:
        return get_data_registry() / "xuchang_pollution_cause" / f"{target_date:%Y%m%d}"

    def _load_previous_streak(self, target_date: date) -> int:
        return read_streak_days(self._evidence_dir(target_date).parent, target_date)

    async def fetch_and_store(self) -> dict[str, Any]:
        now = self.now_factory()
        target_date = (now - timedelta(days=1)).date()
        evidence_dir = self._evidence_dir(target_date)
        evidence_path = evidence_dir / "trigger-evidence.json"
        if evidence_path.exists():
            return {
                "status": "already_evaluated",
                "target_date": target_date.isoformat(),
                "evidence_path": str(evidence_path),
            }

        rows, data_source = load_city_daily_rows(target_date)
        if not rows:
            logger.warning(
                "xuchang_pollution_cause_no_city_rows",
                target_date=target_date.isoformat(),
            )
            return {
                "status": "no_data",
                "target_date": target_date.isoformat(),
                "data_source": data_source,
            }

        evidence = evaluate_trigger(
            target_date,
            rows,
            streak_days=self._load_previous_streak(target_date),
            data_source=data_source,
            evaluated_at=now,
        )
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        published = False
        if evidence["triggered"]:
            published = await self._publish_event(evidence, evidence_path)

        return {
            "status": "triggered" if evidence["triggered"] else "below_threshold",
            "target_date": target_date.isoformat(),
            "xuchang_pm25": evidence["xuchang_pm25"],
            "neighbor_mean_pm25": evidence["neighbor_mean_pm25"],
            "deviation_percent": evidence["deviation_percent"],
            "streak_days": evidence["streak_days"],
            "city_rank": evidence["city_rank"],
            "event_published": published,
            "evidence_path": str(evidence_path),
        }

    async def _publish_event(self, evidence: dict[str, Any], evidence_path: Path) -> bool:
        """触发日发布唯一事件（event_id 含日期，天然幂等）。"""
        from app.scheduled_tasks import get_scheduled_task_service

        target_date = evidence.get("target_date") or ""
        payload = {**evidence, "evidence_package_path": format_agent_path(evidence_path)}
        event = TaskEvent(
            event_id=f"xuchang-pollution-cause-{target_date.replace('-', '') or 'unknown'}",
            event_type=EVENT_TYPE,
            attributes={
                "city": XUCHANG_CITY,
                "target_date": target_date,
                "triggered": True,
                "deviation_percent": evidence.get("deviation_percent"),
            },
            payload=payload,
        )
        try:
            task_service = get_scheduled_task_service()
            await task_service.publish_event(event)
            logger.info(
                "xuchang_pollution_cause_event_published",
                target_date=target_date,
                deviation_percent=evidence.get("deviation_percent"),
            )
            return True
        except Exception:
            logger.error("xuchang_pollution_cause_event_publish_failed", exc_info=True)
            return False
