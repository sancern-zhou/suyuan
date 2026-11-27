"""②企业核查线索周报证据抓取器（每周一，APP 推送，代理口径）。

背景（2026-11 定版）：系统暂无企业实时排放监测数据（CEMS/排口/工况/用电），
"企业连续超标3小时告警"缓建；本抓取器按既定代理口径出周度核查线索：
上周站点告警 episode × 上风向候选企业筛查（screen_inventory_candidates，
清单年排放量距离衰减得分，仅排序核查顺序）→ 线索清单/频率/空间分布/
与站点关系说明。边界声明：不认定企业贡献率或责任。

产出 `<registry>/xuchang_enterprise_clue_weekly/{YYYYMMDD}/evidence.json`
（YYYYMMDD=窗口结束日）并发布 ``xuchang.enterprise_clue_weekly.completed``。
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from app.db.repositories.weather_repo import WeatherRepository
from app.fetchers.base.fetcher_interface import DataFetcher
from app.fetchers.xuchang_station_daily_exceedance import XUCHANG_NMC_STATION_ID
from app.scenarios.xuchang_city_exceedance.candidate_screening import (
    screen_inventory_candidates,
)
from app.scenarios.xuchang_city_exceedance.station_catalog import NATIONAL_STATION_META
from app.scenarios.xuchang_push_common.episodes import load_episodes_between
from app.scheduled_tasks.models import TaskEvent
from app.utils.path_config import format_agent_path, get_data_registry

logger = structlog.get_logger()

TZ = datetime.now().astimezone().tzinfo

EVIDENCE_SCHEMA_VERSION = "xuchang_enterprise_clue_weekly/v1"
EVENT_TYPE = "xuchang.enterprise_clue_weekly.completed"


def _run_sync(coro: Any) -> Any:
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


def summarize_episodes(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """周内 episode 频率分布（按站点/因子/规则/日期）。"""
    by_station: dict[str, int] = defaultdict(int)
    by_pollutant: dict[str, int] = defaultdict(int)
    by_rule: dict[str, int] = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)
    for episode in episodes:
        by_station[str(episode.get("station_name") or episode.get("station_id") or "未知站点")] += 1
        by_pollutant[str(episode.get("target_pollutant") or "未知因子")] += 1
        by_rule[str(episode.get("alert_type") or episode.get("rule") or "未知规则")] += 1
        started = str(episode.get("started_at") or "")[:10]
        if started:
            by_day[started] += 1

    def _top(counter: dict[str, int], limit: int = 8) -> list[dict[str, Any]]:
        return [
            {"name": name, "count": count}
            for name, count in sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        ]

    return {
        "episode_count": len(episodes),
        "station_count": len(by_station),
        "by_station": _top(by_station),
        "by_pollutant": _top(by_pollutant),
        "by_rule": _top(by_rule),
        "by_day": [{"date": day, "count": count} for day, count in sorted(by_day.items())],
    }


def station_meta_for(episode: dict[str, Any]) -> dict[str, Any] | None:
    """episode → 站点坐标/规范名（NATIONAL_STATION_META 按 id 或名称匹配）。"""
    station_id = str(episode.get("station_id") or "").strip()
    station_name = str(episode.get("station_name") or "").strip()
    meta = NATIONAL_STATION_META.get(station_id)
    if meta:
        return {"station_id": station_id, **meta}
    for code, candidate in NATIONAL_STATION_META.items():
        if station_name and candidate.get("name") == station_name:
            return {"station_id": code, **candidate}
    return None


def screen_week_candidates(
    episodes: list[dict[str, Any]],
    meteorology_rows: list[dict[str, Any]],
    *,
    top_n: int = 8,
) -> dict[str, Any]:
    """按站点×因子对周内 episode 跑静态清单上风向筛查，聚合候选企业命中频次。

    筛查得分为清单年排放量距离衰减排序，仅作现场核查顺序参考，不代表
    同期实际排放、贡献率或企业责任（candidate_screening 的边界声明）。
    """
    from app.scenarios.xuchang_city_exceedance.candidate_screening import (
        ANNUAL_EMISSION_FIELD,
    )

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for episode in episodes:
        meta = station_meta_for(episode)
        if not meta:
            continue
        pollutant = str(episode.get("target_pollutant") or "").upper()
        if pollutant not in ANNUAL_EMISSION_FIELD:
            continue
        grouped[(meta["station_id"], pollutant)].append(episode)

    hit_counter: dict[str, dict[str, Any]] = {}
    station_reports: list[dict[str, Any]] = []
    screened_groups = 0
    for (station_id, pollutant), group in sorted(grouped.items()):
        meta = station_meta_for(group[0]) or {}
        trigger_hours = [
            str(item.get("started_at") or "")[:13] for item in group if item.get("started_at")
        ]
        if not trigger_hours:
            continue
        try:
            screening = screen_inventory_candidates(
                receptor_lat=float(meta.get("lat")),
                receptor_lon=float(meta.get("lon")),
                pollutant=pollutant,
                meteorology_rows=meteorology_rows,
                trigger_hours=trigger_hours,
                top_n=top_n,
            )
        except Exception as exc:
            logger.warning(
                "xuchang_enterprise_clue_screening_failed",
                station_id=station_id,
                pollutant=pollutant,
                error=str(exc)[:200],
            )
            continue
        screened_groups += 1
        station_reports.append({
            "station_id": station_id,
            "station_name": meta.get("name"),
            "pollutant": pollutant,
            "episode_count": len(group),
            "screening_status": screening.get("status"),
            "wind": screening.get("wind"),
            "top_candidates": (screening.get("enterprises") or [])[:top_n],
        })
        for candidate in screening.get("enterprises") or []:
            if not candidate.get("in_upwind_sector"):
                continue
            name = str(candidate.get("enterprise_name") or "").strip()
            if not name:
                continue
            # 命中频次按该组内的 episode 数计（筛查窗口覆盖这些触发时点）
            entry = hit_counter.setdefault(name, {
                "enterprise_name": name,
                "district": candidate.get("district"),
                "industry_category": candidate.get("industry_category"),
                "hit_count": 0,
                "stations": set(),
                "best_distance_km": candidate.get("distance_km"),
            })
            entry["hit_count"] += len(group)
            entry["stations"].add(str(meta.get("name") or station_id))
            distance = candidate.get("distance_km")
            if isinstance(distance, (int, float)) and (
                entry["best_distance_km"] is None or distance < entry["best_distance_km"]
            ):
                entry["best_distance_km"] = distance

    ranked_hits = sorted(
        (
            {
                "enterprise_name": entry["enterprise_name"],
                "district": entry["district"],
                "industry_category": entry["industry_category"],
                "hit_count": entry["hit_count"],
                "stations": sorted(entry["stations"]),
                "best_distance_km": entry["best_distance_km"],
            }
            for entry in hit_counter.values()
        ),
        key=lambda item: (-item["hit_count"], item["enterprise_name"]),
    )
    return {
        "status": "screened" if ranked_hits else ("no_hits" if screened_groups else "not_run"),
        "group_count": screened_groups,
        "station_reports": station_reports,
        "frequent_candidates": ranked_hits[:10],
        "district_distribution": _district_counts(ranked_hits),
        "interpretation_limit": (
            "候选企业为静态清单上风向筛查线索（清单年排放量距离衰减排序），"
            "仅代表现场核查顺序参考，不代表同期实际排放、贡献率或企业责任"
        ),
    }


def _district_counts(ranked_hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: dict[str, int] = defaultdict(int)
    for item in ranked_hits:
        district = str(item.get("district") or "").strip()
        if district:
            counter[district] += item.get("hit_count") or 0
    return [
        {"name": name, "count": count}
        for name, count in sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:8]
    ]


class XuchangEnterpriseClueWeeklyFetcher(DataFetcher):
    def __init__(self, now_factory=None) -> None:
        super().__init__(
            name="xuchang_enterprise_clue_weekly_fetcher",
            description="每周一汇总上周站点告警的上风向企业核查线索并触发APP周报（科长/区县/执法）",
            schedule="20 7 * * 1",
            version="1.0.0",
        )
        self.now_factory = now_factory or (lambda: datetime.now(TZ))

    def load_meteorology(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        from app.db.repositories.weather_repo import WeatherRepository

        async def _run():
            repository = WeatherRepository()
            rows: list[dict[str, Any]] = []
            try:
                items = await repository.get_observed_data(XUCHANG_NMC_STATION_ID, start, end)
                for item in items:
                    rows.append({
                        "time": item.time.isoformat() if getattr(item, "time", None) else "",
                        "wind_direction_10m": getattr(item, "wind_direction_10m", None),
                        "wind_speed_10m_ms": getattr(item, "wind_speed_10m", None),
                    })
            except Exception:
                return []
            return rows

        return _run_sync(_run())

    async def fetch_and_store(self) -> dict[str, Any]:
        now = self.now_factory()
        end_date = now.date()
        start_date = end_date - timedelta(days=7)
        window_key = f"{end_date:%Y%m%d}"
        evidence_dir = get_data_registry() / "xuchang_enterprise_clue_weekly" / window_key
        evidence_path = evidence_dir / "evidence.json"
        if evidence_path.exists():
            return {
                "status": "already_generated",
                "window": f"{start_date.isoformat()}~{end_date.isoformat()}",
                "evidence_path": str(evidence_path),
            }

        episodes = load_episodes_between(start_date, end_date)
        meteorology_rows = self.load_meteorology(
            datetime.combine(start_date, datetime.min.time()),
            datetime.combine(end_date, datetime.min.time()),
        )
        try:
            screening = screen_week_candidates(episodes, meteorology_rows)
        except Exception as exc:
            logger.warning("xuchang_enterprise_clue_screening_error", error=str(exc)[:200])
            screening = {"status": "not_run", "frequent_candidates": []}

        evidence = {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "window": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "generated_at": now.isoformat(timespec="seconds"),
            "episodes": summarize_episodes(episodes),
            "enterprise_screening": screening,
            "limits": [
                "企业实时排放监测数据尚未接入，本报告为站点告警×静态清单上风向筛查的代理口径",
                "候选企业得分为核查顺序参考，不认定贡献率或企业责任",
                "连续超标小时级告警待CEMS数据源接入后另行建设",
            ],
        }
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        published = await self._publish_event(evidence, evidence_path)
        return {
            "status": "generated",
            "window": f"{start_date.isoformat()}~{end_date.isoformat()}",
            "episode_count": evidence["episodes"].get("episode_count"),
            "candidate_count": len(screening.get("frequent_candidates") or []),
            "event_published": published,
            "evidence_path": str(evidence_path),
        }

    async def _publish_event(self, evidence: dict[str, Any], evidence_path: Path) -> bool:
        from app.scheduled_tasks import get_scheduled_task_service

        event = TaskEvent(
            event_id=f"xuchang-enterprise-clue-weekly-{self.now_factory():%Y%m%d}",
            event_type=EVENT_TYPE,
            attributes={"city": "许昌市"},
            payload={**evidence, "evidence_package_path": format_agent_path(evidence_path)},
        )
        try:
            task_service = get_scheduled_task_service()
            await task_service.publish_event(event)
            logger.info("xuchang_enterprise_clue_event_published")
            return True
        except Exception:
            logger.error("xuchang_enterprise_clue_event_publish_failed", exc_info=True)
            return False
