"""OCR adapter for attachment review via OpenAI-compatible multimodal APIs."""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
from pathlib import Path
from threading import Lock
from urllib.parse import urljoin, urlparse
from typing import Any

import requests

from config.settings import settings


QWEN_VL_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MIMO_VL_BASE_URL = "https://api.xiaomimimo.com/v1"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_FLOW_VISUAL_TIMEOUT_SECONDS = 90
DEFAULT_PROMPT = "请识别图片中的所有文字内容，按原文输出，不要添加任何解释。"
DEFAULT_MODEL = "qwen-vl-ocr"
DEFAULT_VISION_MODEL = "qwen3.7-plus"
DEFAULT_MIMO_MODEL = "mimo-v2.5"
PDF_FIRST_PAGE_RENDER_DPI = 180
_OCR_CACHE: dict[tuple[str, str, int, int], dict[str, Any]] = {}
_OCR_CACHE_LIMIT = 64
_FLOW_PROVIDER_LOCK = Lock()
_FLOW_PROVIDER_INDEX = 0


def extract_attachment_text(source: str, *, provider: str | None = None) -> dict[str, Any]:
    """Use the configured OCR model to extract text from an attachment."""

    ocr_mode = _normalize_mode(provider)
    target = _resolve_target(ocr_mode)
    return _call_vision_model(source, target=target, mode=ocr_mode, prompt=DEFAULT_PROMPT, task="ocr_text")


def extract_attachment_json(
    source: str,
    *,
    prompt: str,
    task: str,
    provider: str | None = None,
) -> dict[str, Any]:
    """Use the configured multimodal model to extract structured JSON from an attachment."""

    ocr_mode = _normalize_mode(provider)
    target = _resolve_target(ocr_mode)
    result = _call_vision_model(source, target=target, mode=ocr_mode, prompt=prompt, task=task)
    if result.get("status") != "success":
        return result

    parsed = _extract_json_from_text(str(result.get("text") or ""))
    if not isinstance(parsed, dict):
        result["status"] = "error"
        result["error"] = "多模态识别结果不是有效JSON"
        result["data"] = {}
        return result
    result["data"] = parsed
    return result


def _call_vision_model(source: str, *, target: dict[str, str], mode: str, prompt: str, task: str) -> dict[str, Any]:
    """Call an OpenAI-compatible multimodal endpoint with an image and text prompt."""

    provider_id = target["provider"]
    model = target["model"]

    resolved = _resolve_source(source)
    if resolved.get("status") != "success":
        return _error_result(source, model, str(resolved.get("error") or "附件路径不可用"))

    cache_key = _cache_key(resolved, f"{provider_id}/{model}", task=task, prompt=prompt)
    cached = _OCR_CACHE.get(cache_key)
    if cached:
        return dict(cached)

    api_key = target["api_key"]
    if not api_key:
        return _error_result(source, model, f"未配置 {provider_id} 视觉模型 API Key")

    image_payload = _build_image_url_payload(resolved)
    if image_payload.get("status") != "success":
        return _error_result(source, model, str(image_payload.get("error") or "图片载荷构建失败"))
    api_url = target["base_url"].rstrip("/")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_payload["url"]},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            f"{api_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=_request_timeout_seconds(mode),
        )
        response.raise_for_status()
        raw_response = response.json()
    except requests.Timeout as exc:
        return _error_result(source, model, f"OCR 请求超时：{exc}")
    except requests.RequestException as exc:
        return _error_result(source, model, f"OCR 请求失败：{exc}")
    except ValueError as exc:
        return _error_result(source, model, f"OCR 响应解析失败：{exc}")

    service_error = _extract_service_error(raw_response)
    if service_error:
        return _error_result(source, model, service_error, raw_response=raw_response)

    text = _extract_text_from_response(raw_response)
    confidence = _estimate_confidence(text, raw_response)

    result = {
        "provider": model,
        "provider_id": provider_id,
        "mode": mode,
        "task": task,
        "input_mode": resolved.get("kind"),
        "status": "success",
        "source": str(resolved.get("path") or resolved.get("url") or source),
        "original_source": source,
        "text": text,
        "confidence": confidence,
        "raw_response": raw_response,
    }
    _cache_store(cache_key, result)
    return result


