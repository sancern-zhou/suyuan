"""同小时同组幂等与检测/过滤/入队状态流水（原子 JSON 文件）。"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.utils.path_config import get_data_registry


class AlertStateStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_data_registry() / "xuchang_town_high_value"
        self.path = self.root / "state.json"

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def already_sent(self, group_id: str) -> bool:
        return (self._load().get("sent") or {}).get(group_id) is not None

    def in_cooldown(self, cooldown_key: str, now: datetime, *, hours: int) -> bool:
        """按站点、因子和提醒类型判断冷却；只在实际入队后记录冷却水位。"""
        entry = (self._load().get("cooldowns") or {}).get(cooldown_key)
        if not entry:
            return False
        try:
            sent_at = datetime.fromisoformat(str(entry["sent_at"]))
            # 定时器使用本地无时区时间，水位统一显式标记为 UTC；两类输入均可比较。
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            if sent_at.tzinfo is None:
                sent_at = sent_at.replace(tzinfo=timezone.utc)
            return now.astimezone(timezone.utc) - sent_at < timedelta(hours=hours)
        except (KeyError, TypeError, ValueError):
            return False

    def mark_cooldown(self, cooldown_key: str, now: datetime, detail: dict[str, Any] | None = None) -> None:
        data = self._load()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        data.setdefault("cooldowns", {})[cooldown_key] = {
            "sent_at": now.astimezone(timezone.utc).isoformat(),
            **(detail or {}),
        }
        self._save(data)

    def record(self, group_id: str, status: str, detail: dict[str, Any] | None = None) -> None:
        data = self._load()
        history = data.setdefault("history", [])
        entry = {
            "group_id": group_id,
            "status": status,
            "at": datetime.now(timezone.utc).isoformat(),
            **(detail or {}),
        }
        history.append(entry)
        data["history"] = history[-1000:]
        if status == "sent":
            data.setdefault("sent", {})[group_id] = entry
        self._save(data)

    def _save(self, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.root, delete=False) as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            temporary = Path(handle.name)
        temporary.replace(self.path)
