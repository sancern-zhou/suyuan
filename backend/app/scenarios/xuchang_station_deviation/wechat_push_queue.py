"""微信群 RPA 推送队列：每条消息一个 JSON 文件 + 原子 rename。

写入方分工固定：enqueue 只发生在 worker 进程（告警 workflow 文案定稿后写
pending 新文件），ack 只发生在 web 进程（把单条文件 rename 到 sent/failed），
双方从不读改写同一个状态文件，因此无需跨进程锁即可在 web 多 uvicorn worker
下保持一致。归档目录由 ack 侧顺手清理超期文件。

目录布局（root 表示 data registry 根目录）：
    <root>/xuchang_wechat_push/pending/*.json   待发
    <root>/xuchang_wechat_push/sent/*.json      已发归档
    <root>/xuchang_wechat_push/failed/*.json    重试耗尽归档
    <root>/xuchang_wechat_push/agent_status.json  agent 最近心跳
"""

from __future__ import annotations

import json
import re
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from app.utils.path_config import get_data_registry

logger = structlog.get_logger()

QUEUE_DIR_NAME = "xuchang_wechat_push"
PENDING_DIR = "pending"
SENT_DIR = "sent"
FAILED_DIR = "failed"
AGENT_STATUS_FILE = "agent_status.json"

# failed ack 达到该次数即归档停发，交由人工兜底，避免无限重发刷群
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_ARCHIVE_KEEP_DAYS = 7
PENDING_FETCH_LIMIT = 50

# ack 的 id 来自请求体，白名单校验防目录穿越
_SAFE_MESSAGE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def _queue_base(root: Path | None) -> Path:
    """队列根目录：root 一律表示 data registry 根目录。"""
    base = root if root is not None else get_data_registry()
    return base / QUEUE_DIR_NAME


def _status_dir(status: str, root: Path | None) -> Path:
    return _queue_base(root) / status


def _write_atomic(record: dict[str, Any], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=target.parent, delete=False
    ) as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
        temp_path = Path(handle.name)
    temp_path.replace(target)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return record if isinstance(record, dict) else {}


def _list_message_files(status: str, root: Path | None) -> list[Path]:
    try:
        return sorted(_status_dir(status, root).glob("*.json"))
    except OSError:
        return []


def _first_episode_id(package: dict[str, Any]) -> str:
    for item in package.get("alerts") or []:
        alert = item.get("alert") if isinstance(item, dict) else None
        episode = (alert or {}).get("scenario_1_episode") or {}
        episode_id = str(episode.get("episode_id") or "").strip()
        if episode_id:
            return episode_id
    return ""


def _pollutants(package: dict[str, Any]) -> str:
    values: list[str] = []
    for item in package.get("alerts") or []:
        alert = item.get("alert") if isinstance(item, dict) else None
        pollutant = str((alert or {}).get("target_pollutant") or "").strip()
        if pollutant and pollutant not in values:
            values.append(pollutant)
    return "、".join(values)


def enqueue_station_alert_wechat_message(
    package: dict[str, Any],
    message: str,
    *,
    root: Path | None = None,
) -> dict[str, Any] | None:
    """把定稿的站点告警通报文案写入待发队列，返回入队记录。

    空文案跳过；调用方（alert_notification workflow）负责 try/except，
    入队失败只记日志、不影响现有投递主流程。
    """
    text = str(message or "").strip()
    if not text:
        return None
    now = datetime.now()
    record = {
        "id": f"wx-{now:%Y%m%d%H%M%S%f}-{uuid.uuid4().hex[:8]}",
        "kind": "station_alert",
        "text": text,
        "metadata": {
            "episode_id": _first_episode_id(package),
            "station_id": str(package.get("station_id") or ""),
            "station_name": str(package.get("station_name") or ""),
            "pollutants": _pollutants(package),
        },
        "created_at": now.isoformat(timespec="seconds"),
        "attempts": 0,
    }
    _write_atomic(record, _status_dir(PENDING_DIR, root) / f"{record['id']}.json")
    return record