def _normalize_mode(provider: str | None) -> str:
    value = str(provider or "general").strip().lower()
    if value in {"document", "table", "general", "flow_visual"}:
        return value
    return "general"


def _resolve_target(mode: str) -> dict[str, str]:
    if mode == "flow_visual":
        return _select_flow_visual_target()
    return _qwen_target(mode)


def _select_flow_visual_target() -> dict[str, str]:
    providers = _flow_visual_providers()
    if not providers:
        return _qwen_target("general")

    global _FLOW_PROVIDER_INDEX
    with _FLOW_PROVIDER_LOCK:
        target = providers[_FLOW_PROVIDER_INDEX % len(providers)]
        _FLOW_PROVIDER_INDEX += 1
        return target


def _flow_visual_providers() -> list[dict[str, str]]:
    raw = os.getenv("OPS_AUDIT_FLOW_VISUAL_PROVIDERS", "qwen")
    names = [item.strip().lower() for item in raw.split(",") if item.strip()]
    targets: list[dict[str, str]] = []
    for name in names:
        if name in {"qwen", "qwen_vl", "qwen-vl"}:
            targets.append(_qwen_target("flow_visual"))
        elif name in {"mimo", "mimo_vl", "mimo-vl"}:
            targets.append(_mimo_target())
    return targets


def flow_visual_provider_summary() -> list[dict[str, Any]]:
    """Return provider/model settings used by flow-photo vision checks."""

    summary = []
    for target in _flow_visual_providers():
        summary.append(
            {
                "provider": target["provider"],
                "model": target["model"],
                "base_url": target["base_url"],
            }
        )
    return summary


def _qwen_target(mode: str) -> dict[str, str]:
    return {
        "provider": "qwen",
        "model": _resolve_qwen_model(mode),
        "base_url": _resolve_qwen_base_url(),
        "api_key": _resolve_qwen_api_key(),
    }


def _mimo_target() -> dict[str, str]:
    return {
        "provider": "mimo",
        "model": str(
            os.getenv("MIMO_VL_MODEL")
            or os.getenv("OPS_AUDIT_FLOW_VISUAL_MIMO_MODEL")
            or getattr(settings, "mimo_vl_model", "")
            or DEFAULT_MIMO_MODEL
        ).strip(),
        "base_url": _normalize_openai_base_url(
            str(
                os.getenv("MIMO_VL_BASE_URL")
                or getattr(settings, "mimo_vl_base_url", "")
                or getattr(settings, "mimo_base_url", "")
                or MIMO_VL_BASE_URL
            ).strip()
        ),
        "api_key": str(
            os.getenv("MIMO_VL_API_KEY")
            or getattr(settings, "mimo_vl_api_key", "")
            or getattr(settings, "mimo_api_key", "")
            or ""
        ).strip(),
    }


def _resolve_qwen_model(mode: str) -> str:
    if mode == "flow_visual":
        return str(
            os.getenv("QWEN_VISION_MODEL")
            or os.getenv("OPS_AUDIT_FLOW_VISUAL_QWEN_MODEL")
            or getattr(settings, "qwen_vision_model", "")
            or DEFAULT_VISION_MODEL
        ).strip()
    if mode == "document":
        return str(os.getenv("OCR_DOCUMENT_MODEL") or os.getenv("OCR_MODEL") or DEFAULT_MODEL).strip()
    if mode == "table":
        return str(os.getenv("OCR_TABLE_MODEL") or os.getenv("OCR_MODEL") or DEFAULT_MODEL).strip()
    return str(
        os.getenv("OCR_GENERAL_MODEL")
        or os.getenv("OCR_MODEL")
        or getattr(settings, "qwen_vl_model", "")
        or DEFAULT_MODEL
    ).strip()


