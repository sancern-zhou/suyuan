"""数据源地图：把"哪个数据域走哪个工具/表"的路由知识注入 Agent 提示词。

单一事实源是部署 registry 目录下的 ``data_source_catalog.yaml``（部署数据，
不入 git）。渲染为紧凑 markdown 后注入 query/专家族/报告模式系统提示词；
文件缺失或条目非法时 fail-soft 跳过并告警，绝不阻断服务启动。

按 Anthropic context engineering 的 hybrid 策略：地图只放路由级元数据
（域 → 工具/表 + 口径 + 禁区），字段细节由 describe_table 等工具按需提供。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

import structlog

logger = structlog.get_logger()

CATALOG_FILENAME = "data_source_catalog.yaml"

_CACHE: Optional[List[dict[str, Any]]] = None


def _catalog_path() -> Path:
    from config.settings import settings

    return Path(settings.data_registry_dir) / CATALOG_FILENAME


def load_data_source_catalog(*, refresh: bool = False) -> List[dict[str, Any]]:
    """加载并校验数据源目录；缺失/损坏时返回空列表并记录日志。"""
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE

    path = _catalog_path()
    raw: Any = []
    try:
        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    except FileNotFoundError:
        logger.info("data_source_catalog_missing", path=str(path))
    except Exception as exc:  # noqa: BLE001 — 目录损坏时降级为无地图
        logger.warning("data_source_catalog_load_failed", path=str(path), error=str(exc))

    if isinstance(raw, dict):
        raw = raw.get("sources") or []

    entries: List[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or "").strip()
        locator = str(item.get("locator") or "").strip()
        if not domain or not locator:
            logger.warning("data_source_catalog_entry_invalid", entry=item)
            continue
        entries.append(item)

    _CACHE = entries
    return entries


def render_data_source_map() -> str:
    """渲染为注入提示词的紧凑 markdown；目录为空时返回空串。"""
    entries = load_data_source_catalog()
    if not entries:
        return ""

    lines = [
        "## 数据源地图（取数前先按此路由，禁止盲目探索其他数据源）",
        "",
    ]
    for item in entries:
        line = f"- **{item['domain']}** → `{item['locator']}`"
        usage = str(item.get("usage") or "").strip()
        if usage:
            line += f"：{usage}"
        lines.append(line)
        caveats = str(item.get("caveats") or "").strip()
        if caveats:
            lines.append(f"  - 注意：{caveats}")
    return "\n".join(lines) + "\n"


def reset_cache() -> None:
    """测试与配置热更新辅助。"""
    global _CACHE
    _CACHE = None
