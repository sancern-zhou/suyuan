"""Frame target resolution for browser actions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class FrameTarget:
    """Parsed frame target from explicit params or a frame-prefixed ref."""

    frame_url: Optional[str] = None
    frame_name: Optional[str] = None
    frame_index: Optional[int] = None
    element_ref: Optional[str] = None

    @classmethod
    def from_ref(cls, ref: Optional[str]) -> "FrameTarget":
        """Parse refs like f1:e3 into frame index and element ref."""
        if not ref or ":" not in ref:
            return cls(element_ref=ref)

        frame_part, element_ref = ref.split(":", 1)
        if len(frame_part) < 2 or frame_part[0] != "f" or not frame_part[1:].isdigit():
            return cls(element_ref=ref)

        return cls(frame_index=int(frame_part[1:]), element_ref=element_ref)


def split_frame_ref(ref: Optional[str]) -> Tuple[Optional[int], Optional[str]]:
    """Return (frame_index, element_ref) for a ref."""
    target = FrameTarget.from_ref(ref)
    return target.frame_index, target.element_ref


def resolve_frame(
    page,
    frame_url: Optional[str] = None,
    frame_name: Optional[str] = None,
    frame_index: Optional[int] = None,
):
    """Resolve a Playwright Frame from explicit target params.

    Defaults to the main frame (index 0). URL matching is substring-based so
    callers can target generated or query-bearing frame URLs without exact URLs.
    """
    try:
        frames = list(page.frames)
    except TypeError:
        if frame_index is None and not frame_name and not frame_url:
            return page
        raise

    if frame_index is not None:
        index = int(frame_index)
        if index < 0 or index >= len(frames):
            raise ValueError(f"Frame index {index} out of range. Available frames: 0..{len(frames) - 1}")
        return frames[index]

    if frame_name:
        for frame in frames:
            name = getattr(frame, "name", None)
            if callable(name):
                name = name()
            if name == frame_name:
                return frame
        raise ValueError(f"Frame with name '{frame_name}' not found")

    if frame_url:
        for frame in frames:
            if frame_url in getattr(frame, "url", ""):
                return frame
        raise ValueError(f"Frame with URL containing '{frame_url}' not found")

    if not frames:
        raise ValueError("No frames are available on the active page")
    return frames[0]
