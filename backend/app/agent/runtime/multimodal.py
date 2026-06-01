"""Helpers for native multimodal social-mode messages."""

from __future__ import annotations

import base64
from mimetypes import guess_type
from pathlib import Path
from typing import Any, Dict, List, Optional


def build_anthropic_user_content(
    text: str,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> str | List[Dict[str, Any]]:
    """Build Anthropic content blocks for a user turn.

    Social mode uses MiniMax-M3 through the Anthropic-compatible endpoint, so
    image attachments should be sent as native image blocks instead of as text
    paths that the model cannot inspect.
    """
    if not attachments:
        return text

    blocks: List[Dict[str, Any]] = [{"type": "text", "text": text}]
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        if attachment.get("type") != "image":
            continue

        image_block = _build_image_block(attachment)
        if image_block:
            blocks.append(image_block)

    return blocks if len(blocks) > 1 else text


def _build_image_block(attachment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    local_path = attachment.get("local_path") or attachment.get("path")
    if local_path:
        path = Path(str(local_path))
        if path.exists() and path.is_file():
            media_type = _media_type(attachment, path)
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": encoded,
                },
            }

    url = attachment.get("url")
    if isinstance(url, str) and (url.startswith("http://") or url.startswith("https://")):
        return {
            "type": "image",
            "source": {
                "type": "url",
                "url": url,
            },
        }

    return None


def _media_type(attachment: Dict[str, Any], path: Path) -> str:
    value = attachment.get("mime_type") or attachment.get("content_type")
    if isinstance(value, str) and value.startswith("image/"):
        return value

    guessed, _ = guess_type(path.name)
    if guessed and guessed.startswith("image/"):
        return guessed
    return "image/png"
