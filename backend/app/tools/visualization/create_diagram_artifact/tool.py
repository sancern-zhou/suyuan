"""Tool for creating previewable diagram HTML artifacts."""
from __future__ import annotations

import html
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

from app.tools.artifact_utils import attach_document_artifact
from app.services.html_artifact_service import html_artifact_service
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.visualization.font_sizing import FontScale, resolve_font_scale


DOT_ID_PATTERN = re.compile(r"[^A-Za-z0-9_]")
REFERENCE_ROOT = Path(__file__).resolve().parent / "references"
COMPACT_LAYER_ITEM_THRESHOLD = 12
COMPACT_GROUP_THRESHOLD = 6
WORD_A4_PORTRAIT_SIZE = "6.4,9.2"
WORD_A4_LANDSCAPE_SIZE = "9.2,6.4"
WORD_A4_PORTRAIT_PX = (1240, 1754)
WORD_A4_LANDSCAPE_PX = (1754, 1240)
WORD_A4_LONG_PROCESS_THRESHOLD = 12
WORD_A4_PROCESS_ROW_SIZE = 5
DIAGRAM_FONT_CANDIDATES = [
    {
        "family": "FZXiaoBiaoSong-B05S",
        "regular": "/home/xckj/.local/share/fonts/方正小标宋简.TTF",
        "bold": "/home/xckj/.local/share/fonts/方正小标宋简.TTF",
    },
    {
        "family": "Noto Sans CJK SC",
        "regular": "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
        "bold": "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
    },
    {
        "family": "Noto Sans CJK SC",
        "regular": "/usr/share/fonts/google-noto-cjk/NotoSansCJKsc-Regular.otf",
        "bold": "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
    },
    {
        "family": "Droid Sans",
        "regular": "/usr/share/fonts/google-droid-sans-fonts/DroidSansFallbackFull.ttf",
        "bold": "/usr/share/fonts/google-droid-sans-fonts/DroidSansFallbackFull.ttf",
    },
    {
        "family": "Noto Sans CJK SC",
        "regular": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "bold": "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    },
    {
        "family": "AR PL UMing CN",
        "regular": "/usr/share/fonts/truetype/arphic/uming.ttc",
        "bold": "/usr/share/fonts/truetype/arphic/uming.ttc",
    },
]
ICON_TOKENS = {
    "app",
    "api",
    "air",
    "alarm",
    "camera",
    "cloud",
    "compute",
    "container",
    "dashboard",
    "database",
    "desktop",
    "device",
    "emission",
    "external",
    "factory",
    "file",
    "gateway",
    "lake",
    "map",
    "message",
    "meter",
    "mobile",
    "network",
    "notification",
    "object-storage",
    "report",
    "river",
    "rule",
    "search",
    "security",
    "sensor",
    "server",
    "storage",
    "station",
    "switch",
    "sync",
    "terminal",
    "timeseries",
    "user",
    "video",
    "warehouse",
    "water",
    "web",
    "weather",
    "wind",
    "rain",
    "temperature",
    "humidity",
    "noise",
    "soil",
    "groundwater",
    "waste",
    "hazard",
    "pipeline",
    "outfall",
    "sampling",
    "lab",
    "inspection",
    "drone",
    "satellite",
    "model",
    "forecast",
    "trace",
    "workflow",
}


def diagram_design_reference_paths() -> Dict[str, str]:
    """Return stable reference keys Agent can read before creating diagrams."""
    return {
        "index": "create_diagram_artifact/references/index.md",
        "architecture": "create_diagram_artifact/references/architecture.md",
        "process": "create_diagram_artifact/references/process.md",
        "decision_tree": "create_diagram_artifact/references/decision-tree.md",
        "data_flow": "create_diagram_artifact/references/data-flow.md",
        "layered_system": "create_diagram_artifact/references/layered-system.md",
        "icon_catalog": "create_diagram_artifact/references/icon-catalog.md",
        "checklist": "create_diagram_artifact/references/checklist.md",
    }


def _normalise_diagram_type(diagram_type: str | None) -> str:
    mapping = {
        "layered_system": "layered_architecture",
        "architecture": "layered_architecture",
        "system_architecture": "layered_architecture",
        "flowchart": "process",
    }
    value = (diagram_type or "auto").strip().lower()
    return mapping.get(value, value)


def _scaled_int(value: int, font_scale: FontScale = None) -> int:
    return int(round(value * resolve_font_scale(font_scale)))


def select_diagram_font_path(bold: bool = False) -> str | None:
    key = "bold" if bold else "regular"
    for candidate in DIAGRAM_FONT_CANDIDATES:
        path = Path(candidate[key])
        if path.exists():
            return str(path)
    return None


def select_diagram_font_family() -> str:
    for candidate in DIAGRAM_FONT_CANDIDATES:
        if Path(candidate["regular"]).exists():
            return candidate["family"]
    return "DejaVu Sans"


def diagram_css_font_stack() -> str:
    return '"FZXiaoBiaoSong-B05S", "Noto Sans CJK SC", "Droid Sans", Inter, "PingFang SC", sans-serif'


def _sanitize_dot_id(raw_id: Any, index: int) -> str:
    text = DOT_ID_PATTERN.sub("_", str(raw_id or "")).strip("_")
    if not text:
        text = f"n{index + 1}"
    if text[0].isdigit():
        text = f"n_{text}"
    return text


def _escape_dot_label(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def _shape_to_graphviz(shape: str) -> str:
    mapping = {
        "rect": "box",
        "rounded": "box",
        "diamond": "diamond",
        "circle": "circle",
        "stadium": "oval",
        "subroutine": "box3d",
    }
    return mapping.get(shape, "box")


def _safe_asset_name(value: str, suffix: str = ".png") -> str:
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip()).strip("_")
    return f"{name or 'diagram'}{suffix}"


def _normalise_output_target(value: Any) -> str:
    text = str(value or "word_a4").strip().lower()
    return text if text in {"word_a4", "html"} else "word_a4"


def _normalise_page_orientation(value: Any, steps: List[Dict[str, Any]]) -> str:
    text = str(value or "auto").strip().lower()
    if text in {"portrait", "landscape"}:
        return text
    return "landscape" if len(steps or []) > 8 else "portrait"


def _word_a4_layout_warnings(
    diagram_type: str,
    steps: List[Dict[str, Any]],
    layers: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    warnings: List[str] = []
    if diagram_type in {"process", "decision_tree", "data_flow", "auto"} and len(steps or []) > WORD_A4_LONG_PROCESS_THRESHOLD:
        warnings.append("long_process_split_recommended")
    for layer in layers or []:
        item_count = sum(len(group.get("items") or []) for group in layer.get("groups") or [])
        if item_count > COMPACT_LAYER_ITEM_THRESHOLD:
            warnings.append("dense_layer_split_recommended")
            break
    return warnings


def _static_direction_for_word_a4(
    diagram_type: str,
    direction: str,
    page_orientation: str,
    steps: List[Dict[str, Any]],
) -> str:
    if page_orientation == "landscape" and diagram_type in {"auto", "process", "decision_tree", "data_flow"} and len(steps or []) > 8:
        return "LR"
    return direction


def _chunked(values: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _normalise_icon(icon: Any) -> str:
    value = str(icon or "").strip().lower().replace("_", "-")
    aliases = {
        "db": "database",
        "sql": "database",
        "mysql": "database",
        "redis": "storage",
        "cache": "storage",
        "objectstore": "object-storage",
        "oss": "object-storage",
        "s3": "object-storage",
        "time-series": "timeseries",
        "time-series-db": "timeseries",
        "tsdb": "timeseries",
        "data-warehouse": "warehouse",
        "dw": "warehouse",
        "data-lake": "lake",
        "vm": "server",
        "host": "server",
        "phone": "mobile",
        "app-mobile": "mobile",
        "pc": "desktop",
        "browser": "web",
        "website": "web",
        "iot": "sensor",
        "camera-monitor": "camera",
        "alert": "alarm",
        "warning": "alarm",
        "notify": "notification",
        "gis": "map",
        "auth": "security",
        "gateway-api": "gateway",
        "queue": "message",
        "mq": "message",
        "rules": "rule",
        "flow": "workflow",
        "process": "workflow",
        "cockpit": "dashboard",
        "bi": "dashboard",
        "sync-service": "sync",
        "search-service": "search",
        "terminal-device": "terminal",
        "station-monitor": "station",
        "factory-source": "factory",
        "pollution": "emission",
        "exhaust": "emission",
    }
    value = aliases.get(value, value)
    return value if value in ICON_TOKENS else ""


def _normalise_semantic(value: Any, allowed: set[str], default: str = "") -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    return text if text in allowed else default


def _normalise_emphasis(value: Any) -> str:
    return _normalise_semantic(value, {"normal", "high", "muted"}, "normal")


def _normalise_role(value: Any) -> str:
    return _normalise_semantic(
        value,
        {"entry", "business", "platform", "data", "infrastructure", "external", "support"},
        "",
    )


def _normalise_variant(value: Any) -> str:
    return _normalise_semantic(value, {"default", "foundation", "external", "critical"}, "default")


def _normalise_flow_strength(value: Any) -> str:
    return _normalise_semantic(value, {"normal", "strong"}, "normal")


def _normalise_icon_policy(value: Any) -> str:
    return _normalise_semantic(value, {"auto", "show", "hide"}, "auto")


def _diagram_icon_svg(icon: str) -> str:
    common = 'class="diagram-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"'
    icons = {
        "database": '<ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v10c0 1.7 3.1 3 7 3s7-1.3 7-3V5"/><path d="M5 10c0 1.7 3.1 3 7 3s7-1.3 7-3"/>',
        "timeseries": '<ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v11c0 1.7 3.1 3 7 3s7-1.3 7-3V5"/><path d="M8 14l2-3 3 2 3-5"/>',
        "warehouse": '<path d="M4 10l8-5 8 5v10H4V10Z"/><path d="M8 20v-7h8v7M6 10h12M9 15h6M9 18h6"/>',
        "object-storage": '<path d="M5 8l7-4 7 4-7 4-7-4Z"/><path d="M5 8v8l7 4 7-4V8"/><path d="M8 14l4 2 4-2"/>',
        "lake": '<path d="M4 16c2-2 4-2 6 0s4 2 6 0 3-2 4-1"/><path d="M4 20c2-2 4-2 6 0s4 2 6 0 3-2 4-1"/><path d="M8 12c1-4 3-7 4-9 1 2 3 5 4 9"/>',
        "server": '<rect x="5" y="4" width="14" height="6" rx="1.5"/><rect x="5" y="14" width="14" height="6" rx="1.5"/><path d="M8 7h.1M8 17h.1M12 7h4M12 17h4"/>',
        "mobile": '<rect x="8" y="3" width="8" height="18" rx="2"/><path d="M11 18h2"/>',
        "desktop": '<rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M9 20h6M12 16v4"/>',
        "cloud": '<path d="M7 18h10a4 4 0 0 0 .7-7.9A6 6 0 0 0 6.2 9.2 4.5 4.5 0 0 0 7 18Z"/>',
        "network": '<circle cx="6" cy="7" r="2"/><circle cx="18" cy="7" r="2"/><circle cx="12" cy="17" r="2"/><path d="M8 8l3 7M16 8l-3 7M8 7h8"/>',
        "gateway": '<path d="M4 12h12"/><path d="M12 8l4 4-4 4"/><rect x="3" y="5" width="6" height="14" rx="1.5"/><rect x="17" y="7" width="4" height="10" rx="1"/>',
        "api": '<path d="M7 8l-4 4 4 4M17 8l4 4-4 4M14 5l-4 14"/>',
        "security": '<path d="M12 3l7 3v5c0 4.5-2.8 8-7 10-4.2-2-7-5.5-7-10V6l7-3Z"/><path d="M9 12l2 2 4-5"/>',
        "message": '<path d="M4 5h16v11H8l-4 4V5Z"/><path d="M8 9h8M8 13h5"/>',
        "notification": '<path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/>',
        "alarm": '<path d="M18 9a6 6 0 0 0-12 0v4l-2 4h16l-2-4V9Z"/><path d="M10 20h4M4 5l3-2M20 5l-3-2"/>',
        "map": '<path d="M4 6l5-2 6 2 5-2v14l-5 2-6-2-5 2V6Z"/><path d="M9 4v14M15 6v14"/>',
        "dashboard": '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 15a4 4 0 0 1 8 0M12 15l3-5M7 9h2M15 9h2"/>',
        "report": '<path d="M7 3h7l4 4v14H7V3Z"/><path d="M14 3v5h5M9 13h6M9 17h5"/><path d="M9 10h2"/>',
        "search": '<circle cx="10" cy="10" r="5"/><path d="M14 14l6 6M8 10h4"/>',
        "workflow": '<rect x="3" y="5" width="6" height="5" rx="1.2"/><rect x="15" y="5" width="6" height="5" rx="1.2"/><rect x="9" y="15" width="6" height="5" rx="1.2"/><path d="M9 7.5h6M18 10v3l-6 2M6 10v3l6 2"/>',
        "sync": '<path d="M20 7h-5a6 6 0 0 0-10 3"/><path d="M17 4l3 3-3 3"/><path d="M4 17h5a6 6 0 0 0 10-3"/><path d="M7 20l-3-3 3-3"/>',
        "rule": '<path d="M5 6h14M5 12h10M5 18h7"/><path d="M17 12l2 2 3-5"/>',
        "file": '<path d="M7 3h7l4 4v14H7V3Z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
        "video": '<rect x="4" y="6" width="12" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3"/>',
        "camera": '<path d="M5 7h3l2-2h4l2 2h3v12H5V7Z"/><circle cx="12" cy="13" r="3"/><path d="M17 10h.1"/>',
        "sensor": '<path d="M12 19v2M8 21h8"/><circle cx="12" cy="9" r="3"/><path d="M6 9a6 6 0 0 1 12 0M3 9a9 9 0 0 1 18 0"/>',
        "device": '<rect x="6" y="4" width="12" height="16" rx="2"/><path d="M9 8h6M9 12h6M10 16h4"/>',
        "terminal": '<rect x="7" y="3" width="10" height="18" rx="2"/><path d="M10 7h4M10 11h4M10 15h2M12 19h.1"/>',
        "meter": '<circle cx="12" cy="12" r="8"/><path d="M8 14a4 4 0 0 1 8 0M12 12l3-4M9 18h6"/>',
        "switch": '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',
        "water": '<path d="M12 3c3 4 5 7 5 10a5 5 0 0 1-10 0c0-3 2-6 5-10Z"/><path d="M9 15c1 1 3 2 5 0"/>',
        "air": '<path d="M4 8h10a3 3 0 1 0-3-3"/><path d="M4 13h15a3 3 0 1 1-3 3"/><path d="M4 18h8"/>',
        "weather": '<path d="M7 18h10a4 4 0 0 0 .7-7.9A6 6 0 0 0 6.2 9.2 4.5 4.5 0 0 0 7 18Z"/><path d="M17 4v2M21 8h-2M19.5 5.5l-1.4 1.4"/>',
        "wind": '<path d="M4 8h10a3 3 0 1 0-3-3"/><path d="M4 13h14a3 3 0 1 1-3 3"/><path d="M4 18h7"/>',
        "rain": '<path d="M7 14h10a4 4 0 0 0 .7-7.9A6 6 0 0 0 6.2 5.2 4.5 4.5 0 0 0 7 14Z"/><path d="M8 18v2M12 17v3M16 18v2"/>',
        "temperature": '<path d="M10 14.5V5a2 2 0 1 1 4 0v9.5a4 4 0 1 1-4 0Z"/><path d="M12 7v8M12 19h.1"/>',
        "humidity": '<path d="M12 3c3.5 4.2 5.5 7.3 5.5 10.2a5.5 5.5 0 0 1-11 0C6.5 10.3 8.5 7.2 12 3Z"/><path d="M9 14c1.3 1.4 3.5 1.8 6 0"/>',
        "noise": '<path d="M5 10v4h3l4 4V6l-4 4H5Z"/><path d="M15 9c1 1 1 5 0 6M18 7c2.2 2.5 2.2 7.5 0 10"/>',
        "soil": '<path d="M4 17c2-2 4-2 6 0s4 2 6 0 3-2 4-1"/><path d="M5 20h14"/><path d="M12 4v9M9 7l3-3 3 3M8 11h8"/>',
        "groundwater": '<path d="M4 16c2-2 4-2 6 0s4 2 6 0 3-2 4-1"/><path d="M5 20h14"/><path d="M12 3c2.4 3 3.5 5.2 3.5 7a3.5 3.5 0 0 1-7 0c0-1.8 1.1-4 3.5-7Z"/>',
        "waste": '<path d="M6 7h12M9 7V5h6v2M8 7l1 13h6l1-13"/><path d="M10 11v5M14 11v5"/>',
        "hazard": '<path d="M12 3l10 18H2L12 3Z"/><path d="M12 9v5M12 17h.1"/>',
        "pipeline": '<path d="M4 9h10a3 3 0 0 1 0 6H8a3 3 0 0 0 0 6h12"/><path d="M4 6v6M20 18v6M11 12h4"/>',
        "outfall": '<path d="M4 10h9v5H4z"/><path d="M13 12.5h4"/><path d="M17 10v5"/><path d="M4 20c2-2 4-2 6 0s4 2 6 0 3-2 4-1"/>',
        "sampling": '<path d="M10 3h4M11 3v6l-5 9a2 2 0 0 0 1.7 3h8.6a2 2 0 0 0 1.7-3l-5-9V3"/><path d="M8 16h8"/>',
        "lab": '<path d="M9 3h6M10 3v5l-5 9a3 3 0 0 0 2.6 4h8.8a3 3 0 0 0 2.6-4l-5-9V3"/><path d="M8 15h8M10 11h4"/>',
        "inspection": '<path d="M9 4h6l1 2h3v15H5V6h3l1-2Z"/><path d="M9 12l2 2 4-5M9 18h6"/>',
        "drone": '<path d="M9 12h6M12 9v6"/><rect x="9" y="9" width="6" height="6" rx="1.5"/><circle cx="5" cy="5" r="3"/><circle cx="19" cy="5" r="3"/><circle cx="5" cy="19" r="3"/><circle cx="19" cy="19" r="3"/><path d="M7 7l2 2M17 7l-2 2M7 17l2-2M17 17l-2-2"/>',
        "satellite": '<path d="M10 10l4 4M8 12l4 4M12 8l4 4"/><rect x="9" y="9" width="6" height="6" rx="1.2" transform="rotate(45 12 12)"/><path d="M4 4l5 2-3 3-2-5ZM20 20l-5-2 3-3 2 5ZM17 5c2 1 2 3 2 5M5 17c-2-1-2-3-2-5"/>',
        "model": '<path d="M4 18c3-8 5-8 8 0s5 8 8 0"/><path d="M4 6h16M4 12h16"/><circle cx="8" cy="15" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="16" cy="15" r="1.5"/>',
        "forecast": '<path d="M4 18h16"/><path d="M6 15l4-4 3 3 5-7"/><path d="M18 7v5h-5"/><path d="M7 6h.1M10 6h.1"/>',
        "trace": '<circle cx="6" cy="18" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="18" cy="6" r="2"/><path d="M7.5 16.5l3-3M13.5 10.5l3-3"/><path d="M4 5h4M4 8h2M16 19h4M18 16h2"/>',
        "emission": '<path d="M5 20V9h5v11M14 20V6h5v14"/><path d="M3 20h18M7 9V5h2v4M16 6V3h2v3"/><path d="M8 4c-2-1-2-3 0-3M17 2c-2-1-2-3 0-3"/>',
        "factory": '<path d="M3 20h18V9l-6 4V9l-6 4V5H3v15Z"/><path d="M6 17h2M11 17h2M16 17h2"/>',
        "river": '<path d="M8 3c4 3-4 5 0 8s-4 5 0 10"/><path d="M15 3c4 3-4 5 0 8s-4 5 0 10"/><path d="M5 8h14M5 16h14"/>',
        "station": '<path d="M5 20h14V8l-7-4-7 4v12Z"/><path d="M9 20v-6h6v6M9 10h6M7 4h10"/>',
        "compute": '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 1v4M15 1v4M9 19v4M15 19v4M1 9h4M1 15h4M19 9h4M19 15h4"/>',
        "container": '<path d="M4 8l8-4 8 4-8 4-8-4Z"/><path d="M4 8v8l8 4 8-4V8"/><path d="M12 12v8"/>',
        "storage": '<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M8 9h8M8 13h8M8 17h5"/>',
        "user": '<circle cx="12" cy="8" r="3"/><path d="M5 21a7 7 0 0 1 14 0"/>',
        "web": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.2 2.5 3.4 5.5 3.4 9S14.2 18.5 12 21c-2.2-2.5-3.4-5.5-3.4-9S9.8 5.5 12 3Z"/>',
        "app": '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
        "external": '<path d="M14 4h6v6M10 14L20 4"/><path d="M20 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h5"/>',
    }
    body = icons.get(icon)
    if not body:
        return ""
    return f'<svg {common} data-icon="{html.escape(icon)}">{body}</svg>'


class CreateDiagramArtifactTool(LLMTool):
    """Create a previewable/shareable diagram artifact with type-specific renderers."""

    def __init__(self, name: str = "create_diagram_artifact"):
        super().__init__(
            name=name,
            description=(
                "创建流程/架构/决策图；报告/Word/QMD插图默认用 word_a4，明确要网页展示才用 html。"
                "不要空参调用。先读 create_diagram_artifact/references/index.md 和 checklist.md。"
            ),
            category=ToolCategory.VISUALIZATION,
            version="3.0.0",
        )
        self.function_schema = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "artifact_id": {
                        "type": "string",
                    },
                    "title": {
                        "type": "string",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["TB", "BT", "LR", "RL"],
                    },
                    "layout_engine": {
                        "type": "string",
                        "enum": ["graphviz", "mermaid", "auto"],
                    },
                    "output_target": {
                        "type": "string",
                        "enum": ["word_a4", "html"],
                        "default": "word_a4",
                        "description": (
                            "正式报告、Word、QMD、文档插图必须用 word_a4；"
                            "只有用户明确要求 HTML/网页展示/交互预览时才用 html。"
                        ),
                    },
                    "page_orientation": {
                        "type": "string",
                        "enum": ["auto", "portrait", "landscape"],
                    },
                    "diagram_type": {
                        "type": "string",
                        "enum": [
                            "auto",
                            "layered_architecture",
                            "architecture",
                            "layered_system",
                            "c4_context",
                            "c4_container",
                            "c4_component",
                            "deployment",
                            "process",
                            "decision_tree",
                            "data_flow",
                        ],
                    },
                    "mermaid": {
                        "type": "string",
                    },
                    "layers": {
                        "type": "array",
                        "description": "分层架构结构；支持 role、variant、emphasis、icon_policy，模板不根据 label 关键词推断。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {"type": "string"},
                                "variant": {"type": "string"},
                                "emphasis": {"type": "string"},
                                "icon_policy": {"type": "string"},
                            },
                            "additionalProperties": True,
                        },
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                                "shape": {
                                    "type": "string",
                                    "enum": ["rect", "rounded", "diamond", "circle", "stadium", "subroutine"],
                                },
                                "group": {"type": "string"},
                            },
                            "required": ["label"],
                        },
                    },
                    "edges": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": {"type": "string"},
                                "to": {"type": "string"},
                                "label": {"type": "string"},
	                                "style": {
	                                    "type": "string",
	                                    "enum": ["solid", "dashed"],
	                                },
	                                "flow_strength": {
	                                    "type": "string",
	                                    "enum": ["normal", "strong"],
	                                },
	                            },
                            "required": ["from", "to"],
                        },
                    },
                    "notes": {
                        "type": "string",
                    },
                    "font_scale": {
                        "description": "字号。",
                        "oneOf": [
                            {"type": "string", "enum": ["small", "normal", "large", "xlarge"]},
                            {"type": "number", "minimum": 0.8, "maximum": 1.6},
                        ],
                    },
                    "metadata": {
                        "type": "object",
                    },
                },
                "required": ["artifact_id", "title"],
            },
        }

    def _build_dot_from_steps(
        self,
        steps: List[Dict[str, Any]],
        edges: Optional[List[Dict[str, Any]]],
        direction: str,
        title: str,
        font_scale: FontScale = None,
        output_target: str = "html",
        page_orientation: str = "portrait",
    ) -> str:
        rankdir = direction if direction in {"TB", "BT", "LR", "RL"} else "TB"
        node_font_size = _scaled_int(12, font_scale)
        edge_font_size = _scaled_int(10, font_scale)
        title_font_size = _scaled_int(18, font_scale)
        graphviz_font = select_diagram_font_path() or select_diagram_font_family()
        graph_attrs = [
            f'rankdir="{rankdir}"',
            'bgcolor="transparent"',
            'pad="0.25"',
            'nodesep="0.45"',
            'ranksep="0.8"',
            'splines="ortho"',
            "concentrate=true",
        ]
        if output_target == "word_a4":
            graph_attrs.extend([
                f'size="{WORD_A4_LANDSCAPE_SIZE if page_orientation == "landscape" else WORD_A4_PORTRAIT_SIZE}"',
                'ratio="compress"',
                'margin="0.08"',
            ])
        dot_lines = [
            "digraph G {",
            f"  graph [{', '.join(graph_attrs)}];",
            f'  node [shape=box, style="rounded,filled", fontname="{graphviz_font}", fontsize={node_font_size}, margin="0.12,0.08", color="#9aa9c3", fillcolor="#ffffff", fontcolor="#18202f"];',
            f'  edge [color="#5b6b82", penwidth=1.8, arrowsize=0.8, fontname="{graphviz_font}", fontsize={edge_font_size}];',
            f'  label="{_escape_dot_label(title)}";',
            '  labelloc="t";',
            f'  fontsize={title_font_size};',
            f'  fontname="{graphviz_font}";',
        ]

        if not steps:
            dot_lines.extend([
                '  empty [label="无步骤数据", shape=box, style="rounded,filled", fillcolor="#f6f7fb"];',
                '  hint [label="请提供 steps / edges 或 mermaid", shape=box, style="dashed", color="#c0cad8"];',
                "  empty -> hint;",
            ])
            dot_lines.append("}")
            return "\n".join(dot_lines)

        node_ids: Dict[str, str] = {}
        for idx, step in enumerate(steps):
            node_id = _sanitize_dot_id(step.get("id") or step.get("label"), idx)
            node_ids[str(step.get("id") or step.get("label") or node_id)] = node_id
            label = _escape_dot_label(step.get("label", node_id))
            shape = _shape_to_graphviz((step.get("shape") or "rect").lower())
            style = "rounded,filled" if shape in {"box", "oval", "box3d"} else "filled"
            fillcolor = step.get("fillcolor") or "#ffffff"
            color = step.get("color") or "#9aa9c3"
            if shape == "diamond":
                style = "filled"
                fillcolor = step.get("fillcolor") or "#fff8ec"
                color = step.get("color") or "#f0b44c"

            dot_lines.append(
                f'  {node_id} [label="{label}", shape="{shape}", style="{style}", fillcolor="{fillcolor}", color="{color}"];'
            )

        if edges:
            for edge in edges:
                src_key = str(edge.get("from") or "")
                dst_key = str(edge.get("to") or "")
                src = node_ids.get(src_key) or _sanitize_dot_id(src_key, 0)
                dst = node_ids.get(dst_key) or _sanitize_dot_id(dst_key, 0)
                label = _escape_dot_label(edge.get("label", ""))
                style = "dashed" if edge.get("style") == "dashed" else "solid"
                attrs = [f'style="{style}"']
                if label:
                    attrs.append(f'label="{label}"')
                    attrs.append('fontcolor="#6b7280"')
                dot_lines.append(f"  {src} -> {dst} [{', '.join(attrs)}];")
        else:
            ordered_ids = list(node_ids.values())
            for left, right in zip(ordered_ids, ordered_ids[1:]):
                dot_lines.append(f"  {left} -> {right};")

        dot_lines.append("}")
        return "\n".join(dot_lines)

    def _render_graphviz_svg(self, dot_source: str) -> str:
        result = subprocess.run(
            ["dot", "-Tsvg"],
            input=dot_source,
            text=True,
            capture_output=True,
            check=True,
        )
        svg = result.stdout.strip()
        svg_start = svg.find("<svg")
        if svg_start >= 0:
            svg = svg[svg_start:]
        return svg

    def _render_graphviz_png(
        self,
        dot_source: str,
        output_path: Path,
        page_orientation: str = "portrait",
        output_target: str = "word_a4",
    ) -> Dict[str, Any]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_output_path = output_path.with_name(f"{output_path.stem}.raw.png")
        subprocess.run(
            ["dot", "-Tpng", "-o", str(raw_output_path)],
            input=dot_source,
            text=True,
            capture_output=True,
            check=True,
        )
        if output_target == "word_a4":
            self._compose_word_a4_png(raw_output_path, output_path, page_orientation)
            try:
                raw_output_path.unlink()
            except OSError:
                pass
        else:
            raw_output_path.replace(output_path)
        return {
            "path": str(output_path),
            "relative_path": str(output_path.name),
            "format": "png",
            "size_kb": round(output_path.stat().st_size / 1024, 2),
        }

    async def _render_html_word_a4_screenshot(
        self,
        index_path: Path,
        output_path: Path,
        page_orientation: str,
    ) -> Dict[str, Any]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        viewport_width, viewport_height = (
            WORD_A4_LANDSCAPE_PX if page_orientation == "landscape" else WORD_A4_PORTRAIT_PX
        )
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright is required to render Word A4 screenshots") from exc

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            try:
                page = await browser.new_page(
                    viewport={"width": viewport_width, "height": viewport_height},
                    device_scale_factor=1,
                )
                await page.goto(Path(index_path).resolve().as_uri(), wait_until="networkidle")
                await page.evaluate(
                    """
                    async () => {
                        if (document.fonts && document.fonts.ready) {
                            await document.fonts.ready;
                        }
                        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                    }
                    """
                )
                await page.wait_for_timeout(250)
                await page.screenshot(path=str(output_path), type="png", full_page=False)
            finally:
                await browser.close()

        return {
            "path": str(output_path),
            "relative_path": str(output_path.name),
            "format": "png",
            "size_kb": round(output_path.stat().st_size / 1024, 2),
        }

    def _compose_word_a4_png(self, source_path: Path, output_path: Path, page_orientation: str) -> None:
        canvas_size = WORD_A4_LANDSCAPE_PX if page_orientation == "landscape" else WORD_A4_PORTRAIT_PX
        canvas = Image.new("RGB", canvas_size, "white")
        image = Image.open(source_path).convert("RGBA")
        content_bbox = image.getbbox()
        if content_bbox:
            image = image.crop(content_bbox)

        max_width = int(canvas_size[0] * 0.9)
        max_height = int(canvas_size[1] * 0.84)
        scale = min(max_width / max(1, image.width), max_height / max(1, image.height))
        if scale > 0:
            resized_size = (
                max(1, int(round(image.width * scale))),
                max(1, int(round(image.height * scale))),
            )
            resampling = getattr(Image, "Resampling", Image).LANCZOS
            image = image.resize(resized_size, resampling)

        offset = ((canvas_size[0] - image.width) // 2, (canvas_size[1] - image.height) // 2)
        canvas.paste(image, offset, image)
        canvas.save(output_path, format="PNG")

    def _render_wrapped_process_png(
        self,
        steps: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        title: str,
        output_path: Path,
    ) -> Dict[str, Any]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas = Image.new("RGB", WORD_A4_LANDSCAPE_PX, "white")
        draw = ImageDraw.Draw(canvas)
        title_font = self._load_word_a4_font(30, bold=True)
        node_font = self._load_word_a4_font(22)
        edge_font = self._load_word_a4_font(15)

        title_text = str(title or "流程图")
        title_box = draw.textbbox((0, 0), title_text, font=title_font)
        draw.text(
            ((WORD_A4_LANDSCAPE_PX[0] - (title_box[2] - title_box[0])) / 2, 74),
            title_text,
            fill="#18202f",
            font=title_font,
        )

        rows = _chunked(steps, WORD_A4_PROCESS_ROW_SIZE)
        top = 210
        row_gap = 250 if len(rows) <= 3 else max(170, int((WORD_A4_LANDSCAPE_PX[1] - top - 120) / max(1, len(rows) - 1)))
        node_w, node_h = 150, 62
        x_min, x_max = 110, WORD_A4_LANDSCAPE_PX[0] - 110
        positions: Dict[str, tuple[int, int]] = {}

        for row_index, row in enumerate(rows):
            count = len(row)
            slots = [x_min + int((x_max - x_min) * index / max(1, count - 1)) for index in range(count)]
            visual_row = list(reversed(row)) if row_index % 2 else row
            y = top + row_index * row_gap
            for slot_index, step in enumerate(visual_row):
                step_key = str(step.get("id") or step.get("label") or f"s{slot_index}")
                positions[step_key] = (slots[slot_index], y)

        edge_label_by_pair = {
            (str(edge.get("from") or ""), str(edge.get("to") or "")): str(edge.get("label") or "")
            for edge in edges or []
        }
        ordered_keys = [str(step.get("id") or step.get("label") or f"s{index}") for index, step in enumerate(steps)]
        for left, right in zip(ordered_keys, ordered_keys[1:]):
            if left not in positions or right not in positions:
                continue
            label = edge_label_by_pair.get((left, right), "")
            self._draw_arrow(draw, positions[left], positions[right], node_w, node_h, label, edge_font)

        for index, step in enumerate(steps):
            step_key = str(step.get("id") or step.get("label") or f"s{index}")
            center = positions.get(step_key)
            if not center:
                continue
            self._draw_process_node(draw, center, node_w, node_h, str(step.get("label") or step_key), node_font)

        canvas.save(output_path, format="PNG")
        return {
            "path": str(output_path),
            "relative_path": str(output_path.name),
            "format": "png",
            "size_kb": round(output_path.stat().st_size / 1024, 2),
        }

    def _load_word_a4_font(self, size: int, bold: bool = False):
        selected = select_diagram_font_path(bold=bold) or select_diagram_font_path(bold=False)
        if selected:
            try:
                return ImageFont.truetype(selected, size)
            except Exception:
                pass
        return ImageFont.load_default()

    def _draw_process_node(self, draw: ImageDraw.ImageDraw, center: tuple[int, int], width: int, height: int, label: str, font) -> None:
        x, y = center
        box = (x - width // 2, y - height // 2, x + width // 2, y + height // 2)
        draw.rounded_rectangle(box, radius=16, fill="#ffffff", outline="#9aa9c3", width=3)
        text = label[:12]
        text_box = draw.textbbox((0, 0), text, font=font)
        draw.text(
            (x - (text_box[2] - text_box[0]) / 2, y - (text_box[3] - text_box[1]) / 2 - 2),
            text,
            fill="#18202f",
            font=font,
        )

    def _draw_arrow(
        self,
        draw: ImageDraw.ImageDraw,
        source: tuple[int, int],
        target: tuple[int, int],
        node_w: int,
        node_h: int,
        label: str,
        font,
    ) -> None:
        sx, sy = source
        tx, ty = target
        if abs(sy - ty) < node_h:
            start = (sx + (node_w // 2 if tx > sx else -node_w // 2), sy)
            end = (tx - (node_w // 2 if tx > sx else -node_w // 2), ty)
            self._draw_line_arrow(draw, start, end)
            label_pos = ((start[0] + end[0]) // 2, sy - 30)
        elif abs(sx - tx) < node_w:
            start = (sx, sy + node_h // 2)
            end = (tx, ty - node_h // 2)
            self._draw_line_arrow(draw, start, end)
            label_pos = (sx + 12, (start[1] + end[1]) // 2 - 12)
        else:
            mid = (sx, ty)
            start = (sx, sy + node_h // 2)
            end = (tx, ty - node_h // 2)
            draw.line([start, mid, end], fill="#5b6b82", width=3)
            self._draw_arrow_head(draw, mid, end)
            label_pos = ((sx + tx) // 2, ty - node_h - 18)
        if label:
            draw.text(label_pos, label[:8], fill="#5b6b82", font=font)

    def _draw_line_arrow(self, draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int]) -> None:
        draw.line([start, end], fill="#5b6b82", width=3)
        self._draw_arrow_head(draw, start, end)

    def _draw_arrow_head(self, draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int]) -> None:
        sx, sy = start
        ex, ey = end
        if abs(ex - sx) >= abs(ey - sy):
            sign = 1 if ex >= sx else -1
            points = [(ex, ey), (ex - sign * 14, ey - 8), (ex - sign * 14, ey + 8)]
        else:
            sign = 1 if ey >= sy else -1
            points = [(ex, ey), (ex - 8, ey - sign * 14), (ex + 8, ey - sign * 14)]
        draw.polygon(points, fill="#5b6b82")

    def _layers_from_grouped_steps(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, str]]] = {}
        order: List[str] = []
        for step in steps:
            group = str(step.get("group") or "未分组").strip() or "未分组"
            label = str(step.get("label") or "").strip()
            if not label:
                continue
            if group not in grouped:
                grouped[group] = []
                order.append(group)
            if label == group and str(step.get("id") or "").endswith("_title"):
                continue
            grouped[group].append({"label": label, "detail": str(step.get("detail") or "").strip()})

        return [
            {
                "id": _sanitize_dot_id(group, index),
                "label": group,
                "groups": [{"label": "核心模块", "items": grouped[group]}],
            }
            for index, group in enumerate(order)
        ]

    def _normalise_layer_item(self, item: Dict[str, Any]) -> Dict[str, str]:
        return {
            "label": str(item.get("label") or item.get("name") or "").strip(),
            "detail": str(item.get("detail") or item.get("description") or "").strip(),
            "icon": _normalise_icon(item.get("icon")),
            "role": _normalise_role(item.get("role")),
            "emphasis": _normalise_emphasis(item.get("emphasis")),
            "variant": _normalise_variant(item.get("variant")),
        }

    def _normalise_layers(
        self,
        layers: Optional[List[Dict[str, Any]]],
        steps: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        source_layers = layers or []
        if not source_layers and any(step.get("group") for step in steps):
            source_layers = self._layers_from_grouped_steps(steps)

        normalised: List[Dict[str, Any]] = []
        for index, layer in enumerate(source_layers):
            label = str(layer.get("label") or layer.get("name") or f"层 {index + 1}").strip()
            layer_id = str(layer.get("id") or _sanitize_dot_id(label, index))
            groups = []
            for group in layer.get("groups") or []:
                items = [
                    self._normalise_layer_item(item)
                    for item in group.get("items") or []
                    if str(item.get("label") or item.get("name") or "").strip()
                ]
                if items:
                    group_label = str(group.get("label") or group.get("name") or "模块组").strip()
                    groups.append({"label": group_label, "items": items})

            direct_items = [
                self._normalise_layer_item(item)
                for item in layer.get("items") or []
                if str(item.get("label") or item.get("name") or "").strip()
            ]
            if direct_items:
                groups.append({"label": "核心模块", "items": direct_items})

            normalised.append({
                "id": layer_id,
                "label": label,
                "theme": str(layer.get("theme") or "").strip(),
                "role": _normalise_role(layer.get("role")),
                "variant": _normalise_variant(layer.get("variant")),
                "icon_policy": _normalise_icon_policy(layer.get("icon_policy")),
                "groups": groups or [{"label": "核心模块", "items": [{"label": "待补充模块", "detail": ""}]}],
            })

        return normalised

    def _build_layered_architecture_html(
        self,
        title: str,
        layers: List[Dict[str, Any]],
        edges: Optional[List[Dict[str, Any]]] = None,
        notes: str | None = None,
        font_scale: FontScale = None,
    ) -> str:
        safe_title = html.escape(title)
        safe_font_scale = f"{resolve_font_scale(font_scale):.3f}"
        css_font_stack = diagram_css_font_stack()
        palette = ["cyan", "blue", "green", "amber", "purple", "slate"]
        layer_id_to_label = {str(layer.get("id") or ""): str(layer.get("label") or "") for layer in layers}

        edge_labels: Dict[str, str] = {}
        edge_strengths: Dict[str, str] = {}
        for edge in edges or []:
            src = str(edge.get("from") or "")
            dst = str(edge.get("to") or "")
            if not src or not dst:
                continue
            label = str(edge.get("label") or "依赖").strip()
            edge_labels[f"{src}->{dst}"] = label
            edge_strengths[f"{src}->{dst}"] = _normalise_flow_strength(edge.get("flow_strength"))

        band_html = []
        layer_count = len(layers)
        for index, layer in enumerate(layers):
            theme = layer.get("theme") or palette[index % len(palette)]
            groups_html = []
            layer_item_count = sum(len(group.get("items") or []) for group in layer.get("groups") or [])
            icon_policy = _normalise_icon_policy(layer.get("icon_policy"))
            if icon_policy == "show":
                layer_icons_visible = True
            elif icon_policy == "hide":
                layer_icons_visible = False
            else:
                layer_icons_visible = index >= max(0, layer_count - 2)
            for group in layer.get("groups") or []:
                cards = []
                for item in group.get("items") or []:
                    detail = str(item.get("detail") or "").strip()
                    detail_html = f"<p>{html.escape(detail)}</p>" if detail else ""
                    icon_html = _diagram_icon_svg(str(item.get("icon") or "")) if layer_icons_visible else ""
                    icon_symbol_html = f"<span class=\"module-symbol\">{icon_html}</span>" if icon_html else ""
                    item_classes = ["module-item"]
                    if not icon_symbol_html:
                        item_classes.append("module-item-no-icon")
                    emphasis = _normalise_emphasis(item.get("emphasis"))
                    variant = _normalise_variant(item.get("variant"))
                    role = _normalise_role(item.get("role"))
                    if emphasis != "normal":
                        item_classes.append(f"module-emphasis-{emphasis}")
                    if variant != "default":
                        item_classes.append(f"module-variant-{variant}")
                    if role:
                        item_classes.append(f"module-role-{role}")
                    cards.append(
                        f"<article data-label=\"{html.escape(str(item.get('label') or ''))}\" class=\"{html.escape(' '.join(item_classes))}\">"
                        f"{icon_symbol_html}"
                        f"<strong class=\"module-label\">{html.escape(str(item.get('label') or ''))}</strong>"
                        f"{detail_html}"
                        "</article>"
                    )
                group_classes = ["module-group"]
                if (
                    layer_item_count > COMPACT_LAYER_ITEM_THRESHOLD
                    or len(group.get("items") or []) > COMPACT_GROUP_THRESHOLD
                ):
                    group_classes.append("group-density-compact")
                groups_html.append(
                    f"<section class=\"{html.escape(' '.join(group_classes))}\">"
                    f"<h2>{html.escape(str(group.get('label') or '模块组'))}</h2>"
                    f"<div class=\"module-grid centered-grid\">{''.join(cards)}</div>"
                    "</section>"
                )

            connector = ""
            if index < len(layers) - 1:
                current_id = str(layer.get("id") or "")
                next_id = str(layers[index + 1].get("id") or "")
                forward_key = f"{current_id}->{next_id}"
                reverse_key = f"{next_id}->{current_id}"
                is_reverse_transition = reverse_key in edge_labels and forward_key not in edge_labels
                edge_key = reverse_key if is_reverse_transition else forward_key
                transition_label = edge_labels.get(edge_key) or ""
                transition_strength = edge_strengths.get(edge_key) or "normal"
                transition_classes = ["layer-transition"]
                if transition_strength == "strong":
                    transition_classes.append("layer-transition-strong")
                if is_reverse_transition:
                    transition_classes.append("layer-transition-reverse")
                label_html = f"<span>{html.escape(transition_label)}</span>" if transition_label else ""
                connector = (
                    f"<div data-edge=\"{html.escape(edge_key)}\" class=\"{html.escape(' '.join(transition_classes))}\" "
                    f"aria-hidden=\"true\"><i></i>{label_html}</div>"
                )
            layer_classes = ["layer-band", f"theme-{str(theme)}"]
            layer_variant = _normalise_variant(layer.get("variant"))
            layer_role = _normalise_role(layer.get("role"))
            if layer_variant != "default":
                layer_classes.append(f"layer-variant-{layer_variant}")
            if layer_role:
                layer_classes.append(f"layer-role-{layer_role}")
            if layer_item_count > COMPACT_LAYER_ITEM_THRESHOLD or len(layer.get("groups") or []) > 3:
                layer_classes.append("layer-density-compact")
            band_html.append(
                f"<section data-layer-id=\"{html.escape(str(layer.get('id') or ''))}\" class=\"{html.escape(' '.join(layer_classes))}\">"
                "<aside class=\"layer-label\">"
                f"<span class=\"layer-index\">{index + 1:02d}</span>"
                f"<strong>{html.escape(str(layer.get('label') or ''))}</strong>"
                "</aside>"
                f"<div class=\"layer-content\">{''.join(groups_html)}</div>"
                f"</section>{connector}"
            )

        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f3f6fb;
      --panel: #ffffff;
      --text: #101828;
	      --muted: #475467;
	      --border: #cfd9e8;
	      --shadow: 0 14px 34px rgba(15, 23, 42, 0.13);
	      --font-scale: {safe_font_scale};
	    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: {css_font_stack}; background: var(--bg); color: var(--text); }}
    .wrap {{ max-width: 1440px; margin: 0 auto; padding: 24px; }}
    .header {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin-bottom: 18px; }}
	    h1 {{ margin: 0; font-size: calc(32px * var(--font-scale)); line-height: 1.16; font-weight: 850; letter-spacing: 0; color: var(--text); }}
	    .meta {{ color: var(--muted); font-size: calc(13px * var(--font-scale)); font-weight: 650; }}
    .canvas {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px; box-shadow: var(--shadow); }}
    .layered-diagram {{ display: grid; gap: 9px; }}
    .layer-band {{ display: grid; grid-template-columns: 154px minmax(0, 1fr); gap: 14px; min-height: 86px; border: 1px solid var(--layer-border); border-left: 5px solid var(--layer-strong); background: var(--layer-bg); border-radius: 8px; padding: 10px 12px; }}
    .layer-variant-foundation {{ box-shadow: inset 0 -4px 0 color-mix(in srgb, var(--layer-strong) 18%, transparent), 0 8px 18px rgba(15, 23, 42, 0.09); }}
    .layer-variant-external {{ border-style: dashed; background: #ffffff; }}
    .layer-variant-critical {{ border-left-width: 7px; box-shadow: 0 12px 26px rgba(185, 28, 28, 0.13); }}
    .layer-label {{ display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; min-height: 100%; border-right: 1px solid var(--layer-border); padding-right: 12px; text-align: center; }}
	    .layer-index {{ display: inline-flex; align-items: center; justify-content: center; min-width: 38px; height: 26px; border-radius: 999px; background: var(--layer-strong); color: #fff; font-size: calc(14px * var(--font-scale)); font-weight: 850; letter-spacing: 0; box-shadow: 0 4px 10px rgba(15, 23, 42, 0.14); }}
	    .layer-label strong {{ max-width: 120px; font-size: calc(26px * var(--font-scale)); line-height: 1.08; color: var(--layer-strong); font-weight: 850; overflow-wrap: anywhere; }}
    .layer-content {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 9px; align-items: stretch; min-width: 0; }}
    .layer-density-compact {{ gap: 12px; padding: 9px 11px; }}
    .layer-density-compact .layer-content {{ grid-template-columns: repeat(auto-fit, minmax(205px, 1fr)); gap: 8px; }}
	    .layer-density-compact .layer-label strong {{ font-size: calc(24px * var(--font-scale)); }}
    .module-group {{ border: 1px solid color-mix(in srgb, var(--layer-border) 78%, #7f8ea3); border-radius: 8px; padding: 8px 10px; background: rgba(255,255,255,0.72); min-width: 0; }}
    .group-density-compact {{ padding: 7px 8px; }}
	    .module-group h2 {{ margin: 0 0 7px; font-size: calc(15px * var(--font-scale)); font-weight: 820; color: var(--layer-strong); line-height: 1.2; text-align: center; }}
	    .group-density-compact h2 {{ margin-bottom: 6px; font-size: calc(14px * var(--font-scale)); }}
    .module-grid {{ display: flex; flex-wrap: wrap; justify-content: center; align-content: center; gap: 8px 14px; }}
    .layer-density-compact .module-grid {{ gap: 7px 10px; }}
    .centered-grid {{ justify-content: center; }}
    .module-item {{ flex: 0 1 132px; max-width: 176px; min-width: 112px; min-height: 42px; border-radius: 7px; padding: 7px 8px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 5px; overflow: hidden; text-align: center; border: 1px solid transparent; }}
    .module-item-no-icon {{ min-height: 36px; padding-top: 5px; padding-bottom: 5px; }}
    .layer-density-compact .module-item {{ flex-basis: 116px; min-width: 96px; min-height: 36px; padding: 5px 6px; gap: 4px; }}
    .module-item:hover {{ background: rgba(255,255,255,0.72); }}
    .module-emphasis-high {{ background: var(--layer-strong); color: #fff; border-color: var(--layer-strong); box-shadow: 0 12px 22px color-mix(in srgb, var(--layer-strong) 24%, transparent); }}
    .module-emphasis-muted {{ opacity: 0.72; }}
    .module-variant-critical {{ background: #b42318; color: #fff; border-color: #b42318; }}
    .module-variant-external {{ border-style: dashed; background: #fff; }}
	    .module-symbol {{ width: calc(30px * var(--font-scale)); height: calc(30px * var(--font-scale)); display: inline-flex; align-items: center; justify-content: center; color: var(--layer-strong); flex: 0 0 auto; }}
	    .layer-density-compact .module-symbol {{ width: calc(26px * var(--font-scale)); height: calc(26px * var(--font-scale)); }}
	    .module-emphasis-high .module-symbol, .module-variant-critical .module-symbol {{ color: #fff; }}
	    .diagram-icon {{ width: calc(28px * var(--font-scale)); height: calc(28px * var(--font-scale)); fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }}
	    .layer-density-compact .diagram-icon {{ width: calc(24px * var(--font-scale)); height: calc(24px * var(--font-scale)); }}
	    .module-label {{ font-size: 17px; font-size: calc(17px * var(--font-scale)); line-height: 1.18; color: #182230; font-weight: 800; overflow-wrap: anywhere; }}
	    .layer-density-compact .module-label {{ font-size: calc(15px * var(--font-scale)); line-height: 1.16; }}
	    .module-emphasis-high .module-label, .module-variant-critical .module-label {{ color: #fff; }}
	    .module-item p {{ margin: -1px 0 0; color: var(--muted); font-size: calc(12px * var(--font-scale)); line-height: 1.28; font-weight: 520; overflow-wrap: anywhere; }}
	    .module-emphasis-high p, .module-variant-critical p {{ color: rgba(255,255,255,0.84); }}
	    .layer-transition {{ display: flex; align-items: center; gap: 9px; height: 22px; margin-left: 76px; color: #344054; font-size: calc(12px * var(--font-scale)); font-weight: 650; }}
    .layer-transition i {{ width: 3px; height: 18px; background: #64748b; position: relative; display: inline-block; border-radius: 999px; }}
    .layer-transition i::after {{ content: ""; position: absolute; left: -5px; bottom: -1px; border-left: 7px solid transparent; border-right: 7px solid transparent; border-top: 9px solid #64748b; }}
    .layer-transition-reverse i::after {{ top: -1px; bottom: auto; border-top: 0; border-bottom: 9px solid #64748b; }}
    .layer-transition-strong {{ color: #1d4ed8; font-weight: 820; }}
    .layer-transition-strong i {{ width: 4px; height: 20px; background: #2563eb; }}
    .layer-transition-strong i::after {{ border-left-width: 8px; border-right-width: 8px; border-top: 10px solid #2563eb; left: -6px; }}
    .layer-transition-reverse.layer-transition-strong i::after {{ border-top: 0; border-bottom: 10px solid #2563eb; }}
    .layer-transition span {{ border: 1px solid #c9d4e4; background: #fff; border-radius: 999px; padding: 4px 10px; box-shadow: 0 3px 8px rgba(15, 23, 42, 0.07); }}
    .theme-cyan {{ --layer-bg: #e6fbff; --layer-border: #67d4e7; --layer-strong: #0e7490; }}
    .theme-blue {{ --layer-bg: #eaf4ff; --layer-border: #8ec5f6; --layer-strong: #1d4ed8; }}
    .theme-green {{ --layer-bg: #ebfbee; --layer-border: #86d69a; --layer-strong: #15803d; }}
    .theme-amber {{ --layer-bg: #fff7dc; --layer-border: #f4c84f; --layer-strong: #b45309; }}
    .theme-purple {{ --layer-bg: #f7edff; --layer-border: #c99aee; --layer-strong: #7e22ce; }}
    .theme-slate {{ --layer-bg: #f4f7fb; --layer-border: #a9b7ca; --layer-strong: #334155; }}
    @media (max-width: 760px) {{
      .wrap {{ padding: 14px; }}
      .header {{ display: block; }}
      .canvas {{ padding: 12px; }}
      .layer-band {{ grid-template-columns: 1fr; gap: 10px; }}
      .layer-label {{ border-right: 0; border-bottom: 1px solid var(--layer-border); padding: 0 0 10px; }}
      .layer-content {{ grid-template-columns: 1fr; }}
      .layer-transition {{ margin-left: 50%; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="header">
      <h1>{safe_title}</h1>
      <div class="meta">分层架构图 · 确定性布局</div>
    </header>
    <main class="canvas">
      <div class="layered-diagram">
        {''.join(band_html)}
      </div>
    </main>
  </div>
</body>
</html>
"""

    def _build_mermaid_html(self, title: str, mermaid: str, notes: str | None = None) -> str:
        notes_html = ""
        if notes:
            notes_html = f"<section class=\"notes\"><pre>{html.escape(str(notes))}</pre></section>"

        safe_mermaid = html.escape(mermaid)
        safe_title = html.escape(title)
        css_font_stack = diagram_css_font_stack()
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    body {{ margin: 0; font-family: {css_font_stack}; background: #f6f7fb; color: #18202f; }}
    .wrap {{ max-width: 1280px; margin: 0 auto; padding: 24px; }}
    .panel {{ background: #fff; border: 1px solid #d9e0ee; border-radius: 8px; padding: 20px; overflow: auto; }}
    .notes {{ margin-top: 16px; border-top: 1px solid #d9e0ee; padding-top: 12px; color: #5d677b; font-size: 13px; }}
    .notes pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; }}
    .mermaid {{ min-height: 220px; }}
  </style>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <script>
    window.addEventListener('DOMContentLoaded', () => {{
      mermaid.initialize({{
        startOnLoad: true,
        securityLevel: 'loose',
        theme: 'default',
        flowchart: {{ useMaxWidth: true, htmlLabels: true }}
      }});
    }});
  </script>
</head>
<body>
  <div class="wrap">
    <h1>{safe_title}</h1>
    <div class="panel">
      <div class="mermaid">{safe_mermaid}</div>
      {notes_html}
    </div>
  </div>
</body>
</html>
"""

    def _build_graphviz_html(self, title: str, svg: str, notes: str | None = None) -> str:
        notes_html = ""
        if notes:
            notes_html = f"<section class=\"notes\"><pre>{html.escape(str(notes))}</pre></section>"

        safe_title = html.escape(title)
        css_font_stack = diagram_css_font_stack()
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7fb;
      --panel: #ffffff;
      --text: #18202f;
      --muted: #5d677b;
      --border: #d9e0ee;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: {css_font_stack}; background: var(--bg); color: var(--text); }}
    .wrap {{ max-width: 1600px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 12px; font-size: 24px; line-height: 1.2; }}
    .hint {{ color: var(--muted); font-size: 13px; margin-bottom: 16px; }}
    .panel {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 20px; overflow: auto; }}
    .svg-wrap {{ width: 100%; overflow: auto; }}
    .svg-wrap svg {{ width: 100%; height: auto; display: block; }}
    .notes {{ margin-top: 16px; border-top: 1px solid var(--border); padding-top: 12px; color: var(--muted); font-size: 13px; }}
    .notes pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>{safe_title}</h1>
    <div class="hint">由助手模式自动生成的静态流程图</div>
    <div class="panel">
      <div class="svg-wrap">
        {svg}
      </div>
      {notes_html}
    </div>
  </div>
</body>
</html>
"""

    async def execute(
        self,
        artifact_id: Optional[str] = None,
        title: Optional[str] = None,
        direction: str = "TB",
        layout_engine: str = "graphviz",
        diagram_type: str = "auto",
        mermaid: Optional[str] = None,
        layers: Optional[List[Dict[str, Any]]] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
        edges: Optional[List[Dict[str, Any]]] = None,
        notes: Optional[str] = None,
        font_scale: FontScale = None,
        output_target: str = "word_a4",
        page_orientation: str = "auto",
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            artifact_id = str(artifact_id or "").strip()
            title = str(title or "").strip()
            missing = []
            if not artifact_id:
                missing.append("artifact_id")
            if not title:
                missing.append("title")
            if missing:
                return {
                    "success": False,
                    "data": None,
                    "metadata": {
                        "generator": self.name,
                        "schema_version": "diagram_html.v3",
                        "missing_required": missing,
                    },
                    "summary": f"图表生成失败：缺少必填参数 {', '.join(missing)}。不要空参调用 create_diagram_artifact。",
                }

            direction = direction if direction in {"TB", "BT", "LR", "RL"} else "TB"
            layout_engine = (layout_engine or "graphviz").lower()
            diagram_type = _normalise_diagram_type(diagram_type)
            diagram_type = diagram_type if diagram_type in {
                "auto",
                "layered_architecture",
                "c4_context",
                "c4_container",
                "c4_component",
                "deployment",
                "process",
                "decision_tree",
                "data_flow",
            } else "auto"
            steps = steps or []
            edges = edges or []
            output_target = _normalise_output_target(output_target)
            page_orientation = _normalise_page_orientation(page_orientation, steps)
            static_direction = _static_direction_for_word_a4(diagram_type, direction, page_orientation, steps)
            layout_warnings: List[str] = []
            static_dot_source: Optional[str] = None
            static_image_from_html = False

            if diagram_type == "layered_architecture":
                normalised_layers = self._normalise_layers(layers, steps)
                layout_warnings = _word_a4_layout_warnings(diagram_type, steps, normalised_layers)
                html_content = self._build_layered_architecture_html(
                    title,
                    normalised_layers,
                    edges,
                    notes,
                    font_scale=font_scale,
                )
                static_image_from_html = output_target == "word_a4"
                page_orientation = "landscape"
                render_engine = "layered_html"
            elif layout_engine == "mermaid" or (layout_engine == "auto" and mermaid and not steps):
                layout_warnings = _word_a4_layout_warnings(diagram_type, steps)
                mermaid_body = mermaid.strip() if mermaid else "flowchart TB\n  A[无步骤数据] --> B[请提供 steps 或 mermaid]"
                if not mermaid_body.startswith("flowchart "):
                    mermaid_body = f"flowchart {direction}\n{mermaid_body}"
                html_content = self._build_mermaid_html(title, mermaid_body, notes)
                static_dot_source = self._build_dot_from_steps(
                    steps,
                    edges,
                    static_direction,
                    title,
                    font_scale=font_scale,
                    output_target=output_target,
                    page_orientation=page_orientation,
                )
                render_engine = "mermaid"
            else:
                layout_warnings = _word_a4_layout_warnings(diagram_type, steps)
                dot_source = self._build_dot_from_steps(
                    steps,
                    edges,
                    direction,
                    title,
                    font_scale=font_scale,
                    output_target="html",
                    page_orientation=page_orientation,
                )
                static_dot_source = self._build_dot_from_steps(
                    steps,
                    edges,
                    static_direction,
                    title,
                    font_scale=font_scale,
                    output_target=output_target,
                    page_orientation=page_orientation,
                )
                try:
                    svg = self._render_graphviz_svg(dot_source)
                    html_content = self._build_graphviz_html(title, svg, notes)
                    render_engine = "graphviz"
                except Exception as graphviz_exc:
                    if mermaid:
                        mermaid_body = mermaid.strip()
                    else:
                        mermaid_body = "flowchart TB\n  A[Graphviz 渲染失败] --> B[请检查输入数据]"
                    if not mermaid_body.startswith("flowchart "):
                        mermaid_body = f"flowchart {direction}\n{mermaid_body}"
                    html_content = self._build_mermaid_html(
                        title,
                        mermaid_body + f"\n%% Graphviz fallback: {html.escape(str(graphviz_exc))}",
                        notes,
                    )
                    render_engine = "mermaid"

            data = html_artifact_service.create_artifact(
                artifact_id,
                html_content,
                title=title,
                metadata={
                    "artifact_kind": "diagram",
                    "diagram_type": diagram_type,
                    "direction": direction,
                    "layout_engine": render_engine,
                    "output_target": output_target,
                    "page_orientation": page_orientation,
                    "layout_warnings": layout_warnings,
                    "font_family": select_diagram_font_family(),
                    "generated_at": datetime.now().isoformat(),
                    "design_reference_paths": diagram_design_reference_paths(),
                    **(metadata or {}),
                },
            )
            static_image = None
            if output_target == "word_a4" and (static_image_from_html or static_dot_source):
                image_path = (
                    Path(data["artifact_dir"])
                    / "assets"
                    / _safe_asset_name(f"{data.get('artifact_id')}_word_a4")
                )
                try:
                    if static_image_from_html:
                        static_image = await self._render_html_word_a4_screenshot(
                            Path(data["file_path"]),
                            image_path,
                            page_orientation=page_orientation,
                        )
                    elif (
                        diagram_type in {"auto", "process"}
	                        and len(steps) > WORD_A4_LONG_PROCESS_THRESHOLD
	                        and page_orientation == "landscape"
	                    ):
	                        static_image = self._render_wrapped_process_png(steps, edges, title, image_path)
                    else:
                        static_image = self._render_graphviz_png(
                            static_dot_source,
                            image_path,
                            page_orientation=page_orientation,
                            output_target=output_target,
                        )
                    static_image["relative_path"] = str(image_path.relative_to(Path(data["artifact_dir"])))
                    image_url = f"/api/html-artifacts/{data.get('artifact_id')}/{static_image['relative_path']}"
                    data["static_image_path"] = static_image["path"]
                    data["static_image_url"] = image_url
                    data["assets"] = [static_image]
                    data["visuals"] = [
                        {
                            "id": f"{data.get('artifact_id')}_word_a4",
                            "image_id": f"{data.get('artifact_id')}_word_a4",
                            "title": title,
                            "type": "image",
                            "image_url": image_url,
                            "url": image_url,
                            "data": {
                                "url": image_url,
                                "local_path": static_image["path"],
                            },
                            "markdown_image": f"![{title}]({image_url})",
                            "local_path": static_image["path"],
                            "format": "png",
                            "output_target": output_target,
                            "page_orientation": page_orientation,
                        }
                    ]
                except Exception as png_exc:
                    layout_warnings.append("static_image_render_failed")
                    data["static_image_error"] = str(png_exc)
            data.pop("download_url", None)
            data.pop("share_endpoint", None)
            attach_document_artifact(
                data,
                data.get("static_image_path") or data["file_path"],
                kind="image" if data.get("static_image_path") else "html_artifact",
                format="png" if data.get("static_image_path") else "html",
                title=title,
                preview_key="html_preview",
                generator=self.name,
                metadata={
                    "artifact_id": data.get("artifact_id"),
                    "artifact_kind": "diagram",
                    "layout_engine": render_engine,
                    "output_target": output_target,
                },
            )
            if static_image:
                data["artifact"]["html_file_path"] = data["file_path"]
                data["artifact"]["html_preview"] = data.get("html_preview")
            html_preview = data.get("html_preview")
            return {
                "status": "success",
                "success": True,
                "data": data,
                "visuals": data.get("visuals", []),
                "html_preview": html_preview,
                "file_path": data.get("file_path"),
                "file_type": data.get("file_type", "html_artifact"),
                "artifact": data.get("artifact"),
                "artifacts": data.get("artifacts", []),
                "metadata": {
                    "generator": self.name,
                    "schema_version": "diagram_html.v3",
                    "diagram_type": diagram_type,
                    "direction": direction,
                    "layout_engine": render_engine,
                    "output_target": output_target,
                    "page_orientation": page_orientation,
                    "layout_warnings": layout_warnings,
                    "static_image_path": data.get("static_image_path"),
                    "font_family": select_diagram_font_family(),
                    "artifact_id": data.get("artifact_id"),
                    "design_reference_paths": diagram_design_reference_paths(),
                },
                "summary": (
                    f"图表已生成：{data['artifact_id']}。"
                    + (f"Word A4 静态图路径：{data['static_image_path']}。" if data.get("static_image_path") else "右侧预览已可用。")
                ),
            }
        except Exception as exc:
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "generator": self.name,
                    "schema_version": "diagram_html.v3",
                },
                "summary": f"图表生成失败: {exc}",
            }
