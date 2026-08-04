from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GisctlResult(BaseModel):
    status: Literal["success", "failed"] = "success"
    success: bool = True
    data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""

    @classmethod
    def from_map_program(
        cls,
        *,
        command: str,
        summary: str,
        map_program: dict[str, Any] | None,
        file_paths: list[str] | None = None,
        artifacts: list[str] | None = None,
        success: bool = True,
        metadata_extra: dict[str, Any] | None = None,
    ) -> "GisctlResult":
        file_paths = file_paths or []
        artifacts = artifacts or []
        status: Literal["success", "failed"] = "success" if success else "failed"
        payload = {
            "command": command,
            "file_paths": file_paths,
            "artifacts": artifacts,
            "map_program": map_program,
        }
        metadata = {
            "schema_version": "gisctl.v1",
            "tool_name": "visual_interaction",
            "generator": "visual_interaction",
            "command": command,
            "file_paths": file_paths,
            "artifacts": artifacts,
            "map_program": map_program,
        }
        if metadata_extra:
            metadata.update(metadata_extra)

        return cls(
            status=status,
            success=success,
            data=payload,
            metadata=metadata,
            summary=summary,
        )
