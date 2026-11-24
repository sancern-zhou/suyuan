"""用独立浏览器截取大屏乡镇小时地图，禁止复用 Agent 活动标签页。"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from config.settings import settings
from app.utils.path_config import format_agent_path, get_data_registry


def _hour_key(value: Any) -> str:
    return str(value or "").replace("T", " ")[:16]


def capture_township_hour_map(
    hour: datetime,
    groups: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> str:
    """截取指定因子最新小时地图；数据时刻不匹配时失败而不是发旧图。"""
    if not groups:
        raise ValueError("missing alert group")
    pollutant = str(groups[0]["pollutant"])
    metric = {"PM2.5": "pm25", "PM10": "pm10"}.get(pollutant)
    if not metric:
        raise ValueError("unsupported pollutant")
    from playwright.sync_api import sync_playwright

    base = os.getenv(
        "TOWN_HIGH_VALUE_DASHBOARD_URL", "http://127.0.0.1:5174/suyuan/bigscreen"
    )
    query = {
        "capture": "1", "township_granularity": "hour",
        "layers": "townships", "metric": metric,
    }
    token = getattr(settings, "dashboard_access_token", "")
    if token:
        query["access_token"] = token
    url = f"{base}{'&' if '?' in base else '?'}{urlencode(query)}"
    output = (
        get_data_registry() / "xuchang_town_high_value" / "maps"
        / f"{hour:%Y%m%d%H}-{metric}.png"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            context = browser.new_context(
                viewport={"width": 1600, "height": 1000}, device_scale_factor=1
            )
            page = context.new_page()
            page.set_default_timeout(90_000)
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_function(
                "() => window.__XUCHANG_BIGSCREEN_CAPTURE__?.ready === true",
                timeout=90_000,
            )
            state = page.evaluate("() => window.__XUCHANG_BIGSCREEN_CAPTURE__")
            if state.get("page") != "bigscreen" or state.get("townshipGranularity") != "hour":
                raise RuntimeError("dashboard capture state mismatch")
            if state.get("metric") != metric or state.get("layers") != ["townships"]:
                raise RuntimeError("dashboard capture layer mismatch")
            if not state.get("townshipCount"):
                raise RuntimeError("township hour map is empty")
            if _hour_key(state.get("townshipDataTime")) != _hour_key(hour):
                raise RuntimeError("township hour map data time mismatch")
            page.add_style_tag(content="*{animation:none!important;transition:none!important}")
            page.wait_for_timeout(1500)
            page.locator('[data-testid="bigscreen-capture-root"]').screenshot(
                path=str(output), animations="disabled"
            )
            context.close()
        finally:
            browser.close()
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("dashboard screenshot is empty")
    return format_agent_path(output)
