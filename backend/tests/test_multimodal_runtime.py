from datetime import datetime, timezone

import pytest

from app.agent.resources.resource_service import StoredResource
from app.agent.selection_context import resource_refs_to_runtime_attachments
from app.agent.runtime.multimodal import build_anthropic_user_content


def _stored_image_resource(resource_id: str, path: str, status: str = "active") -> StoredResource:
    return StoredResource(
        resource_id=resource_id,
        session_id="session-1",
        group_id="group-1",
        parent_resource_id=None,
        resource_key="primary:png",
        relation="primary",
        kind="file",
        role="attachment",
        label="现场.png",
        locator={"path": path},
        format="png",
        media_type="image/png",
        renderer="image",
        capabilities=["preview", "download"],
        metadata={"file_id": "file-1"},
        tool_name="upload_chat",
        run_id="",
        turn_sequence=0,
        version=1,
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_build_anthropic_user_content_inlines_local_image_bytes(tmp_path):
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

    assert content[0] == {"type": "text", "text": "看图"}
    assert content[1]["type"] == "image"
    assert content[1]["source"]["type"] == "base64"
    assert content[1]["source"]["media_type"] == "image/png"


def test_build_anthropic_user_content_falls_back_to_public_image_url():
    content = build_anthropic_user_content(
        "看图",
        [
            {
                "type": "image",
                "name": "remote.png",
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
    missing = _stored_image_resource("missing-image", str(tmp_path / "missing.png"))

    with pytest.raises(ValueError, match="current_turn_image_missing"):
        resource_refs_to_runtime_attachments([missing])