def _request_timeout_seconds(mode: str) -> int:
    if mode != "flow_visual":
        return DEFAULT_TIMEOUT_SECONDS
    raw = os.getenv("OPS_AUDIT_FLOW_VISUAL_TIMEOUT_SECONDS")
    try:
        return max(1, int(raw)) if raw else DEFAULT_FLOW_VISUAL_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        return DEFAULT_FLOW_VISUAL_TIMEOUT_SECONDS


def _resolve_qwen_base_url() -> str:
    return str(os.getenv("QWEN_VL_BASE_URL") or getattr(settings, "qwen_vl_base_url", "") or QWEN_VL_BASE_URL).strip()


def _resolve_qwen_api_key() -> str:
    key = (
        os.getenv("QWEN_VL_API_KEY")
        or os.getenv("OCR_API_KEY")
        or getattr(settings, "qwen_vl_api_key", "")
        or getattr(settings, "aliyun_ocr_access_key_id", "")
    )
    return str(key).strip()


def _normalize_openai_base_url(base_url: str) -> str:
    value = (base_url or MIMO_VL_BASE_URL).strip().rstrip("/")
    if value.endswith("/anthropic"):
        return value[: -len("/anthropic")] + "/v1"
    return value


def _resolve_source(source: str) -> dict[str, Any]:
    text = str(source or "").strip()
    if not text:
        return {"status": "error", "error": "附件路径为空"}

    parsed = urlparse(text)
    if parsed.scheme in {"http", "https"}:
        return {"status": "success", "kind": "url", "url": text}

    path = Path(text).expanduser()
    if path.exists():
        return {"status": "success", "kind": "file", "path": str(path)}

    attachment_root = (
        os.getenv("OPS_ATTACHMENT_ROOT")
        or os.getenv("ATTACHMENT_ROOT")
        or getattr(settings, "ops_attachment_root", "")
        or getattr(settings, "attachment_root", "")
    )
    if attachment_root:
        rooted = Path(attachment_root).expanduser() / text.lstrip("/")
        if rooted.exists():
            return {"status": "success", "kind": "file", "path": str(rooted)}

    attachment_base_url = (
        os.getenv("OPS_ATTACHMENT_BASE_URL")
        or os.getenv("ATTACHMENT_BASE_URL")
        or getattr(settings, "ops_attachment_base_url", "")
        or getattr(settings, "attachment_base_url", "")
    )
    if attachment_base_url and text.startswith("/"):
        full_url = urljoin(attachment_base_url.rstrip("/") + "/", text.lstrip("/"))
        return {"status": "success", "kind": "url", "url": full_url}

    return {"status": "error", "error": f"文件不存在且未配置附件根路径/基础URL：{source}"}


def _build_image_url_payload(resolved: dict[str, Any]) -> dict[str, Any]:
    if resolved.get("kind") == "url" and resolved.get("url"):
        url = str(resolved["url"])
        if _looks_like_pdf_source(url):
            try:
                response = requests.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
                response.raise_for_status()
            except requests.Timeout as exc:
                return {"status": "error", "error": f"下载PDF首页失败，请求超时：{exc}"}
            except requests.RequestException as exc:
                return {"status": "error", "error": f"下载PDF首页失败：{exc}"}
            return _pdf_first_page_image_payload(response.content)
        return {"status": "success", "url": url}

    source_path = Path(str(resolved.get("path") or "")).expanduser()
    if not source_path.exists():
        return {"status": "error", "error": f"文件不存在：{source_path}"}
    if not source_path.is_file():
        return {"status": "error", "error": f"指定路径不是文件：{source_path}"}
    try:
        image_payload = source_path.read_bytes()
    except Exception as exc:
        return {"status": "error", "error": f"读取文件失败：{exc}"}
    if _looks_like_pdf_source(str(source_path)):
        return _pdf_first_page_image_payload(image_payload)
    image_base64 = base64.b64encode(image_payload).decode("utf-8")
    mime_type = mimetypes.guess_type(source_path.name)[0] or "image/jpeg"
    return {"status": "success", "url": f"data:{mime_type};base64,{image_base64}"}


def _looks_like_pdf_source(source: str) -> bool:
    path = urlparse(str(source or "")).path or str(source or "")
    return path.lower().endswith(".pdf")


