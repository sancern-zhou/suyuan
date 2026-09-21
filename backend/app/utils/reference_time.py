"""Agent-facing reference time with optional demo freeze.

Set ``AGENT_TIME_FREEZE_DATE=YYYY-MM-DD`` to pin the reference time exposed
to agents (system prompts, relative-date reasoning) to one fixed real day,
e.g. for controlled demos. Only the date part is replaced: hour/minute/
second and timezone keep following the real clock, so TLS handshakes, token
expiry and database timestamps all stay on real wall-clock time.
"""

from __future__ import annotations

import os
from datetime import date, datetime

import structlog

logger = structlog.get_logger(__name__)

FREEZE_DATE_ENV = "AGENT_TIME_FREEZE_DATE"


def reference_freeze_date() -> date | None:
    """Return the pinned reference date, or None when unfrozen."""
    raw = (os.getenv(FREEZE_DATE_ENV) or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        logger.warning("agent_reference_time_invalid_freeze_date", value=raw, env=FREEZE_DATE_ENV)
        return None


def reference_now() -> datetime:
    """Real local time with the date pinned to the freeze day when configured."""
    now = datetime.now().astimezone()
    pinned = reference_freeze_date()
    if pinned is None:
        return now
    return datetime.combine(pinned, now.timetz())
