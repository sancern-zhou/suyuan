"""Audit window calculation for operations work order review."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_ANCHOR_WEEKDAY = 0  # Monday=0：自然周锚点，周一运行审核上上周完整周
DEFAULT_FINISH_START_OFFSET_DAYS = 14
DEFAULT_FINISH_END_OFFSET_DAYS = 7


@dataclass(frozen=True)
class AuditWindow:
    preset: str
    anchor_time: str
    create_time_start: str
    create_time_end: str
    order_statuses: list[str]
    timezone: str
    finish_time_start: str = ""
    finish_time_end: str = ""

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
    finish_start_offset_days: int | None = None,
    finish_end_offset_days: int | None = None,
) -> AuditWindow:
    """Return the default weekly review window based on work order creation time.

    anchor_weekday=Monday（默认）且 offsets=14/7 时，窗口为"上上周完整自然周"：
    周一 2026-10-26 运行 → 创建与完成窗口均为 [2026-10-12 00:00, 2026-10-19 00:00)。

    finish offsets 传入时同时给出完成时间窗口（"创建并完成"口径）；
    传 None 保持旧行为（仅创建时间窗口，不约束完成时间）。
    """

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
    finish_start = (
        anchor_time - timedelta(days=finish_start_offset_days)
        if finish_start_offset_days is not None
        else None
    )
    finish_end = (
        anchor_time - timedelta(days=finish_end_offset_days)
        if finish_end_offset_days is not None
        else None
    )
    return AuditWindow(
        preset="weekly_created",
        anchor_time=anchor_time.strftime("%Y-%m-%d %H:%M:%S"),
        create_time_start=start.strftime("%Y-%m-%d %H:%M:%S"),
        create_time_end=end.strftime("%Y-%m-%d %H:%M:%S"),
        order_statuses=order_statuses or ["Finish"],
        timezone=timezone,
        finish_time_start=finish_start.strftime("%Y-%m-%d %H:%M:%S") if finish_start else "",
        finish_time_end=finish_end.strftime("%Y-%m-%d %H:%M:%S") if finish_end else "",
    )
