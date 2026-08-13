import base64

import pytest

from app.services.voice_service import (
    MAX_VOICE_UPLOAD_BYTES,
    VoiceConfigError,
    build_mimo_asr_payload,
    build_mimo_tts_payload,
    data_url_for_audio,
    ensure_allowed_audio_upload,
    extract_asr_text,
    extract_tts_audio,
)


def test_voice_upload_accepts_compact_webm_audio():
    ensure_allowed_audio_upload(
        filename="question.webm",
        content_type="audio/webm",
        size=4096,
    )


def test_voice_upload_rejects_files_over_limit():
    with pytest.raises(ValueError, match="音频文件过大"):
        ensure_allowed_audio_upload(
            filename="question.webm",
            content_type="audio/webm",
            size=MAX_VOICE_UPLOAD_BYTES + 1,
        )


def test_data_url_uses_supported_mimo_mime_type():
    data_url = data_url_for_audio(b"abc", "audio/mpeg")

    assert data_url == "data:audio/mpeg;base64,YWJj"


def test_mimo_asr_payload_places_audio_in_input_audio_content():
    payload = build_mimo_asr_payload("data:audio/wav;base64,YWJj", language="zh")

    assert payload["model"] == "mimo-v2.5-asr"
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][0]["content"][0]["type"] == "input_audio"
    assert payload["messages"][0]["content"][0]["input_audio"]["data"] == "data:audio/wav;base64,YWJj"
    assert payload["asr_options"] == {"language": "zh"}


def test_extract_asr_text_reads_openai_compatible_response():
    response = {
        "choices": [
            {
                "message": {
                    "content": "查询广州今天空气质量"
                }
            }
        ]
    }

    assert extract_asr_text(response) == "查询广州今天空气质量"


def test_mimo_tts_payload_places_target_text_in_assistant_message():
    payload = build_mimo_tts_payload(
        text="分析完成，广州空气质量整体良好。",
        voice="冰糖",
        fmt="wav",
        style_prompt="用专业、清晰、平稳的语气播报。",
    )

    assert payload["model"] == "mimo-v2.5-tts"
    assert payload["messages"][0] == {
        "role": "user",
        "content": "用专业、清晰、平稳的语气播报。",
    }
    assert payload["messages"][1] == {
        "role": "assistant",
        "content": "分析完成，广州空气质量整体良好。",
    }
    assert payload["audio"] == {"format": "wav", "voice": "冰糖"}


def test_extract_tts_audio_decodes_base64_audio_data():
    encoded = base64.b64encode(b"RIFF").decode("ascii")
    response = {
        "choices": [
            {
                "message": {
                    "audio": {
                        "data": encoded
                    }
                }
            }
        ]
    }

    assert extract_tts_audio(response) == b"RIFF"


def test_extract_tts_audio_requires_audio_data():
    with pytest.raises(VoiceConfigError, match="语音合成响应中缺少音频数据"):
        extract_tts_audio({"choices": [{"message": {"content": "no audio"}}]})
