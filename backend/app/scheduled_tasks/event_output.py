"""Parse the strict delivery contract returned by event task Agents."""

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class BroadcastPayload(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    media: list[str] = Field(default_factory=list)


class EventTaskOutput(BaseModel):
    success: bool
    broadcast: BroadcastPayload | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_result(self):
        if self.success and self.broadcast is None:
            raise ValueError("broadcast is required for successful event output")
        if not self.success and not (self.error or "").strip():
            raise ValueError("error is required for failed event output")
        return self


def parse_event_task_output(text: str) -> EventTaskOutput:
    """Parse JSON, accepting a single optional Markdown JSON fence."""
    stripped = (text or "").strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped)
    if fence_match:
        stripped = fence_match.group(1).strip()
    else:
        prefaced_fence = re.fullmatch(
            r"[^`]{1,200}?\s*```json\s*([\s\S]*?)\s*```",
            stripped,
            flags=re.IGNORECASE,
        )
        if prefaced_fence:
            stripped = prefaced_fence.group(1).strip()

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"event task output is not valid JSON: {exc.msg}") from exc

    output = EventTaskOutput.model_validate(payload)
    if output.success and output.broadcast:
        for media_path in output.broadcast.media:
            if media_path.startswith(("http://", "https://")):
                continue
            if not Path(media_path).is_file():
                raise ValueError(f"attachment does not exist: {media_path}")
    return output
