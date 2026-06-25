"""Voice input/output API for the web Agent."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.voice_service import (
    VoiceConfigError,
    ensure_allowed_audio_upload,
    normalize_audio_for_mimo,
    synthesize_with_mimo,
    transcribe_with_mimo,
)


router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceTranscribeResponse(BaseModel):
    text: str
    language: str = "zh"


class VoiceSynthesisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    voice: Optional[str] = None
    format: str = Field(default="wav", pattern="^(wav|mp3)$")
    style_prompt: Optional[str] = Field(default=None, max_length=500)


@router.post("/transcribe", response_model=VoiceTranscribeResponse)
async def transcribe_voice(
    file: UploadFile = File(...),
    language: str = Form(default="zh"),
) -> VoiceTranscribeResponse:
    audio_bytes = await file.read()
    try:
        ensure_allowed_audio_upload(
            filename=file.filename or "voice.webm",
            content_type=file.content_type or "",
            size=len(audio_bytes),
        )
        normalized_bytes, normalized_mime = await normalize_audio_for_mimo(
            audio_bytes,
            filename=file.filename or "voice.webm",
            content_type=file.content_type or "",
        )
        text = await transcribe_with_mimo(normalized_bytes, normalized_mime, language=language)
        return VoiceTranscribeResponse(text=text, language=language)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except VoiceConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/synthesize")
async def synthesize_voice(request: VoiceSynthesisRequest) -> Response:
    try:
        audio_bytes = await synthesize_with_mimo(
            text=request.text,
            voice=request.voice,
            fmt=request.format,
            style_prompt=request.style_prompt,
        )
    except VoiceConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    media_type = "audio/wav" if request.format == "wav" else "audio/mpeg"
    suffix = "wav" if request.format == "wav" else "mp3"
    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="agent-reply.{suffix}"'},
    )
