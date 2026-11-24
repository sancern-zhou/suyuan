"""同小时同组幂等与检测/过滤/入队状态流水（原子 JSON 文件）。"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
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
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.root, delete=False) as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            temporary = Path(handle.name)
        temporary.replace(self.path)
