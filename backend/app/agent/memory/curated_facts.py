"""Provenance-aware, mode-shared facts with a compact model-facing index."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
import fcntl
import os
from pathlib import Path
import tempfile
from typing import Any, Iterator
from uuid import uuid4

import yaml

from app.utils.path_config import format_agent_path


class CuratedFactStore:
    INDEX_LIMIT = 200
    INDEX_CHAR_LIMIT = 25_000

    def __init__(self, workspace: Path) -> None:
        self.root = Path(workspace).resolve() / "facts"

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / ".lock").open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _one_line(value: str, limit: int) -> str:
        return " ".join(str(value or "").split())[:limit]

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())

    @staticmethod
    def _parse_date(value: str) -> str:
        if not value:
            return ""
        return date.fromisoformat(value).isoformat()

    def _read(self, path: Path) -> dict[str, Any] | None:
        try:
            content = path.read_text(encoding="utf-8")
            if not content.startswith("---\n"):
                return None
            frontmatter, fact = content[4:].split("\n---\n", 1)
            metadata = yaml.safe_load(frontmatter)
            if not isinstance(metadata, dict) or not fact.strip():
                return None
            return {**metadata, "fact": fact.strip(), "path": path}
        except (OSError, ValueError, yaml.YAMLError):
            return None

    def _records(self) -> list[dict[str, Any]]:
        return [
            record for path in self.root.glob("*.md")
            if (record := self._read(path)) is not None
        ]

    def _write(self, path: Path, record: dict[str, Any]) -> None:
        metadata = {key: value for key, value in record.items() if key not in {"fact", "path"}}
        content = "---\n" + yaml.safe_dump(
            metadata, allow_unicode=True, sort_keys=False
        ) + "---\n\n" + record["fact"].strip() + "\n"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.root, prefix=".fact-", delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def add(
        self, *, fact: str, category: str, source_ref: str = "",
        applies_when: str = "", valid_until: str = "",
    ) -> dict[str, Any]:
        fact = self._one_line(fact, 1000)
        if not fact:
            raise ValueError("fact is required")
        source_ref = self._one_line(source_ref, 200)
        applies_when = self._one_line(applies_when, 200)
        if not source_ref or not applies_when:
            raise ValueError("source_ref and applies_when are required")
        valid_until = self._parse_date(valid_until)
        if valid_until and valid_until < date.today().isoformat():
            raise ValueError("已过期的事实不能写入长期记忆")
        with self._locked():
            for existing in self._records():
                if self._normalize(existing["fact"]) == self._normalize(fact):
                    return {"status": "duplicate", "fact_id": existing["name"]}
            fact_id = f"fact-{uuid4().hex[:16]}"
            record = {
                "name": fact_id,
                "description": fact[:150],
                "metadata": {
                    "type": category,
                    "source_ref": source_ref,
                    "applies_when": applies_when,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "valid_until": valid_until or None,
                },
                "fact": fact,
            }
            self._write(self.root / f"{fact_id}.md", record)
            return {"status": "created", "fact_id": fact_id}

    def _find(self, old_text: str, category: str | None = None) -> list[dict[str, Any]]:
        needle = self._normalize(old_text)
        if not needle:
            return []
        return [
            record for record in self._records()
            if (needle in self._normalize(record["fact"]) or needle == record["name"])
            and (not category or record.get("metadata", {}).get("type") == category)
        ]

    def replace(self, old_text: str, new_text: str, category: str | None = None) -> str:
        with self._locked():
            matches = self._find(old_text, category)
            if not matches:
                return "not_found"
            if len(matches) > 1:
                return "ambiguous"
            record = matches[0]
            replacement = self._one_line(new_text, 1000)
            if not replacement:
                raise ValueError("new_text is required")
            record["fact"] = replacement
            record["description"] = replacement[:150]
            record["metadata"]["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._write(record["path"], record)
            return "replaced"

    def remove(self, old_text: str, category: str | None = None) -> str:
        with self._locked():
            matches = self._find(old_text, category)
            if not matches:
                return "not_found"
            if len(matches) > 1:
                return "ambiguous"
            matches[0]["path"].unlink()
            return "removed"

    def index(self) -> str:
        if not self.root.is_dir():
            return ""
        today = date.today().isoformat()
        with self._locked():
            records = sorted(
                self._records(),
                key=lambda record: record.get("metadata", {}).get("updated_at")
                or record.get("metadata", {}).get("created_at", ""),
                reverse=True,
            )
        lines = []
        used = 0
        for record in records:
            metadata = record.get("metadata") or {}
            expiry = metadata.get("valid_until")
            if expiry and str(expiry) < today:
                continue
            line = (
                f"- [{record['description']}]({format_agent_path(record['path'])}) "
                f"[{metadata.get('type', '事实')}] "
                f"适用：{metadata.get('applies_when', '需核验')}；"
                f"来源：{metadata.get('source_ref', '未记录，待核验')}"
            )
            if len(lines) >= self.INDEX_LIMIT or used + len(line) > self.INDEX_CHAR_LIMIT:
                lines.append("- 其余事实未载入；需要时查看记忆目录。")
                break
            lines.append(line)
            used += len(line)
        if not lines:
            return ""
        return "## 已整理事实索引\n" + "\n".join(lines)