def _pdf_first_page_image_payload(pdf_payload: bytes) -> dict[str, Any]:
    if not pdf_payload:
        return {"status": "error", "error": "PDF内容为空，无法识别首页"}
    try:
        import fitz

        doc = fitz.open(stream=pdf_payload, filetype="pdf")
        if doc.page_count < 1:
            doc.close()
            return {"status": "error", "error": "PDF没有可识别页面"}
        page = doc.load_page(0)
        matrix = fitz.Matrix(PDF_FIRST_PAGE_RENDER_DPI / 72, PDF_FIRST_PAGE_RENDER_DPI / 72)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        png_payload = pixmap.tobytes("png")
        doc.close()
    except Exception as exc:
        return {"status": "error", "error": f"PDF首页转图片失败：{exc}"}
    image_base64 = base64.b64encode(png_payload).decode("utf-8")
    return {"status": "success", "url": f"data:image/png;base64,{image_base64}"}


def _extract_service_error(raw_response: dict[str, Any]) -> str | None:
    code = raw_response.get("code")
    message = raw_response.get("message")

    if code and str(code).strip() not in {"", "Success", "200", "0"}:
        return f"{code}: {message or 'OCR 调用失败'}"

    output = raw_response.get("output", {})
    if isinstance(output, dict):
        finish_reason = output.get("finish_reason")
        if finish_reason and finish_reason != "stop":
            return f"OCR 未正常完成: {finish_reason}"

    return None


def _extract_text_from_response(raw_response: dict[str, Any]) -> str:
    output = raw_response.get("output", {})
    choices = raw_response.get("choices")
    if not choices and isinstance(output, dict):
        choices = output.get("choices", [])
    if not choices or not isinstance(choices, list):
        return ""

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""

    message = first_choice.get("message", {})
    if not isinstance(message, dict):
        return ""

    content = message.get("content", [])
    if isinstance(content, str):
        return content.strip()
    if not content or not isinstance(content, list):
        return ""

    texts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            text = item.get("text", "")
            if text and isinstance(text, str):
                texts.append(text)
        elif isinstance(item, str) and item.strip():
            texts.append(item.strip())

    return "\n".join(texts).strip()


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.I)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except Exception:
        match = re.search(r"\{.*\}", stripped, flags=re.S)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return None
    return parsed if isinstance(parsed, dict) else None


def _estimate_confidence(text: str, raw_response: dict[str, Any]) -> float:
    if not text.strip():
        return 0.0

    output = raw_response.get("output", {})
    if isinstance(output, dict):
        choices = output.get("choices", [])
        if choices and isinstance(choices, list):
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                finish_reason = first_choice.get("finish_reason", "")
                if finish_reason != "stop":
                    return 0.5

    data_size = len(text.strip())
    if data_size > 100:
        return 0.95
    if data_size > 20:
        return 0.9
    return 0.8


def _error_result(source: str, provider: str, message: str, *, raw_response: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "provider": provider,
        "status": "error",
        "source": source,
        "text": "",
        "confidence": 0.0,
        "error": message,
    }
    if raw_response is not None:
        result["raw_response"] = raw_response
    return result


def _cache_key(resolved: dict[str, Any], provider: str, *, task: str = "ocr_text", prompt: str = "") -> tuple[str, str, int, int]:
    provider_key = f"{provider}:{task}:{hashlib.sha1(prompt.encode('utf-8')).hexdigest()[:12]}"
    if resolved.get("kind") == "url":
        return (str(resolved.get("url") or ""), provider_key, 0, 0)
    path = Path(str(resolved.get("path") or "")).expanduser()
    stat = path.stat()
    return (str(path.resolve()), provider_key, int(stat.st_mtime_ns), int(stat.st_size))


def _cache_store(key: tuple[str, str, int, int], value: dict[str, Any]) -> None:
    if len(_OCR_CACHE) >= _OCR_CACHE_LIMIT:
        _OCR_CACHE.pop(next(iter(_OCR_CACHE)))
    _OCR_CACHE[key] = dict(value)
