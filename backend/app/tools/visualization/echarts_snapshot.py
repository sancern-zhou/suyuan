"""Create a durable document-ready rendition from a JSON ECharts option."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import cairosvg

from app.utils.path_config import PROJECT_ROOT, get_chart_images_dir


SCRIPT = Path(__file__).with_name("echarts_snapshot.mjs")
WIDTH = 1200
HEIGHT = 675


def render_echarts_png(option: dict, visual_id: str) -> Path:
    """Render with the project's installed ECharts version and return a stored PNG."""
    if not isinstance(option, dict) or not isinstance(option.get("series"), list):
        raise ValueError("invalid ECharts option")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", visual_id):
        raise ValueError("invalid visual id")
    payload = json.dumps(
        {"option": option, "width": WIDTH, "height": HEIGHT},
        ensure_ascii=False,
    )
    if len(payload.encode("utf-8")) > 5_000_000:
        raise ValueError("ECharts option exceeds snapshot limit")
    result = subprocess.run(
        ["node", str(SCRIPT), str(PROJECT_ROOT / "frontend")],
        input=payload,
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )
    svg = result.stdout
    if not svg.startswith("<svg ") or len(svg) > 15_000_000:
        raise ValueError("invalid ECharts SVG output")
    if re.search(r"(?:href\s*=|url\s*\()\s*['\"]?(?:https?:|file:|/)", svg, re.I):
        raise ValueError("external SVG assets are not supported")
    target = get_chart_images_dir() / f"{visual_id}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(target),
                     output_width=WIDTH * 2, output_height=HEIGHT * 2)
    return target
