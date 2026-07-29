from app.api.upload_routes import _uploaded_file_url
from app.db.session_repository import SessionRepository
from app.routers.agent import _build_user_message_for_history


ATTACHMENTS = [
    {
        "file_id": "file-1",
        "type": "image",
        "name": "现场.png",
        "mime_type": "image/png",
        "size": 123,
        "url": "/api/upload/file-1",
    }
]


class _LightRow:
    id = 42
    role = "user"
    msg_type = "user"
    content = "请分析图片"
    content_preview = content
    data = None
    timestamp = None
    sequence_number = 7
    msg_metadata = {"attachments": ATTACHMENTS, "source": "agent"}


def test_uploaded_file_url_is_a_stable_gateway_relative_resource():
    assert _uploaded_file_url("file-123") == "/api/upload/file-123"


def test_user_message_preserves_structured_attachments_outside_content():
    message = _build_user_message_for_history(
        "请分析这个文件",
        ATTACHMENTS,
        timestamp="2026-07-18T10:00:00",
    )

    assert message == {
        "type": "user",
        "content": "请分析这个文件",
        "attachments": ATTACHMENTS,
        "timestamp": "2026-07-18T10:00:00",
    }


def test_lightweight_display_rows_preserve_only_attachment_metadata():
    repository = SessionRepository()

    context_message = repository._message_row_to_context_dict(_LightRow(), include_data=False)
    light_message = repository._message_row_to_light_dict(_LightRow())

    assert context_message["attachments"] == ATTACHMENTS
    assert light_message["attachments"] == ATTACHMENTS
    assert "source" not in context_message
    assert "source" not in light_message
