"""采集库（DataCrawler MySQL）表契约：单一事实源驱动的字段知识注入。

契约文件由真实库 information_schema 生成（backend/config/data_table_contracts.yaml），
部署可用 ``<data_registry_dir>/data_table_contracts.yaml`` 覆盖。渲染为紧凑 markdown
后拼进 execute_crawler_sql_query 的工具描述，替代易漂移的手写表说明。

fail-soft：文件缺失或损坏时返回空串并告警，工具描述退化为"先 describe_table"引导。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

CONTRACT_FILENAME = "data_table_contracts.yaml"

# 渲染时从 value_columns 中再细分的语义列（生成脚本只做粗分类）
_REVIEW_COLUMNS = {"Type", "Level", "Description", "Quality", "PrimaryPollutant"}
_BOOKKEEPING_COLUMNS = {"Id", "CreateTime", "UpdateTime", "SourceId"}

_CACHE: Optional[Dict[str, Any]] = None


def _candidate_paths() -> List[Path]:
    from config.settings import settings

    paths = [Path(settings.data_registry_dir) / CONTRACT_FILENAME]
    config_path = Path(__file__).resolve()
    # app/tools/query/execute_crawler_sql_query/table_contracts.py → backend/config
    backend_config = config_path.parents[4] / "config" / CONTRACT_FILENAME
    paths.append(backend_config)
    return paths


def load_table_contracts(*, refresh: bool = False) -> Optional[Dict[str, Any]]:
    """加载表契约；缺失/损坏返回 None（调用方按无契约降级）。"""
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE

    import yaml

    for path in _candidate_paths():
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except Exception as exc:  # noqa: BLE001 — 损坏时尝试下一个候选路径
            logger.warning("table_contracts_load_failed", path=str(path), error=str(exc))
            continue
        tables = (raw or {}).get("tables") if isinstance(raw, dict) else None
        if isinstance(tables, dict) and tables:
            logger.info("table_contracts_loaded", path=str(path), tables=len(tables))
            _CACHE = {"path": str(path), "tables": tables}
            return _CACHE
        logger.warning("table_contracts_invalid", path=str(path))
    logger.warning("table_contracts_missing", candidates=[str(p) for p in _candidate_paths()])
    _CACHE = None
    return None


def table_columns(table_name: str) -> List[str]:
    """返回某表的真实列名（按库中顺序）；未知表返回空列表。"""
    contracts = load_table_contracts()
    if not contracts:
        return []
    info = contracts["tables"].get(table_name)
    if not isinstance(info, dict):
        return []
    columns: List[str] = []
    for key in ("time_columns", "dimension_columns", "value_columns", "mark_columns", "caliber_columns"):
        columns.extend(str(name) for name in (info.get(key) or []))
    return columns


def _split_values(names: List[str]) -> Dict[str, List[str]]:
    review = [n for n in names if n in _REVIEW_COLUMNS or n.rstrip("_2") in _REVIEW_COLUMNS]
    bookkeeping = [n for n in names if n in _BOOKKEEPING_COLUMNS]
    values = [
        n for n in names
        if n not in review and n not in bookkeeping and n.rstrip("_2") not in _REVIEW_COLUMNS
    ]
    return {"values": values, "review": review, "bookkeeping": bookkeeping}


def render_table_contracts(table_names: Optional[List[str]] = None) -> str:
    """渲染为工具描述中的紧凑契约文本；无契约时返回空串。

    table_names 指定时只渲染这些表（问数模式按站点/城市层级注入上下文用）。
    """
    contracts = load_table_contracts()
    if not contracts:
        return ""

    all_tables = contracts["tables"]
    if table_names is None:
        selected_tables = list(all_tables.keys())
    else:
        selected_tables = [
            str(name) for name in table_names
            if isinstance(all_tables.get(name), dict)
        ]
        if not selected_tables:
            return ""

    lines = [
        "",
        "## 表字段契约（由真实库生成，字段大小写与命名以此为准，写 SQL 前逐字核对）",
        "",
    ]
    for table in selected_tables:
        info = all_tables[table]
        parts = [f"- **{table}**"]
        time_cols = info.get("time_columns") or []
        if time_cols:
            parts.append(f"时间 {time_cols[0]}" + (f"等 {'/'.join(time_cols)}" if len(time_cols) > 1 else ""))
        for key, label in (("dimension_columns", "维度"), ("caliber_columns", "口径")):
            cols = info.get(key) or []
            if cols:
                parts.append(f"{label} {'/'.join(cols)}")
        split = _split_values(list(info.get("value_columns") or []))
        if split["review"]:
            parts.append(f"评价 {'/'.join(split['review'])}")
        if split["values"]:
            parts.append(f"数值 {'/'.join(split['values'])}")
        lines.append("；".join(parts))
        marks = info.get("mark_columns") or []
        if marks:
            lines.append(f"  - 审核标记列：{'/'.join(marks)}")
    lines.append(
        "  - 注意：各表审核标记命名不一致（如 StationDay 为 COMark、CityDay 为 CO_Mark），"
        "严禁跨表套用字段名；查询失败返回的错误会附该表真实字段，直接据此修正。"
    )
    return "\n".join(lines) + "\n"


def reset_cache() -> None:
    """测试与配置热更新辅助。"""
    global _CACHE
    _CACHE = None
