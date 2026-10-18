"""Use APScheduler triggers; coalesce missed periodic slots, retain one-shot work."""

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger


def definition_hash(task) -> str:
    # nanobot binding_revision excludes runtime state; here only editable goal scope counts.
    return sha256(
        json.dumps([task.goal, task.completion_criteria], ensure_ascii=False).encode()
    ).hexdigest()


def normalize_schedule(
    kind, *, run_at=None, interval_minutes=None, cron=None, timezone_name="Asia/Shanghai", now=None
):
    now = now or datetime.utcnow()
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
        raise ValueError("请提供有效的 IANA 时区") from exc
    config = {"timezone": timezone_name}
    if kind == "now":
        return config, now
    if kind == "once":
        value = datetime.fromisoformat(run_at) if isinstance(run_at, str) else run_at
        if not isinstance(value, datetime):
            raise ValueError("单次提醒需要 run_at")
        value = value.replace(tzinfo=zone) if value.tzinfo is None else value
        at = value.astimezone(UTC).replace(tzinfo=None)
        if at < now - timedelta(seconds=60):
            raise ValueError("不能创建已过期的单次计划")
        return {**config, "run_at": at.isoformat()}, max(now, at)
    if kind == "interval":
        if type(interval_minutes) is not int or not 1 <= interval_minutes <= 525600:
            raise ValueError("间隔须为 1-525600 分钟")
        config["interval_minutes"] = interval_minutes
    elif kind == "cron":
        if not isinstance(cron, str) or len(cron.split()) != 5:
            raise ValueError("cron 须为五段表达式")
        config["cron"] = cron
    else:
        raise ValueError("不支持的触发方式")
    return config, next_occurrence(kind, config, now)


def next_occurrence(kind, config, now):
    if kind in {"now", "once"}:
        return None
    if kind == "interval":
        return now + timedelta(minutes=config["interval_minutes"])
    value = CronTrigger.from_crontab(
        config["cron"], timezone=config["timezone"]
    ).get_next_fire_time(
        None,
        (now + timedelta(microseconds=1)).replace(tzinfo=UTC),
    )
    if value is None:
        raise ValueError("计划没有下一次运行时间")
    return value.astimezone(UTC).replace(tzinfo=None)
