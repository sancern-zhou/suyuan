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


def build_base64_user_content(
    text: str,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> str | List[Dict[str, Any]]:
    """Build Anthropic content blocks forcing local image bytes.

    Used only as a current-turn fallback when a provider cannot fetch a remote
    signed URL. The returned content must never be persisted to history.
    """
    if not attachments:
        return text

    blocks: List[Dict[str, Any]] = [{"type": "text", "text": text}]
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        if attachment.get("type") != "image":
            continue
        image_block = _build_local_base64_image_block(attachment)
        if image_block:
            blocks.append(image_block)

    return blocks if len(blocks) > 1 else text


def _build_image_block(attachment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    local_path = attachment.get("local_path") or attachment.get("path")
    if local_path:
        image_block = _build_local_base64_image_block(attachment)
        if image_block:
            return image_block

    url = attachment.get("url") or attachment.get("signed_url")
    if isinstance(url, str) and (url.startswith("http://") or url.startswith("https://")):
        return {
            "type": "image",
            "source": {
                "type": "url",
                "url": url,
            },
        }

    return None


def _build_local_base64_image_block(attachment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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

    return None


def build_persisted_user_content(
    text: str,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> str | List[Dict[str, Any]]:
    """Build compact history content for a multimodal social user turn."""
    if not attachments:
        return text

    blocks: List[Dict[str, Any]] = [{"type": "text", "text": text}]
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        if attachment.get("type") != "image":
            continue
        name = str(attachment.get("name") or "image")
        media_type = str(attachment.get("mime_type") or attachment.get("content_type") or "image")
        blocks.append(
            {
                "type": "text",
                "text": f"[用户发送了一张图片：{name}，{media_type}，已在当前轮以原生多模态方式提供。]",
            }
        )

    return blocks if len(blocks) > 1 else text


def extract_multimodal_attachments(observation: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract image attachments emitted by tools for the next native multimodal turn."""
    attachments: List[Dict[str, Any]] = []

    def collect(value: Any) -> None:
        if not isinstance(value, dict):
            return

        if value.get("type") == "multimodal_attachment":
            candidates = value.get("attachments")
            if not candidates and isinstance(value.get("data"), dict):
                candidates = value["data"].get("attachments")
            if isinstance(candidates, list):
                for item in candidates:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") != "image":
                        continue
                    if item.get("url") or item.get("signed_url") or item.get("local_path") or item.get("path"):
                        attachments.append(item)

        for item in value.get("tool_results", []) or []:
            if isinstance(item, dict):
                collect(item.get("result"))

    collect(observation)
    return attachments


def _media_type(attachment: Dict[str, Any], path: Path) -> str:
    value = attachment.get("mime_type") or attachment.get("content_type")
    if isinstance(value, str) and value.startswith("image/"):
        return value

    guessed, _ = guess_type(path.name)
    if guessed and guessed.startswith("image/"):
        return guessed
    return "image/png"
