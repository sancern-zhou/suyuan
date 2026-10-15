"""Fetcher 运行留痕（JSONL，追加写）。

Fetcher 基类每次真实执行（成功或失败）追加一条记录，供运行监控工具查询
"上一时段抓取失败"。只有 worker 进程运行 fetcher，因此是单写者；
记录文件放在 DATA_REGISTRY 下，随部署环境持久化目录走。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import structlog

logger = structlog.get_logger()

# 单文件体积上限：超过后重写为最近 KEEP_RECORDS 条，避免无限增长。
_MAX_FILE_BYTES = 512 * 1024
_KEEP_RECORDS = 500

FILE_NAME = "fetcher_runs.jsonl"


def run_log_path() -> Path:
    from app.utils.path_config import get_data_registry

    return Path(get_data_registry()) / FILE_NAME


def record_fetcher_run(
    *,
    fetcher: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    error: Optional[str] = None,
) -> None:
    """追加一条运行记录；留痕失败只记日志，绝不影响抓取本身。"""
    try:
        path = run_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "fetcher": fetcher,
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": finished_at.isoformat(timespec="seconds"),
            "status": status,
            "error": (error or "")[:500] or None,
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        _trim_if_oversized(path)
    except Exception as exc:  # noqa: BLE001 - 留痕属于旁路能力
        logger.warning("fetcher_run_log_write_failed", fetcher=fetcher, error=str(exc))


def _trim_if_oversized(path: Path) -> None:
    try:
        if path.stat().st_size <= _MAX_FILE_BYTES:
            return
        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()
        if len(lines) <= _KEEP_RECORDS:
            return
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(lines[-_KEEP_RECORDS:]), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetcher_run_log_trim_failed", error=str(exc))


def read_recent_runs(limit: int = 500) -> List[dict[str, Any]]:
    """读取最近运行记录（新→旧）；文件不存在或损坏行跳过。"""
    try:
        path = run_log_path()
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()
        records: List[dict[str, Any]] = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(records) >= max(int(limit), 1):
                break
        return records
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetcher_run_log_read_failed", error=str(exc))
        return []
