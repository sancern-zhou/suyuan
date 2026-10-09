"""许昌国控站周边路况定时抓取（cron */6 一次性执行，flock 防重叠）。

设计依据：projects/xuchang/国控站周边路况定时抓取实施方案.md
- 每轮 6 站串行、请求间隔 3 秒；slot_at 对齐 6 分钟栅格（UTC），
  UNIQUE(station_code, slot_at) 幂等，重跑不产生重复行；
- Redis 共享配额计数器：轮前预检查（剩余 < 站数+2 跳过本轮），每次调用前 INCR，越硬顶即止；
- 道路级查询在配置的早晚高峰时点触发（北京时间 HH:MM 命中当前时隙即查），
  结果以 station_code='road:路名' 落快照表，拥堵明细照常入 traffic_section；
- 网络类失败（network_error，含超时/5xx）30 秒后重试一次；业务错误码不重试，记 ERROR；
- 不做跨时隙补采：错过的时隙即永久缺失；
- 连续 3 轮全站失败记 ERROR（journalctl 侧可接告警）。
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import structlog  # noqa: E402
from sqlalchemy import text  # noqa: E402
from app.utils.path_config import resolve_agent_path  # noqa: E402

logger = structlog.get_logger()

STATIONS_CONFIG = "projects/xuchang/traffic_stations.json"
SLICE_SECONDS = 360  # 6 分钟时隙
REQUEST_INTERVAL = 3  # 秒/请求，6 站约 18 秒/轮，峰值 0.33 QPS
RETRY_DELAY_SECONDS = 30
FAIL_STREAK_KEY = "baidu_traffic:collect:fail_streak"
FAIL_STREAK_ALERT = 3
CST = timezone(timedelta(hours=8))  # 北京时间，道路级高峰时点按它判断


def current_slot(now: datetime | None = None) -> datetime:
    """对齐到 6 分钟栅格的时隙起点（UTC）。"""
    ts = int((now or datetime.now(timezone.utc)).timestamp()) // SLICE_SECONDS * SLICE_SECONDS
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _slot_hhmm(slot_at: datetime) -> str:
    return slot_at.astimezone(CST).strftime("%H:%M")


def _section_rows(payload: dict, fallback_road_name: str | None) -> list[dict]:
    """把响应归一化成 traffic_section 行。

    周边查询：明细在 road_traffic[].congestion_sections；
    道路查询：明细直接在 congestion_sections，road_name 用查询的路名兜底。
    """
    rows: list[dict] = []
    roads = payload.get("road_traffic") or []
    for road in roads:
        for sec in road.get("congestion_sections") or []:
            rows.append(
                {
                    "road_name": road.get("road_name"),
                    "section_desc": sec.get("section_desc"),
                    "status": sec.get("status"),
                    "speed_km_h": sec.get("speed"),
                    "congestion_distance_m": sec.get("congestion_distance"),
                    "congestion_trend": sec.get("congestion_trend"),
                }
            )
    if not roads:
        for sec in payload.get("congestion_sections") or []:
            rows.append(
                {
                    "road_name": fallback_road_name,
                    "section_desc": sec.get("section_desc"),
                    "status": sec.get("status"),
                    "speed_km_h": sec.get("speed"),
                    "congestion_distance_m": sec.get("congestion_distance"),
                    "congestion_trend": sec.get("congestion_trend"),
                }
            )
    return rows


async def _save_snapshot(
    conn,
    station_code: str,
    slot_at: datetime,
    payload: dict,
    fallback_road_name: str | None = None,
) -> None:
    """UPSERT 快照（冲突即幂等跳过）并写入拥堵路段明细。"""
    evaluation = payload.get("evaluation") or {}
    roads = payload.get("road_traffic") or []
    sections = _section_rows(payload, fallback_road_name)

    row = (
        await conn.execute(
            text(
                """
                INSERT INTO traffic_snapshot
                    (station_code, slot_at, evaluation_status, evaluation_desc,
                     description, road_count, congestion_section_count, raw)
                VALUES
                    (:station_code, :slot_at, :status, :status_desc,
                     :description, :road_count, :section_count, CAST(:raw AS jsonb))
                ON CONFLICT (station_code, slot_at) DO NOTHING
                RETURNING id
                """
            ),
            {
                "station_code": station_code,
                "slot_at": slot_at,
                "status": evaluation.get("status"),
                "status_desc": evaluation.get("status_desc"),
                "description": payload.get("description"),
                "road_count": len(roads),
                "section_count": len(sections),
                "raw": json.dumps(payload, ensure_ascii=False),
            },
        )
    ).first()

    if row is None:  # 同一时隙已有数据（幂等重跑），明细也跳过
        return
    snapshot_id = int(row[0])
    for sec in sections:
        await conn.execute(
            text(
                """
                INSERT INTO traffic_section
                    (snapshot_id, road_name, section_desc, status, speed_km_h,
                     congestion_distance_m, congestion_trend)
                VALUES (:snapshot_id, :road_name, :section_desc, :status, :speed_km_h,
                        :congestion_distance_m, :congestion_trend)
                """
            ),
            {"snapshot_id": snapshot_id, **sec},
        )


def _db_connect():
    from app.db.database import engine

    return engine.connect()


async def _collect_one(
    client,
    quota,
    station_code: str,
    lat: float,
    lng: float,
    slot_at: datetime,
) -> bool:
    """抓取单站；网络类失败重试一次。返回是否成功。"""
    from app.tools.xuchang.traffic_status.client import BaiduTrafficError

    for attempt in (0, 1):
        if await quota.quota_exceeded():
            return False
        try:
            payload = await client.query_around(latitude=lat, longitude=lng)
            async with _db_connect() as conn:
                async with conn.begin():
                    await _save_snapshot(conn, station_code, slot_at, payload)
            return True
        except BaiduTrafficError as exc:
            retryable = getattr(exc, "status", None) == "network_error"
            if retryable and attempt == 0:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                continue
            logger.error(
                "baidu_traffic_collect_failed",
                station_code=station_code,
                status=getattr(exc, "status", None),
                error=str(exc),
                final_attempt=attempt == 1,
            )
            return False
    return False


async def collect_round() -> None:
    from app.tools.xuchang.traffic_status import quota
    from app.tools.xuchang.traffic_status.client import BaiduTrafficClient

    config = json.loads(
        Path(resolve_agent_path(STATIONS_CONFIG)).read_text(encoding="utf-8")
    )
    stations = config.get("stations") or []
    if not stations:
        logger.error("baidu_traffic_collect_no_stations", config=STATIONS_CONFIG)
        return

    slot_at = current_slot()
    remaining = await quota.quota_remaining()
    if remaining is not None and remaining < len(stations) + 2:
        logger.warning(
            "baidu_traffic_quota_low_skip_round",
            remaining=remaining,
            slot_at=slot_at.isoformat(),
        )
        return

    client = BaiduTrafficClient()
    ok_count = 0
    for idx, st in enumerate(stations):
        if idx:
            await asyncio.sleep(REQUEST_INTERVAL)
        ok = await _collect_one(
            client, quota, st["code"], st["lat"], st["lng"], slot_at
        )
        ok_count += int(ok)

    logger.info(
        "baidu_traffic_round_done",
        slot_at=slot_at.isoformat(),
        ok=ok_count,
        total=len(stations),
        local_hhmm=_slot_hhmm(slot_at),
    )

    # 连续全站失败告警（Redis 不可用时跳过跟踪，不影响抓取）
    try:
        redis = quota._get_redis()
        if ok_count == 0:
            streak = int(await redis.incr(FAIL_STREAK_KEY))
            await redis.expire(FAIL_STREAK_KEY, 172800)
            if streak >= FAIL_STREAK_ALERT:
                logger.error(
                    "baidu_traffic_collect_all_fail_streak",
                    streak=streak,
                    hint="连续多轮全站失败，请检查进程/凭证/网络",
                )
        else:
            await redis.delete(FAIL_STREAK_KEY)
    except Exception:
        pass

    # 道路级补充：当前时隙命中配置的高峰时点才触发（北京时间）
    roads = config.get("roads") or []
    peak_slots = set(config.get("peak_road_slots_local") or [])
    if not (roads and _slot_hhmm(slot_at) in peak_slots):
        return
    for idx, road_name in enumerate(roads):
        if idx or ok_count:
            await asyncio.sleep(REQUEST_INTERVAL)
        if await quota.quota_exceeded():
            break
        try:
            payload = await client.query_road(road_name=road_name)
            async with _db_connect() as conn:
                async with conn.begin():
                    await _save_snapshot(
                        conn, f"road:{road_name}", slot_at, payload,
                        fallback_road_name=road_name,
                    )
            logger.info(
                "baidu_traffic_road_saved", road_name=road_name, slot_at=slot_at.isoformat()
            )
        except Exception as exc:
            logger.error("baidu_traffic_road_failed", road_name=road_name, error=str(exc))


async def async_main() -> None:
    # 独立进程：先加载 .env 再触达任何依赖环境变量的模块
    from dotenv import load_dotenv

    load_dotenv(resolve_agent_path("backend/.env"), override=False)
    try:
        await collect_round()
    finally:
        try:
            from app.db.database import engine
            from app.tools.xuchang.traffic_status import quota

            await quota._get_redis().aclose()
            await engine.dispose()
        except Exception:
            pass


if __name__ == "__main__":
    started = time.monotonic()
    asyncio.run(async_main())
    print(f"elapsed={time.monotonic() - started:.1f}s")
