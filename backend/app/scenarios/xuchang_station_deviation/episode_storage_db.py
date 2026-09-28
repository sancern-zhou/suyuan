"""Database persistence for Scenario-1 episode summaries."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any


def episode_db_enabled() -> bool:
    configured = os.getenv("XUCHANG_STATION_EPISODE_STORAGE")
    return bool(configured and configured.strip().lower() == "database")


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def _row_values(episode: dict[str, Any]) -> dict[str, Any]:
    return {
        "city": str(episode.get("city") or "许昌市"),
        "station_id": str(episode.get("station_id") or ""),
        "station_name": episode.get("station_name"),
        "target_pollutant": str(episode.get("target_pollutant") or "").upper(),
        "alert_type": episode.get("alert_type"),
        "measurement_granularity": episode.get("measurement_granularity"),
        "status": str(episode.get("status") or "unknown"),
        "started_at": _datetime(episode.get("started_at")),
        "last_seen_at": _datetime(episode.get("last_seen_at")) or _datetime(episode.get("started_at")),
        "closed_at": _datetime(episode.get("closed_at")),
        "closed_reason": episode.get("closed_reason"),
        "event_ids": list(episode.get("event_ids") or []),
        "hour_count": episode.get("hour_count"),
        "notification_count": episode.get("notification_count"),
        "peak_station_value": episode.get("peak_station_value"),
        "peak_deviation_ratio": episode.get("peak_deviation_ratio"),
        "updated_at": datetime.now(),
    }


def upsert_episode(episode: dict[str, Any]) -> None:
    if not episode_db_enabled() or not episode.get("episode_id"):
        return
    from app.db.sync_bridge import run_db

    async def _write():
        from app.db.models.xuchang_station_alert_episode_db import XuchangStationAlertEpisodeDB
        from app.db.sync_bridge import bridge_session

        async with bridge_session() as session:
            row = await session.get(XuchangStationAlertEpisodeDB, str(episode["episode_id"]))
            if row is None:
                row = XuchangStationAlertEpisodeDB(episode_id=str(episode["episode_id"]))
                session.add(row)
            for key, value in _row_values(episode).items():
                setattr(row, key, value)
            await session.commit()

    try:
        run_db(_write())
    except Exception:
        # The JSON state remains the operational fallback during DB outages.
        return


def query_episodes(target_date) -> list[dict[str, Any]] | None:
    if not episode_db_enabled():
        return None
    from app.db.sync_bridge import run_db

    async def _read():
        from sqlalchemy import select
        from app.db.models.xuchang_station_alert_episode_db import XuchangStationAlertEpisodeDB
        from app.db.sync_bridge import bridge_session

        day_start = datetime.combine(target_date, datetime.min.time())
        day_end = day_start.replace(hour=23)
        async with bridge_session() as session:
            stmt = select(XuchangStationAlertEpisodeDB).where(
                XuchangStationAlertEpisodeDB.started_at <= day_end,
                XuchangStationAlertEpisodeDB.last_seen_at >= day_start,
            ).order_by(XuchangStationAlertEpisodeDB.started_at, XuchangStationAlertEpisodeDB.station_id)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
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
                for row in rows
            ]

    try:
        return run_db(_read())
    except Exception:
        return None
