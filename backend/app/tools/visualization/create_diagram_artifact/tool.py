"""Tool for creating diagram artifacts with SVG, Draw.io, and template exports."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime
from datetime import date as date_cls
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageChops, ImageDraw, ImageFont

from app.tools.artifact_utils import (
    attach_document_artifact,
    build_artifact_resume_context,
    build_document_artifact,
)
from app.services.html_artifact_service import _safe_artifact_id, html_artifact_service
from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.visualization.create_diagram_artifact.freeform_exporter import export_freeform_diagram
from app.tools.visualization.create_diagram_artifact.freeform_models import (
    FreeformValidationError,
    normalize_freeform_diagram,
)
from app.tools.visualization.create_diagram_artifact.freeform_postprocessor import (
    postprocess_freeform_diagram,
)
from app.tools.visualization.font_sizing import FontScale, resolve_font_scale


DOT_ID_PATTERN = re.compile(r"[^A-Za-z0-9_]")
REFERENCE_ROOT = Path(__file__).resolve().parent / "references"
COMPACT_LAYER_ITEM_THRESHOLD = 12
COMPACT_GROUP_THRESHOLD = 6
WORD_A4_ARCHITECTURE_ITEM_THRESHOLD = 20
WORD_A4_PORTRAIT_SIZE = "6.4,9.2"
WORD_A4_LANDSCAPE_SIZE = "9.2,6.4"
WORD_A4_PORTRAIT_PX = (1240, 1754)
WORD_A4_LANDSCAPE_PX = (1754, 1240)
WORD_A4_LONG_PROCESS_THRESHOLD = 12
WORD_A4_PROCESS_LAYER_THRESHOLD = 8
WORD_A4_GANTT_TASK_THRESHOLD = 10
WORD_A4_GANTT_LAYER_THRESHOLD = 6
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
NODE_SHAPES = {"rectangle", "database", "cloud", "document", "queue"}
DATABASE_ICON_TOKENS = {"database", "timeseries", "warehouse", "object-storage", "lake", "storage"}
DEFAULT_DIAGRAM_FONT_SCALE = 2.0
AUTO_CENTER_FREEFORM_INTENTS = {"architecture", "system_architecture", "layered_architecture", "topology"}


def diagram_design_reference_paths() -> Dict[str, str]:
    """Return stable reference keys Agent can read before creating diagrams."""
    return {
        "index": "create_diagram_artifact/references/index.md",
        "architecture": "create_diagram_artifact/references/architecture.md",
        "process": "create_diagram_artifact/references/process.md",
        "decision_tree": "create_diagram_artifact/references/decision-tree.md",
        "data_flow": "create_diagram_artifact/references/data-flow.md",
        "mind_map": "create_diagram_artifact/references/mind-map.md",
        "gantt": "create_diagram_artifact/references/gantt.md",
        "layered_system": "create_diagram_artifact/references/layered-system.md",
        "freeform_index": "create_diagram_artifact/references/freeform-index.md",
        "freeform_primitives": "create_diagram_artifact/references/freeform-primitives.md",
        "freeform_architecture": "create_diagram_artifact/references/freeform-architecture.md",
        "freeform_checklist": "create_diagram_artifact/references/freeform-checklist.md",
        "icon_catalog": "create_diagram_artifact/references/icon-catalog.md",
        "checklist": "create_diagram_artifact/references/checklist.md",
    }


def _normalise_diagram_type(diagram_type: str | None) -> str:
    mapping = {
        "layered_system": "layered_architecture",
        "architecture": "layered_architecture",
        "system_architecture": "layered_architecture",
        "flowchart": "process",
        "mindmap": "mind_map",
        "mind-map": "mind_map",
        "gantt_chart": "gantt",
        "gantt-chart": "gantt",
    }
    value = (diagram_type or "auto").strip().lower()
    return mapping.get(value, value)


def _freeform_postprocess_options(
    diagram_intent: Optional[str],
    postprocess: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    options = dict(postprocess or {})
    intent = str(diagram_intent or "").strip().lower()
    if intent in AUTO_CENTER_FREEFORM_INTENTS and "center_group_children" not in options:
        options["center_group_children"] = True
    return options or postprocess


def _scaled_int(value: int, font_scale: FontScale = None) -> int:
    return int(round(value * resolve_font_scale(font_scale)))


def resolve_diagram_font_scale(font_scale: FontScale = None) -> float:
    if font_scale is None:
        return DEFAULT_DIAGRAM_FONT_SCALE
    return resolve_font_scale(font_scale)


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


def diagram_css_font_face() -> str:
    font_path = select_diagram_font_path(bold=False)
    if not font_path:
        return ""
    font_uri = Path(font_path).resolve().as_uri()
    font_family = select_diagram_font_family()
    return (
        "@font-face { "
        f"font-family: \"{font_family}\"; "
        f"src: url(\"{font_uri}\"); "
        "font-weight: 400 800; "
        "font-style: normal; "
        "font-display: swap; "
        "}"
    )


def _sanitize_dot_id(raw_id: Any, index: int) -> str:
    text = DOT_ID_PATTERN.sub("_", str(raw_id or "")).strip("_")
    if not text:
        text = f"n{index + 1}"
    if text[0].isdigit():
        text = f"n_{text}"
    return text


def _safe_asset_name(value: str, suffix: str = ".png") -> str:
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip()).strip("_")
    return f"{name or 'diagram'}{suffix}"


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
    if diagram_type in {"process", "decision_tree", "data_flow", "auto"} and len(steps or []) > WORD_A4_PROCESS_LAYER_THRESHOLD:
        warnings.append("process_layers_exceed_a4_recommended")
    if diagram_type == "gantt":
        phases = {
            str(step.get("phase") or step.get("group") or "计划")
            for step in steps or []
        }
        if len(steps or []) > WORD_A4_GANTT_TASK_THRESHOLD:
            warnings.append("gantt_tasks_exceed_a4_recommended")
        if len(phases) > WORD_A4_GANTT_LAYER_THRESHOLD:
            warnings.append("gantt_layers_exceed_a4_recommended")
    total_layer_items = 0
    for layer in layers or []:
        item_count = sum(len(group.get("items") or []) for group in layer.get("groups") or [])
        total_layer_items += item_count
        if item_count > COMPACT_LAYER_ITEM_THRESHOLD:
            warnings.append("dense_layer_split_recommended")
            break
    if diagram_type in {"layered_architecture", "architecture", "layered_system"} and total_layer_items > WORD_A4_ARCHITECTURE_ITEM_THRESHOLD:
        warnings.append("architecture_modules_exceed_a4_recommended")
    return warnings


def _layout_warning_summary(warnings: List[str]) -> str:
    if not warnings:
        return ""
    return "布局告警：" + "、".join(warnings) + "。建议 Agent 调整层级或减少同图模块后重新绘制。"


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


def _normalise_node_shape(value: Any, icon: str = "") -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "rect": "rectangle",
        "box": "rectangle",
        "cylinder": "database",
        "db": "database",
        "data-store": "database",
        "file": "document",
        "page": "document",
        "message": "queue",
        "mq": "queue",
    }
    shape = aliases.get(text, text)
    if shape in NODE_SHAPES:
        return shape
    if icon in DATABASE_ICON_TOKENS:
        return "database"
    if icon == "cloud":
        return "cloud"
    if icon in {"file", "report"}:
        return "document"
    if icon == "message":
        return "queue"
    return "rectangle"


def _normalise_process_shape(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "rect": "rectangle",
        "box": "rectangle",
        "rounded": "rectangle",
        "start": "stadium",
        "end": "stadium",
        "terminator": "stadium",
        "decision": "diamond",
        "database": "database",
        "cylinder": "database",
        "document": "document",
        "file": "document",
        "queue": "queue",
        "message": "queue",
        "cloud": "cloud",
    }
    shape = aliases.get(text, text)
    return shape if shape in {"rectangle", "stadium", "diamond", "database", "document", "queue", "cloud"} else "rectangle"


def _parse_gantt_date(value: Any, fallback: date_cls) -> date_cls:
    text = str(value or "").strip()
    if not text:
        return fallback
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return fallback


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
    """Create editable diagram artifacts with type-specific renderers."""

    def __init__(self, name: str = "create_diagram_artifact"):
        super().__init__(
            name=name,
            description=(
                "先判断 diagram_mode。template 模式输出 HTML+WordA4/Draw.io，先读 "
                "create_diagram_artifact/references/index.md 和对应模板/checklist；"
                "freeform 模式输出可编辑 Draw.io、SVG 预览和 PNG 兜底，先读 "
                "create_diagram_artifact/references/freeform-index.md 和 "
                "freeform-primitives.md；架构/拓扑类再读 freeform-architecture.md，"
                "最后读 freeform-checklist.md。所有图表必须先写大纲、再生成、"
                "再 QA、必要修改后才最终提交。"
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
                    "operation": {
                        "type": "string",
                        "enum": ["create", "patch", "validate", "render"],
                        "default": "create",
                        "description": "create 新建；patch 基于上一版 diagram_plan 局部修改；validate 仅质量检查；render 只按已有 plan 重新导出 Draw.io/SVG/PNG。",
                    },
                    "artifact_id": {
                        "type": "string",
                        "description": "图表产物 ID；create/patch/validate/render 均必须显式传入。",
                    },
                    "title": {
                        "type": "string",
                        "description": "新建图表时的标题；patch/render 可从 base_plan_path 中沿用。",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["TB", "BT", "LR", "RL"],
                    },
                    "page_orientation": {
                        "type": "string",
                        "enum": ["auto", "portrait", "landscape"],
                    },
                    "diagram_mode": {
                        "type": "string",
                        "enum": ["template", "freeform"],
                        "description": "Defaults to freeform. Use template only when explicitly requesting the built-in layered/process/data-flow templates.",
                    },
                    "diagram_intent": {
                        "type": "string",
                        "enum": [
                            "architecture",
                            "process",
                            "mind_map",
                            "data_flow",
                            "topology",
                            "org_chart",
                            "custom",
                        ],
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
                            "mind_map",
                            "gantt",
                        ],
                    },
                    "layers": {
                        "type": "array",
                        "description": "Layered groups/items. Item shape: rectangle/database/cloud/document/queue; database=cylinder.",
                        "items": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": True,
                        },
                    },
                    "steps": {
                        "type": "array",
                        "description": "Nodes/tasks/tree. Fields: id,label,shape,group,children,parent_id,parent,start,end,duration,phase,owner,progress.",
                        "items": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": True,
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
                        "oneOf": [
                            {"type": "string", "enum": ["small", "normal", "large", "xlarge"]},
                            {"type": "number", "minimum": 0.8, "maximum": 1.6},
                        ],
                    },
                    "metadata": {
                        "type": "object",
                    },
                    "canvas": {
                        "type": "object",
                        "description": "Freeform canvas settings, including width, height, grid, and background.",
                        "additionalProperties": True,
                    },
                    "shapes": {
                        "type": "array",
                        "description": "Freeform shapes with id, type, label, x, y, width, height, and optional Draw.io fields.",
                        "items": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": True,
                        },
                    },
                    "connectors": {
                        "type": "array",
                        "description": "Freeform connectors with id, from, to, label, and type.",
                        "items": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": True,
                        },
                    },
                    "groups": {
                        "type": "array",
                        "description": "Freeform grouping containers with id, label, children, x, y, width, and height.",
                        "items": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": True,
                        },
                    },
                    "postprocess": {
                        "type": "object",
                        "description": "Freeform deterministic cleanup options. Set enabled=false to preserve raw Agent layout exactly. center_group_children=true horizontally centers each row of group children.",
                        "additionalProperties": True,
                    },
                    "base_plan_path": {
                        "type": "string",
                        "description": "patch/render/validate 用。上一版 data.diagram_plan_path 或 data.next_revision_base_plan_path。",
                    },
                    "diagram_plan_path": {
                        "type": "string",
                        "description": "base_plan_path 的别名，用于读取已有 diagram_plan.v*.json。",
                    },
                    "diagram_patch": {
                        "type": "object",
                        "description": "operation=patch 用。支持 replace_shapes/add_shapes/remove_shapes、replace_connectors/add_connectors/remove_connectors、replace_groups/add_groups/remove_groups。",
                        "additionalProperties": True,
                    },
                    "diagram_patch_path": {
                        "type": "string",
                        "description": "长补丁用。JSON 文件路径，内容为 diagram_patch 对象。",
                    },
                },
                "required": ["artifact_id"],
            },
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
                    device_scale_factor=2,
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
                raw_output_path = output_path.with_name(f"{output_path.stem}.raw.png")
                content_locator = page.locator(".wrap")
                content_size = await content_locator.evaluate(
                    """
                    element => {
                        const rect = element.getBoundingClientRect();
                        return {
                            width: Math.ceil(Math.max(rect.width, element.scrollWidth || 0)),
                            height: Math.ceil(Math.max(rect.height, element.scrollHeight || 0))
                        };
                    }
                    """
                )
                if isinstance(content_size, dict):
                    content_width = int(content_size.get("width") or viewport_width)
                    content_height = int(content_size.get("height") or viewport_height)
                    await page.set_viewport_size({
                        "width": max(320, content_width),
                        "height": max(240, content_height),
                    })
                    await page.wait_for_timeout(100)
                await content_locator.screenshot(path=str(raw_output_path), type="png")
                self._compose_word_a4_png(raw_output_path, output_path, page_orientation)
                try:
                    raw_output_path.unlink()
                except OSError:
                    pass
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
        rgb_image = image.convert("RGB")
        white_background = Image.new("RGB", rgb_image.size, "white")
        content_bbox = ImageChops.difference(rgb_image, white_background).getbbox()
        if content_bbox:
            image = image.crop(content_bbox)

        max_width = int(canvas_size[0] * 0.99)
        max_height = int(canvas_size[1] * 0.99)
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
        final_bbox = ImageChops.difference(canvas, Image.new("RGB", canvas.size, "white")).getbbox()
        if final_bbox:
            canvas = canvas.crop(final_bbox)
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
        icon = _normalise_icon(item.get("icon"))
        return {
            "label": str(item.get("label") or item.get("name") or "").strip(),
            "detail": str(item.get("detail") or item.get("description") or "").strip(),
            "icon": icon,
            "shape": _normalise_node_shape(item.get("shape"), icon),
            "role": _normalise_role(item.get("role")),
            "emphasis": _normalise_emphasis(item.get("emphasis")),
            "variant": _normalise_variant(item.get("variant")),
        }

    def _render_drawio_node_html(
        self,
        item: Dict[str, Any],
        *,
        icon_visible: bool,
        extra_classes: Optional[List[str]] = None,
    ) -> str:
        detail = str(item.get("detail") or "").strip()
        detail_html = f"<p>{html.escape(detail)}</p>" if detail else ""
        icon_html = _diagram_icon_svg(str(item.get("icon") or "")) if icon_visible else ""
        icon_symbol_html = f"<span class=\"module-symbol\">{icon_html}</span>" if icon_html else ""
        shape = _normalise_node_shape(item.get("shape"), str(item.get("icon") or ""))
        item_classes = ["drawio-node", "module-item", f"drawio-shape-{shape}"]
        item_classes.extend(extra_classes or [])
        if not icon_symbol_html:
            item_classes.append("drawio-node-no-icon")
        emphasis = _normalise_emphasis(item.get("emphasis"))
        variant = _normalise_variant(item.get("variant"))
        role = _normalise_role(item.get("role"))
        if emphasis != "normal":
            item_classes.append(f"drawio-node-emphasis-{emphasis}")
        if variant != "default":
            item_classes.append(f"drawio-node-variant-{variant}")
        if role:
            item_classes.append(f"drawio-node-role-{role}")
        label = html.escape(str(item.get("label") or ""))
        return (
            f"<article data-label=\"{label}\" data-shape=\"{html.escape(shape)}\" class=\"{html.escape(' '.join(item_classes))}\">"
            f"{icon_symbol_html}"
            f"<strong class=\"drawio-node-label module-label\">{label}</strong>"
            f"{detail_html}"
            "</article>"
        )

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

    def _build_drawio_shell_html(
        self,
        *,
        title: str,
        meta: str,
        body_html: str,
        component_css: str,
        notes: str | None = None,
        font_scale: FontScale = None,
    ) -> str:
        safe_title = html.escape(title)
        safe_font_scale = f"{resolve_diagram_font_scale(font_scale):.3f}"
        css_font_stack = diagram_css_font_stack()
        css_font_face = diagram_css_font_face()

        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    {css_font_face}
    :root {{
      color-scheme: light;
      --paper: #ffffff;
      --text: #202124;
      --muted: #4b5563;
      --line: #333333;
      --node-border: #5f6368;
      --font-scale: {safe_font_scale};
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: {css_font_stack}; background: #ffffff; color: var(--text); }}
    .wrap {{ width: 1440px; margin: 0 auto; padding: 16px; background: var(--paper); }}
    .header {{ display: flex; align-items: center; margin-bottom: 10px; border-bottom: 1px solid #d6dbe3; padding-bottom: 8px; }}
    h1 {{ margin: 0; font-size: calc(24px * var(--font-scale)); line-height: 1.2; font-weight: 700; letter-spacing: 0; color: var(--text); }}
    .canvas {{ position: relative; border: 1px solid #c9cdd3; background: var(--paper); padding: 18px; min-height: 720px; }}
    {component_css}
    @media (max-width: 760px) {{
      .wrap {{ width: 100%; padding: 10px; }}
      .header {{ display: block; }}
      .canvas {{ padding: 12px; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="header">
      <h1>{safe_title}</h1>
    </header>
    <main class="canvas">
      {body_html}
    </main>
  </div>
</body>
</html>
"""

    def _build_process_html(
        self,
        title: str,
        steps: List[Dict[str, Any]],
        edges: Optional[List[Dict[str, Any]]] = None,
        notes: str | None = None,
        direction: str = "TB",
        diagram_type: str = "process",
        font_scale: FontScale = None,
    ) -> str:
        ordered_steps = steps or [{"id": "empty", "label": "请提供步骤", "shape": "stadium"}]
        edge_by_pair = {
            (str(edge.get("from") or ""), str(edge.get("to") or "")): edge
            for edge in edges or []
        }
        step_keys = [
            str(step.get("id") or step.get("label") or f"s{index}")
            for index, step in enumerate(ordered_steps)
        ]
        rendered_pairs = set()
        items_html: List[str] = []
        is_lr = direction in {"LR", "RL"}
        should_wrap = (
            diagram_type in {"auto", "process"}
            and not is_lr
            and len(ordered_steps) > WORD_A4_PROCESS_LAYER_THRESHOLD
        )

        def render_node(step: Dict[str, Any], index: int) -> str:
            key = str(step.get("id") or step.get("label") or f"s{index}")
            label = html.escape(str(step.get("label") or key))
            detail = str(step.get("detail") or step.get("description") or "").strip()
            detail_html = f"<p>{html.escape(detail)}</p>" if detail else ""
            shape = _normalise_process_shape(step.get("shape"))
            emphasis = _normalise_emphasis(step.get("emphasis"))
            classes = [
                "drawio-process-node",
                "drawio-node",
                f"drawio-process-shape-{shape}",
            ]
            if emphasis != "normal":
                classes.append(f"drawio-node-emphasis-{emphasis}")
            return (
                f"<article data-node-id=\"{html.escape(key)}\" data-shape=\"{html.escape(shape)}\" "
                f"class=\"{html.escape(' '.join(classes))}\">"
                f"<div class=\"drawio-process-node-inner\">"
                f"<strong class=\"drawio-node-label module-label\">{label}</strong>"
                f"{detail_html}"
                f"</div>"
                "</article>"
            )

        def render_link(edge: Dict[str, Any] | None = None) -> str:
            edge = edge or {}
            label = str(edge.get("label") or "").strip()
            style = "dashed" if edge.get("style") == "dashed" else "solid"
            strength = _normalise_flow_strength(edge.get("flow_strength"))
            classes = ["drawio-process-link", f"drawio-process-link-{style}"]
            if strength == "strong":
                classes.append("drawio-process-link-strong")
            label_html = (
                f"<span class=\"drawio-process-edge-label\">{html.escape(label)}</span>"
                if label
                else ""
            )
            return f"<div class=\"{html.escape(' '.join(classes))}\" aria-hidden=\"true\"><i></i>{label_html}</div>"

        if should_wrap:
            row_html = []
            rows = _chunked(ordered_steps, WORD_A4_PROCESS_ROW_SIZE)
            for row_index, row in enumerate(rows):
                row_start = row_index * WORD_A4_PROCESS_ROW_SIZE
                indexed_row = list(enumerate(row, start=row_start))
                visual_row = list(reversed(indexed_row)) if row_index % 2 else indexed_row
                row_items = []
                for visual_index, (source_index, step) in enumerate(visual_row):
                    row_items.append(render_node(step, source_index))
                    if visual_index >= len(visual_row) - 1:
                        continue
                    current_key = str(step.get("id") or step.get("label") or f"s{source_index}")
                    next_index, next_step = visual_row[visual_index + 1]
                    next_key = str(next_step.get("id") or next_step.get("label") or f"s{next_index}")
                    pair = (current_key, next_key) if row_index % 2 == 0 else (next_key, current_key)
                    rendered_pairs.add(pair)
                    row_items.append(render_link(edge_by_pair.get(pair)))
                row_direction = "reverse" if row_index % 2 else "forward"
                row_html.append(
                    f"<div class=\"drawio-process-row drawio-process-row-{row_direction}\">{''.join(row_items)}</div>"
                )
                if row_index < len(rows) - 1:
                    row_html.append("<div class=\"drawio-process-row-connector\" aria-hidden=\"true\"><i></i></div>")
            items_html.append(f"<div class=\"drawio-process-wrap-grid\">{''.join(row_html)}</div>")
        else:
            for index, step in enumerate(ordered_steps):
                items_html.append(render_node(step, index))
                if index >= len(ordered_steps) - 1:
                    continue
                pair = (step_keys[index], step_keys[index + 1])
                rendered_pairs.add(pair)
                items_html.append(render_link(edge_by_pair.get(pair)))

        orientation_class = "drawio-process-wrapped" if should_wrap else ("drawio-process-lr" if is_lr else "drawio-process-tb")
        body_html = (
            f"<section class=\"drawio-process {orientation_class}\" data-diagram-type=\"{html.escape(diagram_type)}\">"
            f"<div class=\"drawio-process-main\">{''.join(items_html)}</div>"
            "</section>"
        )
        component_css = """
    .drawio-process { min-height: 650px; display: flex; align-items: center; justify-content: center; }
    .drawio-process-main { display: flex; align-items: center; justify-content: center; gap: 0; width: 100%; }
    .drawio-process-tb .drawio-process-main { flex-direction: column; }
    .drawio-process-lr .drawio-process-main { flex-direction: row; overflow: hidden; }
    .drawio-process-wrapped { min-height: 650px; align-items: center; }
    .drawio-process-wrapped .drawio-process-main { display: block; width: 100%; }
    .drawio-process-wrap-grid { display: grid; gap: 12px; width: 100%; align-content: center; }
    .drawio-process-row { display: flex; align-items: center; justify-content: center; gap: 0; min-height: 92px; }
    .drawio-process-row-connector { position: relative; height: 28px; }
    .drawio-process-row-connector i { position: absolute; left: 50%; top: 0; width: 1.5px; height: 24px; background: var(--line); }
    .drawio-process-row-connector i::after { content: ""; position: absolute; left: -5px; bottom: -1px; border-left: 6px solid transparent; border-right: 6px solid transparent; border-top: 8px solid var(--line); }
    .drawio-process-node { position: relative; width: 184px; min-height: 58px; border: 1.4px solid var(--node-border); background: #ffffff; color: #1f2937; display: flex; align-items: center; justify-content: center; text-align: center; padding: 9px 14px; overflow: hidden; }
    .drawio-process-node-inner { position: relative; z-index: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px; }
    .drawio-process-node p { margin: 0; font-size: calc(10px * var(--font-scale)); line-height: 1.2; color: #4b5563; }
    .drawio-process-shape-rectangle { border-radius: 5px; }
    .drawio-process-shape-stadium, .drawio-process-shape-queue { border-radius: 999px; }
    .drawio-process-shape-diamond { width: 128px; height: 128px; padding: 0; transform: rotate(45deg); }
    .drawio-process-shape-diamond .drawio-process-node-inner { width: 88px; transform: rotate(-45deg); }
    .drawio-process-shape-database { min-height: 68px; padding-top: 20px; border-radius: 50% / 13px; }
    .drawio-process-shape-database::before { content: ""; position: absolute; left: -1.4px; right: -1.4px; top: -1.4px; height: 21px; border: 1.4px solid var(--node-border); border-radius: 50%; background: inherit; }
    .drawio-process-shape-cloud { border-radius: 999px 999px 820px 820px; min-height: 66px; }
    .drawio-process-shape-document { border-radius: 3px; }
    .drawio-process-shape-document::after { content: ""; position: absolute; right: -1px; top: -1px; width: 20px; height: 20px; border-left: 1.4px solid var(--node-border); border-bottom: 1.4px solid var(--node-border); background: #f3f4f6; }
    .drawio-process-link { position: relative; flex: 0 0 56px; height: 56px; color: #374151; font-size: calc(11px * var(--font-scale)); }
    .drawio-process-tb .drawio-process-link i { position: absolute; left: 50%; top: 4px; width: 1.5px; height: 46px; background: var(--line); }
    .drawio-process-tb .drawio-process-link i::after { content: ""; position: absolute; left: -5px; bottom: -1px; border-left: 6px solid transparent; border-right: 6px solid transparent; border-top: 8px solid var(--line); }
    .drawio-process-lr .drawio-process-link i { position: absolute; left: 4px; top: 50%; width: 46px; height: 1.5px; background: var(--line); }
    .drawio-process-lr .drawio-process-link i::after { content: ""; position: absolute; right: -1px; top: -5px; border-top: 6px solid transparent; border-bottom: 6px solid transparent; border-left: 8px solid var(--line); }
    .drawio-process-wrapped .drawio-process-link i { position: absolute; left: 4px; top: 50%; width: 46px; height: 1.5px; background: var(--line); }
    .drawio-process-wrapped .drawio-process-link i::after { content: ""; position: absolute; right: -1px; top: -5px; border-top: 6px solid transparent; border-bottom: 6px solid transparent; border-left: 8px solid var(--line); }
    .drawio-process-row-reverse .drawio-process-link i::after { left: -1px; right: auto; border-left: 0; border-right: 8px solid var(--line); }
    .drawio-process-link-dashed i { background: repeating-linear-gradient(to bottom, var(--line) 0 6px, transparent 6px 10px); }
    .drawio-process-lr .drawio-process-link-dashed i { background: repeating-linear-gradient(to right, var(--line) 0 6px, transparent 6px 10px); }
    .drawio-process-link-strong i { width: 2px; }
    .drawio-process-edge-label { position: absolute; left: calc(50% + 14px); top: 50%; transform: translateY(-50%); max-width: 112px; padding: 1px 5px; background: #ffffff; border: 1px solid #c9cdd3; white-space: normal; overflow-wrap: anywhere; text-align: center; line-height: 1.15; font-size: calc(8px * var(--font-scale)); color: #374151; }
    .drawio-process-lr .drawio-process-edge-label { left: 50%; top: calc(50% - 24px); transform: translateX(-50%); }
    @media (max-width: 760px) {
      .drawio-process-main { transform: scale(0.86); transform-origin: top center; }
      .drawio-process-lr .drawio-process-main { flex-direction: column; }
    }
"""
        return self._build_drawio_shell_html(
            title=title,
            meta=f"Process Diagram · draw.io style · 总层数：{len(ordered_steps)}层",
            body_html=body_html,
            component_css=component_css,
            notes=notes,
            font_scale=font_scale,
        )

    def _build_mind_map_html(
        self,
        title: str,
        steps: List[Dict[str, Any]],
        notes: str | None = None,
        font_scale: FontScale = None,
    ) -> str:
        def nested_children(step: Dict[str, Any]) -> List[Dict[str, Any]]:
            for child_key in ("children", "branches", "topics", "items"):
                children = step.get(child_key)
                if isinstance(children, list):
                    return [child for child in children if isinstance(child, dict)]
            return []

        source_steps: List[Dict[str, Any]] = []

        def append_step(step: Dict[str, Any], parent_key: str = "", index_path: str = "0") -> None:
            children = nested_children(step)
            node = {key: value for key, value in step.items() if key not in {"children", "branches", "topics", "items"}}
            key = str(node.get("id") or node.get("label") or f"n{index_path}").strip() or f"n{index_path}"
            if parent_key and not (node.get("parent_id") or node.get("parent")):
                node["parent_id"] = parent_key
            source_steps.append(node)
            for child_index, child in enumerate(children):
                append_step(child, key, f"{index_path}_{child_index}")

        for index, step in enumerate(steps or [{"id": "root", "label": title}]):
            append_step(step, index_path=str(index))

        node_by_key: Dict[str, Dict[str, Any]] = {}
        ordered_keys: List[str] = []
        for index, step in enumerate(source_steps):
            key = str(step.get("id") or step.get("label") or f"n{index}")
            if key in node_by_key:
                key = f"{key}_{index}"
            node_by_key[key] = {**step, "_key": key}
            ordered_keys.append(key)

        root_key = ""
        for key in ordered_keys:
            parent = str(node_by_key[key].get("parent_id") or node_by_key[key].get("parent") or "").strip()
            if not parent:
                root_key = key
                break
        if not root_key and ordered_keys:
            root_key = ordered_keys[0]

        children_by_parent: Dict[str, List[str]] = {key: [] for key in ordered_keys}
        for key in ordered_keys:
            if key == root_key:
                continue
            parent = str(node_by_key[key].get("parent_id") or node_by_key[key].get("parent") or "").strip()
            if parent and parent in node_by_key:
                children_by_parent.setdefault(parent, []).append(key)
            else:
                children_by_parent.setdefault(root_key, []).append(key)

        def render_topic(key: str, depth: int = 0) -> str:
            node = node_by_key[key]
            label = html.escape(str(node.get("label") or key))
            detail = str(node.get("detail") or node.get("description") or "").strip()
            detail_html = f"<p>{html.escape(detail)}</p>" if detail else ""
            child_html = "".join(render_topic(child_key, depth + 1) for child_key in children_by_parent.get(key, []))
            children_html = f"<div class=\"drawio-mind-children\">{child_html}</div>" if child_html else ""
            return (
                f"<section class=\"drawio-mind-child\" data-depth=\"{depth}\" data-node-id=\"{html.escape(key)}\">"
                "<i class=\"drawio-mind-connector\" aria-hidden=\"true\"></i>"
                "<div class=\"drawio-mind-topic\">"
                f"<strong class=\"drawio-node-label module-label\">{label}</strong>"
                f"{detail_html}"
                "</div>"
                f"{children_html}"
                "</section>"
            )

        root_label = html.escape(str(node_by_key.get(root_key, {}).get("label") or title))
        root_detail = str(node_by_key.get(root_key, {}).get("detail") or node_by_key.get(root_key, {}).get("description") or "").strip()
        root_detail_html = f"<p>{html.escape(root_detail)}</p>" if root_detail else ""
        root_children = children_by_parent.get(root_key, [])
        left_keys = [key for index, key in enumerate(root_children) if index % 2 == 0]
        right_keys = [key for index, key in enumerate(root_children) if index % 2 == 1]
        left_html = "".join(render_topic(key, 1) for key in left_keys)
        right_html = "".join(render_topic(key, 1) for key in right_keys)
        body_html = (
            "<section class=\"drawio-mind-map\">"
            f"<div class=\"drawio-mind-side drawio-mind-left\">{left_html}</div>"
            "<article class=\"drawio-mind-center drawio-node\">"
            f"<strong class=\"drawio-node-label module-label\">{root_label}</strong>"
            f"{root_detail_html}"
            "</article>"
            f"<div class=\"drawio-mind-side drawio-mind-right\">{right_html}</div>"
            "</section>"
        )
        component_css = """
    .drawio-mind-map { min-height: 650px; display: grid; grid-template-columns: 1fr 230px 1fr; gap: 28px; align-items: center; }
    .drawio-mind-center { min-height: 92px; border: 1.6px solid #315f87; background: #e8f3fb; border-radius: 6px; padding: 16px 20px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; color: #123047; }
    .drawio-mind-center p, .drawio-mind-topic p { margin: 4px 0 0; font-size: calc(10px * var(--font-scale)); line-height: 1.2; color: #4b5563; }
    .drawio-mind-side { display: grid; gap: 16px; align-content: center; }
    .drawio-mind-left { justify-items: end; }
    .drawio-mind-right { justify-items: start; }
    .drawio-mind-child { position: relative; display: grid; gap: 8px; max-width: 310px; overflow: visible; }
    .drawio-mind-branch, .drawio-mind-topic { position: relative; min-width: 142px; max-width: 260px; min-height: 44px; border: 1.4px solid var(--node-border); background: #ffffff; border-radius: 5px; padding: 8px 12px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; color: #1f2937; }
    .drawio-mind-connector { position: absolute; top: 22px; width: 34px; border-top: 1.6px solid var(--line); z-index: 0; }
    .drawio-mind-left .drawio-mind-connector { right: -35px; }
    .drawio-mind-right .drawio-mind-connector { left: -35px; }
    .drawio-mind-children { display: grid; gap: 7px; margin-top: 1px; }
    .drawio-mind-left .drawio-mind-children { justify-items: end; padding-right: 24px; border-right: 1px solid #c9cdd3; }
    .drawio-mind-right .drawio-mind-children { justify-items: start; padding-left: 24px; border-left: 1px solid #c9cdd3; }
    .drawio-mind-children .drawio-mind-topic { min-width: 118px; min-height: 38px; background: #fbfbfc; }
    @media (max-width: 760px) {
      .drawio-mind-map { grid-template-columns: 1fr; gap: 14px; }
      .drawio-mind-left, .drawio-mind-right { justify-items: center; }
      .drawio-mind-center { order: -1; }
      .drawio-mind-connector { display: none; }
    }
"""
        return self._build_drawio_shell_html(
            title=title,
            meta="Mind Map · draw.io style",
            body_html=body_html,
            component_css=component_css,
            notes=notes,
            font_scale=font_scale,
        )

    def _build_gantt_html(
        self,
        title: str,
        steps: List[Dict[str, Any]],
        notes: str | None = None,
        font_scale: FontScale = None,
    ) -> str:
        fallback_start = datetime.now().date()
        tasks = []
        cursor = fallback_start
        for index, step in enumerate(steps or []):
            start = _parse_gantt_date(step.get("start"), cursor)
            duration_value = step.get("duration")
            try:
                duration_days = max(1, int(float(duration_value))) if duration_value not in {None, ""} else 1
            except (TypeError, ValueError):
                duration_days = 1
            end_fallback = date_cls.fromordinal(start.toordinal() + duration_days - 1)
            end = _parse_gantt_date(step.get("end"), end_fallback)
            if end < start:
                end = start
            cursor = date_cls.fromordinal(end.toordinal() + 1)
            try:
                progress = max(0, min(100, int(float(step.get("progress") or 0))))
            except (TypeError, ValueError):
                progress = 0
            tasks.append({
                "id": str(step.get("id") or step.get("label") or f"task-{index}"),
                "label": str(step.get("label") or f"任务 {index + 1}"),
                "phase": str(step.get("phase") or step.get("group") or "计划"),
                "owner": str(step.get("owner") or ""),
                "start": start,
                "end": end,
                "progress": progress,
            })

        if not tasks:
            tasks.append({
                "id": "task-1",
                "label": "待补充任务",
                "phase": "计划",
                "owner": "",
                "start": fallback_start,
                "end": fallback_start,
                "progress": 0,
            })

        min_date = min(task["start"] for task in tasks)
        max_date = max(task["end"] for task in tasks)
        total_days = max(1, max_date.toordinal() - min_date.toordinal() + 1)
        tick_count = min(6, total_days)
        ticks = []
        for index in range(tick_count):
            offset = round(index * (total_days - 1) / max(1, tick_count - 1))
            tick_date = date_cls.fromordinal(min_date.toordinal() + offset)
            left = (offset / total_days) * 100
            ticks.append(
                f"<span class=\"drawio-gantt-tick\" style=\"left:{left:.2f}%\">{html.escape(tick_date.isoformat())}</span>"
            )

        rows = []
        phase_order: List[str] = []
        for task in tasks:
            if task["phase"] not in phase_order:
                phase_order.append(task["phase"])
        phase_classes = {phase: f"phase-{index % 6}" for index, phase in enumerate(phase_order)}
        for task in tasks:
            start_offset = task["start"].toordinal() - min_date.toordinal()
            task_days = max(1, task["end"].toordinal() - task["start"].toordinal() + 1)
            left = (start_offset / total_days) * 100
            width = max(3.5, (task_days / total_days) * 100)
            owner_html = f"<small>{html.escape(task['owner'])}</small>" if task["owner"] else ""
            rows.append(
                "<div class=\"drawio-gantt-row\">"
                "<div class=\"drawio-gantt-task\">"
                f"<strong>{html.escape(task['label'])}</strong>"
                f"<span>{html.escape(task['phase'])}</span>"
                f"{owner_html}"
                "</div>"
                "<div class=\"drawio-gantt-lane\">"
                f"<div class=\"drawio-gantt-bar {phase_classes[task['phase']]}\" "
                f"style=\"left:{left:.2f}%; width:{width:.2f}%\" "
                f"data-start=\"{html.escape(task['start'].isoformat())}\" data-end=\"{html.escape(task['end'].isoformat())}\">"
                f"<i class=\"drawio-gantt-progress\" style=\"width:{task['progress']}%\"></i>"
                f"<b>{task['progress']}%</b>"
                "</div>"
                "</div>"
                "</div>"
            )

        body_html = (
            "<section class=\"drawio-gantt\">"
            "<div class=\"drawio-gantt-header\">"
            "<div class=\"drawio-gantt-task-head\">任务</div>"
            f"<div class=\"drawio-gantt-timeline\">{''.join(ticks)}</div>"
            "</div>"
            f"<div class=\"drawio-gantt-rows\">{''.join(rows)}</div>"
            "</section>"
        )
        component_css = """
    .drawio-gantt { min-height: 650px; display: flex; flex-direction: column; justify-content: center; gap: 10px; }
    .drawio-gantt-header, .drawio-gantt-row { display: grid; grid-template-columns: 230px minmax(0, 1fr); gap: 12px; align-items: stretch; }
    .drawio-gantt-task-head { border: 1px solid #c9cdd3; background: #eef1f5; padding: 8px 10px; font-size: calc(12px * var(--font-scale)); font-weight: 700; color: #374151; }
    .drawio-gantt-timeline { position: relative; border: 1px solid #c9cdd3; background: #ffffff; min-height: 38px; overflow: hidden; }
    .drawio-gantt-timeline::before { content: ""; position: absolute; inset: 0; background: repeating-linear-gradient(to right, transparent 0, transparent calc(16.66% - 1px), #e5e7eb calc(16.66% - 1px), #e5e7eb 16.66%); }
    .drawio-gantt-tick { position: absolute; top: 10px; transform: translateX(-50%); white-space: nowrap; font-size: calc(10px * var(--font-scale)); color: #4b5563; background: #ffffff; padding: 0 3px; }
    .drawio-gantt-rows { display: grid; gap: 8px; }
    .drawio-gantt-task { border: 1px solid #c9cdd3; background: #ffffff; min-height: 48px; padding: 7px 10px; display: grid; align-content: center; gap: 2px; }
    .drawio-gantt-task strong { font-size: calc(12px * var(--font-scale)); line-height: 1.18; color: #1f2937; }
    .drawio-gantt-task span, .drawio-gantt-task small { font-size: calc(10px * var(--font-scale)); color: #6b7280; }
    .drawio-gantt-lane { position: relative; min-height: 48px; border: 1px solid #d6dbe3; background: repeating-linear-gradient(to right, #ffffff 0, #ffffff calc(16.66% - 1px), #f3f4f6 calc(16.66% - 1px), #f3f4f6 16.66%); }
    .drawio-gantt-bar { position: absolute; top: 9px; height: 28px; border: 1.4px solid #5f6368; border-radius: 4px; background: #e7f0fb; overflow: hidden; display: flex; align-items: center; justify-content: flex-end; color: #1f2937; }
    .drawio-gantt-progress { position: absolute; left: 0; top: 0; bottom: 0; background: rgba(49, 95, 135, 0.28); }
    .drawio-gantt-bar b { position: relative; z-index: 1; padding: 0 6px; font-size: calc(10px * var(--font-scale)); font-weight: 650; }
    .phase-0 { background: #e7f0fb; }
    .phase-1 { background: #e5f2e5; }
    .phase-2 { background: #fff3cf; }
    .phase-3 { background: #eee4f4; }
    .phase-4 { background: #e8f6f9; }
    .phase-5 { background: #eef1f5; }
    @media (max-width: 760px) {
      .drawio-gantt-header, .drawio-gantt-row { grid-template-columns: 150px minmax(0, 1fr); }
      .drawio-gantt-tick { font-size: 9px; }
    }
"""
        return self._build_drawio_shell_html(
            title=title,
            meta=f"Gantt Chart · draw.io style · 总层数：{len(phase_order)}层 · 总任务：{len(tasks)}项",
            body_html=body_html,
            component_css=component_css,
            notes=notes,
            font_scale=font_scale,
        )

    def _build_layered_architecture_html(
        self,
        title: str,
        layers: List[Dict[str, Any]],
        edges: Optional[List[Dict[str, Any]]] = None,
        notes: str | None = None,
        font_scale: FontScale = None,
    ) -> str:
        safe_title = html.escape(title)
        safe_font_scale = f"{resolve_diagram_font_scale(font_scale):.3f}"
        css_font_stack = diagram_css_font_stack()
        css_font_face = diagram_css_font_face()
        palette = ["cyan", "blue", "green", "amber", "purple", "slate"]
        layer_id_to_label = {str(layer.get("id") or ""): str(layer.get("label") or "") for layer in layers}

        main_layers = [
            layer
            for layer in layers
            if _normalise_role(layer.get("role")) != "external"
            and _normalise_variant(layer.get("variant")) != "external"
        ]
        external_layers = [
            layer
            for layer in layers
            if _normalise_role(layer.get("role")) == "external"
            or _normalise_variant(layer.get("variant")) == "external"
        ]
        if not main_layers:
            main_layers = layers
            external_layers = []

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
        layer_count = len(main_layers)
        for index, layer in enumerate(main_layers):
            theme = layer.get("theme") or palette[index % len(palette)]
            groups_html = []
            layer_item_count = sum(len(group.get("items") or []) for group in layer.get("groups") or [])
            icon_policy = _normalise_icon_policy(layer.get("icon_policy"))
            if icon_policy == "show":
                layer_icons_visible = True
            elif icon_policy == "hide":
                layer_icons_visible = False
            else:
                layer_items = [
                    item
                    for group in layer.get("groups") or []
                    for item in group.get("items") or []
                ]
                all_items_have_icons = bool(layer_items) and all(str(item.get("icon") or "") for item in layer_items)
                layer_icons_visible = index >= max(0, layer_count - 2) or all_items_have_icons
            for group in layer.get("groups") or []:
                cards = []
                for item in group.get("items") or []:
                    cards.append(self._render_drawio_node_html(item, icon_visible=layer_icons_visible))
                group_classes = ["drawio-group"]
                if (
                    layer_item_count > COMPACT_LAYER_ITEM_THRESHOLD
                    or len(group.get("items") or []) > COMPACT_GROUP_THRESHOLD
                ):
                    group_classes.append("drawio-group-compact")
                groups_html.append(
                    f"<section class=\"{html.escape(' '.join(group_classes))}\">"
                    f"<h2>{html.escape(str(group.get('label') or '模块组'))}</h2>"
                    f"<div class=\"drawio-node-grid module-grid centered-grid\">{''.join(cards)}</div>"
                    "</section>"
                )

            connector = ""
            if index < len(main_layers) - 1:
                current_id = str(layer.get("id") or "")
                next_id = str(main_layers[index + 1].get("id") or "")
                forward_key = f"{current_id}->{next_id}"
                reverse_key = f"{next_id}->{current_id}"
                is_reverse_transition = reverse_key in edge_labels and forward_key not in edge_labels
                edge_key = reverse_key if is_reverse_transition else forward_key
                transition_label = edge_labels.get(edge_key) or ""
                transition_strength = edge_strengths.get(edge_key) or "normal"
                transition_classes = ["drawio-layer-link", "layer-transition"]
                if transition_strength == "strong":
                    transition_classes.append("drawio-layer-link-strong")
                if is_reverse_transition:
                    transition_classes.append("drawio-layer-link-reverse")
                label_html = f"<span>{html.escape(transition_label)}</span>" if transition_label else ""
                connector = (
                    f"<div data-edge=\"{html.escape(edge_key)}\" class=\"{html.escape(' '.join(transition_classes))}\" "
                    f"aria-hidden=\"true\"><i></i>{label_html}</div>"
                )
            layer_classes = ["drawio-layer", "layer-band", f"theme-{str(theme)}"]
            layer_variant = _normalise_variant(layer.get("variant"))
            layer_role = _normalise_role(layer.get("role"))
            if layer_variant != "default":
                layer_classes.append(f"drawio-layer-variant-{layer_variant}")
            if layer_role:
                layer_classes.append(f"drawio-layer-role-{layer_role}")
            if layer_item_count > COMPACT_LAYER_ITEM_THRESHOLD or len(layer.get("groups") or []) > 3:
                layer_classes.append("drawio-layer-compact")
            band_html.append(
                f"<section data-layer-id=\"{html.escape(str(layer.get('id') or ''))}\" class=\"{html.escape(' '.join(layer_classes))}\">"
                "<aside class=\"drawio-layer-title\">"
                f"<strong>{html.escape(str(layer.get('label') or ''))}</strong>"
                "</aside>"
                f"<div class=\"drawio-layer-content\">{''.join(groups_html)}</div>"
                f"</section>{connector}"
            )

        external_html = []
        for layer in external_layers:
            items_html = []
            for group in layer.get("groups") or []:
                for item in group.get("items") or []:
                    items_html.append(
                        self._render_drawio_node_html(
                            item,
                            icon_visible=False,
                            extra_classes=["drawio-external-node"],
                        )
                    )
            if not items_html:
                items_html.append(
                    self._render_drawio_node_html(
                        {"label": "外部系统", "shape": "rectangle"},
                        icon_visible=False,
                        extra_classes=["drawio-external-node"],
                    )
                )
            external_html.append(
                "<section class=\"drawio-external-panel\">"
                f"<h2>{html.escape(str(layer.get('label') or '外部系统'))}</h2>"
                f"<div class=\"drawio-external-items\">{''.join(items_html)}</div>"
                "</section>"
            )
        external_rail_html = (
            f"<aside class=\"drawio-external-rail\">{''.join(external_html)}</aside>"
            if external_html
            else ""
        )

        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
	  <title>{safe_title}</title>
	  <style>
	    {css_font_face}
	    :root {{
	      color-scheme: light;
	      --bg: #f7f8fb;
	      --paper: #ffffff;
	      --text: #202124;
	      --muted: #4b5563;
	      --line: #333333;
	      --node-border: #5f6368;
	      --font-scale: {safe_font_scale};
	    }}
	    * {{ box-sizing: border-box; }}
	    body {{ margin: 0; font-family: {css_font_stack}; background: var(--bg); color: var(--text); }}
	    .wrap {{ width: 1440px; margin: 0 auto; padding: 16px; background: var(--paper); }}
	    .header {{ display: flex; align-items: center; margin-bottom: 10px; border-bottom: 1px solid #d6dbe3; padding-bottom: 8px; }}
	    h1 {{ margin: 0; font-size: calc(24px * var(--font-scale)); line-height: 1.2; font-weight: 700; letter-spacing: 0; color: var(--text); }}
	    .canvas {{ position: relative; border: 1px solid #c9cdd3; background: var(--paper); padding: 12px; min-height: 720px; }}
	    .drawio-architecture {{ position: relative; display: grid; grid-template-columns: minmax(0, 1fr) 210px; gap: 16px; align-items: stretch; }}
	    .drawio-architecture-no-external {{ grid-template-columns: minmax(0, 1fr); }}
	    .drawio-main-stack, .layered-diagram {{ display: grid; gap: 14px; min-width: 0; }}
	    .drawio-layer, .layer-band {{ display: grid; grid-template-columns: 178px minmax(0, 1fr); gap: 14px; min-height: 104px; border: 1.5px solid var(--layer-border); background: var(--layer-bg); padding: 12px; }}
	    .drawio-layer-title {{ display: flex; align-items: flex-start; justify-content: flex-start; border-right: 1px solid color-mix(in srgb, var(--layer-border) 72%, #ffffff); padding: 4px 12px 4px 2px; }}
	    .drawio-layer-title strong {{ font-size: calc(15px * var(--font-scale)); line-height: 1.25; font-weight: 700; color: #111827; overflow-wrap: anywhere; }}
	    .drawio-layer-content {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; align-items: stretch; min-width: 0; }}
	    .drawio-layer-compact .drawio-layer-content {{ grid-template-columns: repeat(auto-fit, minmax(205px, 1fr)); gap: 8px; }}
	    .drawio-group {{ min-width: 0; display: flex; flex-direction: column; justify-content: center; border: 1px dashed color-mix(in srgb, var(--layer-border) 72%, #6b7280); background: rgba(255,255,255,0.38); padding: 9px; }}
	    .drawio-group h2 {{ margin: 0 0 8px; text-align: center; color: #374151; font-size: calc(12px * var(--font-scale)); font-weight: 650; line-height: 1.2; }}
	    .drawio-group-compact {{ padding: 7px; }}
	    .drawio-node-grid {{ flex: 1; display: flex; flex-wrap: wrap; justify-content: center; align-items: center; align-content: center; gap: 12px 18px; }}
	    .drawio-node {{ position: relative; flex: 0 1 148px; min-width: 122px; min-height: 44px; border: 1.4px solid var(--node-border); border-radius: 5px; background: #ffffff; padding: 8px 12px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; color: #1f2937; overflow: hidden; }}
	    .drawio-node-label {{ font-size: calc(13px * var(--font-scale)); line-height: 1.18; font-weight: 650; overflow-wrap: anywhere; }}
	    .drawio-node p {{ margin: 4px 0 0; font-size: calc(10px * var(--font-scale)); line-height: 1.2; color: #4b5563; }}
	    .drawio-shape-database {{ min-height: 58px; padding-top: 17px; border-radius: 50% / 12px; }}
	    .drawio-shape-database::before {{ content: ""; position: absolute; left: -1.4px; right: -1.4px; top: -1.4px; height: 19px; border: 1.4px solid var(--node-border); border-radius: 50%; background: inherit; }}
	    .drawio-shape-database .drawio-node-label, .drawio-shape-database p {{ position: relative; z-index: 1; }}
	    .drawio-shape-cloud {{ border-radius: 999px 999px 820px 820px; min-height: 54px; }}
	    .drawio-shape-document {{ border-radius: 3px; }}
	    .drawio-shape-document::after {{ content: ""; position: absolute; right: -1px; top: -1px; width: 18px; height: 18px; border-left: 1.4px solid var(--node-border); border-bottom: 1.4px solid var(--node-border); background: #f3f4f6; }}
	    .drawio-shape-queue {{ border-radius: 999px; }}
	    .drawio-node-emphasis-high {{ background: #fff2bf; border-color: #d89b00; }}
	    .drawio-node-emphasis-muted {{ color: #6b7280; background: #f9fafb; }}
	    .drawio-node-variant-critical {{ background: #fde2e2; border-color: #b42318; color: #7f1d1d; }}
	    .drawio-node-variant-external {{ border-style: dashed; }}
	    .module-symbol {{ display: none; }}
	    .drawio-layer-link {{ position: relative; height: 24px; color: #374151; font-size: calc(11px * var(--font-scale)); text-align: center; }}
	    .drawio-layer-link i {{ position: absolute; left: 50%; top: -2px; width: 1.5px; height: 20px; background: var(--line); }}
	    .drawio-layer-link i::after {{ content: ""; position: absolute; left: -5px; bottom: -1px; border-left: 6px solid transparent; border-right: 6px solid transparent; border-top: 8px solid var(--line); }}
	    .drawio-layer-link-reverse i::after {{ top: -1px; bottom: auto; border-top: 0; border-bottom: 8px solid var(--line); }}
	    .drawio-layer-link span {{ position: absolute; left: calc(50% + 14px); top: 50%; transform: translateY(-50%); display: inline-block; margin-top: 0; padding: 1px 6px; background: #ffffff; border: 1px solid #c9cdd3; color: #374151; white-space: nowrap; }}
	    .drawio-layer-link-strong i {{ width: 2px; background: #111827; }}
	    .drawio-external-rail {{ display: grid; align-content: stretch; gap: 12px; }}
	    .drawio-external-panel {{ border: 1.5px solid #e0a03f; background: #fde8cb; padding: 14px 10px; display: flex; flex-direction: column; justify-content: center; gap: 18px; min-height: 100%; }}
	    .drawio-external-panel h2 {{ margin: 0; text-align: center; font-size: calc(14px * var(--font-scale)); font-weight: 700; color: #3f2f18; }}
	    .drawio-external-items {{ display: grid; gap: 12px; justify-items: center; }}
	    .drawio-external-node {{ width: 150px; flex-basis: auto; }}
	    .drawio-connector-overlay {{ position: absolute; inset: 0; pointer-events: none; }}
	    .theme-cyan {{ --layer-bg: #e8f6f9; --layer-border: #7bbdcc; }}
	    .theme-blue {{ --layer-bg: #e7f0fb; --layer-border: #82aad8; }}
	    .theme-green {{ --layer-bg: #e5f2e5; --layer-border: #8fbd8c; }}
	    .theme-amber {{ --layer-bg: #fff3cf; --layer-border: #e2bf63; }}
	    .theme-purple {{ --layer-bg: #eee4f4; --layer-border: #b59ac6; }}
	    .theme-slate {{ --layer-bg: #eef1f5; --layer-border: #a9b0bb; }}
	    @media (max-width: 760px) {{
	      .wrap {{ width: 100%; padding: 10px; }}
	      .header {{ display: block; }}
	      .drawio-architecture {{ grid-template-columns: 1fr; }}
	      .drawio-layer, .layer-band {{ grid-template-columns: 1fr; }}
	      .drawio-layer-title {{ border-right: 0; border-bottom: 1px solid var(--layer-border); }}
	      .drawio-external-panel {{ min-height: 160px; }}
	    }}
  </style>
</head>
<body>
	  <div class="wrap">
	    <header class="header">
	      <h1>{safe_title}</h1>
	    </header>
	    <main class="canvas">
	      <div class="drawio-architecture {'drawio-architecture-no-external' if not external_rail_html else ''}">
	        <svg class="drawio-connector-overlay" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
	          <defs>
	            <marker id="drawio-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
	              <path d="M0,0 L6,3 L0,6 Z" fill="#333333"></path>
	            </marker>
	          </defs>
	        </svg>
	        <div class="drawio-main-stack layered-diagram">
	          {''.join(band_html)}
	        </div>
	        {external_rail_html}
	      </div>
	    </main>
	  </div>
</body>
</html>
"""

    def _build_freeform_preview_html(self, title: str, artifact_id: str) -> str:
        safe_title = html.escape(title or artifact_id)
        safe_drawio_url = "assets/diagram.drawio"
        safe_svg_url = "assets/diagram.drawio.svg"
        safe_png_url = "assets/diagram.png"
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    body {{
      margin: 0;
      background: #f6f7f9;
      color: #1f2937;
      font-family: {diagram_css_font_stack()};
    }}
    .wrap {{
      min-height: 100vh;
      padding: 24px;
      box-sizing: border-box;
    }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin: 0 auto 16px;
      max-width: 1200px;
    }}
    h1 {{
      margin: 0;
      font-size: 24px;
      font-weight: 700;
      line-height: 1.25;
    }}
    .actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }}
    a {{
      color: #1d4ed8;
      text-decoration: none;
      font-size: 14px;
      font-weight: 600;
    }}
    main {{
      max-width: 1200px;
      margin: 0 auto;
      background: #ffffff;
      border: 1px solid #d7dce3;
      overflow: auto;
    }}
    img {{
      display: block;
      max-width: 100%;
      height: auto;
      margin: 0 auto;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>{safe_title}</h1>
      <nav class="actions" aria-label="diagram downloads">
        <a href="{safe_drawio_url}" download>Draw.io</a>
        <a href="{safe_svg_url}" download>SVG</a>
        <a href="{safe_png_url}" download>PNG</a>
      </nav>
    </header>
    <main>
      <img src="{safe_svg_url}" alt="{safe_title}" />
    </main>
  </div>
</body>
</html>
"""

    async def _execute_freeform_diagram(
        self,
        *,
        operation: str = "create",
        base_plan_path: Optional[str] = None,
        artifact_id: str,
        title: str,
        diagram_intent: Optional[str],
        canvas: Optional[Dict[str, Any]],
        shapes: Optional[List[Dict[str, Any]]],
        connectors: Optional[List[Dict[str, Any]]],
        groups: Optional[List[Dict[str, Any]]],
        postprocess: Optional[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            diagram = normalize_freeform_diagram(
                artifact_id=artifact_id,
                title=title,
                canvas=canvas,
                shapes=shapes,
                connectors=connectors,
                groups=groups,
                output_formats=None,
                diagram_intent=diagram_intent,
            )
        except FreeformValidationError as validation_exc:
            return {
                "status": "failed",
                "success": False,
                "data": None,
                "metadata": {
                    "generator": self.name,
                    "schema_version": "diagram_html.v3",
                    "diagram_mode": "freeform",
                    "diagram_intent": diagram_intent,
                    "validation_error": str(validation_exc),
                },
                "summary": f"自由画布图表生成失败：{validation_exc}",
            }

        postprocess_result = postprocess_freeform_diagram(
            diagram,
            style_pack=None,
            options=_freeform_postprocess_options(diagram.diagram_intent, postprocess),
        )
        diagram = postprocess_result.diagram
        quality_warnings = list(postprocess_result.quality_warnings)
        postprocess_actions = list(postprocess_result.actions)
        quality_gate = self._build_freeform_quality_gate(
            diagram,
            quality_warnings,
            block_delivery=True,
        )
        qa_status = quality_gate["status"]
        revision_tasks = list(quality_gate["revision_tasks"])

        safe_artifact_id = _safe_artifact_id(artifact_id)
        artifact_dir = html_artifact_service.get_artifact_dir(safe_artifact_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        plan_version = self._next_diagram_plan_version(base_plan_path) if operation == "patch" else 1
        design_spec_path = artifact_dir / "design_spec.md"
        diagram_plan_path = artifact_dir / f"diagram_plan.v{plan_version}.json"
        qa_report_path = artifact_dir / "qa_report.json"
        design_spec_path.write_text(
            self._build_freeform_design_spec(diagram, postprocess_result.style_pack),
            encoding="utf-8",
        )
        diagram_plan_path.write_text(
            json.dumps(diagram.to_source_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        qa_report_path.write_text(
            json.dumps(quality_gate, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        metadata_out = {
            "generator": self.name,
            "schema_version": "diagram_html.v3",
            "artifact_kind": "diagram",
            "diagram_mode": "freeform",
            "diagram_intent": diagram.diagram_intent,
            "layout_engine": "freeform_drawio",
            "output_targets": list(diagram.output_formats),
            "style_pack": postprocess_result.style_pack,
            "quality_warnings": quality_warnings,
            "postprocess_actions": postprocess_actions,
            "export_warnings": [],
            "qa_status": qa_status,
            "delivery_blocked": qa_status == "blocked",
        }
        if qa_status == "blocked":
            blocked_data = {
                "operation": operation,
                "artifact_id": safe_artifact_id,
                "title": title,
                "artifact_dir": str(artifact_dir),
                "design_spec_path": str(design_spec_path),
                "diagram_plan_path": str(diagram_plan_path),
                "qa_report_path": str(qa_report_path),
                "next_revision_base_plan_path": str(diagram_plan_path),
                "qa_status": qa_status,
                "quality_gate": quality_gate,
                "revision_tasks": revision_tasks,
                "delivery_blocked": True,
                "drawio_path": None,
                "preview_svg_path": None,
                "file_path": None,
                "file_type": "diagram",
                "metadata": metadata_out,
            }
            return {
                "status": "success",
                "success": True,
                "data": blocked_data,
                "visuals": [],
                "refs": {
                    "diagram_plan": str(diagram_plan_path),
                    "qa_report": str(qa_report_path),
                },
                "file_path": None,
                "file_type": "diagram",
                "artifact": None,
                "artifacts": [],
                "related_files": [],
                "metadata": metadata_out,
                "summary": f"自由画布图表未导出：{safe_artifact_id} 的架构质量门禁阻断交付。",
            }

        export_result = export_freeform_diagram(diagram, artifact_dir)
        drawio_url = f"/api/html-artifacts/{safe_artifact_id}/assets/diagram.drawio"
        png_url = f"/api/html-artifacts/{safe_artifact_id}/assets/diagram.png"
        svg_exists = export_result.preview_svg_path.exists()
        svg_url = (
            f"/api/html-artifacts/{safe_artifact_id}/assets/diagram.drawio.svg"
            if svg_exists
            else None
        )
        preview_url = svg_url or png_url
        preview_path = export_result.preview_svg_path if svg_exists else export_result.preview_png_path
        preview_format = "svg" if svg_exists else "png"
        export_warnings = list(export_result.warnings)

        metadata_out["export_warnings"] = export_warnings
        visuals = [
            {
                "id": f"{safe_artifact_id}_freeform_{preview_format}",
                "image_id": f"{safe_artifact_id}_freeform_{preview_format}",
                "title": title,
                "type": "image",
                "image_url": preview_url,
                "url": preview_url,
                "data": {
                    "url": preview_url,
                    "local_path": str(preview_path),
                },
                "markdown_image": f"![{title}]({preview_url})",
                "local_path": str(preview_path),
                "format": preview_format,
                "output_target": "freeform",
            }
        ]
        refs = {
            "drawio": str(export_result.drawio_path),
            "source_json": str(export_result.source_json_path),
            "png": str(export_result.preview_png_path),
        }
        if svg_exists:
            refs["drawio_svg"] = str(export_result.preview_svg_path)

        artifacts = [
            build_document_artifact(
                export_result.drawio_path,
                kind="drawio",
                format="drawio",
                title=f"{title} Draw.io",
                generator=self.name,
                metadata={"url": drawio_url, "diagram_mode": "freeform"},
            ),
            build_document_artifact(
                export_result.preview_png_path,
                kind="image",
                format="png",
                title=f"{title} PNG",
                generator=self.name,
                metadata={"url": png_url, "diagram_mode": "freeform"},
            ),
            build_document_artifact(
                export_result.source_json_path,
                kind="source",
                format="json",
                title=f"{title} Source JSON",
                generator=self.name,
                metadata={"diagram_mode": "freeform"},
            ),
        ]
        if svg_exists:
            artifacts.append(
                build_document_artifact(
                    export_result.preview_svg_path,
                    kind="image",
                    format="svg",
                    title=f"{title} Draw.io SVG",
                    generator=self.name,
                    metadata={"url": svg_url, "diagram_mode": "freeform"},
                )
            )

        related_files = [
            {
                "path": str(export_result.drawio_path),
                "relative_path": "assets/diagram.drawio",
                "url": drawio_url,
                "format": "drawio",
            },
            {
                "path": str(export_result.source_json_path),
                "relative_path": "diagram.source.json",
                "format": "json",
            },
            {
                "path": str(export_result.preview_png_path),
                "relative_path": "assets/diagram.png",
                "url": png_url,
                "format": "png",
            },
        ]
        if svg_exists:
            related_files.append({
                "path": str(export_result.preview_svg_path),
                "relative_path": "assets/diagram.drawio.svg",
                "url": svg_url,
                "format": "drawio_svg",
            })

        generated_at = datetime.now().isoformat()
        meta = {
            "artifact_id": safe_artifact_id,
            "title": title,
            "artifact_type": "diagram",
            "artifact_kind": "diagram",
            "diagram_mode": "freeform",
            "diagram_intent": diagram.diagram_intent,
            "layout_engine": "freeform_drawio",
            "output_targets": list(diagram.output_formats),
            "style_pack": postprocess_result.style_pack,
            "quality_warnings": quality_warnings,
            "postprocess_actions": postprocess_actions,
            "qa_status": qa_status,
            "quality_gate": quality_gate,
            "generated_at": generated_at,
            "files": {
                "diagram_plan": str(diagram_plan_path),
                "qa_report": str(qa_report_path),
                "drawio": str(export_result.drawio_path),
                "source_json": str(export_result.source_json_path),
                "png": str(export_result.preview_png_path),
                **({"svg": str(export_result.preview_svg_path)} if svg_exists else {}),
            },
            "related_files": related_files,
            **(metadata or {}),
        }
        html_artifact_service.write_meta(safe_artifact_id, meta)

        data = {
            "operation": operation,
            "artifact_id": safe_artifact_id,
            "title": title,
            "artifact_dir": str(artifact_dir),
            "design_spec_path": str(design_spec_path),
            "diagram_plan_path": str(diagram_plan_path),
            "qa_report_path": str(qa_report_path),
            "next_revision_base_plan_path": str(diagram_plan_path),
            "qa_status": qa_status,
            "quality_gate": quality_gate,
            "revision_tasks": revision_tasks,
            "file_path": str(export_result.drawio_path),
            "file_type": "drawio",
            "format": "drawio",
            "preview_url": preview_url,
            "preview_path": str(preview_path),
            "preview_format": preview_format,
            "drawio_path": str(export_result.drawio_path),
            "drawio_url": drawio_url,
            "source_json_path": str(export_result.source_json_path),
            "static_image_path": str(export_result.preview_png_path),
            "static_image_url": png_url,
            "metadata": metadata_out,
            "assets": [
                {
                    "path": str(export_result.preview_png_path),
                    "relative_path": "assets/diagram.png",
                    "format": "png",
                    "size_kb": round(export_result.preview_png_path.stat().st_size / 1024, 2),
                }
            ],
            "visuals": visuals,
            "refs": refs,
            "artifact": artifacts[0],
            "artifacts": artifacts,
            "related_files": related_files,
        }
        if svg_exists:
            data["preview_svg_path"] = str(export_result.preview_svg_path)
            data["preview_svg_url"] = svg_url
            data["svg_preview"] = {
                "svg_path": str(export_result.preview_svg_path),
                "svg_url": svg_url,
                "file_type": "drawio_svg",
                "format": "drawio_svg",
            }

        return {
            "status": "success",
            "success": True,
            "data": data,
            "refs": refs,
            "file_path": data.get("file_path"),
            "file_type": data.get("file_type", "drawio"),
            "artifact": data.get("artifact"),
            "artifacts": artifacts,
            "related_files": related_files,
            "metadata": metadata_out,
            "summary": f"自由画布图表已生成：{data['artifact_id']}。Draw.io 路径：{data['drawio_path']}。",
        }

    async def _execute_freeform_validate(
        self,
        *,
        artifact_id: str,
        title: str,
        diagram_intent: Optional[str],
        canvas: Optional[Dict[str, Any]],
        shapes: Optional[List[Dict[str, Any]]],
        connectors: Optional[List[Dict[str, Any]]],
        groups: Optional[List[Dict[str, Any]]],
        postprocess: Optional[Dict[str, Any]],
        base_plan_path: Optional[str],
    ) -> Dict[str, Any]:
        if base_plan_path:
            try:
                source = self._load_diagram_plan(base_plan_path)
            except ValueError as exc:
                return {"status": "failed", "success": False, "data": {"error": str(exc)}, "summary": f"图表验证失败：{exc}"}
            artifact_id = str(source.get("artifact_id") or artifact_id)
            title = str(source.get("title") or title)
            diagram_intent = source.get("diagram_intent") or diagram_intent
            canvas = source.get("canvas")
            shapes = source.get("shapes")
            connectors = source.get("connectors")
            groups = source.get("groups")
        try:
            diagram = normalize_freeform_diagram(
                artifact_id=artifact_id,
                title=title,
                canvas=canvas,
                shapes=shapes,
                connectors=connectors,
                groups=groups,
                output_formats=None,
                diagram_intent=diagram_intent,
            )
        except FreeformValidationError as validation_exc:
            return {"status": "failed", "success": False, "data": {"error": str(validation_exc)}, "summary": f"图表验证失败：{validation_exc}"}
        postprocess_result = postprocess_freeform_diagram(
            diagram,
            style_pack=None,
            options=_freeform_postprocess_options(diagram.diagram_intent, postprocess),
        )
        quality_gate = self._build_freeform_quality_gate(
            postprocess_result.diagram,
            list(postprocess_result.quality_warnings),
        )
        data = {
            "operation": "validate",
            "artifact_id": _safe_artifact_id(artifact_id),
            "title": title,
            "diagram_mode": "freeform",
            "diagram_intent": postprocess_result.diagram.diagram_intent,
            "qa_status": quality_gate["status"],
            "quality_gate": quality_gate,
            "revision_tasks": quality_gate["revision_tasks"],
            "drawio_path": None,
            "preview_svg_path": None,
        }
        return {
            "status": "success",
            "success": True,
            "data": data,
            "metadata": {
                "generator": self.name,
                "artifact_kind": "diagram",
                "diagram_mode": "freeform",
                "qa_status": quality_gate["status"],
            },
            "summary": f"自由画布图表验证完成：{quality_gate['status']}。",
        }

    def _load_diagram_plan(self, path: str) -> Dict[str, Any]:
        plan_path = Path(path)
        if not plan_path.exists():
            raise ValueError(f"diagram_plan_not_found: {plan_path}")
        try:
            data = json.loads(plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"diagram_plan_invalid_json: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("diagram_plan_must_be_object")
        return data

    def _apply_diagram_patch(self, base_plan: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(patch, dict):
            raise ValueError("diagram_patch_must_be_object")
        next_plan = dict(base_plan)
        for key in ("canvas", "artifact_id", "title", "diagram_intent"):
            if key in patch:
                next_plan[key] = patch[key]
        next_plan["shapes"] = self._patch_items(
            list(base_plan.get("shapes") or []),
            patch.get("replace_shapes") or [],
            patch.get("add_shapes") or [],
            patch.get("remove_shapes") or [],
            "shape",
        )
        next_plan["connectors"] = self._patch_items(
            list(base_plan.get("connectors") or []),
            patch.get("replace_connectors") or [],
            patch.get("add_connectors") or [],
            patch.get("remove_connectors") or [],
            "connector",
        )
        next_plan["groups"] = self._patch_items(
            list(base_plan.get("groups") or []),
            patch.get("replace_groups") or [],
            patch.get("add_groups") or [],
            patch.get("remove_groups") or [],
            "group",
        )
        next_plan["diagram_mode"] = "freeform"
        return next_plan

    def _patch_items(
        self,
        base_items: List[Dict[str, Any]],
        replace_items: List[Dict[str, Any]],
        add_items: List[Dict[str, Any]],
        remove_ids: List[Any],
        item_name: str,
    ) -> List[Dict[str, Any]]:
        items_by_id = {}
        order = []
        for item in base_items:
            if not isinstance(item, dict) or not item.get("id"):
                raise ValueError(f"diagram_patch_{item_name}_requires_id")
            item_id = str(item["id"])
            items_by_id[item_id] = dict(item)
            order.append(item_id)
        for raw_id in remove_ids:
            item_id = str(raw_id)
            items_by_id.pop(item_id, None)
            order = [existing_id for existing_id in order if existing_id != item_id]
        for item in replace_items:
            if not isinstance(item, dict) or not item.get("id"):
                raise ValueError(f"diagram_patch_replace_{item_name}_requires_id")
            item_id = str(item["id"])
            merged = dict(items_by_id.get(item_id, {}))
            merged.update(item)
            items_by_id[item_id] = merged
            if item_id not in order:
                order.append(item_id)
        for item in add_items:
            if not isinstance(item, dict) or not item.get("id"):
                raise ValueError(f"diagram_patch_add_{item_name}_requires_id")
            item_id = str(item["id"])
            items_by_id[item_id] = dict(item)
            if item_id not in order:
                order.append(item_id)
        return [items_by_id[item_id] for item_id in order if item_id in items_by_id]

    def _next_diagram_plan_version(self, base_plan_path: Optional[str]) -> int:
        if not base_plan_path:
            return 1
        match = re.search(r"diagram_plan\.v(\d+)\.json$", str(base_plan_path))
        if not match:
            return 2
        return int(match.group(1)) + 1

    def _build_freeform_design_spec(self, diagram: Any, style_pack: Optional[str]) -> str:
        return "\n".join(
            [
                f"# {diagram.title}",
                "",
                f"- diagram_mode: freeform",
                f"- diagram_intent: {diagram.diagram_intent or 'unspecified'}",
                f"- style_pack: {style_pack or 'default'}",
                f"- shapes: {len(diagram.shapes)}",
                f"- connectors: {len(diagram.connectors)}",
                f"- groups: {len(diagram.groups)}",
                "",
                "Agent edits this diagram through diagram_plan.v*.json and diagram_patch payloads.",
            ]
        )

    def _build_freeform_quality_gate(
        self,
        diagram: Any,
        warning_codes: List[str],
        *,
        block_delivery: bool = False,
    ) -> Dict[str, Any]:
        issues: List[Dict[str, Any]] = []
        for code in warning_codes:
            if code == "style_pack_applied":
                continue
            issues.append(self._diagram_issue(code, "warning", {"source": "postprocess"}))
        issues.extend(self._architecture_semantic_issues(diagram))
        deduped = []
        seen = set()
        for issue in issues:
            key = (issue.get("code"), json.dumps(issue.get("evidence", {}), ensure_ascii=False, sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(issue)
        if block_delivery:
            for issue in deduped:
                if issue.get("code") == "architecture_shape_level_connectors":
                    issue["severity"] = "error"
        has_blocking_issue = any(issue.get("severity") == "error" for issue in deduped)
        status = "blocked" if has_blocking_issue else "needs_revision" if deduped else "passed"
        revision_tasks = [
            {
                "code": issue["code"],
                "severity": issue["severity"],
                "message": issue["message"],
                "evidence": issue.get("evidence", {}),
                "suggested_patch_hint": issue.get("suggested_patch_hint", ""),
            }
            for issue in deduped
            if issue.get("severity") in {"warning", "error"}
        ]
        return {
            "status": status,
            "qa_status": status,
            "issues": deduped,
            "revision_tasks": revision_tasks,
        }

    def _architecture_semantic_issues(self, diagram: Any) -> List[Dict[str, Any]]:
        if str(diagram.diagram_intent or "").lower() not in {"architecture", "topology", "system_architecture"}:
            return []
        issues: List[Dict[str, Any]] = []
        fan_in: Dict[str, int] = {}
        for connector in diagram.connectors:
            fan_in[connector.target_id] = fan_in.get(connector.target_id, 0) + 1
        for target_id, count in fan_in.items():
            if count >= 4:
                issues.append(
                    self._diagram_issue(
                        "high_fan_in",
                        "warning",
                        {"target_id": target_id, "incoming_count": count},
                    )
                )
        shape_ids = {shape.id for shape in diagram.shapes}
        connector_pairs = {(connector.source_id, connector.target_id) for connector in diagram.connectors}
        for group in diagram.groups:
            children = [child for child in group.children if child in shape_ids]
            if len(children) < 4:
                continue
            chain_edges = 0
            for left, right in zip(children, children[1:]):
                if (left, right) in connector_pairs:
                    chain_edges += 1
            if chain_edges >= 3:
                issues.append(
                    self._diagram_issue(
                        "layer_internal_long_chain",
                        "warning",
                        {
                            "group_id": group.id,
                            "group_label": group.label,
                            "chain_edges": chain_edges,
                            "children_count": len(children),
                        },
                    )
                )
        shape_level_connectors = self._architecture_shape_level_connectors(diagram)
        if shape_level_connectors:
            same_layer_count = sum(1 for item in shape_level_connectors if item.get("same_layer"))
            issues.append(
                self._diagram_issue(
                    "architecture_shape_level_connectors",
                    "warning",
                    {
                        "connector_count": len(shape_level_connectors),
                        "same_layer_connector_count": same_layer_count,
                        "sample_connector_ids": [item["id"] for item in shape_level_connectors[:8]],
                    },
                )
            )
        return issues

    def _architecture_shape_level_connectors(self, diagram: Any) -> List[Dict[str, Any]]:
        shape_by_id = {shape.id: shape for shape in diagram.shapes}
        group_ids = {group.id for group in diagram.groups}
        container_shape_ids = {
            shape.id
            for shape in diagram.shapes
            if str(shape.type or "").lower() in {"container", "swimlane"}
        }
        layer_endpoint_ids = group_ids | container_shape_ids
        if not layer_endpoint_ids:
            return []

        memberships: Dict[str, set[str]] = {}
        for group in diagram.groups:
            for child_id in group.children:
                memberships.setdefault(child_id, set()).add(group.id)

        shape_level_connectors: List[Dict[str, Any]] = []
        for connector in diagram.connectors:
            source_is_plain_shape = connector.source_id in shape_by_id and connector.source_id not in layer_endpoint_ids
            target_is_plain_shape = connector.target_id in shape_by_id and connector.target_id not in layer_endpoint_ids
            if not (source_is_plain_shape or target_is_plain_shape):
                continue
            source_groups = memberships.get(connector.source_id, set())
            target_groups = memberships.get(connector.target_id, set())
            shape_level_connectors.append({
                "id": connector.id,
                "from": connector.source_id,
                "to": connector.target_id,
                "same_layer": bool(source_groups and target_groups and source_groups.intersection(target_groups)),
            })
        return shape_level_connectors

    def _diagram_issue(self, code: str, severity: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
        messages = {
            "overlap_detected": "存在节点重叠，影响阅读和后续编辑。",
            "high_fan_in": "多个源节点直接汇聚到同一目标，架构图应考虑接入总线、网关或聚合节点。",
            "label_too_long": "存在过长标签，建议拆成标题和说明或增大节点。",
            "canvas_sparse": "画布利用率偏低，建议收紧布局或调整画布尺寸。",
            "layer_internal_long_chain": "同一层内出现长流程链，架构图应优先表达能力簇和层间关系。",
            "architecture_shape_level_connectors": "架构图存在普通元素级连线，应优先保留层级、域或边界之间的连接。",
            "canvas_expanded": "画布已被扩展以容纳越界元素。",
        }
        hints = {
            "high_fan_in": "添加接入汇聚/数据总线节点，将多条输入先连到总线，再连到目标。",
            "layer_internal_long_chain": "移除同层连续串联连线，改为并列能力模块或仅保留关键跨层连接。",
            "architecture_shape_level_connectors": "在下一轮 diagram_patch 中移除普通节点之间的 connectors，改为连接 group/container 层级或代表性边界节点。",
            "overlap_detected": "移动或缩放重叠节点。",
            "label_too_long": "缩短 label 或把说明放入独立 note/callout。",
            "canvas_sparse": "压缩节点间距或减小 canvas。",
        }
        return {
            "code": code,
            "severity": severity,
            "message": messages.get(code, code),
            "evidence": evidence,
            "suggested_patch_hint": hints.get(code, ""),
        }

    async def execute(
        self,
        operation: str = "create",
        artifact_id: Optional[str] = None,
        title: Optional[str] = None,
        direction: str = "TB",
        diagram_mode: str = "freeform",
        diagram_intent: Optional[str] = None,
        canvas: Optional[Dict[str, Any]] = None,
        shapes: Optional[List[Dict[str, Any]]] = None,
        connectors: Optional[List[Dict[str, Any]]] = None,
        groups: Optional[List[Dict[str, Any]]] = None,
        postprocess: Optional[Dict[str, Any]] = None,
        base_plan_path: Optional[str] = None,
        diagram_plan_path: Optional[str] = None,
        diagram_patch: Optional[Dict[str, Any]] = None,
        diagram_patch_path: Optional[str] = None,
        diagram_type: str = "auto",
        layers: Optional[List[Dict[str, Any]]] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
        edges: Optional[List[Dict[str, Any]]] = None,
        notes: Optional[str] = None,
        font_scale: FontScale = None,
        page_orientation: str = "auto",
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            operation = str(operation or "create").strip().lower()
            if operation not in {"create", "patch", "validate", "render"}:
                return {
                    "success": False,
                    "data": {"error": "invalid_operation"},
                    "summary": f"图表生成失败：不支持 operation={operation}",
                }
            if diagram_patch_path and diagram_patch is not None:
                return {
                    "success": False,
                    "data": {"error": "diagram_patch_conflict"},
                    "summary": "图表生成失败：diagram_patch 和 diagram_patch_path 只能传一个",
                }
            if diagram_patch_path:
                try:
                    patch_path = Path(diagram_patch_path)
                    diagram_patch = json.loads(patch_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    return {
                        "success": False,
                        "data": {"error": f"diagram_patch_path_invalid: {exc}"},
                        "summary": f"图表生成失败：diagram_patch_path 无法读取：{exc}",
                    }
            if operation in {"patch", "render"}:
                base_path = base_plan_path or diagram_plan_path
                if not base_path:
                    return {
                        "success": False,
                        "data": {"error": "base_plan_path_required"},
                        "summary": f"图表生成失败：operation={operation} 需要 base_plan_path 或 diagram_plan_path。",
                    }
                try:
                    base_plan = self._load_diagram_plan(base_path)
                    if operation == "patch":
                        base_plan = self._apply_diagram_patch(base_plan, diagram_patch or {})
                    artifact_id = str(artifact_id or "").strip()
                    title = str(title or base_plan.get("title") or "").strip()
                    diagram_intent = diagram_intent or base_plan.get("diagram_intent")
                    canvas = canvas or base_plan.get("canvas")
                    shapes = shapes or base_plan.get("shapes")
                    connectors = connectors or base_plan.get("connectors")
                    groups = groups or base_plan.get("groups")
                except ValueError as exc:
                    return {
                        "success": False,
                        "data": {"error": str(exc)},
                        "summary": f"图表生成失败：{str(exc)[:100]}",
                    }
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

            diagram_mode = str(diagram_mode or "freeform").strip().lower()
            if (
                diagram_mode == "freeform"
                and not shapes
                and (layers or steps)
            ):
                diagram_mode = "template"
            if operation == "validate" and str(diagram_mode or "freeform").strip().lower() == "freeform":
                return await self._execute_freeform_validate(
                    artifact_id=artifact_id,
                    title=title,
                    diagram_intent=diagram_intent,
                    canvas=canvas,
                    shapes=shapes,
                    connectors=connectors,
                    groups=groups,
                    postprocess=postprocess,
                    base_plan_path=base_plan_path or diagram_plan_path,
                )

            if diagram_mode == "freeform":
                return await self._execute_freeform_diagram(
                    operation=operation,
                    base_plan_path=base_plan_path or diagram_plan_path,
                    artifact_id=artifact_id,
                    title=title,
                    diagram_intent=diagram_intent,
                    canvas=canvas,
                    shapes=shapes,
                    connectors=connectors,
                    groups=groups,
                    postprocess=postprocess,
                    metadata=metadata,
                )

            direction = direction if direction in {"TB", "BT", "LR", "RL"} else "TB"
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
                "mind_map",
                "gantt",
            } else "auto"
            steps = steps or []
            if diagram_type == "mind_map" and not steps:
                alternate_steps = kwargs.get("nodes") or kwargs.get("topics")
                if isinstance(alternate_steps, list):
                    steps = [step for step in alternate_steps if isinstance(step, dict)]
            edges = edges or []
            page_orientation = _normalise_page_orientation(page_orientation, steps)
            layout_warnings: List[str] = []
            static_image_from_html = True

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
                static_image_from_html = True
                page_orientation = "landscape"
                render_engine = "layered_html"
            elif diagram_type == "mind_map":
                layout_warnings = _word_a4_layout_warnings(diagram_type, steps)
                html_content = self._build_mind_map_html(
                    title,
                    steps,
                    notes=notes,
                    font_scale=font_scale,
                )
                page_orientation = "landscape"
                render_engine = "drawio_mind_map_html"
            elif diagram_type == "gantt":
                layout_warnings = _word_a4_layout_warnings(diagram_type, steps)
                html_content = self._build_gantt_html(
                    title,
                    steps,
                    notes=notes,
                    font_scale=font_scale,
                )
                page_orientation = "landscape"
                render_engine = "drawio_gantt_html"
            else:
                layout_warnings = _word_a4_layout_warnings(diagram_type, steps)
                html_content = self._build_process_html(
                    title,
                    steps,
                    edges,
                    direction=direction,
                    diagram_type=diagram_type,
                    notes=notes,
                    font_scale=font_scale,
                )
                render_engine = "drawio_process_html" if diagram_type in {"auto", "process"} else "drawio_steps_html"

            data = html_artifact_service.create_artifact(
                artifact_id,
                html_content,
                title=title,
                metadata={
                    "artifact_kind": "diagram",
                    "diagram_type": diagram_type,
                    "direction": direction,
                    "layout_engine": render_engine,
                    "output_targets": ["html", "word_a4"],
                    "page_orientation": page_orientation,
                    "layout_warnings": layout_warnings,
                    "font_family": select_diagram_font_family(),
                    "generated_at": datetime.now().isoformat(),
                    "design_reference_paths": diagram_design_reference_paths(),
                    **(metadata or {}),
                },
            )
            static_image = None
            if static_image_from_html:
                image_path = (
                    Path(data["artifact_dir"])
                    / "assets"
                    / _safe_asset_name(f"{data.get('artifact_id')}_word_a4")
                )
                try:
                    static_image = await self._render_html_word_a4_screenshot(
                        Path(data["file_path"]),
                        image_path,
                        page_orientation=page_orientation,
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
                            "output_target": "word_a4",
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
                    "output_targets": ["html", "word_a4"],
                },
            )
            if static_image:
                data["artifact"]["html_file_path"] = data["file_path"]
                data["artifact"]["html_preview"] = data.get("html_preview")
            resume_context = build_artifact_resume_context(
                data,
                data.get("static_image_path") or data["file_path"],
                tool_hint=(
                    f"Use present_artifact(file_path='{data.get('static_image_path')}') to preview the Word A4 image, "
                    f"or present_artifact(file_path='{data['file_path']}') to preview the interactive HTML."
                )
                if static_image
                else None,
                extra_resume={"html_file_path": data["file_path"]} if static_image else None,
            )
            html_preview = data.get("html_preview")
            return {
                "status": "success",
                "success": True,
                "data": data,
                **resume_context,
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
                    "output_targets": ["html", "word_a4"],
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
                    + _layout_warning_summary(layout_warnings)
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
