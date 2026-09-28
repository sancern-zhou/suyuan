import pytest

from app.agent.selection_context import (
    build_uploaded_file_ref,
    resource_refs_to_runtime_attachments,
)
from app.agent.runtime.multimodal import build_anthropic_user_content


def test_build_anthropic_user_content_prefers_public_image_url_over_local_path(tmp_path):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"fake-png")

    content = build_anthropic_user_content(
        "看图",
        [
            {
                "type": "image",
                "name": "image.png",
                "local_path": str(image_path),
                "url": "https://example.com/signed-image.png",
                "mime_type": "image/png",
            }
        ],
    )

    assert content == [
        {"type": "text", "text": "看图"},
        {
            "type": "image",
            "source": {
                "type": "url",
                "url": "https://example.com/signed-image.png",
            },
        },
    ]


def test_build_anthropic_user_content_rejects_missing_current_turn_image(tmp_path):
    missing_path = tmp_path / "missing.png"

    with pytest.raises(ValueError, match="native_image_build_failed"):
        build_anthropic_user_content(
            "看图",
            [{
                "type": "image",
                "name": "missing.png",
                "local_path": str(missing_path),
                "mime_type": "image/png",
            }],
        )


def test_current_turn_image_ref_must_resolve_to_an_existing_file(tmp_path):
    missing = build_uploaded_file_ref(
        file_id="missing-image",
        file_path=str(tmp_path / "missing.png"),
        filename="missing.png",
        mime_type="image/png",
    )

    with pytest.raises(ValueError, match="current_turn_image_missing"):
        resource_refs_to_runtime_attachments([missing])
