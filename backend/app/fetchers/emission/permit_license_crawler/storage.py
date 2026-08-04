from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredFile:
    path: Path
    relative_path: Path
    size_bytes: int
    sha256: str


def safe_component(value: str, *, fallback: str) -> str:
    cleaned = re.sub(r"[\\/\x00-\x1f\x7f]+", "_", value).strip(" .")
    if cleaned in {"", ".", ".."}:
        cleaned = fallback
    return cleaned[:180]


class FileStorage:
    def __init__(
        self,
        root: Path | str,
        project_root: Path | str | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve() if project_root is not None else None
        root_path = Path(root)
        if not root_path.is_absolute() and self.project_root is not None:
            root_path = self.project_root / root_path
        self.root = root_path.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, relative_path: Path | str) -> tuple[Path, Path]:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe path: {relative}")
        root_relative = relative
        if self.project_root is not None:
            try:
                prefix = self.root.relative_to(self.project_root)
            except ValueError:
                prefix = None
            if prefix is not None and (
                relative == prefix or prefix in relative.parents
            ):
                root_relative = relative.relative_to(prefix)
        target = (self.root / root_relative).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError(f"unsafe path: {relative}")
        if self.project_root is not None:
            stored_relative = target.relative_to(self.project_root)
        else:
            stored_relative = root_relative
        return target, stored_relative

    def resolve(self, relative_path: Path | str) -> Path:
        target, _ = self._resolve(relative_path)
        return target

    def write_bytes(self, relative_path: Path | str, content: bytes) -> StoredFile:
        target, relative = self._resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.part")
        try:
            temporary.write_bytes(content)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return StoredFile(
            path=target,
            relative_path=relative,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

    def describe(self, relative_path: Path | str) -> StoredFile:
        target, relative = self._resolve(relative_path)
        content = target.read_bytes()
        return StoredFile(
            path=target,
            relative_path=relative,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
