"""SQLAlchemy model for Scenario-1 (station deviation) alert episodes.

One row per alert episode aggregated by
app.scenarios.xuchang_station_deviation.episode_storage_db; list-shaped
fields are stored as JSON documents.
"""
from sqlalchemy import Column, DateTime, Float, Index, Integer, JSON, String

from app.db.database import Base


class XuchangStationAlertEpisodeDB(Base):
    __tablename__ = "xuchang_station_alert_episodes"

    episode_id = Column(String(255), primary_key=True)
    city = Column(String(120), nullable=False, server_default="许昌市")
    station_id = Column(String(120), nullable=False, index=True)
    station_name = Column(String(255), nullable=True)

    target_pollutant = Column(String(32), nullable=False)
    alert_type = Column(String(64), nullable=True)
    measurement_granularity = Column(String(32), nullable=True)
    status = Column(String(32), nullable=False, server_default="unknown")

    started_at = Column(DateTime, nullable=True, index=True)
    last_seen_at = Column(DateTime, nullable=True, index=True)
    closed_at = Column(DateTime, nullable=True)
    closed_reason = Column(String(120), nullable=True)

    event_ids = Column(JSON, nullable=False, default=list)
    hour_count = Column(Integer, nullable=True)
    notification_count = Column(Integer, nullable=True)
    peak_station_value = Column(Float, nullable=True)
    peak_deviation_ratio = Column(Float, nullable=True)

    updated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index(
            "ix_xuchang_alert_episodes_started_station",
            "started_at",
            "station_id",
        ),
    )
