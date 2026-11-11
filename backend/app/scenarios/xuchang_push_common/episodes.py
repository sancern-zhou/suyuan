"""站点告警 episode 的跨场景读取辅助（DB 优先，episode_state.json 兜底）。

供月度特征分析（①）与企业核查线索周报（②）统计站点告警频率分布使用。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import structlog

from app.utils.path_config import get_data_registry

logger = structlog.get_logger()

EPISODE_STATE_RELATIVE_PATH = "xuchang_station_deviation_alerts/episode_state.json"


def load_episodes_between(start: date, end: date) -> list[dict[str, Any]]:
    """[start, end) 期间开始（或活跃）的 episode 列表；DB 不可用回退 JSON。"""
    db_rows = _query_episodes_db(start, end)
    if db_rows is not None:
        return db_rows
    return _episodes_from_state_file(start, end)


def _row_payload(row: Any) -> dict[str, Any]:
    return {
        "episode_id": row.episode_id,
        "city": row.city,
        "station_id": row.station_id,
        "station_name": row.station_name,
        "target_pollutant": row.target_pollutant,
        "alert_type": row.alert_type,
        "measurement_granularity": row.measurement_granularity,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "closed_reason": row.closed_reason,
        "event_ids": row.event_ids or [],
        "hour_count": row.hour_count,
        "notification_count": row.notification_count,
        "peak_station_value": row.peak_station_value,
        "peak_deviation_ratio": row.peak_deviation_ratio,
    }


def _query_episodes_db(start: date, end: date) -> list[dict[str, Any]] | None:
    from app.db.sync_bridge import run_db

    async def _read():
        from sqlalchemy import select

        from app.db.models.xuchang_station_alert_episode_db import (
            XuchangStationAlertEpisodeDB,
        )
        from app.db.sync_bridge import bridge_session

        dt_start = datetime(start.year, start.month, start.day)
        dt_end = datetime(end.year, end.month, end.day)
        async with bridge_session() as session:
            stmt = select(XuchangStationAlertEpisodeDB).where(
                XuchangStationAlertEpisodeDB.started_at >= dt_start,
                XuchangStationAlertEpisodeDB.started_at < dt_end,
            ).order_by(XuchangStationAlertEpisodeDB.started_at)
            rows = (await session.execute(stmt)).scalars().all()
            return [_row_payload(row) for row in rows]

    try:
        return run_db(_read())
    except Exception:
        return None


def _episodes_from_state_file(start: date, end: date) -> list[dict[str, Any]]:
    state_path = get_data_registry() / EPISODE_STATE_RELATIVE_PATH
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    episodes: list[dict[str, Any]] = []
    for bucket in ("history", "active"):
        for episode in (state.get(bucket) or []):
            if not isinstance(episode, dict):
                continue
            started = str(episode.get("started_at") or "")
            try:
                started_date = datetime.fromisoformat(started).date()
            except (TypeError, ValueError):
                continue
            if start <= started_date < end:
                episodes.append(episode)
    return episodes
