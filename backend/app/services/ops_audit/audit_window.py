"""Audit window calculation for operations work order review."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_ANCHOR_WEEKDAY = 2  # Monday=0, Wednesday=2


@dataclass(frozen=True)
class AuditWindow:
    preset: str
    anchor_time: str
    create_time_start: str
    create_time_end: str
    order_statuses: list[str]
    timezone: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def calculate_weekly_created_window(
    *,
    now: datetime | None = None,
    timezone: str = DEFAULT_TIMEZONE,
    anchor_weekday: int = DEFAULT_ANCHOR_WEEKDAY,
    created_start_offset_days: int = 14,
    created_end_offset_days: int = 7,
    order_statuses: list[str] | None = None,
) -> AuditWindow:
    """Return the default weekly review window based on work order creation time."""

    tz = ZoneInfo(timezone)
    if now is None:
        local_now = datetime.now(tz)
    elif now.tzinfo:
        local_now = now.astimezone(tz)
    else:
        local_now = now.replace(tzinfo=tz)

    days_since_anchor = (local_now.weekday() - anchor_weekday) % 7
    anchor_date = (local_now - timedelta(days=days_since_anchor)).date()
    anchor_time = datetime.combine(anchor_date, datetime.min.time(), tzinfo=tz)
    start = anchor_time - timedelta(days=created_start_offset_days)
    end = anchor_time - timedelta(days=created_end_offset_days)
    return AuditWindow(
        preset="weekly_created",
        anchor_time=anchor_time.strftime("%Y-%m-%d %H:%M:%S"),
        create_time_start=start.strftime("%Y-%m-%d %H:%M:%S"),
        create_time_end=end.strftime("%Y-%m-%d %H:%M:%S"),
        order_statuses=order_statuses or ["Finish"],
        timezone=timezone,
    )
