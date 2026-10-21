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
    """部署 registry 覆盖路径（部署数据，不入 git；兼容既有调用与测试）。"""
    from config.settings import settings

    return Path(settings.data_registry_dir) / CATALOG_FILENAME


def _config_catalog_path() -> Path:
    """随代码入库的基准目录（backend/config/data_source_catalog.yaml）。"""
    return Path(__file__).resolve().parents[3] / "config" / CATALOG_FILENAME


def _candidate_paths() -> List[Path]:
    """查找顺序：部署 registry 覆盖优先，config 基准回落。"""
    return [_catalog_path(), _config_catalog_path()]


def load_data_source_catalog(*, refresh: bool = False) -> List[dict[str, Any]]:
    """加载数据源目录；全部候选缺失/损坏时返回空列表并记录日志。"""
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE

    raw: Any = []
    loaded_from: Optional[Path] = None
    for path in _candidate_paths():
        try:
            import yaml

            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        except FileNotFoundError:
            continue
        except Exception as exc:  # noqa: BLE001 — 目录损坏时尝试下一个候选
            logger.warning("data_source_catalog_load_failed", path=str(path), error=str(exc))
            continue
        loaded_from = path
        break

    if loaded_from is None:
        logger.info(
            "data_source_catalog_missing",
            candidates=[str(path) for path in _candidate_paths()],
        )

    if isinstance(raw, dict):
        raw = raw.get("sources") or []

    if loaded_from is not None:
        logger.info("data_source_catalog_loaded", path=str(loaded_from))

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
        granularity = str(item.get("granularity") or "").strip()
        if granularity:
            lines.append(f"  - 粒度：{granularity}")
        caveats = str(item.get("caveats") or "").strip()
        if caveats:
            lines.append(f"  - 注意：{caveats}")
    return "\n".join(lines) + "\n"


def reset_cache() -> None:
    """测试与配置热更新辅助。"""
    global _CACHE
    _CACHE = None
