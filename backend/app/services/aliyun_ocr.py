"""Aliyun cloud market OCR client for the high-precision text recognition API."""

from __future__ import annotations

import base64
import os
import re
from typing import Any

import httpx
import structlog

from config.settings import settings

logger = structlog.get_logger()

ALIYUN_OCR_ENDPOINT = os.getenv(
    "ALIYUN_OCR_ENDPOINT",
    "https://gjbsb.market.alicloudapi.com/ocrservice/advanced",
).strip()
ALIYUN_OCR_TIMEOUT_SECONDS = float(os.getenv("ALIYUN_OCR_TIMEOUT_SECONDS", "120"))


def resolve_aliyun_ocr_app_code() -> str:
    """Resolve the AppCode used by the Aliyun market OCR endpoint."""
    return str(
        os.getenv("ALIYUN_OCR_APP_CODE")
        or getattr(settings, "aliyun_ocr_app_code", "")
        or ""
    ).strip()


def _join_line_tokens(tokens: list[str]) -> str:
    if not tokens:
        return ""
    if any(re.search(r"[A-Za-z0-9]", token) for token in tokens):
        return " ".join(tokens)
    return "".join(tokens)


def _reconstruct_text_from_words_info(words_info: list[dict[str, Any]]) -> str:
    """Rebuild readable lines from Aliyun OCR word boxes."""
    words: list[tuple[float, float, float, str]] = []
    for item in words_info:
        word = str(item.get("word", "")).strip()
        if not word:
            continue
        x = float(item.get("x") or 0.0)
        y = float(item.get("y") or 0.0)
        height = float(item.get("height") or 0.0)
        words.append((y, x, height, word))

    if not words:
        return ""

    words.sort(key=lambda item: (item[0], item[1]))

    lines: list[list[tuple[float, str]]] = []
    current_line: list[tuple[float, str]] = []
    current_y: float | None = None
    current_height = 0.0

    for y, x, height, word in words:
        if current_line:
            tolerance = max(12.0, current_height * 0.75 or 12.0)
            if current_y is not None and abs(y - current_y) > tolerance:
                lines.append(current_line)
                current_line = []
                current_y = None
                current_height = 0.0

        current_line.append((x, word))
        if current_y is None:
            current_y = y
        else:
            current_y = (current_y + y) / 2.0
        current_height = max(current_height, height)

    if current_line:
        lines.append(current_line)

    rendered_lines = []
    for line in lines:
        line.sort(key=lambda item: item[0])
        tokens = [token for _, token in line if token]
        rendered = _join_line_tokens(tokens).strip()
        if rendered:
            rendered_lines.append(rendered)

    return "\n".join(rendered_lines).strip()


def extract_aliyun_ocr_text(response_data: dict[str, Any]) -> str:
    """Extract a readable text payload from the OCR response."""
    raw_content = str(response_data.get("content") or "").strip()
    words_info = response_data.get("prism_wordsInfo") or []
    if not words_info:
        return raw_content

    reconstructed = _reconstruct_text_from_words_info(words_info)
    if not reconstructed:
        return raw_content

    if raw_content and len(raw_content) >= len(reconstructed) * 1.5 and "\n" not in reconstructed:
        return raw_content

    return reconstructed


async def call_aliyun_ocr(
    image_bytes: bytes,
    *,
    app_code: str | None = None,
    endpoint: str | None = None,
    timeout_seconds: float | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[str, dict[str, Any]]:
    """Call the Aliyun market OCR endpoint and return the normalized text."""
    resolved_app_code = (app_code or resolve_aliyun_ocr_app_code()).strip()
    if not resolved_app_code:
        raise RuntimeError("未配置 ALIYUN_OCR_APP_CODE")

    payload = {
        "img": base64.b64encode(image_bytes).decode("ascii"),
        "NeedRotate": True,
        "NeedSortPage": True,
        "OutputTable": True,
    }
    headers = {
        "Authorization": f"APPCODE {resolved_app_code}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    timeout = httpx.Timeout(timeout_seconds or ALIYUN_OCR_TIMEOUT_SECONDS)
    request_url = (endpoint or ALIYUN_OCR_ENDPOINT).strip()

    try:
        if client is None:
            async with httpx.AsyncClient(timeout=timeout) as local_client:
                response = await local_client.post(request_url, json=payload, headers=headers)
        else:
            response = await client.post(request_url, json=payload, headers=headers)

        response.raise_for_status()
        response_data = response.json()
        if not isinstance(response_data, dict):
            raise RuntimeError("Aliyun OCR returned unexpected payload type")
    except httpx.HTTPStatusError as exc:
        response = exc.response
        snippet = response.text[:500].strip()
        raise RuntimeError(f"Aliyun OCR 请求失败: {response.status_code} {snippet}") from exc
    except ValueError as exc:
        snippet = response.text[:500].strip() if "response" in locals() else ""
        raise RuntimeError(f"Aliyun OCR 返回非 JSON 数据: {snippet}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Aliyun OCR 请求失败: {exc}") from exc

    text = extract_aliyun_ocr_text(response_data).strip()
    logger.debug(
        "aliyun_ocr_page_completed",
        content_length=len(text),
        endpoint=request_url,
    )
    return text, response_data
