"""Shared Anthropic-compatible multimodal calls for Alibaba Cloud Bailian."""

from __future__ import annotations

import base64
import io
from typing import Any

from anthropic import Anthropic, AsyncAnthropic
from PIL import Image

SUPPORTED_IMAGE_MEDIA_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}


def build_anthropic_image_block(image_url: str) -> dict[str, Any]:
    """Convert an HTTP or data URL into an Anthropic image content block."""

    if image_url.startswith("data:"):
        header, separator, data = image_url.partition(",")
        if not separator or ";base64" not in header:
            raise ValueError("Invalid base64 image data URL")
        media_type = header[5:].split(";", 1)[0].lower()
        if media_type == "image/jpg":
            media_type = "image/jpeg"
        elif media_type in {"image/bmp", "image/x-ms-bmp"}:
            try:
                image = Image.open(io.BytesIO(base64.b64decode(data)))
                output = io.BytesIO()
                image.convert("RGB").save(output, format="PNG")
                data = base64.b64encode(output.getvalue()).decode("ascii")
                media_type = "image/png"
            except Exception as exc:
                raise ValueError("Invalid BMP image data") from exc
        if not media_type.startswith("image/") or not data:
            raise ValueError("Invalid image media type or empty image data")
        if media_type not in SUPPORTED_IMAGE_MEDIA_TYPES:
            raise ValueError(f"Unsupported Anthropic image media type: {media_type}")
        source = {"type": "base64", "media_type": media_type, "data": data}
    elif image_url.startswith(("http://", "https://")):
        source = {"type": "url", "url": image_url}
    else:
        raise ValueError("Bailian vision input must be an HTTP URL or image data URL")
    return {"type": "image", "source": source}


def _request_params(*, image_url: str, prompt: str, model: str, max_tokens: int) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    build_anthropic_image_block(image_url),
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }


def _response_text(response: Any) -> str:
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        block_type = getattr(block, "type", None)
        text = getattr(block, "text", None)
        if isinstance(block, dict):
            block_type = block.get("type")
            text = block.get("text")
        if block_type == "text" and text:
            parts.append(str(text))
    return "\n".join(parts).strip()


def _response_dict(response: Any) -> dict[str, Any]:
    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dumped
    return {"content": getattr(response, "content", [])}


def call_bailian_vision_sync(
    *,
    image_url: str,
    prompt: str,
    api_key: str,
    base_url: str,
    model: str,
    timeout: float,
    max_tokens: int = 4096,
) -> tuple[str, dict[str, Any]]:
    """Call Bailian's Anthropic-compatible multimodal API synchronously."""

    client = Anthropic(api_key=api_key, base_url=base_url.rstrip("/"), timeout=timeout, max_retries=2)
    try:
        response = client.messages.create(
            **_request_params(
                image_url=image_url,
                prompt=prompt,
                model=model,
                max_tokens=max_tokens,
            )
        )
        return _response_text(response), _response_dict(response)
    finally:
        client.close()


async def call_bailian_vision(
    *,
    image_url: str,
    prompt: str,
    api_key: str,
    base_url: str,
    model: str,
    timeout: float,
    max_tokens: int = 4096,
) -> tuple[str, dict[str, Any]]:
    """Call Bailian's Anthropic-compatible multimodal API asynchronously."""

    client = AsyncAnthropic(api_key=api_key, base_url=base_url.rstrip("/"), timeout=timeout, max_retries=2)
    try:
        response = await client.messages.create(
            **_request_params(
                image_url=image_url,
                prompt=prompt,
                model=model,
                max_tokens=max_tokens,
            )
        )
        return _response_text(response), _response_dict(response)
    finally:
        await client.close()
