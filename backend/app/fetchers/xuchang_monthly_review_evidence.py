"""①月度特征分析证据抓取器（每月 2 日，事件驱动 APP 通报推送）。

采集上月（自然月）五个分析维度并冻结证据包：
A. 城市浓度与地市对比：官方 ProvinceMonthReport（city/month，含 YoY）优先，
   未发布时回退 SsfbCityDay 日值自算（实时参考口径）；
B. 去年同期：官方 YoY 列 + 去年同期官方月报绝对值（2025-12 起才覆盖）；
C. 排名变化：省内排名（浓度排序）+ Rank168CityMonthly 官方 168 城排名；
D. 气象因素：NMC 逐时观测与 ERA5 边界层的月度描述性统计（去年同期缺数据
   则如实说明）；
E. 站点告警频率分布：xuchang_station_alert_episodes（DB 优先，episode_state
   JSON 兜底）按站点/污染物/规则/日期分布 + 企业静态清单背景。

产出 `<registry>/xuchang_monthly_reviews/{YYYYMM}/evidence.json` 并发布
``xuchang.monthly_review.completed`` 事件；文件已存在即跳过（幂等）。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import structlog

from app.fetchers.base.fetcher_interface import DataFetcher
from app.scenarios.xuchang_monthly_review.constants import (
    EVIDENCE_SCHEMA_VERSION,
    EVENT_TYPE,
)
from app.scenarios.xuchang_monthly_review.evidence import (
    aggregate_city_month,
    aggregate_weather_month,
    build_rank168_section,
    month_bounds,
    normalize_province_month_rows,
    previous_month,
    same_month_last_year,
    summarize_inventory,
    summarize_month_episodes,
)
from app.scenarios.xuchang_push_common.crawler_mysql import query_crawler_mysql
from app.scheduled_tasks.models import TaskEvent
from app.utils.path_config import format_agent_path, get_data_registry

logger = structlog.get_logger()

TZ = datetime.now().astimezone().tzinfo


def _run_sync(coro: Any) -> Any:
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


class XuchangMonthlyReviewEvidenceFetcher(DataFetcher):
    def __init__(self, now_factory=None) -> None:
        super().__init__(
            name="xuchang_monthly_review_evidence_fetcher",
            description="每月2日生成上月城市月度特征分析证据包并触发APP通报（局长/科长）",
            schedule="40 6 2 * *",
            version="1.0.0",
        )
        self.now_factory = now_factory or (lambda: datetime.now(TZ))

    # ---------- 数据采集 ----------

    def load_ssfb_city_month(self, start: date, end: date) -> list[dict[str, Any]]:
        """SsfbCityDay 月内日值（18城六参数），实时参考口径的自算输入。"""
        rows = _run_sync(
            query_crawler_mysql(
                """
                SELECT City, PM25, PM10, SO2, NO2, CO, O3
                FROM SsfbCityDay
                WHERE DataTime >= %s AND DataTime < %s
                """,
                (
                    datetime(start.year, start.month, start.day),
                    datetime(end.year, end.month, end.day),
                ),
            )
        )
        return [
            {
                "city": str(row.get("City") or "").strip(),
                "pm25": row.get("PM25"),
                "pm10": row.get("PM10"),
                "so2": row.get("SO2"),
                "no2": row.get("NO2"),
                "co": row.get("CO"),
                "o3": row.get("O3"),
            }
            for row in rows
        ]

    def load_province_month_report(self, data_month: str) -> list[dict[str, Any]]:
        """官方省月报 city/month 行（data_month 形如 2026-10，上界为次月 1 日）。"""
        year, month = int(data_month[:4]), int(data_month[5:7])
        if month == 12:
            upper = f"{year + 1:04d}-01-01"
        else:
            upper = f"{year:04d}-{month + 1:02d}-01"
        rows = _run_sync(
            query_crawler_mysql(
                """
                SELECT Level, City, RegionName, Scope, DataMonth,
                       PM10, PM10_YoY, PM25, PM25_YoY, O3, O3_YoY,
                       SO2, NO2, CO, CompositeIndex, CompositeIndex_YoY,
                       GoodDays, HeavyDays
                FROM ProvinceMonthReport
                WHERE Level = 'city' AND Scope = 'month'
                  AND DataMonth >= %s AND DataMonth < %s
                """,
                (f"{data_month}-01", upper),
            )
        )
        return rows

    def load_rank168(self) -> list[dict[str, Any]]:
        return _run_sync(
            query_crawler_mysql(
                """
                SELECT City, PeriodType, DataMonth, PeriodLabel,
                       CompositeIndex, CompositeIndexRank, Pm25, Pm25Rank
                FROM Rank168CityMonthly
                WHERE PeriodType = 'monthly'
                ORDER BY DataMonth DESC
                LIMIT 400
                """
            )
        )

    def load_weather_month(self, start: date, end: date) -> dict[str, Any]:
        """NMC 许昌站逐时观测 + ERA5 边界层的月度原始行（供描述性统计）。"""
        from app.db.repositories.weather_repo import WeatherRepository
        from app.fetchers.xuchang_station_daily_exceedance import (
            XUCHANG_ERA5_GRID_POINT,
            XUCHANG_NMC_STATION_ID,
        )

        async def _run():
            repository = WeatherRepository()
            observed_rows: list[dict[str, Any]] = []
            era5_rows: list[dict[str, Any]] = []
            errors: list[str] = []
            try:
                items = await repository.get_observed_data(
                    XUCHANG_NMC_STATION_ID,
                    datetime(start.year, start.month, start.day),
                    datetime(end.year, end.month, end.day),
                )
                for item in items:
                    observed_rows.append({
                        "temperature_2m": getattr(item, "temperature_2m", None),
                        "relative_humidity_2m": getattr(item, "relative_humidity_2m", None),
                        "wind_speed_10m_ms": getattr(item, "wind_speed_10m", None),
                        "precipitation": getattr(item, "precipitation", None),
                    })
            except Exception as exc:
                errors.append(f"observed:{type(exc).__name__}")
            try:
                items = await repository.get_weather_data(
                    XUCHANG_ERA5_GRID_POINT[0],
                    XUCHANG_ERA5_GRID_POINT[1],
                    datetime(start.year, start.month, start.day),
                    datetime(end.year, end.month, end.day),
                )
                for item in items:
                    era5_rows.append({
                        "boundary_layer_height": getattr(item, "boundary_layer_height", None),
                    })
            except Exception as exc:
                errors.append(f"era5:{type(exc).__name__}")
            return observed_rows, era5_rows, errors

        observed_rows, era5_rows, errors = _run_sync(_run())
        return {"observed": observed_rows, "era5": era5_rows, "errors": errors}

    def load_month_episodes(self, start: date, end: date) -> list[dict[str, Any]]:
        """月内站点告警 episode：DB 表优先，episode_state.json 兜底。"""
        from app.scenarios.xuchang_push_common.episodes import load_episodes_between

        return load_episodes_between(start, end)

    def load_inventory_dataset(self) -> list[dict[str, Any]]:
        """企业排放源静态清单（背景参考）。"""
        path = (
            get_data_registry()
            / "datasets"
            / "pollution_source_asset_v1_xuchang_emission_inventory_enterprises.json"
        )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return []
        if isinstance(payload, dict):
            records = payload.get("records") or payload.get("data") or []
        elif isinstance(payload, list):
            records = payload
        else:
            records = []
        return [row for row in records if isinstance(row, dict)]

    # ---------- 主流程 ----------

    async def fetch_and_store(self) -> dict[str, Any]:
        now = self.now_factory()
        year, month = previous_month(now.date())
        month_label = f"{year:04d}-{month:02d}"
        evidence_dir = get_data_registry() / "xuchang_monthly_reviews" / f"{year:04d}{month:02d}"
        evidence_path = evidence_dir / "evidence.json"
        if evidence_path.exists():
            return {
                "status": "already_generated",
                "month": month_label,
                "evidence_path": str(evidence_path),
            }

        start, end = month_bounds(year, month)
        ly_year, ly_month = same_month_last_year(year, month)

        # A/B 城市对比与同比
        official = normalize_province_month_rows(
            self.load_province_month_report(month_label), month_label
        )
        official_last_year = normalize_province_month_rows(
            self.load_province_month_report(f"{ly_year:04d}-{ly_month:02d}"),
            f"{ly_year:04d}-{ly_month:02d}",
        )
        try:
            ssfb_rows = self.load_ssfb_city_month(start, end)
        except Exception as exc:
            logger.warning("xuchang_monthly_review_ssfb_load_failed", error=str(exc)[:200])
            ssfb_rows = []
        realtime_rows = aggregate_city_month(ssfb_rows)
        realtime_xuchang = next(
            (item for item in realtime_rows if "许昌" in item["city"]),
            None,
        )

        # C 排名
        try:
            rank168 = build_rank168_section(self.load_rank168(), month_label)
        except Exception as exc:
            logger.warning("xuchang_monthly_review_rank168_failed", error=str(exc)[:200])
            rank168 = {"status": "unavailable"}

        # D 气象（当月 + 去年同期）
        try:
            weather_payload = self.load_weather_month(start, end)
            weather = aggregate_weather_month(weather_payload["observed"], weather_payload["era5"])
        except Exception as exc:
            logger.warning("xuchang_monthly_review_weather_failed", error=str(exc)[:200])
            weather = {"status": "unavailable"}
        try:
            weather_payload = self.load_weather_month(
                date(ly_year, ly_month, 1),
                month_bounds(ly_year, ly_month)[1],
            )
            weather_last_year = aggregate_weather_month(
                weather_payload["observed"], weather_payload["era5"]
            )
        except Exception:
            weather_last_year = {"status": "unavailable"}

        # E 站点告警 + 企业背景
        try:
            episodes_summary = summarize_month_episodes(self.load_month_episodes(start, end))
        except Exception as exc:
            logger.warning("xuchang_monthly_review_episodes_failed", error=str(exc)[:200])
            episodes_summary = {"episode_count": 0, "status": "unavailable"}
        try:
            inventory_summary = summarize_inventory(self.load_inventory_dataset())
        except Exception:
            inventory_summary = {"status": "unavailable"}

        evidence = {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "month": month_label,
            "generated_at": now.isoformat(timespec="seconds"),
            "city_comparison": {
                "official": official,
                "official_last_year": official_last_year,
                "realtime": {
                    "caliber": "ssfb_day_arithmetic_mean",
                    "note": "SsfbCityDay 日值算术平均（实时参考口径，非官方审核月报）",
                    "city_count": len(realtime_rows),
                    "xuchang": realtime_xuchang,
                    "rows": realtime_rows[:20],
                },
            },
            "rank168": rank168,
            "meteorology": weather,
            "meteorology_last_year": weather_last_year,
            "station_alerts": episodes_summary,
            "enterprise_context": inventory_summary,
            "limits": [
                "官方月报未发布期次的城市对比为实时参考口径，发布后以官方为准",
                "168城排名为生态环境部逐月定版，未发布期次不引用",
                "气象为描述性统计，不自动形成污染成因判断",
                "企业章节为年度静态清单背景，不代表当月实际排放，不认定当月责任",
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
            "month": month_label,
            "official_available": official.get("status"),
            "episode_count": episodes_summary.get("episode_count"),
            "event_published": published,
            "evidence_path": str(evidence_path),
        }

    async def _publish_event(self, evidence: dict[str, Any], evidence_path: Path) -> bool:
        from app.scheduled_tasks import get_scheduled_task_service

        event = TaskEvent(
            event_id=f"xuchang-monthly-review-{str(evidence.get('month') or 'unknown').replace('-', '')}",
            event_type=EVENT_TYPE,
            attributes={"city": "许昌市", "month": evidence.get("month")},
            payload={**evidence, "evidence_package_path": format_agent_path(evidence_path)},
        )
        try:
            task_service = get_scheduled_task_service()
            await task_service.publish_event(event)
            logger.info("xuchang_monthly_review_event_published", month=evidence.get("month"))
            return True
        except Exception:
            logger.error("xuchang_monthly_review_event_publish_failed", exc_info=True)
            return False

