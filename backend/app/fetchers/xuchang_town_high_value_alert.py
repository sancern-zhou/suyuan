"""每小时 21 分检测乡镇审核小时值，生成截图后直接写微信群推送队列。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable

import structlog

from app.db.repositories.weather_repo import WeatherRepository
from app.fetchers.base.fetcher_interface import DataFetcher
from app.scenarios.xuchang_station_deviation.wechat_push_queue import enqueue_wechat_message

from app.scenarios.xuchang_town_high_value import screenshot
from app.scenarios.xuchang_town_high_value.config import HighValueConfig
from app.scenarios.xuchang_town_high_value.detector import detect_high_value_groups
from app.scenarios.xuchang_town_high_value.message import render_message
from app.scenarios.xuchang_town_high_value.repository import TownHourRepository
from app.scenarios.xuchang_town_high_value.state import AlertStateStore
from app.scenarios.xuchang_town_high_value.weather import load_weather_evidence

logger = structlog.get_logger()


class XuchangTownHighValueAlertFetcher(DataFetcher):
    def __init__(
        self,
        *,
        repository: Any | None = None,
        weather_repository: Any | None = None,
        state: AlertStateStore | None = None,
        capture: Callable[..., str] | None = None,
        message_renderer: Callable[..., Any] = render_message,
        enqueue: Callable[..., Any] = enqueue_wechat_message,
        config: HighValueConfig | None = None,
        now_factory: Callable[[], datetime] = datetime.now,
    ) -> None:
        super().__init__(
            name="xuchang_town_high_value_alert_fetcher",
            description="乡镇站PM2.5/PM10小时空间高值提醒，极端离群按设备异常过滤",
            # 乡镇小时数据 :11 入库、大屏 :16 物化小时地图，告警 :21 截图。
            schedule="21 * * * *",
            version="1.0.0",
        )
        self.repository = repository or TownHourRepository()
        self.weather_repository = weather_repository or WeatherRepository()
        self.state = state or AlertStateStore()
        self.capture = capture or screenshot.capture_township_hour_map
        self.message_renderer = message_renderer
        self.enqueue = enqueue
        self.config = config or HighValueConfig.from_env()
        self.now_factory = now_factory

    async def fetch_and_store(self) -> dict[str, Any]:
        now = self.now_factory()
        try:
            rows = await self.repository.latest_rows(now=now)
        except Exception as exc:
            logger.warning("town_high_value_query_failed", error=str(exc))
            return {"status": "no_data", "error": str(exc), "sent": 0}
        hour, groups = detect_high_value_groups(rows, config=self.config)
        if hour is None:
            return {"status": "no_data", "sent": 0}
        # 只处理刚入库的完整小时；补跑旧数据/迟到任务不重复翻旧账。
        if now - timedelta(hours=self.config.latest_hour_max_age_hours) > hour:
            return {"status": "stale", "hour": hour.isoformat(), "sent": 0}
        # 同小时重跑保持原幂等语义；跨小时同站同因子走 24/6 小时冷却。
        groups = [
            group for group in groups
            if not self.state.already_sent(group["group_id"])
            or any(item["equipment_suspected"] for item in group["alerts"])
            or bool(group["stations"]) and self.state.in_cooldown(
                "high_value::" + ",".join(sorted(item["station_id"] for item in group["stations"]))
                + f"::{group['pollutant']}", now, hours=self.config.high_value_cooldown_hours,
            )
        ]
        weather_loaded = False
        weather: dict[str, Any] = {}
        sent = 0
        equipment_sent = 0
        failed_groups = 0
        cooled_down = 0
        processed = False
        for group in groups:
            processed = True
            equipment_items = []
            equipment_cooled = False
            for item in group["alerts"]:
                if not item["equipment_suspected"]:
                    continue
                cooldown_key = f"equipment::{item['station_id']}::{group['pollutant']}"
                if self.state.in_cooldown(
                    cooldown_key, now, hours=self.config.equipment_cooldown_hours
                ):
                    equipment_cooled = True
                    continue
                equipment_items.append((item, cooldown_key))
            stations = group["stations"]
            high_value_key = "high_value::" + ",".join(sorted(
                item["station_id"] for item in stations
            )) + f"::{group['pollutant']}"
            high_value_cooled = bool(stations) and self.state.in_cooldown(
                high_value_key, now, hours=self.config.high_value_cooldown_hours
            )
            cooled_down += int(equipment_cooled) + int(high_value_cooled)
            if not equipment_items and (not stations or group["out_of_scope"] or high_value_cooled):
                if equipment_cooled or high_value_cooled:
                    self.state.record(group["group_id"], "cooldown_skipped", {
                        "equipment": equipment_cooled, "high_value": high_value_cooled,
                    })
                elif group["out_of_scope"] and stations:
                    self.state.record(group["group_id"], "regional_pollution_skipped", {
                        "station_count": len(stations),
                        "station_ids": [item["station_id"] for item in stations],
                    })
                continue
            try:
                # 同因子设备异常与普通高值共用对应小时地图；截图失败不推送。
                media = await asyncio.to_thread(self.capture, hour, [group], rows)
                if not media:
                    raise RuntimeError("empty screenshot path")
            except Exception as exc:
                failed_groups += 1
                self.state.record(group["group_id"], "screenshot_failed", {"error": str(exc)})
                logger.warning("town_high_value_screenshot_failed", pollutant=group["pollutant"], error=str(exc))
                continue
            for item, cooldown_key in equipment_items:
                equipment_id = f"{group['group_id']}-equipment-{item['station_id']}"
                if self.state.already_sent(equipment_id):
                    continue
                county = item.get("county_name")
                if not county:
                    self.state.record(equipment_id, "missing_county", {
                        "station_id": item["station_id"], "station_name": item["station_name"],
                    })
                    logger.warning("town_high_value_equipment_county_missing", station=item["station_name"])
                    continue
                message = (
                    f"【乡镇高值提醒】{item['station_name']}站点{group['pollutant']}浓度显示异常，"
                    f"请{county}核实数据异常原因，并及时反馈。"
                )
                record = self.enqueue(
                    "town_high_value", message, media=[media],
                    metadata={"group_id": equipment_id, "hour": hour.isoformat(),
                              "pollutant": group["pollutant"], "station_ids": item["station_id"],
                              "alert_kind": "equipment_anomaly"},
                )
                self.state.record(equipment_id, "sent", {
                    "station_ids": [item["station_id"]], "reason": item["equipment_reason"],
                    "message_id": (record or {}).get("id"),
                })
                self.state.mark_cooldown(cooldown_key, now, {
                    "station_id": item["station_id"], "pollutant": group["pollutant"],
                })
                equipment_sent += 1
            stations = group["stations"]
            if not stations:
                continue
            if self.state.already_sent(group["group_id"]):
                continue
            if group["out_of_scope"] or high_value_cooled:
                if not high_value_cooled:
                    self.state.record(group["group_id"], "regional_pollution_skipped", {
                        "station_count": len(stations),
                        "station_ids": [item["station_id"] for item in stations],
                    })
                continue
            if not weather_loaded:
                weather = await load_weather_evidence(
                    self.weather_repository, hour,
                    lookback_hours=self.config.weather_lookback_hours,
                )
                weather_loaded = True
            deliveries = [stations]
            for selected in deliveries:
                message = await self.message_renderer({**group, "stations": selected}, weather)
                record = self.enqueue(
                    "town_high_value",
                    message,
                    media=[media],
                    metadata={
                        "group_id": group["group_id"],
                        "hour": hour.isoformat(),
                        "pollutant": group["pollutant"],
                        "station_ids": ",".join(item["station_id"] for item in selected),
                    },
                )
                self.state.record(group["group_id"], "sent", {
                    "station_ids": [item["station_id"] for item in selected],
                    "message_id": (record or {}).get("id"),
                })
                self.state.mark_cooldown(high_value_key, now, {
                    "station_ids": [item["station_id"] for item in selected],
                    "pollutant": group["pollutant"],
                })
                sent += 1
        if not processed:
            return {"status": "no_alert_or_duplicate", "hour": hour.isoformat(), "sent": 0, "equipment_sent": 0, "cooled_down": 0}
        return {
            "status": "completed", "hour": hour.isoformat(), "sent": sent,
            "equipment_sent": equipment_sent, "failed_groups": failed_groups,
            "cooled_down": cooled_down,
        }
