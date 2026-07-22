from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChangeRecord:
    revision: int
    source: str
    paths: list[str]
    dirty_slides: list[str]


@dataclass(frozen=True)
class ProjectState:
    project_dir: str
    revision: int
    dirty_slides: list[str] = field(default_factory=list)
    hashes: dict[str, str] = field(default_factory=dict)
    changes: list[ChangeRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


EditResult = ProjectState
DirtyState = ProjectState
