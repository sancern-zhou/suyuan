# -*- coding: utf-8 -*-
"""Output paths for monthly consultation data packages."""

from __future__ import annotations

from pathlib import Path


def get_monthly_consultation_dir(year: int, month: int) -> Path:
    """Return the unified monthly consultation package directory."""
    return Path(f"/tmp/A会商文件/{year}年{month:02d}月")
