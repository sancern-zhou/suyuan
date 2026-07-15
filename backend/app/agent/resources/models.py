"""Typed identities for resources that survive agent requests."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ResourceKind(str, Enum):
    DATA = "data"
    FILE = "file"
    ARTIFACT = "artifact"
    URL = "url"
    VISUAL = "visual"


class ResourceRole(str, Enum):
    PRIMARY = "primary"
    SOURCE = "source"
    REPORT = "report"
    OUTPUT = "output"
    ATTACHMENT = "attachment"


class ResourceStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    MISSING = "missing"
    INVALID = "invalid"


class ResourceImportance(str, Enum):
    NORMAL = "normal"
    HIGH = "high"
    PINNED = "pinned"


class ResourceLocator(BaseModel):
    data_id: str | None = None
    path: str | None = None
    url: str | None = None
    artifact_id: str | None = None
    visual_id: str | None = None

    @model_validator(mode="after")
    def validate_one_identifier(self) -> "ResourceLocator":
        values = [self.data_id, self.path, self.url, self.artifact_id, self.visual_id]
        if sum(bool(value) for value in values) != 1:
            raise ValueError("resource locator requires exactly one primary identifier")
        if self.path:
            self.path = str(Path(self.path).expanduser().resolve())
        return self

    def identity_payload(self) -> dict[str, str]:
        return {
            key: value
            for key, value in self.model_dump().items()
            if isinstance(value, str) and value
        }


class SessionResourceRef(BaseModel):
    ref_id: str
    kind: ResourceKind
    locator: ResourceLocator
    logical_key: str | None = None
    role: ResourceRole = ResourceRole.OUTPUT
    label: str
    tool_name: str
    run_id: str
    turn_sequence: int
    status: ResourceStatus = ResourceStatus.ACTIVE
    importance: ResourceImportance = ResourceImportance.NORMAL
    created_at: datetime
    last_seen_at: datetime
    last_used_at: datetime | None = None
    supersedes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        kind: ResourceKind,
        locator: ResourceLocator,
        **kwargs: Any,
    ) -> "SessionResourceRef":
        identity = json.dumps(
            {"kind": kind.value, "locator": locator.identity_payload()},
            ensure_ascii=False,
            sort_keys=True,
        )
        now = datetime.now(timezone.utc)
        return cls(
            ref_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
            kind=kind,
            locator=locator,
            created_at=now,
            last_seen_at=now,
            **kwargs,
        )
