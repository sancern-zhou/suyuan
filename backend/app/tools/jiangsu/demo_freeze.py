"""演示冻结（demo freeze）开关：把江苏数据管道与默认查询窗口固定到某一天。

在江苏运维后端环境文件（如 ``backend/.env.jiangsu-ops``）中设置::

    JIANGSU_DEMO_FREEZE_DATE=2026-09-10

即可进入演示冻结模式：所有江苏 fetcher 暂停拉新，智能事件查询默认窗口固定为
该日全天，实时同步接口被拒绝，前端默认展示该日真实采集数据。留空或删除该
变量即恢复正常滚动模式。冻结日期必须晚于或等于数据实际采集日，才能看到数据。
"""

from __future__ import annotations

import os
from datetime import date, datetime, time

import structlog

logger = structlog.get_logger(__name__)

FREEZE_DATE_ENV = "JIANGSU_DEMO_FREEZE_DATE"


def demo_freeze_date() -> date | None:
    """Return the pinned demo date, or None when freezing is disabled."""
    raw = (os.getenv(FREEZE_DATE_ENV) or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        logger.warning("jiangsu_demo_freeze_invalid_date", value=raw, env=FREEZE_DATE_ENV)
        return None


def demo_freeze_active() -> bool:
    return demo_freeze_date() is not None


def demo_freeze_window() -> tuple[datetime, datetime]:
    """Local-time window covering the frozen day: 00:00:00 - 23:59:59.999999."""
    pinned = demo_freeze_date()
    if pinned is None:
        raise RuntimeError("jiangsu demo freeze is not active")
    start = datetime.combine(pinned, time.min).astimezone()
    end = datetime.combine(pinned, time(23, 59, 59, 999999)).astimezone()
    return start, end


def demo_freeze_skip_result(fetcher: str) -> dict[str, str]:
    return {"status": "skipped", "reason": "demo_freeze_active", "fetcher": fetcher}
