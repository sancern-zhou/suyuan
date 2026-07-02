"""Voice ASR/TTS helpers for web Agent input and output."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx

from config.settings import settings


MAX_VOICE_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_MIME_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
}
MIMO_SUPPORTED_MIME_TYPES = {
    "audio/wav": "audio/wav",
    "audio/x-wav": "audio/wav",
    "audio/mpeg": "audio/mpeg",
    "audio/mp3": "audio/mp3",
}


class VoiceConfigError(RuntimeError):
    """Raised when voice provider configuration or response is invalid."""


def ensure_allowed_audio_upload(filename: str, content_type: str, size: int) -> None:
    """Validate browser audio upload before transcode/provider calls."""
    if size > MAX_VOICE_UPLOAD_BYTES:
        raise ValueError("音频文件过大，单次语音输入最大支持 10MB")

    normalized_type = (content_type or "").split(";")[0].strip().lower()
    suffix = Path(filename or "").suffix.lower()
    allowed_suffixes = {".webm", ".ogg", ".wav", ".mp3", ".m4a", ".mp4"}
    if normalized_type not in ALLOWED_UPLOAD_MIME_TYPES and suffix not in allowed_suffixes:
        raise ValueError("不支持的音频格式，请使用 webm、ogg、wav、mp3 或 m4a")


def data_url_for_audio(audio_bytes: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(audio_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_mimo_asr_payload(data_url: str, language: str = "zh") -> Dict[str, Any]:
    return {
        "model": settings.voice_asr_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": data_url,
                        },
                    }
                ],
            }
        ],
        "asr_options": {
            "language": language or "zh",
        },
    }


def extract_asr_text(response_json: Dict[str, Any]) -> str:
    try:
        content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise VoiceConfigError("语音识别响应格式异常") from exc

    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        text = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        ).strip()
    else:
        text = str(content).strip()

    if not text:
        raise VoiceConfigError("语音识别结果为空")
    return text


def build_mimo_tts_payload(
    text: str,
    voice: Optional[str] = None,
    fmt: str = "wav",
    style_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    messages = []
    if style_prompt:
        messages.append({"role": "user", "content": style_prompt})
    messages.append({"role": "assistant", "content": text})
    return {
        "model": settings.voice_tts_model,
        "messages": messages,
        "audio": {
            "format": fmt or "wav",
            "voice": voice or settings.voice_tts_voice,
        },
    }


def extract_tts_audio(response_json: Dict[str, Any]) -> bytes:
    try:
        audio_data = response_json["choices"][0]["message"]["audio"]["data"]
    except (KeyError, IndexError, TypeError) as exc:
        raise VoiceConfigError("语音合成响应中缺少音频数据") from exc
    try:
        return base64.b64decode(audio_data)
    except (TypeError, ValueError) as exc:
        raise VoiceConfigError("语音合成音频数据不是有效 Base64") from exc


def _mimo_chat_completions_url() -> str:
    return settings.voice_mimo_base_url.rstrip("/") + "/chat/completions"


def _mimo_headers() -> Dict[str, str]:
    if not settings.mimo_api_key:
        raise VoiceConfigError("未配置 MIMO_API_KEY，无法调用语音服务")
    return {
        "api-key": settings.mimo_api_key,
        "Content-Type": "application/json",
    }


async def _post_mimo(payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            _mimo_chat_completions_url(),
            headers=_mimo_headers(),
            json=payload,
        )
    if response.status_code >= 400:
        raise VoiceConfigError(f"语音服务调用失败: HTTP {response.status_code} {response.text[:300]}")
    return response.json()


def _guess_mime_type(filename: str, content_type: str) -> str:
    normalized = (content_type or "").split(";")[0].strip().lower()
    if normalized:
        return normalized
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".ogg":
        return "audio/ogg"
    if suffix in {".m4a", ".mp4"}:
        return "audio/mp4"
    return "audio/webm"


async def _transcode_to_mimo_supported(audio_bytes: bytes, source_suffix: str) -> Tuple[bytes, str]:
    """Convert browser formats to mp3 for MiMo ASR when needed."""
    with tempfile.TemporaryDirectory(prefix="voice-asr-") as tmpdir:
        input_path = Path(tmpdir) / f"input{source_suffix or '.webm'}"
        output_path = Path(tmpdir) / "output.mp3"
        input_path.write_bytes(audio_bytes)
        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-b:a",
                "48k",
                str(output_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise VoiceConfigError("服务器未安装 ffmpeg，无法将浏览器录音转为 MiMo ASR 支持的 mp3/wav") from exc
        _, stderr = await process.communicate()
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="ignore")[-500:]
            raise VoiceConfigError(f"音频转码失败，请确认服务器已安装 ffmpeg: {message}")
        return output_path.read_bytes(), "audio/mpeg"


async def normalize_audio_for_mimo(
    audio_bytes: bytes,
    filename: str,
    content_type: str,
) -> Tuple[bytes, str]:
    mime_type = _guess_mime_type(filename, content_type)
    if mime_type in MIMO_SUPPORTED_MIME_TYPES:
        return audio_bytes, MIMO_SUPPORTED_MIME_TYPES[mime_type]
    suffix = Path(filename or "").suffix.lower() or ".webm"
    return await _transcode_to_mimo_supported(audio_bytes, suffix)


async def transcribe_with_mimo(audio_bytes: bytes, mime_type: str, language: str = "zh") -> str:
    data_url = data_url_for_audio(audio_bytes, mime_type)
    payload = build_mimo_asr_payload(data_url, language=language)
    response_json = await _post_mimo(payload, timeout=settings.voice_asr_timeout_seconds)
    return extract_asr_text(response_json)


async def synthesize_with_mimo(
    text: str,
    voice: Optional[str] = None,
    fmt: str = "wav",
    style_prompt: Optional[str] = None,
) -> bytes:
    payload = build_mimo_tts_payload(
        text=text,
        voice=voice,
        fmt=fmt,
        style_prompt=style_prompt,
    )
    response_json = await _post_mimo(payload, timeout=settings.voice_tts_timeout_seconds)
    return extract_tts_audio(response_json)
