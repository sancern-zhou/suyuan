"""Mode-scoped case storage maintained through Agent tool calls."""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import fcntl

from app.utils.path_config import get_data_registry


def _safe_mode(mode: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(mode or "").strip()).strip("_")
    if not value:
        raise ValueError("case library mode is required")
    return value[:80]


class AgentCaseLibrary:
    """Append-only case library for one Agent mode."""

    MAX_CASES = 1000

    def __init__(self, mode: str, *, base_dir: Path | None = None) -> None:
        self.mode = _safe_mode(mode)
        root = base_dir or (get_data_registry() / "memory" / self.mode)
        self.root = Path(root).resolve()
        self.cases_file = self.root / "cases.jsonl"
        self.lock_file = self.root / ".cases.lock"

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lock_file.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def append(self, case: dict[str, Any]) -> None:
        """Append an Agent-authored case and retain the newest bounded set."""

        with self._lock():
            with self.cases_file.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(case, ensure_ascii=False, default=str) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._prune_unlocked()

    def search(
        self,
        *,
        query: str = "",
        scenario: str = "",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return newest matching cases using a compact literal text filter."""

        normalized_query = query.strip().casefold()
        normalized_scenario = scenario.strip().casefold()
        matches: list[dict[str, Any]] = []
        with self._lock():
            cases = self._read_unlocked()
        for case in reversed(cases):
            case_scenario = str(case.get("scenario") or "").casefold()
            if normalized_scenario and case_scenario != normalized_scenario:
                continue
            if normalized_query:
                haystack = json.dumps(case, ensure_ascii=False, default=str).casefold()
                if normalized_query not in haystack:
                    continue
            matches.append(case)
            if len(matches) >= max(1, min(limit, 100)):
                break
        return matches

    def count(self) -> int:
        with self._lock():
            return len(self._read_unlocked())

    def _read_unlocked(self) -> list[dict[str, Any]]:
        try:
            lines = self.cases_file.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        cases: list[dict[str, Any]] = []
        for line in lines:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                cases.append(value)
        return cases

    def _prune_unlocked(self) -> None:
        cases = self._read_unlocked()
        if len(cases) <= self.MAX_CASES:
            return
        temporary = self.cases_file.with_name(f".{self.cases_file.name}.{os.getpid()}.tmp")
        temporary.write_text(
            "".join(
                json.dumps(case, ensure_ascii=False, default=str) + "\n"
                for case in cases[-self.MAX_CASES:]
            ),
            encoding="utf-8",
        )
        os.replace(temporary, self.cases_file)