def list_pending_messages(
    limit: int = 10, *, root: Path | None = None
) -> list[dict[str, Any]]:
    """按入队时间返回待发消息（文件名时间戳前缀保证顺序）；坏文件跳过。"""
    limit = max(1, min(int(limit), PENDING_FETCH_LIMIT))
    messages: list[dict[str, Any]] = []
    for path in _list_message_files(PENDING_DIR, root):
        record = _read_json(path)
        if not record or not str(record.get("text") or "").strip():
            logger.warning("xuchang_wechat_push_pending_file_invalid", file=path.name)
            continue
        messages.append(record)
        if len(messages) >= limit:
            break
    return messages


def ack_message(
    message_id: str,
    ack_status: str,
    *,
    detail: str | None = None,
    root: Path | None = None,
) -> str:
    """处理 agent 回执，返回动作结果：archived_sent/archived_failed/requeued/unknown。

    pending 中已无该文件（重复 ack 或从未存在）一律幂等返回 unknown。
    """
    if not _SAFE_MESSAGE_ID.fullmatch(message_id or ""):
        raise ValueError("非法的消息 id")
    if ack_status not in {"sent", "failed"}:
        raise ValueError(f"不支持的回执状态: {ack_status}")
    pending_path = _status_dir(PENDING_DIR, root) / f"{message_id}.json"
    if not pending_path.exists():
        return "unknown"

    if ack_status == "sent":
        sent_dir = _status_dir(SENT_DIR, root)
        sent_dir.mkdir(parents=True, exist_ok=True)
        pending_path.replace(sent_dir / pending_path.name)
        return "archived_sent"

    record = _read_json(pending_path)
    attempts = int(record.get("attempts") or 0) + 1
    record["attempts"] = attempts
    if detail:
        record["last_error"] = str(detail)[:500]
    if attempts >= DEFAULT_MAX_ATTEMPTS:
        failed_dir = _status_dir(FAILED_DIR, root)
        failed_dir.mkdir(parents=True, exist_ok=True)
        failed_path = failed_dir / pending_path.name
        pending_path.replace(failed_path)
        _write_atomic(record, failed_path)
        return "archived_failed"
    _write_atomic(record, pending_path)
    return "requeued"


def record_agent_heartbeat(
    agent: dict[str, Any] | None = None, *, root: Path | None = None
) -> None:
    """记录推送 agent 最近心跳；web 多 worker 覆盖写无锁，语义仅"最近有人来过"。"""
    payload: dict[str, Any] = {
        "last_seen_at": datetime.now().isoformat(timespec="seconds")
    }
    if agent:
        payload["agent"] = agent
    _write_atomic(payload, _queue_base(root) / AGENT_STATUS_FILE)


def push_status_snapshot(*, root: Path | None = None) -> dict[str, Any]:
    oldest_created_at = None
    pending_paths = _list_message_files(PENDING_DIR, root)
    for path in pending_paths:
        created_at = str(_read_json(path).get("created_at") or "")
        if created_at and (oldest_created_at is None or created_at < oldest_created_at):
            oldest_created_at = created_at
    agent = _read_json(_queue_base(root) / AGENT_STATUS_FILE)
    return {
        "pending_count": len(pending_paths),
        "oldest_pending_created_at": oldest_created_at,
        "sent_count": len(_list_message_files(SENT_DIR, root)),
        "failed_count": len(_list_message_files(FAILED_DIR, root)),
        "agent": agent or None,
    }


def cleanup_archive(
    *, keep_days: int = DEFAULT_ARCHIVE_KEEP_DAYS, root: Path | None = None
) -> int:
    """清理 sent/failed 归档中超期文件，返回删除数；单文件失败跳过。"""
    deadline = time.time() - keep_days * 86400
    removed = 0
    for status in (SENT_DIR, FAILED_DIR):
        for path in _list_message_files(status, root):
            try:
                if path.stat().st_mtime < deadline:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
    return removed
